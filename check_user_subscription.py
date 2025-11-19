"""Check user subscription status"""
from pymongo import MongoClient
from bson import ObjectId
from config import get_config
from datetime import datetime
import pytz

config = get_config()
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]
users_collection = db.users

# User ID from the transaction
user_id = "68d2dce0e6e6c150ec468e04"

# Find user
user = users_collection.find_one({"_id": ObjectId(user_id)})

if not user:
    print(f"User not found: {user_id}")
else:
    print(f"\nUser: {user.get('email')}")
    print(f"User ID: {user_id}")
    print("-" * 60)

    subscription = user.get('subscription', {})

    if not subscription:
        print("\n[WARNING] No subscription found!")
        print("The subscription may not have been applied.")
    else:
        print(f"\nSubscription Status:")
        print(f"  Plan: {subscription.get('plan_name', 'N/A')}")
        print(f"  Duration: {subscription.get('plan_duration', 'N/A')}")
        print(f"  Start Date: {subscription.get('start_date', 'N/A')}")
        print(f"  Expiry Date: {subscription.get('expiry_date', 'N/A')}")
        print(f"  Transaction ID: {subscription.get('transaction_id', 'N/A')}")
        print(f"  Status: {subscription.get('status', 'N/A')}")

        # Check if expired
        expiry_date = subscription.get('expiry_date')
        if expiry_date:
            try:
                if isinstance(expiry_date, str):
                    expiry_dt = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                else:
                    expiry_dt = expiry_date

                now = datetime.now(pytz.UTC)

                if expiry_dt > now:
                    print(f"\n[SUCCESS] Subscription is ACTIVE")
                    days_left = (expiry_dt - now).days
                    print(f"Days remaining: {days_left}")
                else:
                    print(f"\n[WARNING] Subscription has EXPIRED")
            except:
                print(f"\n[WARNING] Could not parse expiry date")

# Check transaction status
transactions_collection = db.transactions
transaction = transactions_collection.find_one(
    {"gateway_order_id": "WW_68D2DCE0E6E6C150EC468E04_PRO_MONTHLY_CF3C8B87"}
)

if transaction:
    print(f"\n\nTransaction Status:")
    print(f"  Order ID: {transaction.get('gateway_order_id')}")
    print(f"  Status: {transaction.get('status')}")
    print(f"  Plan: {transaction.get('plan_id')}")
    print(f"  Duration: {transaction.get('plan_duration')}")
    print(f"  Amount: Rs.{transaction.get('amount')}")
    print(f"  Payment ID: {transaction.get('gateway_payment_id', 'N/A')}")
