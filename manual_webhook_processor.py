"""
Manual Webhook Processor - Process the failed webhook from error.md
This script manually processes the successful payment that failed to update via webhook
"""
import requests
import json
from datetime import datetime

# The webhook data from error.md (lines 40-92)
webhook_data = {
    "data": {
        "order": {
            "order_id": "WW_68D2DCE0E6E6C150EC468E04_PRO_MONTHLY_CF3C8B87",
            "order_amount": 499,
            "order_currency": "INR",
            "order_tags": {
                "duration": "monthly",
                "plan": "PRO"
            }
        },
        "payment": {
            "cf_payment_id": "5114922279439",
            "payment_status": "SUCCESS",
            "payment_amount": 499,
            "payment_currency": "INR",
            "payment_message": "Simulated response message",
            "payment_time": "2025-11-10T22:28:24+05:30",
            "bank_reference": "5114922279439",
            "auth_id": None,
            "payment_method": {
                "card": {
                    "channel": None,
                    "card_number": "XXXXXXXXXXXX2123",
                    "card_network": "visa",
                    "card_type": "debit_card",
                    "card_sub_type": "R",
                    "card_country": "IN",
                    "card_bank_name": "KOTAK MAHINDRA BANK"
                }
            },
            "payment_group": "debit_card"
        },
        "customer_details": {
            "customer_name": None,
            "customer_id": "68d2dce0e6e6c150ec468e04",
            "customer_email": "kunalkumar9457.kk@gmail.com",
            "customer_phone": "9999999999"
        },
        "payment_gateway_details": {
            "gateway_name": "CASHFREE",
            "gateway_order_id": "2200144682",
            "gateway_payment_id": "5114922279439",
            "gateway_status_code": None,
            "gateway_order_reference_id": "null",
            "gateway_settlement": "CASHFREE",
            "gateway_reference_name": None
        },
        "payment_offers": None
    },
    "event_time": "2025-11-10T22:28:38+05:30",
    "type": "PAYMENT_SUCCESS_WEBHOOK"
}

# Headers that would be sent by Cashfree
headers = {
    "Content-Type": "application/json",
    "x-webhook-signature": "w1K5L7Kn4wzmtMb+Wp9uAvRvcVh4cC1z9vBDcfYur7M=",
    "x-webhook-timestamp": "1762793918373",
    "x-webhook-version": "2023-08-01"
}

def process_manually():
    """Process the webhook manually by posting to local webhook endpoint"""

    # Local webhook URL
    webhook_url = "http://localhost:5000/api/payment/webhook"

    print(f"Processing failed webhook for order: {webhook_data['data']['order']['order_id']}")
    print(f"Payment ID: {webhook_data['data']['payment']['cf_payment_id']}")
    print(f"Amount: ₹{webhook_data['data']['payment']['payment_amount']}")
    print(f"Customer: {webhook_data['data']['customer_details']['customer_email']}")
    print()

    # Send POST request to webhook endpoint
    print(f"Sending POST request to: {webhook_url}")

    try:
        response = requests.post(
            webhook_url,
            json=webhook_data,
            headers=headers,
            timeout=10
        )

        print(f"\nResponse Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")

        if response.status_code == 200:
            print("\n[SUCCESS]: Webhook processed successfully!")
            print("The transaction should now be updated to SUCCESS and subscription applied.")
        elif response.status_code == 400:
            print("\n[ERROR]: Invalid signature or bad request")
            print("Note: Signature verification may fail if CASHFREE_SECRET_KEY is different")
        elif response.status_code == 404:
            print("\n[ERROR]: Webhook endpoint not found")
            print("Make sure Flask server is running on port 5000")
        else:
            print(f"\n[ERROR]: Unexpected response code {response.status_code}")

    except requests.exceptions.ConnectionError:
        print("\n[ERROR]: Cannot connect to Flask server")
        print("Make sure the Flask server is running on port 5000")
    except Exception as e:
        print(f"\n[ERROR]: {e}")

def process_via_database():
    """Alternative: Process directly via MongoDB (bypasses webhook signature verification)"""
    from pymongo import MongoClient
    from bson import ObjectId
    from config import get_config
    from services.subscription_service import SubscriptionService

    config = get_config()
    db = MongoClient(config.MONGODB_URI)[config.DB_NAME]
    transactions_collection = db.transactions
    subscription_service = SubscriptionService()

    order_id = webhook_data['data']['order']['order_id']

    print(f"\n{'='*60}")
    print("PROCESSING VIA DATABASE (bypassing webhook)")
    print(f"{'='*60}\n")

    # Find transaction
    transaction = transactions_collection.find_one({"gateway_order_id": order_id})

    if not transaction:
        print(f"[ERROR] Transaction not found for order: {order_id}")
        return

    print(f"Found transaction: {transaction['_id']}")
    print(f"Current status: {transaction.get('status')}")

    # Check if already processed
    if transaction.get('status') == 'SUCCESS':
        print("[SUCCESS] Transaction already marked as SUCCESS")
        return

    # Update transaction to SUCCESS
    payment_data = webhook_data['data']['payment']

    transactions_collection.update_one(
        {"_id": transaction["_id"]},
        {
            "$set": {
                "status": "SUCCESS",
                "gateway_payment_id": payment_data.get('cf_payment_id'),
                "payment_status": payment_data.get('payment_status'),
                "payment_time": payment_data.get('payment_time'),
                "payment_method": payment_data.get('payment_group'),
                "bank_reference": payment_data.get('bank_reference'),
                "updated_at": datetime.utcnow(),
                "meta": webhook_data
            }
        }
    )

    print("[SUCCESS] Transaction updated to SUCCESS")

    # Apply subscription to user
    user_id = str(transaction['user_id'])
    plan = transaction['plan_id']
    duration = transaction['plan_duration']
    transaction_id = str(transaction['_id'])

    print(f"\nApplying subscription:")
    print(f"  User ID: {user_id}")
    print(f"  Plan: {plan}")
    print(f"  Duration: {duration}")

    success, message = subscription_service.apply_premium_subscription(
        user_id=user_id,
        plan_name=plan,
        plan_duration=duration,
        transaction_id=transaction_id
    )

    if success:
        print(f"\n[SUCCESS]: {message}")
        print("User subscription has been activated!")
    else:
        print(f"\n[FAILED]: {message}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("MANUAL WEBHOOK PROCESSOR")
    print("="*60)
    print("\nThis script will process the failed webhook from the test payment.")
    print("\nOptions:")
    print("1. Try via webhook endpoint (tests signature verification)")
    print("2. Process directly via database (bypasses verification)")
    print()

    choice = input("Choose option (1 or 2): ").strip()

    if choice == "1":
        process_manually()
    elif choice == "2":
        process_via_database()
    else:
        print("Invalid choice")
