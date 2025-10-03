"""
Anonymous Trial Limit Middleware
Enforces per-feature usage limits for anonymous users using Redis
"""
import uuid
from functools import wraps
from flask import request, jsonify, current_app, g, make_response
from services.usage_service import get_feature_usage, incr_feature_usage, is_redis_available
import logging

logger = logging.getLogger(__name__)


def anon_or_auth_feature_limit(feature):
    """
    Decorator to enforce anonymous trial limits for features.

    Flow:
    1. If user is authenticated (JWT), allow access (skip anonymous counting)
    2. If anonymous:
       - Check/create session cookie
       - Check Redis usage counter for this feature
       - If >= limit, return 403 with trial_exceeded error
       - Else increment counter and allow access

    Args:
        feature: Feature name (e.g., 'welth-ai-assistant', 'backtest-beta', 'ai-market-analysis')

    Usage:
        @app.route('/api/ai-analysis/run', methods=['POST'])
        @anon_or_auth_feature_limit('welth-ai-assistant')
        def run_ai_analysis():
            # Your endpoint logic
            pass
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Check if anonymous trials are enabled
            if not current_app.config.get('ENABLE_ANON_TRIALS', True):
                # If disabled, require authentication
                if not hasattr(g, 'current_user') or g.current_user is None:
                    return jsonify({
                        "ok": False,
                        "error": "authentication_required",
                        "message": "Please log in to use this feature."
                    }), 401

            # 1) Try to get JWT identity (optional - won't throw error if no token)
            from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

            user_authenticated = False
            try:
                verify_jwt_in_request(optional=True)
                user_identity = get_jwt_identity()
                if user_identity:
                    user_authenticated = True
                    logger.info(f"Authenticated user {user_identity} accessing {feature}")
                    # Set current_user in g for consistency with other parts of the app
                    g.current_user = {'email': user_identity, 'id': user_identity}
                    return f(*args, **kwargs)
            except Exception as e:
                # JWT verification failed or no token present - treat as anonymous
                logger.debug(f"No valid JWT token, treating as anonymous: {e}")
                user_authenticated = False

            # Explicitly set current_user to None for anonymous users (set early to ensure it's always defined)
            if not user_authenticated:
                g.current_user = None

            # 2) If we reach here, user is anonymous - enforce trial limits
            # Check if Redis is available
            if not is_redis_available():
                logger.error("Redis is not available - cannot enforce anonymous limits")
                return jsonify({
                    "ok": False,
                    "error": "service_unavailable",
                    "message": "Service temporarily unavailable. Please try again later."
                }), 503

            # 3) Anonymous path - get or create session
            cookie_name = current_app.config['ANON_SESSION_COOKIE']
            session_id = request.cookies.get(cookie_name)

            is_new_session = False
            if not session_id:
                # Create new session id
                session_id = uuid.uuid4().hex
                is_new_session = True
                logger.info(f"Created new anonymous session: {session_id[:8]}... for feature {feature}")
                # Store in g so we can set cookie on response
                g._new_anon_session_id = session_id

            # 4) Check current usage for this feature
            try:
                used = get_feature_usage(session_id, feature)
                limit = current_app.config.get('ANON_TRIAL_LIMIT', 10)

                logger.debug(f"Session {session_id[:8]}... - Feature {feature}: {used}/{limit}")

                # 5) If limit exceeded, deny with trial_exceeded error
                if used >= limit:
                    logger.warning(f"Trial limit exceeded for session {session_id[:8]}... on feature {feature}")
                    return jsonify({
                        "ok": False,
                        "error": "trial_exceeded",
                        "message": f"Your {limit} free runs for {feature} are used. Please log in to continue.",
                        "usage": {
                            "used": used,
                            "limit": limit,
                            "remaining": 0
                        }
                    }), 403

                # 6) Atomically increment usage counter
                new_count = incr_feature_usage(session_id, feature)
                logger.info(f"Session {session_id[:8]}... used {feature}: {new_count}/{limit}")

                # Store usage info in g for response
                g._anon_feature_usage = {
                    "used": new_count,
                    "limit": limit,
                    "remaining": max(0, limit - new_count),
                    "feature": feature
                }

                # Mark that we need to set cookie if this is a new session
                if is_new_session:
                    g._set_anon_cookie = True

                # 7) Call the actual endpoint
                response = f(*args, **kwargs)

                # 8) Set cookie on response if needed
                if hasattr(g, '_set_anon_cookie') and g._set_anon_cookie:
                    # Import Response for type checking
                    from flask import Response

                    # Handle different response types
                    if isinstance(response, tuple):
                        # Response is (data, status_code) or (data, status_code, headers)
                        if len(response) == 2:
                            data, status_code = response
                            headers = {}
                        elif len(response) == 3:
                            data, status_code, headers = response
                        else:
                            # Unexpected tuple length, just use response as-is
                            resp = make_response(response)
                            resp.set_cookie(
                                cookie_name,
                                g._new_anon_session_id,
                                max_age=current_app.config['ANON_SESSION_TTL_SECONDS'],
                                samesite='Lax',
                                secure=current_app.config.get('ENV') == 'production',
                                httponly=False
                            )
                            return resp

                        # Check if data is already a Response object
                        if isinstance(data, Response):
                            resp = data
                            resp.status_code = status_code
                            if headers:
                                resp.headers.update(headers)
                        else:
                            resp = make_response(data, status_code, headers)
                    else:
                        resp = make_response(response)

                    resp.set_cookie(
                        cookie_name,
                        g._new_anon_session_id,
                        max_age=current_app.config['ANON_SESSION_TTL_SECONDS'],
                        samesite='Lax',
                        secure=current_app.config.get('ENV') == 'production',  # Only secure in production
                        httponly=False  # Allow JS to read for debugging, change to True for production
                    )
                    return resp

                return response

            except Exception as e:
                logger.error(f"Error in anonymous trial middleware for feature '{feature}': {e}", exc_info=True)
                # On error, ensure g.current_user is set to None and allow request
                g.current_user = None
                # Return a proper error response instead of continuing
                return jsonify({
                    "ok": False,
                    "error": "middleware_error",
                    "message": f"An error occurred while processing your request: {str(e)}"
                }), 500

        return wrapper
    return decorator


def get_anonymous_session_id():
    """
    Helper function to get the current anonymous session ID from cookies.
    Returns None if not found.
    """
    cookie_name = current_app.config.get('ANON_SESSION_COOKIE', 'ww_session_id')
    return request.cookies.get(cookie_name)