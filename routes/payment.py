"""
Payment Routes - Handle Cashfree payment integration and webhooks
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.payment_cashfree import get_cashfree_service
from services.subscription_service import SubscriptionService
from services.notification_service import notification_service
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from config import get_config
import logging
import uuid

logger = logging.getLogger(__name__)

# Create blueprint
payment_bp = Blueprint('payment', __name__, url_prefix='/api/payment')

# Initialize services
cashfree_service = get_cashfree_service()
subscription_service = SubscriptionService()
config = get_config()

# Initialize MongoDB
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]
transactions_collection = db.transactions
webhook_events_collection = db.webhook_events


@payment_bp.route('/create-order', methods=['POST'])
@jwt_required()
def create_order():
    """
    Create a Cashfree payment order

    Request Body:
        {
            "plan": "PRO",
            "duration": "monthly"
        }

    Returns:
        200: Order created with payment link
        400: Invalid request
        403: Payment gateway disabled
        500: Server error
    """
    try:
        user_id = get_jwt_identity()
        data = request.json

        # Validate request
        if not data or 'plan' not in data or 'duration' not in data:
            return jsonify({
                "success": False,
                "error": "Plan and duration are required"
            }), 400

        plan = data['plan'].upper()
        duration = data['duration'].lower()

        # Validate plan
        if plan not in config.PLAN_PRICES:
            return jsonify({
                "success": False,
                "error": "Invalid plan"
            }), 400

        # Validate duration
        if duration not in ['weekly', 'monthly', 'annual']:
            return jsonify({
                "success": False,
                "error": "Invalid duration"
            }), 400

        # Check if payment gateway is enabled
        if not config.IS_PAYMENT_GATEWAY_ENABLED:
            return jsonify({
                "success": False,
                "error": "Payment gateway is currently disabled. Please contact support for manual purchase."
            }), 403

        # Get user details
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({
                "success": False,
                "error": "User not found"
            }), 404

        # Get price
        amount = config.PLAN_PRICES[plan][duration]

        if amount == 0:
            return jsonify({
                "success": False,
                "error": "Cannot purchase FREE plan"
            }), 400

        # Generate unique order ID
        order_id = f"WW_{user_id}_{plan}_{duration}_{uuid.uuid4().hex[:8]}".upper()

        # Get user billing details
        customer_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or 'Customer'
        customer_email = user.get('email', 'user@example.com')
        customer_phone = user.get('phone', '9999999999')
        billing_address = user.get('billing_address', '')

        # Create transaction record with billing info
        transaction = {
            "user_id": ObjectId(user_id),
            "plan_id": plan,
            "plan_duration": duration,
            "amount": amount,
            "currency": "INR",
            "status": "PENDING",
            "gateway": "CASHFREE",
            "gateway_order_id": order_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "billing_address": billing_address,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = transactions_collection.insert_one(transaction)
        transaction_id = str(result.inserted_id)

        # Create Cashfree order
        success, order_data = cashfree_service.create_order(
            order_id=order_id,
            amount=amount,
            customer_id=user_id,
            customer_email=customer_email,
            customer_phone=customer_phone,
            customer_name=customer_name,
            return_url=f"{config.FRONTEND_URL}/payment-success",
            plan_name=plan,
            plan_duration=duration
        )

        if success:
            # Update transaction with Cashfree details
            transactions_collection.update_one(
                {"_id": ObjectId(transaction_id)},
                {
                    "$set": {
                        "payment_session_id": order_data.get('payment_session_id'),
                        "order_status": order_data.get('order_status'),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            logger.info(f"Order created successfully: {order_id} for user {user_id}")

            return jsonify({
                "success": True,
                "order_id": order_id,
                "transaction_id": transaction_id,
                "payment_session_id": order_data.get('payment_session_id'),
                "payment_link": order_data.get('payment_link'),
                "amount": amount,
                "currency": "INR",
                "plan": plan,
                "duration": duration
            }), 200
        else:
            # Update transaction as failed
            transactions_collection.update_one(
                {"_id": ObjectId(transaction_id)},
                {
                    "$set": {
                        "status": "FAILED",
                        "error": order_data.get('error'),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            return jsonify({
                "success": False,
                "error": order_data.get('error', 'Failed to create order')
            }), 500

    except Exception as e:
        logger.error(f"Error creating order: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to create order"
        }), 500


@payment_bp.route('/webhook', methods=['POST'])
def cashfree_webhook():
    """
    Handle Cashfree webhook events

    This endpoint receives payment notifications from Cashfree

    Returns:
        200: Webhook processed
        400: Invalid signature
        404: Transaction not found
        500: Server error
    """
    try:
        # Get raw payload and headers
        payload = request.get_data()
        signature = request.headers.get('x-webhook-signature')
        timestamp = request.headers.get('x-webhook-timestamp')

        # Log webhook received
        logger.info(f"Webhook received: signature={signature}, timestamp={timestamp}")

        # Verify signature
        if not cashfree_service.verify_webhook_signature(payload, signature, timestamp):
            logger.warning("Webhook signature verification failed")

            # Log failed webhook
            webhook_events_collection.insert_one({
                "payload": request.json,
                "headers": dict(request.headers),
                "verification_status": "FAILED",
                "created_at": datetime.utcnow()
            })

            return jsonify({"error": "Invalid signature"}), 400

        # Parse webhook data
        webhook_data = request.json

        # Log successful webhook
        webhook_events_collection.insert_one({
            "payload": webhook_data,
            "headers": dict(request.headers),
            "verification_status": "SUCCESS",
            "created_at": datetime.utcnow()
        })

        # Process payment
        processed_data = cashfree_service.process_webhook_payment(webhook_data)
        order_id = processed_data.get('order_id')

        if not order_id:
            logger.error("No order_id in webhook data")
            return jsonify({"error": "Invalid webhook data"}), 400

        # Find transaction
        transaction = transactions_collection.find_one({"gateway_order_id": order_id})

        if not transaction:
            logger.error(f"Transaction not found for order {order_id}")
            return jsonify({"error": "Transaction not found"}), 404

        # Check if already processed (idempotency)
        if transaction.get('status') == 'SUCCESS':
            logger.info(f"Transaction {order_id} already processed")
            return jsonify({"status": "already_processed"}), 200

        # Check if payment is successful
        if cashfree_service.is_payment_success(webhook_data):
            # Update transaction
            transactions_collection.update_one(
                {"_id": transaction["_id"]},
                {
                    "$set": {
                        "status": "SUCCESS",
                        "gateway_payment_id": processed_data.get('payment_id'),
                        "payment_status": processed_data.get('payment_status'),
                        "payment_time": processed_data.get('payment_time'),
                        "payment_method": processed_data.get('payment_method'),
                        "bank_reference": processed_data.get('bank_reference'),
                        "updated_at": datetime.utcnow(),
                        "meta": processed_data
                    }
                }
            )

            # Apply subscription to user
            user_id = str(transaction['user_id'])
            plan = transaction['plan_id']
            duration = transaction['plan_duration']
            transaction_id = str(transaction['_id'])

            success, message = subscription_service.apply_premium_subscription(
                user_id=user_id,
                plan_name=plan,
                plan_duration=duration,
                transaction_id=transaction_id
            )

            if success:
                logger.info(f"Subscription applied successfully for user {user_id}: {plan} ({duration})")

                # Create success notification
                try:
                    notification_service.notify_payment_success(
                        user_id=user_id,
                        amount=transaction.get('amount', 0),
                        plan_name=plan,
                        transaction_id=transaction_id
                    )
                except Exception as e:
                    logger.error(f"Failed to create payment success notification: {str(e)}")
            else:
                logger.error(f"Failed to apply subscription: {message}")

            return jsonify({"status": "success"}), 200
        else:
            # Payment failed
            transactions_collection.update_one(
                {"_id": transaction["_id"]},
                {
                    "$set": {
                        "status": "FAILED",
                        "payment_status": processed_data.get('payment_status'),
                        "updated_at": datetime.utcnow(),
                        "meta": processed_data
                    }
                }
            )

            logger.warning(f"Payment failed for order {order_id}")

            # Create failure notification
            try:
                user_id = str(transaction['user_id'])
                notification_service.notify_payment_failed(
                    user_id=user_id,
                    amount=transaction.get('amount', 0),
                    plan_name=transaction.get('plan_id', 'Unknown'),
                    reason=processed_data.get('payment_status', 'Payment processing failed')
                )
            except Exception as e:
                logger.error(f"Failed to create payment failure notification: {str(e)}")

            return jsonify({"status": "payment_failed"}), 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@payment_bp.route('/order-status/<order_id>', methods=['GET'])
@jwt_required()
def get_order_status(order_id):
    """
    Get order status

    Args:
        order_id: Order identifier

    Returns:
        200: Order status
        404: Order not found
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Find transaction
        transaction = transactions_collection.find_one({
            "gateway_order_id": order_id,
            "user_id": ObjectId(user_id)
        })

        if not transaction:
            return jsonify({
                "success": False,
                "error": "Order not found"
            }), 404

        # Get status from Cashfree if pending
        if transaction.get('status') == 'PENDING' and config.IS_PAYMENT_GATEWAY_ENABLED:
            success, order_data = cashfree_service.get_order_status(order_id)
            if success:
                # Update transaction with latest status
                transactions_collection.update_one(
                    {"_id": transaction["_id"]},
                    {
                        "$set": {
                            "order_status": order_data.get('order_status'),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

        # Refresh transaction
        transaction = transactions_collection.find_one({"_id": transaction["_id"]})

        return jsonify({
            "success": True,
            "order": {
                "order_id": transaction.get('gateway_order_id'),
                "status": transaction.get('status'),
                "plan": transaction.get('plan_id'),
                "duration": transaction.get('plan_duration'),
                "amount": transaction.get('amount'),
                "currency": transaction.get('currency'),
                "created_at": transaction.get('created_at'),
                "updated_at": transaction.get('updated_at')
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting order status: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to get order status"
        }), 500


@payment_bp.route('/transaction-history', methods=['GET'])
@jwt_required()
def get_transaction_history():
    """
    Get user's transaction history

    Returns:
        200: List of transactions
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Get all transactions for user
        transactions = list(transactions_collection.find(
            {"user_id": ObjectId(user_id)}
        ).sort("created_at", -1).limit(50))

        # Format transactions
        formatted_transactions = []
        for txn in transactions:
            formatted_transactions.append({
                "transaction_id": str(txn['_id']),
                "order_id": txn.get('gateway_order_id'),
                "plan": txn.get('plan_id'),
                "duration": txn.get('plan_duration'),
                "amount": txn.get('amount'),
                "currency": txn.get('currency'),
                "status": txn.get('status'),
                "customer_name": txn.get('customer_name', ''),
                "customer_email": txn.get('customer_email', ''),
                "billing_address": txn.get('billing_address', ''),
                "created_at": txn.get('created_at'),
                "updated_at": txn.get('updated_at')
            })

        return jsonify({
            "success": True,
            "transactions": formatted_transactions
        }), 200

    except Exception as e:
        logger.error(f"Error getting transaction history: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to get transaction history"
        }), 500
