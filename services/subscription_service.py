import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from bson.objectid import ObjectId
from pymongo import MongoClient, ASCENDING
from config import get_config

logger = logging.getLogger(__name__)

class SubscriptionService:
    """Service for managing user subscriptions and usage tracking"""
    
    def __init__(self):
        self.config = get_config()
        self.db = MongoClient(self.config.MONGODB_URI)[self.config.DB_NAME]
        self.users = self.db.users
        
        # Ensure indexes for performance
        self.users.create_index([("subscription.expires_at", ASCENDING)])
        self.users.create_index([("subscription.tier", ASCENDING)])
        
    def initialize_subscription(self, user_id: str) -> bool:
        """Initialize a new user's subscription with FREE tier"""
        try:
            # First check if user exists and doesn't already have a subscription
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                logger.error(f"User {user_id} not found")
                return False
                
            if "subscription" in user:
                logger.info(f"User {user_id} already has a subscription")
                return True
                
            # Create subscription data
            subscription_data = {
                "subscription": {
                    "tier": "FREE",
                    "starts_at": datetime.utcnow(),
                    "expires_at": None,  # FREE tier doesn't expire
                    "usage": {
                        "daily": {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        },
                        "monthly": {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        }
                    }
                }
            }
            
            # Update user document with subscription
            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": subscription_data}
            )
            
            success = result.modified_count > 0
            if success:
                logger.info(f"Successfully initialized subscription for user {user_id}")
            else:
                logger.error(f"Failed to initialize subscription for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error initializing subscription for user {user_id}: {str(e)}")
            return False
    
    def get_subscription_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's current subscription details"""
        try:
            user = self.users.find_one(
                {"_id": ObjectId(user_id)},
                {"subscription": 1}
            )
            if user and "subscription" in user:
                subscription = user["subscription"]
                tier_info = self.config.SUBSCRIPTION_TIERS[subscription["tier"]]
                
                # Ensure usage data exists
                if "usage" not in subscription:
                    logger.warning(f"Missing usage data for user {user_id}, fixing...")
                    self.fix_missing_subscription(user_id)
                    # Re-fetch the user data
                    user = self.users.find_one(
                        {"_id": ObjectId(user_id)},
                        {"subscription": 1}
                    )
                    if user and "subscription" in user:
                        subscription = user["subscription"]
                    else:
                        return None
                
                # Handle infinity values for JSON serialization
                backtest_limit = tier_info["backtest_daily_limit"]
                llm_limit = tier_info["llm_daily_limit"]
                
                # Convert infinity to a large number that can be JSON serialized
                if backtest_limit == float('inf'):
                    backtest_limit = 999999
                if llm_limit == float('inf'):
                    llm_limit = 999999
                
                return {
                    **subscription,
                    "limits": {
                        "backtest_daily_limit": backtest_limit,
                        "llm_daily_limit": llm_limit,
                        "market_data_delay": tier_info["market_data_delay"]
                    }
                }
            return None
        except Exception as e:
            logger.error(f"Error getting subscription details for user {user_id}: {str(e)}")
            return None
    
    def upgrade_subscription(self, user_id: str, new_tier: str) -> Tuple[bool, str]:
        """Upgrade user's subscription to a new tier"""
        if new_tier not in self.config.SUBSCRIPTION_TIERS:
            return False, "Invalid subscription tier"
            
        try:
            subscription_data = {
                "subscription.tier": new_tier,
                "subscription.starts_at": datetime.utcnow(),
                "subscription.expires_at": datetime.utcnow() + timedelta(days=30)
            }
            
            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": subscription_data}
            )
            
            if result.modified_count > 0:
                return True, f"Successfully upgraded to {new_tier} tier"
            return False, "Failed to upgrade subscription"
        except Exception as e:
            logger.error(f"Error upgrading subscription for user {user_id}: {str(e)}")
            return False, "Internal error occurred"
    
    def check_and_update_usage(self, user_id: str, feature: str) -> Tuple[bool, str]:
        """Check if user can use a feature and update usage counter"""
        try:
            subscription = self.get_subscription_details(user_id)
            if not subscription:
                return False, "Subscription not found"
            
            # Reset counters if needed
            self._reset_counters_if_needed(user_id)
            
            # Get current usage and limits
            usage = subscription["usage"]["daily"]
            tier_info = self.config.SUBSCRIPTION_TIERS[subscription["tier"]]
            
            if feature == "backtest":
                current_usage = usage["backtest_count"]
                limit = tier_info["backtest_daily_limit"]
                counter_field = "subscription.usage.daily.backtest_count"
            elif feature == "llm_query":
                current_usage = usage["llm_query_count"]
                limit = tier_info["llm_daily_limit"]
                counter_field = "subscription.usage.daily.llm_query_count"
            else:
                return False, "Invalid feature"
            
            # Check if limit is reached (handle infinity case)
            if limit != float('inf') and current_usage >= limit:
                return False, f"Daily {feature} limit reached for your subscription tier"
            
            # Update usage counter
            self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$inc": {counter_field: 1}}
            )
            
            return True, "Usage updated successfully"
        except Exception as e:
            logger.error(f"Error checking usage for user {user_id}: {str(e)}")
            return False, "Internal error occurred"
    
    def increment_usage(self, user_id: str, feature: str) -> Tuple[bool, str]:
        """Increment usage counter for a feature without checking limits"""
        try:
            # Reset counters if needed
            self._reset_counters_if_needed(user_id)
            
            # Validate feature
            if feature not in ["backtest", "llm_query"]:
                return False, "Invalid feature"
            
            # Determine counter field
            if feature == "backtest":
                counter_field = "subscription.usage.daily.backtest_count"
            else:  # llm_query
                counter_field = "subscription.usage.daily.llm_query_count"
            
            # Update usage counter
            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$inc": {counter_field: 1}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Incremented {feature} usage for user {user_id}")
                return True, f"Successfully incremented {feature} usage"
            else:
                logger.warning(f"No document updated for user {user_id}")
                return False, "User not found or no changes made"
                
        except Exception as e:
            logger.error(f"Error incrementing usage for user {user_id}: {str(e)}")
            return False, "Internal error occurred"
    
    def get_usage_metrics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get current usage metrics for a user"""
        try:
            user = self.users.find_one(
                {"_id": ObjectId(user_id)},
                {"subscription": 1}
            )
            if user and "subscription" in user:
                subscription = user["subscription"]
                tier_info = self.config.SUBSCRIPTION_TIERS[subscription["tier"]]
                
                # Handle infinity values for JSON serialization
                backtest_limit = tier_info["backtest_daily_limit"]
                llm_limit = tier_info["llm_daily_limit"]
                
                # Convert infinity to a large number that can be JSON serialized
                if backtest_limit == float('inf'):
                    backtest_limit = 999999
                if llm_limit == float('inf'):
                    llm_limit = 999999
                
                return {
                    "tier": subscription["tier"],
                    "daily_usage": subscription["usage"]["daily"],
                    "monthly_usage": subscription["usage"]["monthly"],
                    "limits": {
                        "backtest_daily_limit": backtest_limit,
                        "llm_daily_limit": llm_limit
                    }
                }
            return None
        except Exception as e:
            logger.error(f"Error getting usage metrics for user {user_id}: {str(e)}")
            return None
    
    def _reset_counters_if_needed(self, user_id: str) -> None:
        """Reset daily/monthly counters if needed"""
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user or "subscription" not in user:
                return
            
            now = datetime.utcnow()
            last_daily_reset = user["subscription"]["usage"]["daily"]["last_reset"]
            last_monthly_reset = user["subscription"]["usage"]["monthly"]["last_reset"]
            
            updates = {}
            
            # Check daily reset
            if (now.date() > last_daily_reset.date()):
                updates.update({
                    "subscription.usage.daily.backtest_count": 0,
                    "subscription.usage.daily.llm_query_count": 0,
                    "subscription.usage.daily.last_reset": now
                })
            
            # Check monthly reset
            if (now.year > last_monthly_reset.year or 
                now.month > last_monthly_reset.month):
                updates.update({
                    "subscription.usage.monthly.backtest_count": 0,
                    "subscription.usage.monthly.llm_query_count": 0,
                    "subscription.usage.monthly.last_reset": now
                })
            
            if updates:
                self.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": updates}
                )
                logger.info(f"Reset usage counters for user {user_id}")
        except Exception as e:
            logger.error(f"Error resetting counters for user {user_id}: {str(e)}") 

    def create_subscription_tier(self, tier_name: str, tier_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Create a new subscription tier"""
        try:
            # Validate required fields
            required_fields = ['price', 'backtest_daily_limit', 'llm_daily_limit', 'market_data_delay', 'description']
            missing_fields = [field for field in required_fields if field not in tier_data]
            if missing_fields:
                return False, f"Missing required fields: {', '.join(missing_fields)}"
            
            # Validate field types
            if not isinstance(tier_data['price'], (int, float)):
                return False, "Price must be a number"
            if not isinstance(tier_data['backtest_daily_limit'], (int, float)):
                return False, "Backtest daily limit must be a number"
            if not isinstance(tier_data['llm_daily_limit'], (int, float)):
                return False, "LLM daily limit must be a number"
            if not isinstance(tier_data['market_data_delay'], str):
                return False, "Market data delay must be a string"
            if not isinstance(tier_data['description'], str):
                return False, "Description must be a string"
            
            # Check if tier already exists
            if tier_name in self.config.SUBSCRIPTION_TIERS:
                return False, f"Tier {tier_name} already exists"
            
            # Add the new tier to config
            self.config.SUBSCRIPTION_TIERS[tier_name] = tier_data
            
            # Create a collection for subscription tiers if it doesn't exist
            if 'subscription_tiers' not in self.db.list_collection_names():
                self.db.create_collection('subscription_tiers')
            
            # Store the tier in MongoDB
            tier_doc = {
                'name': tier_name,
                **tier_data,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            self.db.subscription_tiers.update_one(
                {'name': tier_name},
                {'$set': tier_doc},
                upsert=True
            )
            
            return True, f"Successfully created subscription tier {tier_name}"
        except Exception as e:
            logger.error(f"Error creating subscription tier {tier_name}: {str(e)}")
            return False, "Internal error occurred"
            
    def get_all_subscription_tiers(self) -> Dict[str, Any]:
        """Get all available subscription tiers"""
        try:
            return {
                'tiers': self.config.SUBSCRIPTION_TIERS,
                'total_count': len(self.config.SUBSCRIPTION_TIERS)
            }
        except Exception as e:
            logger.error(f"Error getting subscription tiers: {str(e)}")
            return {'tiers': {}, 'total_count': 0} 

    def fix_missing_subscription(self, user_id: str) -> bool:
        """Fix missing subscription for a user by initializing FREE tier"""
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False
                
            updates = {}
            
            # Check if subscription exists at all
            if "subscription" not in user:
                updates["subscription"] = {
                    "tier": "FREE",
                    "starts_at": datetime.utcnow(),
                    "expires_at": None,  # FREE tier doesn't expire
                    "usage": {
                        "daily": {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        },
                        "monthly": {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        }
                    }
                }
            else:
                # Check if usage data is missing
                subscription = user["subscription"]
                if "usage" not in subscription:
                    updates["subscription.usage"] = {
                        "daily": {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        },
                        "monthly": {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        }
                    }
                else:
                    # Check if daily or monthly usage is missing
                    if "daily" not in subscription["usage"]:
                        updates["subscription.usage.daily"] = {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        }
                    if "monthly" not in subscription["usage"]:
                        updates["subscription.usage.monthly"] = {
                            "backtest_count": 0,
                            "llm_query_count": 0,
                            "last_reset": datetime.utcnow()
                        }
            
            if updates:
                result = self.users.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": updates}
                )
                return result.modified_count > 0
                
            return True  # User already has subscription
        except Exception as e:
            logger.error(f"Error fixing subscription for user {user_id}: {str(e)}")
            return False 