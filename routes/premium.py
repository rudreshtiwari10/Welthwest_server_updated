"""
Premium Routes - Handle premium plan queries and user subscription information
"""
from flask import Blueprint, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.subscription_service import SubscriptionService
from services.premium_usage_service import get_premium_usage_service
from config import get_config
import logging

logger = logging.getLogger(__name__)

# Create blueprint
premium_bp = Blueprint('premium', __name__, url_prefix='/api/premium')

# Services initialized on first request to avoid slow startup
_subscription_service = None
_config = None

def _get_subscription_service():
    global _subscription_service
    if _subscription_service is None:
        _subscription_service = SubscriptionService()
    return _subscription_service

def _get_config():
    global _config
    if _config is None:
        _config = get_config()
    return _config


@premium_bp.route('/plans', methods=['GET'])
def get_plans():
    """
    Get all available premium plans with pricing and limits

    Returns:
        200: List of plans
        500: Server error
    """
    try:
        # Get all plans from database
        plans_from_db = _get_subscription_service().get_all_premium_plans()

        # If no plans in DB, return from config
        if not plans_from_db:
            logger.warning("No plans found in database, returning from config")
            plans = []
            for plan_id in ['FREE', 'STARTER', 'PRO', 'ADVANCED', 'ENTERPRISE']:
                plans.append({
                    "_id": plan_id,
                    "display_name": plan_id.capitalize(),
                    "prices": _get_config().PLAN_PRICES.get(plan_id, {}),
                    "limits": _get_config().PLAN_LIMITS.get(plan_id, {}),
                    "features": list(_get_config().PLAN_LIMITS.get(plan_id, {}).keys())
                })
        else:
            plans = []
            for plan in plans_from_db:
                plans.append({
                    "_id": plan.get('_id'),
                    "display_name": plan.get('display_name', plan.get('_id', '').capitalize()),
                    "prices": plan.get('prices', {}),
                    "limits": plan.get('limits', {}),
                    "features": plan.get('features', list(plan.get('limits', {}).keys())),
                    "description": plan.get('description', '')
                })

        return jsonify({
            "success": True,
            "plans": plans,
            "feature_names": {
                "welth-market-regime": "Market Regime Classifier",
                "welth-ai-assistant": "AI Assistant",
                "backtest-beta": "Backtesting"
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting premium plans: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch premium plans"
        }), 500


@premium_bp.route('/user/subscription', methods=['GET'])
@jwt_required()
def get_user_subscription():
    """
    Get current user's subscription details

    Returns:
        200: Subscription details
        404: User not found
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        subscription = _get_subscription_service().get_user_subscription(user_id)

        if not subscription:
            return jsonify({
                "success": False,
                "error": "Subscription not found"
            }), 404

        return jsonify({
            "success": True,
            "subscription": subscription
        }), 200

    except Exception as e:
        logger.error(f"Error getting user subscription: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch subscription"
        }), 500


@premium_bp.route('/user/usage', methods=['GET'])
@jwt_required()
def get_user_usage():
    """
    Get current user's usage for all features

    Returns:
        200: Usage details
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Get user's limits
        limits = _get_subscription_service().get_limits_for_user(user_id)

        # Get usage for all features
        feature_keys = list(limits.keys())
        usage = get_premium_usage_service().get_all_usage(
            actor_id=user_id,
            feature_keys=feature_keys,
            limits=limits,
            is_anonymous=False
        )

        # Get subscription info
        subscription = _get_subscription_service().get_user_subscription(user_id)

        return jsonify({
            "success": True,
            "usage": usage,
            "subscription": {
                "plan": subscription.get('plan', 'FREE') if subscription else 'FREE',
                "is_active": subscription.get('is_active', True) if subscription else True
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting user usage: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch usage"
        }), 500


@premium_bp.route('/feature/<feature_key>/remaining', methods=['GET'])
def get_feature_remaining(feature_key):
    """
    Get remaining usage for a specific feature (works for both authenticated and anonymous)

    Args:
        feature_key: Feature identifier

    Returns:
        200: Remaining usage
        400: Invalid feature
        500: Server error
    """
    try:
        # Validate feature key
        valid_features = ['welth-market-regime', 'welth-ai-assistant', 'backtest-beta']
        if feature_key not in valid_features:
            return jsonify({
                "success": False,
                "error": "Invalid feature key"
            }), 400

        # Try to get user ID
        user_id = None
        is_anonymous = True
        try:
            from flask_jwt_extended import verify_jwt_in_request
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id:
                is_anonymous = False
        except:
            pass

        # Get session ID for anonymous
        from flask import request
        session_id = None
        if is_anonymous:
            session_id = request.cookies.get(_get_config().ANON_SESSION_COOKIE)
            if not session_id:
                # Return full anonymous limit if no session yet
                limit = _get_config().ANON_LIMITS.get(feature_key, 0)
                return jsonify({
                    "success": True,
                    "remaining": limit,
                    "limit": limit,
                    "used": 0,
                    "is_anonymous": True
                }), 200

        # Get limits and remaining
        if is_anonymous:
            limits = _get_subscription_service().get_anonymous_limits()
            actor_id = session_id
        else:
            limits = _get_subscription_service().get_limits_for_user(user_id)
            actor_id = user_id

        limit = limits.get(feature_key, 0)
        remaining = get_premium_usage_service().get_remaining(actor_id, feature_key, limit, is_anonymous)

        return jsonify({
            "success": True,
            "remaining": remaining,
            "limit": limit,
            "used": limit - remaining,
            "is_anonymous": is_anonymous
        }), 200

    except Exception as e:
        logger.error(f"Error getting feature remaining: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch remaining usage"
        }), 500


@premium_bp.route('/check-expired', methods=['POST'])
def check_expired_subscriptions():
    """
    Check and downgrade expired subscriptions (should be called by cron job)
    Protected by requiring admin role or API key

    Returns:
        200: Results
        401: Unauthorized
        500: Server error
    """
    try:
        # Simple API key check (you can make this more sophisticated)
        from flask import request
        api_key = request.headers.get('X-API-Key')

        # Check if API key matches (set in env)
        import os
        expected_key = os.getenv('CRON_API_KEY', 'change-this-in-production')

        if api_key != expected_key:
            return jsonify({
                "success": False,
                "error": "Unauthorized"
            }), 401

        # Run expiry check
        results = _get_subscription_service().check_and_downgrade_expired()

        return jsonify({
            "success": True,
            "results": results
        }), 200

    except Exception as e:
        logger.error(f"Error checking expired subscriptions: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to check expired subscriptions"
        }), 500
