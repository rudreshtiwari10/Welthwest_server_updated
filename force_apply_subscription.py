"""Force apply subscription for the successful payment"""
from pymongo import MongoClient
from bson import ObjectId
from config import get_config
from services.subscription_service import SubscriptionService

config = get_config()
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]
transactions_collection = db.transactions
subscription_service = SubscriptionService()

# Find the transaction
order_id = "WW_68D2DCE0E6E6C150EC468E04_PRO_MONTHLY_CF3C8B87"
transaction = transactions_collection.find_one({"gateway_order_id": order_id})

if not transaction:
    print(f"Transaction not found for order: {order_id}")
    exit(1)

print("="*60)
print("FORCE APPLY SUBSCRIPTION")
print("="*60)
print(f"\nTransaction ID: {transaction['_id']}")
print(f"Order ID: {order_id}")
print(f"Status: {transaction.get('status')}")
print(f"Plan: {transaction.get('plan_id')}")
print(f"Duration: {transaction.get('plan_duration')}")
print(f"Amount: Rs.{transaction.get('amount')}")
print()

# Apply subscription to user
user_id = str(transaction['user_id'])
plan = transaction['plan_id']
duration = transaction['plan_duration']
transaction_id = str(transaction['_id'])

print(f"Applying subscription:")
print(f"  User ID: {user_id}")
print(f"  Plan: {plan}")
print(f"  Duration: {duration}")
print(f"  Transaction ID: {transaction_id}")
print()

success, message = subscription_service.apply_premium_subscription(
    user_id=user_id,
    plan_name=plan,
    plan_duration=duration,
    transaction_id=transaction_id
)

if success:
    print(f"[SUCCESS]: {message}")
    print("\nUser subscription has been activated!")
    print("\nPlease refresh your dashboard to see the updated subscription.")
else:
    print(f"[FAILED]: {message}")
