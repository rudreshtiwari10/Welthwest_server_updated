#!/usr/bin/env python3
"""
Migration script to fix subscription tier field for all users.
This script ensures both 'tier' and 'plan' fields are set correctly for backward compatibility.

Usage:
    python fix_subscription_tiers.py
"""

import logging
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from config import get_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_all_user_subscriptions():
    """Fix subscription tier/plan fields for all users"""
    try:
        config = get_config()
        db = MongoClient(config.MONGODB_URI)[config.DB_NAME]
        users_collection = db.users

        # Find all users
        users = list(users_collection.find({}))
        logger.info(f"Found {len(users)} users to process")

        fixed_count = 0
        skipped_count = 0
        error_count = 0

        for user in users:
            try:
                user_id = str(user['_id'])

                # Check if user has subscription
                if 'subscription' not in user:
                    logger.info(f"User {user_id} has no subscription, initializing with FREE tier")
                    users_collection.update_one(
                        {"_id": user['_id']},
                        {
                            "$set": {
                                "subscription": {
                                    "plan": "FREE",
                                    "tier": "FREE",
                                    "plan_duration": None,
                                    "start_date": datetime.utcnow(),
                                    "expiry_date": None,
                                    "starts_at": datetime.utcnow(),
                                    "expires_at": None,
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
                        }
                    )
                    fixed_count += 1
                    continue

                subscription = user['subscription']
                updates = {}
                needs_update = False

                # Get plan and tier values
                plan_value = subscription.get('plan')
                tier_value = subscription.get('tier')

                # If both are missing, set to FREE
                if not plan_value and not tier_value:
                    logger.warning(f"User {user_id} has no plan or tier, setting to FREE")
                    updates['subscription.plan'] = 'FREE'
                    updates['subscription.tier'] = 'FREE'
                    needs_update = True

                # If plan is missing but tier exists, copy tier to plan
                elif not plan_value and tier_value:
                    logger.info(f"User {user_id} missing plan field, copying from tier: {tier_value}")
                    updates['subscription.plan'] = tier_value
                    needs_update = True

                # If tier is missing but plan exists, copy plan to tier
                elif plan_value and not tier_value:
                    logger.info(f"User {user_id} missing tier field, copying from plan: {plan_value}")
                    updates['subscription.tier'] = plan_value
                    needs_update = True

                # If both exist but are different, use plan value (it's newer)
                elif plan_value and tier_value and plan_value != tier_value:
                    logger.warning(f"User {user_id} has mismatched plan ({plan_value}) and tier ({tier_value}), using plan value")
                    updates['subscription.tier'] = plan_value
                    needs_update = True

                # Add backward compatibility fields if missing
                if 'starts_at' not in subscription and 'start_date' in subscription:
                    updates['subscription.starts_at'] = subscription['start_date']
                    needs_update = True
                elif 'starts_at' not in subscription:
                    updates['subscription.starts_at'] = datetime.utcnow()
                    needs_update = True

                if 'expires_at' not in subscription and 'expiry_date' in subscription:
                    updates['subscription.expires_at'] = subscription['expiry_date']
                    needs_update = True
                elif 'expires_at' not in subscription:
                    updates['subscription.expires_at'] = None
                    needs_update = True

                if 'is_active' not in subscription:
                    updates['subscription.is_active'] = True
                    needs_update = True

                # Ensure usage data exists
                if 'usage' not in subscription:
                    logger.warning(f"User {user_id} missing usage data, adding default structure")
                    updates['subscription.usage'] = {
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
                    needs_update = True

                # Apply updates if needed
                if needs_update:
                    users_collection.update_one(
                        {"_id": user['_id']},
                        {"$set": updates}
                    )
                    fixed_count += 1
                    logger.info(f"✓ Fixed subscription for user {user_id}")
                else:
                    skipped_count += 1
                    logger.debug(f"○ User {user_id} already has correct subscription structure")

            except Exception as e:
                error_count += 1
                logger.error(f"✗ Error processing user {user.get('_id')}: {str(e)}")

        # Print summary
        logger.info("=" * 60)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total users processed: {len(users)}")
        logger.info(f"✓ Fixed: {fixed_count}")
        logger.info(f"○ Skipped (already correct): {skipped_count}")
        logger.info(f"✗ Errors: {error_count}")
        logger.info("=" * 60)

        return fixed_count, skipped_count, error_count

    except Exception as e:
        logger.error(f"Error in migration script: {str(e)}")
        raise

if __name__ == "__main__":
    logger.info("Starting subscription tier migration...")
    logger.info("This script will fix missing 'tier' and 'plan' fields for all users")
    logger.info("-" * 60)

    try:
        fixed, skipped, errors = fix_all_user_subscriptions()

        if errors > 0:
            logger.warning(f"Migration completed with {errors} errors")
            exit(1)
        else:
            logger.info("Migration completed successfully!")
            exit(0)

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        exit(1)
