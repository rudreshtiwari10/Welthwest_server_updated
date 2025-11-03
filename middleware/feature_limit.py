"""
Feature Limit Middleware - Enforce per-feature usage limits for premium plans
Decorator to protect premium endpoints with usage tracking
"""
import logging
import uuid
from functools import wraps
from flask import request, jsonify, g, make_response
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from jwt.exceptions import PyJWTError
from services.subscription_service import SubscriptionService
from services.premium_usage_service import get_premium_usage_service
from config import get_config

logger = logging.getLogger(__name__)

# Initialize services
subscription_service = SubscriptionService()
usage_service = get_premium_usage_service()
config = get_config()


def feature_limit(feature_key: str):
    """
    Decorator to enforce feature usage limits

    Args:
        feature_key: Feature identifier (e.g., 'welth-market-regime', 'welth-ai-assistant', 'backtest-beta')

    Usage:
        @app.route('/api/some-premium-feature', methods=['POST'])
        @feature_limit('welth-market-regime')
        def some_feature():
            return jsonify({"result": "success"})
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                # Step 1: Determine if user is authenticated or anonymous
                user_id = None
                is_anonymous = True

                try:
                    # Try to verify JWT
                    verify_jwt_in_request(optional=True)
                    user_id = get_jwt_identity()
                    if user_id:
                        is_anonymous = False
                except Exception as e:
                    # No JWT or invalid JWT - treat as anonymous
                    logger.debug(f"No valid JWT found: {e}")
                    pass

                # Step 2: Get or create session ID for anonymous users
                session_id = None
                if is_anonymous:
                    session_id = request.cookies.get(config.ANON_SESSION_COOKIE)
                    if not session_id:
                        # Create new session ID
                        session_id = f"anon_{uuid.uuid4().hex}"
                        logger.info(f"Created new anonymous session: {session_id}")

                # Step 3: Get limits for user or anonymous
                if is_anonymous:
                    limits = subscription_service.get_anonymous_limits()
                    actor_id = session_id
                    logger.debug(f"Anonymous user {session_id} accessing {feature_key}")
                else:
                    limits = subscription_service.get_limits_for_user(user_id)
                    actor_id = user_id
                    logger.debug(f"Authenticated user {user_id} accessing {feature_key}")

                # Step 4: Get limit for this specific feature
                limit = limits.get(feature_key, 0)

                if limit == 0:
                    logger.warning(f"Feature {feature_key} has zero limit for actor {actor_id}")
                    return jsonify({
                        "error": "feature_not_available",
                        "message": "This feature is not available in your plan",
                        "premium_url": "/premium"
                    }), 403

                # Step 5: Check and increment usage atomically
                allowed, remaining = usage_service.check_and_increment(
                    actor_id=actor_id,
                    feature_key=feature_key,
                    limit=limit,
                    is_anonymous=is_anonymous
                )

                # Step 6: If not allowed, return 403 with upgrade message
                if not allowed:
                    logger.info(f"Usage limit reached for {actor_id} on {feature_key}")

                    # Get current plan for better messaging
                    current_plan = "FREE"
                    if not is_anonymous:
                        user_sub = subscription_service.get_user_subscription(user_id)
                        if user_sub:
                            current_plan = user_sub.get('plan', 'FREE')

                    # Suggest next plan tier
                    plan_hierarchy = ['FREE', 'STARTER', 'PRO', 'ADVANCED', 'ENTERPRISE']
                    suggested_plan = 'STARTER'
                    if current_plan in plan_hierarchy:
                        current_index = plan_hierarchy.index(current_plan)
                        if current_index < len(plan_hierarchy) - 1:
                            suggested_plan = plan_hierarchy[current_index + 1]

                    return jsonify({
                        "error": "usage_limit_reached",
                        "message": f"Daily limit reached for this feature. Upgrade to continue.",
                        "premium_url": "/premium",
                        "current_plan": current_plan,
                        "suggested_plan": suggested_plan,
                        "remaining": 0,
                        "limit": limit
                    }), 403

                # Step 7: Attach usage info to request context
                g.usage_remaining = remaining
                g.usage_limit = limit
                g.feature_key = feature_key

                logger.info(f"Feature {feature_key} access allowed for {actor_id} (remaining: {remaining}/{limit})")

                # Step 8: Call the actual endpoint function
                response = fn(*args, **kwargs)

                # Step 9: Add usage headers to response
                if isinstance(response, tuple):
                    # Response is (data, status_code) or (data, status_code, headers)
                    if len(response) == 2:
                        data, status_code = response
                        headers = {}
                    else:
                        data, status_code, headers = response

                    # Convert to response object
                    if not isinstance(data, (dict, list)):
                        flask_response = make_response(data, status_code, headers)
                    else:
                        flask_response = make_response(jsonify(data), status_code, headers)
                else:
                    flask_response = make_response(response)

                # Add usage information to headers
                flask_response.headers['X-RateLimit-Limit'] = str(limit)
                flask_response.headers['X-RateLimit-Remaining'] = str(remaining)
                flask_response.headers['X-RateLimit-Feature'] = feature_key

                # Set session cookie for anonymous users
                if is_anonymous and session_id:
                    flask_response.set_cookie(
                        config.ANON_SESSION_COOKIE,
                        session_id,
                        max_age=config.ANON_SESSION_TTL_SECONDS,
                        httponly=True,
                        samesite='Lax'
                    )

                return flask_response

            except Exception as e:
                logger.error(f"Error in feature_limit middleware: {e}", exc_info=True)
                # On error, allow the request but log it
                return jsonify({
                    "error": "internal_error",
                    "message": "An error occurred while checking usage limits"
                }), 500

        return wrapper
    return decorator


def get_usage_info_decorator():
    """
    Decorator to attach usage info to response without enforcing limits
    (For non-premium features or informational purposes)
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                # Try to get user ID
                user_id = None
                try:
                    verify_jwt_in_request(optional=True)
                    user_id = get_jwt_identity()
                except:
                    pass

                if user_id:
                    # Get user subscription info
                    user_sub = subscription_service.get_user_subscription(user_id)
                    if user_sub:
                        g.user_subscription = user_sub

                return fn(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in get_usage_info_decorator: {e}")
                return fn(*args, **kwargs)

        return wrapper
    return decorator


def admin_required(fn):
    """
    Decorator to require admin role
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()

            logger.info(f"Admin check for user_id: {user_id}")

            # Get user from database
            from pymongo import MongoClient
            from bson import ObjectId

            db = MongoClient(config.MONGODB_URI)[config.DB_NAME]

            try:
                user = db.users.find_one({"_id": ObjectId(user_id)})
            except Exception as e:
                logger.error(f"Error converting user_id to ObjectId: {e}")
                return jsonify({"error": "Invalid user ID format"}), 400

            if not user:
                logger.warning(f"User not found with ID: {user_id}")
                return jsonify({"error": "User not found"}), 404

            user_role = user.get('role', 'user')
            logger.info(f"User {user_id} has role: {user_role}")

            if user_role != 'admin':
                logger.warning(f"User {user_id} attempted admin action with role: {user_role}")
                return jsonify({
                    "error": "Admin access required",
                    "message": "You do not have permission to perform this action"
                }), 403

            logger.info(f"Admin access granted for user {user_id}")
            return fn(*args, **kwargs)

        except Exception as e:
            logger.error(f"Error in admin_required: {e}", exc_info=True)
            return jsonify({
                "error": "Unauthorized",
                "message": "Authentication failed"
            }), 401

    return wrapper
