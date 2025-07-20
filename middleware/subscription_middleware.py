import functools
from typing import Callable
from flask import request, jsonify, g
from flask_jwt_extended import get_jwt_identity
from services.subscription_service import SubscriptionService

subscription_service = SubscriptionService()

def require_subscription_feature(feature: str) -> Callable:
    """
    Middleware decorator to check subscription limits for specific features
    
    Args:
        feature: The feature to check ('backtest' or 'llm_query')
    """
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = get_jwt_identity()
            
            # Check and update usage
            can_use, message = subscription_service.check_and_update_usage(user_id, feature)
            if not can_use:
                # Get subscription details for error message
                subscription = subscription_service.get_subscription_details(user_id)
                if subscription:
                    tier = subscription["tier"]
                    usage = subscription["usage"]["daily"]
                    limits = subscription["limits"]
                    
                    error_response = {
                        "error": "Subscription limit exceeded",
                        "message": message,
                        "current_tier": tier,
                        "usage": {
                            feature: usage[f"{feature}_count"]
                        },
                        "limit": limits[f"{feature}_daily_limit"],
                        "upgrade_options": [
                            {
                                "tier": next_tier,
                                "price": tier_info["price"],
                                "limit": tier_info[f"{feature}_daily_limit"]
                            }
                            for next_tier, tier_info in subscription_service.config.SUBSCRIPTION_TIERS.items()
                            if tier_info["price"] > subscription_service.config.SUBSCRIPTION_TIERS[tier]["price"]
                        ]
                    }
                    return jsonify(error_response), 429
                
                return jsonify({"error": "Subscription error", "message": message}), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def check_market_data_access(f: Callable) -> Callable:
    """Middleware to check market data access level based on subscription"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_jwt_identity()
        subscription = subscription_service.get_subscription_details(user_id)
        
        if not subscription:
            return jsonify({"error": "Subscription not found"}), 404
        
        # Add market data delay info to request context
        g.market_data_delay = subscription["limits"]["market_data_delay"]
        
        # Add rate limit headers
        tier = subscription["tier"]
        tier_info = subscription_service.config.SUBSCRIPTION_TIERS[tier]
        
        response = f(*args, **kwargs)
        
        # Add rate limit headers to response
        if isinstance(response, tuple):
            response_obj, status_code = response
        else:
            response_obj, status_code = response, 200
            
        # Convert response to flask Response if it's not already
        if not hasattr(response_obj, 'headers'):
            response_obj = jsonify(response_obj)
        
        # Add custom headers
        response_obj.headers['X-Market-Data-Delay'] = g.market_data_delay
        response_obj.headers['X-Subscription-Tier'] = tier
        response_obj.headers['X-Rate-Limit-Backtest'] = str(tier_info['backtest_daily_limit'])
        response_obj.headers['X-Rate-Limit-LLM'] = str(tier_info['llm_daily_limit'])
        
        return response_obj, status_code
        
    return decorated_function 