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
        self.plans = self.db.plans

        # Ensure indexes for performance
        self.users.create_index([("subscription.expires_at", ASCENDING)])
        self.users.create_index([("subscription.tier", ASCENDING)])
        self.users.create_index([("subscription.plan", ASCENDING)])
        # Note: _id is already unique by default in MongoDB, no need to create index
        
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
                    "plan": "FREE",  # New system field
                    "tier": "FREE",  # Old system field (for backward compatibility)
                    "plan_duration": None,
                    "start_date": datetime.utcnow(),
                    "expiry_date": None,  # FREE tier doesn't expire
                    "starts_at": datetime.utcnow(),  # Old system field
                    "expires_at": None,  # Old system field
                    "is_active": True,
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

                # Get tier from either 'tier' or 'plan' field (backward compatibility)
                tier = subscription.get("tier") or subscription.get("plan", "FREE")

                # If tier is still missing, fix it
                if not tier:
                    logger.warning(f"Missing tier for user {user_id}, fixing...")
                    self.fix_missing_subscription(user_id)
                    tier = "FREE"

                # Get tier info with fallback to FREE if tier not found in config
                tier_info = self.config.SUBSCRIPTION_TIERS.get(tier, self.config.SUBSCRIPTION_TIERS.get("FREE"))

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
                        # Re-get tier after fix
                        tier = subscription.get("tier") or subscription.get("plan", "FREE")
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
                    "tier": tier,  # Ensure tier is always present in response
                    "plan": tier,  # Ensure plan is always present for backward compatibility
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
    
    def upgrade_subscription(self, user_id: str, new_tier: str, payment_verified: bool = False) -> Tuple[bool, str]:
        """Upgrade user's subscription to a new tier"""
        if new_tier not in self.config.SUBSCRIPTION_TIERS:
            return False, "Invalid subscription tier"
        
        # For paid tiers, require payment verification
        if new_tier != "FREE" and not payment_verified:
            return False, "Payment verification required for paid tiers"
            
        try:
            # Set expiry date based on tier
            if new_tier == "FREE":
                expires_at = None  # FREE tier doesn't expire
            else:
                expires_at = datetime.utcnow() + timedelta(days=30)  # Paid tiers expire after 30 days
                
            subscription_data = {
                "subscription.tier": new_tier,
                "subscription.starts_at": datetime.utcnow(),
                "subscription.expires_at": expires_at,
                "subscription.payment_verified": payment_verified,
                "subscription.updated_at": datetime.utcnow()
            }
            
            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": subscription_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Successfully upgraded user {user_id} to {new_tier} tier")
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
                    "plan": "FREE",  # New system field
                    "tier": "FREE",  # Old system field
                    "plan_duration": None,
                    "start_date": datetime.utcnow(),
                    "expiry_date": None,
                    "starts_at": datetime.utcnow(),
                    "expires_at": None,  # FREE tier doesn't expire
                    "is_active": True,
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
                subscription = user["subscription"]

                # Add 'plan' field if missing (for backward compatibility)
                if "plan" not in subscription:
                    # Use tier value if it exists, otherwise default to FREE
                    tier_value = subscription.get("tier", "FREE")
                    updates["subscription.plan"] = tier_value

                # Add 'tier' field if missing (for backward compatibility)
                if "tier" not in subscription:
                    # Use plan value if it exists, otherwise default to FREE
                    plan_value = subscription.get("plan", "FREE")
                    updates["subscription.tier"] = plan_value

                # Add other missing fields
                if "plan_duration" not in subscription:
                    updates["subscription.plan_duration"] = None
                if "start_date" not in subscription and "starts_at" in subscription:
                    updates["subscription.start_date"] = subscription["starts_at"]
                elif "start_date" not in subscription:
                    updates["subscription.start_date"] = datetime.utcnow()
                if "expiry_date" not in subscription and "expires_at" in subscription:
                    updates["subscription.expiry_date"] = subscription["expires_at"]
                if "is_active" not in subscription:
                    updates["subscription.is_active"] = True

                # Check if usage data is missing
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
    
    def check_subscription_expiry(self, user_id: str) -> Dict[str, Any]:
        """Check if user's subscription has expired and handle expiry"""
        try:
            subscription = self.get_subscription_details(user_id)
            if not subscription:
                return {"expired": False, "message": "No subscription found"}
            
            # FREE tier doesn't expire
            if subscription["tier"] == "FREE":
                return {"expired": False, "message": "FREE tier doesn't expire"}
            
            # Check if subscription has expiry date
            if "expires_at" not in subscription or not subscription["expires_at"]:
                return {"expired": False, "message": "No expiry date set"}
            
            # Parse expiry date if it's a string
            expires_at = subscription["expires_at"]
            if isinstance(expires_at, str):
                from dateutil.parser import parse
                expires_at = parse(expires_at)
            
            # Check if expired
            now = datetime.utcnow()
            if expires_at and expires_at < now:
                # Downgrade to FREE tier
                success, message = self.upgrade_subscription(user_id, "FREE", payment_verified=True)
                if success:
                    logger.info(f"Downgraded expired subscription for user {user_id} to FREE tier")
                    return {
                        "expired": True, 
                        "message": "Subscription expired and downgraded to FREE tier",
                        "downgraded": True
                    }
                else:
                    logger.error(f"Failed to downgrade expired subscription for user {user_id}")
                    return {
                        "expired": True,
                        "message": "Subscription expired but failed to downgrade",
                        "downgraded": False
                    }
            
            return {"expired": False, "message": "Subscription is active"}
            
        except Exception as e:
            logger.error(f"Error checking subscription expiry for user {user_id}: {str(e)}")
            return {"expired": False, "message": f"Error checking expiry: {str(e)}"}
    
    def get_subscription_analytics(self) -> Dict[str, Any]:
        """Get subscription analytics for admin dashboard"""
        try:
            # Get tier distribution
            tier_pipeline = [
                {"$group": {
                    "_id": "$subscription.tier",
                    "count": {"$sum": 1}
                }}
            ]
            tier_distribution = list(self.users.aggregate(tier_pipeline))
            
            # Get recent upgrades (last 30 days)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            recent_upgrades = self.users.count_documents({
                "subscription.starts_at": {"$gte": thirty_days_ago},
                "subscription.tier": {"$ne": "FREE"}
            })
            
            # Get total active paid subscriptions
            active_paid = self.users.count_documents({
                "subscription.tier": {"$ne": "FREE"},
                "$or": [
                    {"subscription.expires_at": {"$gte": datetime.utcnow()}},
                    {"subscription.expires_at": None}
                ]
            })
            
            # Get expired subscriptions
            expired_subs = self.users.count_documents({
                "subscription.expires_at": {"$lt": datetime.utcnow()},
                "subscription.tier": {"$ne": "FREE"}
            })
            
            return {
                "tier_distribution": {item["_id"]: item["count"] for item in tier_distribution},
                "recent_upgrades": recent_upgrades,
                "active_paid_subscriptions": active_paid,
                "expired_subscriptions": expired_subs,
                "total_users": self.users.count_documents({})
            }
            
        except Exception as e:
            logger.error(f"Error getting subscription analytics: {str(e)}")
            return {}
    
    def bulk_check_expiries(self) -> Dict[str, Any]:
        """Bulk check and handle expired subscriptions"""
        try:
            current_time = datetime.utcnow()
            
            # Find expired subscriptions
            expired_subscriptions = self.users.find({
                "subscription.expires_at": {"$lt": current_time},
                "subscription.tier": {"$ne": "FREE"}
            })
            
            downgraded_count = 0
            failed_count = 0
            
            for user in expired_subscriptions:
                user_id = str(user["_id"])
                try:
                    success, _ = self.upgrade_subscription(user_id, "FREE", payment_verified=True)
                    if success:
                        downgraded_count += 1
                        logger.info(f"Auto-downgraded expired subscription for user {user_id}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to auto-downgrade expired subscription for user {user_id}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error auto-downgrading user {user_id}: {str(e)}")
            
            return {
                "success": True,
                "processed": downgraded_count + failed_count,
                "downgraded": downgraded_count,
                "failed": failed_count
            }
            
        except Exception as e:
            logger.error(f"Error in bulk check expiries: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def cancel_subscription(self, user_id: str, reason: str = "User requested") -> Tuple[bool, str]:
        """Cancel user's subscription and downgrade to FREE tier"""
        try:
            # Check if user exists
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False, "User not found"

            # Check if user has a subscription
            if "subscription" not in user:
                return False, "User has no subscription"

            # Support both 'plan' (new system) and 'tier' (old system)
            current_plan = user["subscription"].get("plan")
            current_tier = user["subscription"].get("tier")

            # Determine current subscription level
            current_subscription = current_plan or current_tier or "FREE"

            # If already on FREE, nothing to cancel
            if current_subscription == "FREE":
                return False, "User is already on FREE tier"

            # Store cancellation information
            cancellation_info = {
                "cancelled_at": datetime.utcnow(),
                "cancelled_plan": current_subscription,
                "reason": reason,
                "cancelled_by": "user"
            }

            # Update subscription to FREE tier/plan with cancellation info
            update_data = {
                "$set": {
                    "subscription.plan": "FREE",
                    "subscription.tier": "FREE",  # Also update tier for backward compatibility
                    "subscription.plan_duration": None,
                    "subscription.expiry_date": None,  # FREE tier doesn't expire
                    "subscription.expires_at": None,  # Also clear old field
                    "subscription.cancelled_at": cancellation_info["cancelled_at"],
                    "subscription.previous_plan": current_subscription,
                    "subscription.previous_tier": current_subscription,  # Backward compatibility
                    "subscription.cancellation_reason": reason,
                    "updated_at": datetime.utcnow()
                },
                "$push": {
                    "subscription.history": {
                        "action": "cancelled",
                        "from_plan": current_subscription,
                        "to_plan": "FREE",
                        "timestamp": datetime.utcnow(),
                        "reason": reason
                    }
                }
            }

            # Perform the update
            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                update_data
            )

            if result.modified_count > 0:
                logger.info(f"Successfully cancelled subscription for user {user_id}. Downgraded from {current_subscription} to FREE")

                # Reset usage counters for new limits
                self._reset_usage_counters(user_id)

                return True, f"Subscription cancelled successfully. Downgraded from {current_subscription} to FREE tier."
            else:
                logger.error(f"Failed to cancel subscription for user {user_id}")
                return False, "Failed to update subscription"

        except Exception as e:
            logger.error(f"Error canceling subscription for user {user_id}: {str(e)}")
            return False, f"Error canceling subscription: {str(e)}"
    
    def get_cancellation_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cancellation information for a user if their subscription was cancelled"""
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user or "subscription" not in user:
                return None
            
            subscription = user["subscription"]
            
            # Check if subscription was cancelled
            if "cancelled_at" not in subscription:
                return None
            
            return {
                "cancelled_at": subscription.get("cancelled_at"),
                "cancelled_tier": subscription.get("previous_tier"),
                "reason": subscription.get("cancellation_reason"),
                "current_tier": subscription.get("tier", "FREE")
            }
            
        except Exception as e:
            logger.error(f"Error getting cancellation info for user {user_id}: {str(e)}")
            return None
    
    def _reset_usage_counters(self, user_id: str) -> bool:
        """Reset usage counters when subscription changes"""
        try:
            current_time = datetime.utcnow()

            reset_data = {
                "$set": {
                    "subscription.usage.daily.backtest_count": 0,
                    "subscription.usage.daily.llm_query_count": 0,
                    "subscription.usage.daily.last_reset": current_time,
                    "subscription.usage.monthly.backtest_count": 0,
                    "subscription.usage.monthly.llm_query_count": 0,
                    "subscription.usage.monthly.last_reset": current_time
                }
            }

            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                reset_data
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Error resetting usage counters for user {user_id}: {str(e)}")
            return False

    # ============================================
    # PREMIUM PLAN METHODS (NEW)
    # ============================================

    def get_premium_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Get premium plan details from plans collection

        Args:
            plan_id: Plan identifier (FREE, STARTER, PRO, ADVANCED, ENTERPRISE)

        Returns:
            Plan details or None
        """
        try:
            plan = self.plans.find_one({"_id": plan_id})
            return plan
        except Exception as e:
            logger.error(f"Error getting premium plan {plan_id}: {str(e)}")
            return None

    def get_all_premium_plans(self) -> list:
        """
        Get all premium plans

        Returns:
            List of all plans
        """
        try:
            plans = list(self.plans.find({}).sort("_id", 1))
            return plans
        except Exception as e:
            logger.error(f"Error getting all premium plans: {str(e)}")
            return []

    def get_limits_for_user(self, user_id: str) -> Dict[str, int]:
        """
        Get per-feature limits for a user based on their subscription plan

        Args:
            user_id: User identifier

        Returns:
            Dict mapping feature keys to limits
        """
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                logger.warning(f"User {user_id} not found, returning FREE limits")
                return self.config.PLAN_LIMITS.get('FREE', {})

            subscription = user.get('subscription', {})
            plan_name = subscription.get('plan', 'FREE')

            # Check for custom limits
            custom_limits = subscription.get('custom_limits', {})
            if custom_limits:
                # Merge with plan limits
                plan_limits = self.config.PLAN_LIMITS.get(plan_name, {}).copy()
                plan_limits.update(custom_limits)
                return plan_limits

            # Return plan limits from config
            return self.config.PLAN_LIMITS.get(plan_name, self.config.PLAN_LIMITS.get('FREE', {}))

        except Exception as e:
            logger.error(f"Error getting limits for user {user_id}: {str(e)}")
            return self.config.PLAN_LIMITS.get('FREE', {})

    def get_anonymous_limits(self) -> Dict[str, int]:
        """
        Get limits for anonymous users

        Returns:
            Dict mapping feature keys to limits
        """
        return self.config.ANON_LIMITS

    def apply_premium_subscription(
        self,
        user_id: str,
        plan_name: str,
        plan_duration: str,
        transaction_id: str = None
    ) -> Tuple[bool, str]:
        """
        Apply premium subscription to a user

        Args:
            user_id: User identifier
            plan_name: Plan name (STARTER, PRO, ADVANCED, ENTERPRISE)
            plan_duration: Duration (weekly, monthly, annual)
            transaction_id: Optional transaction ID

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Validate plan
            if plan_name not in self.config.PLAN_LIMITS:
                return False, f"Invalid plan: {plan_name}"

            # Calculate expiry date
            duration_days = {
                'weekly': 7,
                'monthly': 30,
                'annual': 365
            }

            if plan_duration not in duration_days:
                return False, f"Invalid duration: {plan_duration}"

            expiry_date = datetime.utcnow() + timedelta(days=duration_days[plan_duration])

            # Update user subscription
            update_data = {
                "$set": {
                    "subscription.plan": plan_name,
                    "subscription.tier": plan_name,  # Set tier for backward compatibility
                    "subscription.plan_duration": plan_duration,
                    "subscription.start_date": datetime.utcnow(),
                    "subscription.expiry_date": expiry_date,
                    "subscription.starts_at": datetime.utcnow(),  # Set for backward compatibility
                    "subscription.expires_at": expiry_date,  # Set for backward compatibility
                    "subscription.is_active": True,
                    "subscription.updated_at": datetime.utcnow()
                }
            }

            if transaction_id:
                update_data["$set"]["subscription.transaction_id"] = transaction_id

            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                update_data
            )

            if result.modified_count > 0:
                logger.info(f"Applied {plan_name} subscription to user {user_id}")
                return True, f"Successfully applied {plan_name} subscription"
            else:
                logger.error(f"Failed to apply subscription to user {user_id}")
                return False, "Failed to update subscription"

        except Exception as e:
            logger.error(f"Error applying premium subscription: {str(e)}")
            return False, str(e)

    def get_user_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user's current subscription with plan details

        Args:
            user_id: User identifier

        Returns:
            Subscription details with limits
        """
        try:
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return None

            subscription = user.get('subscription', {})
            plan_name = subscription.get('plan', 'FREE')

            # Get plan limits
            limits = self.get_limits_for_user(user_id)

            # Get plan prices
            prices = self.config.PLAN_PRICES.get(plan_name, {})

            return {
                "plan": plan_name,
                "plan_duration": subscription.get('plan_duration'),
                "start_date": subscription.get('start_date'),
                "expiry_date": subscription.get('expiry_date'),
                "limits": limits,
                "prices": prices,
                "is_active": self._is_subscription_active(subscription)
            }

        except Exception as e:
            logger.error(f"Error getting user subscription: {str(e)}")
            return None

    def _is_subscription_active(self, subscription: Dict[str, Any]) -> bool:
        """Check if subscription is active"""
        plan = subscription.get('plan', 'FREE')
        if plan == 'FREE':
            return True

        expiry_date = subscription.get('expiry_date')
        if not expiry_date:
            return False

        return datetime.utcnow() < expiry_date

    def check_and_downgrade_expired(self) -> Dict[str, int]:
        """
        Check for expired subscriptions and downgrade to FREE
        (Run this as a cron job daily)

        Returns:
            Dict with counts of processed subscriptions
        """
        try:
            current_time = datetime.utcnow()

            # Find expired subscriptions
            expired = self.users.find({
                "subscription.expiry_date": {"$lt": current_time},
                "subscription.plan": {"$ne": "FREE"}
            })

            downgraded_count = 0
            failed_count = 0

            for user in expired:
                try:
                    result = self.users.update_one(
                        {"_id": user["_id"]},
                        {
                            "$set": {
                                "subscription.plan": "FREE",
                                "subscription.plan_duration": None,
                                "subscription.expiry_date": None,
                                "subscription.updated_at": current_time,
                                "subscription.downgraded_at": current_time,
                                "subscription.downgrade_reason": "Subscription expired"
                            }
                        }
                    )
                    if result.modified_count > 0:
                        downgraded_count += 1
                        logger.info(f"Downgraded expired subscription for user {user['_id']}")
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"Failed to downgrade user {user['_id']}: {e}")
                    failed_count += 1

            return {
                "downgraded": downgraded_count,
                "failed": failed_count,
                "total": downgraded_count + failed_count
            }

        except Exception as e:
            logger.error(f"Error checking expired subscriptions: {str(e)}")
            return {"downgraded": 0, "failed": 0, "total": 0} 