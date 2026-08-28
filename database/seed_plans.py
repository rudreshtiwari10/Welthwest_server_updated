"""
Seed Plans - Initialize plans collection from environment configuration
Run this at application startup to ensure plans are in database
"""
import logging
from datetime import datetime
from pymongo import MongoClient
from config import get_config

logger = logging.getLogger(__name__)


def seed_plans_to_database():
    """
    Seed premium plans from config to MongoDB
    This function is idempotent - safe to run multiple times
    """
    try:
        config = get_config()

        # Connect to MongoDB
        client = MongoClient(config.MONGODB_URI)
        db = client[config.DB_NAME]
        plans_collection = db.plans

        # Define plans to seed
        plans = ['FREE', 'STARTER', 'PRO', 'ADVANCED', 'ENTERPRISE']

        seeded_count = 0
        updated_count = 0

        for plan_id in plans:
            # Get plan data from config
            plan_data = {
                "_id": plan_id,
                "display_name": plan_id.capitalize(),
                "prices": config.PLAN_PRICES.get(plan_id, {}),
                "limits": config.PLAN_LIMITS.get(plan_id, {}),
                "features": list(config.PLAN_LIMITS.get(plan_id, {}).keys()),
                "description": get_plan_description(plan_id),
                "updated_at": datetime.utcnow()
            }

            # Check if plan exists
            existing_plan = plans_collection.find_one({"_id": plan_id})

            if existing_plan:
                # Update existing plan
                result = plans_collection.update_one(
                    {"_id": plan_id},
                    {"$set": plan_data}
                )
                if result.modified_count > 0:
                    updated_count += 1
                    logger.info(f"Updated plan: {plan_id}")
            else:
                # Insert new plan
                plan_data["created_at"] = datetime.utcnow()
                plans_collection.insert_one(plan_data)
                seeded_count += 1
                logger.info(f"Seeded new plan: {plan_id}")

        logger.info(f"Plans seeding complete: {seeded_count} new, {updated_count} updated")

        return {
            "success": True,
            "seeded": seeded_count,
            "updated": updated_count,
            "total": len(plans)
        }

    except Exception as e:
        logger.error(f"Error seeding plans: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def get_plan_description(plan_id: str) -> str:
    """Get description for a plan"""
    descriptions = {
        "FREE": "Perfect for getting started with basic features and limited usage",
        "STARTER": "Great for individual users who want more features and higher limits",
        "PRO": "Ideal for professionals who need advanced features and higher daily limits",
        "ADVANCED": "For power users who need extensive access to all features",
        "ENTERPRISE": "Maximum limits for teams and businesses with high usage requirements"
    }
    return descriptions.get(plan_id, "")


def create_indexes():
    """Create necessary MongoDB indexes for premium features"""
    try:
        config = get_config()
        client = MongoClient(config.MONGODB_URI)
        db = client[config.DB_NAME]

        # Plans collection indexes (MongoDB automatically creates unique index on _id)
        # db.plans.create_index([("_id", 1)], unique=True)

        # Transactions collection indexes
        db.transactions.create_index([("user_id", 1)])
        db.transactions.create_index([("gateway_order_id", 1)], unique=True)
        db.transactions.create_index([("status", 1)])
        db.transactions.create_index([("created_at", -1)])

        # Usage logs collection indexes
        db.usage_logs.create_index([("actor_id", 1)])
        db.usage_logs.create_index([("feature", 1)])
        db.usage_logs.create_index([("created_at", -1)])
        db.usage_logs.create_index([("is_anonymous", 1)])

        # Webhook events collection indexes
        db.webhook_events.create_index([("created_at", -1)])
        db.webhook_events.create_index([("verification_status", 1)])

        logger.info("MongoDB indexes created successfully")
        return True

    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        return False


def initialize_premium_system():
    """
    Complete initialization of premium system
    Call this function at application startup
    """
    logger.info("Initializing premium system...")

    # Create indexes
    create_indexes()

    # Seed plans
    result = seed_plans_to_database()

    if result["success"]:
        logger.info(f"✓ Premium system initialized: {result['seeded']} new plans, {result['updated']} updated")
    else:
        logger.error(f"✗ Premium system initialization failed: {result.get('error')}")

    return result
