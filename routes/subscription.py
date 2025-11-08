"""
Subscription Management Routes - Enhanced subscription and usage tracking
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.subscription_service import SubscriptionService
from services.premium_usage_service import get_premium_usage_service
from services.payment_cashfree import get_cashfree_service
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from config import get_config
import logging

logger = logging.getLogger(__name__)

# Create blueprint
subscription_bp = Blueprint('subscription', __name__, url_prefix='/api/subscription')

# Initialize services
subscription_service = SubscriptionService()
usage_service = get_premium_usage_service()
cashfree_service = get_cashfree_service()
config = get_config()

# Initialize MongoDB
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]
transactions_collection = db.transactions


@subscription_bp.route('/status', methods=['GET'])
@jwt_required()
def get_subscription_status():
    """
    Get detailed subscription status with per-feature usage

    Returns:
        200: Subscription status with usage details
        404: User not found
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Fix missing subscription fields (migration for old users)
        subscription_service.fix_missing_subscription(user_id)

        # Get subscription details
        subscription = subscription_service.get_user_subscription(user_id)

        if not subscription:
            return jsonify({
                "success": False,
                "error": "Subscription not found"
            }), 404

        # Get per-feature limits
        limits = subscription_service.get_limits_for_user(user_id)

        # Get usage for all features
        feature_keys = list(limits.keys())
        usage = usage_service.get_all_usage(
            actor_id=user_id,
            feature_keys=feature_keys,
            limits=limits,
            is_anonymous=False
        )

        # Format response with feature details
        feature_usage = []
        feature_names = {
            'welth-market-regime': 'Welth Market Regime',
            'welth-ai-assistant': 'Welth AI Assistant',
            'backtest-beta': 'Backtest Beta'
        }

        for feature_key in feature_keys:
            feature_data = usage.get(feature_key, {})
            feature_usage.append({
                'feature_key': feature_key,
                'feature_name': feature_names.get(feature_key, feature_key),
                'used': feature_data.get('used', 0),
                'remaining': feature_data.get('remaining', 0),
                'limit': feature_data.get('limit', 0),
                'percentage': round((feature_data.get('used', 0) / feature_data.get('limit', 1)) * 100, 1) if feature_data.get('limit', 0) > 0 else 0
            })

        # Calculate time until next reset
        from datetime import timedelta
        import pytz

        tz = pytz.timezone(config.SERVER_TIMEZONE)
        now = datetime.now(tz)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        time_until_reset = tomorrow - now
        hours_until_reset = int(time_until_reset.total_seconds() / 3600)
        minutes_until_reset = int((time_until_reset.total_seconds() % 3600) / 60)

        return jsonify({
            "success": True,
            "subscription": {
                "plan": subscription.get('plan', 'FREE'),
                "plan_duration": subscription.get('plan_duration'),
                "start_date": subscription.get('start_date').isoformat() if subscription.get('start_date') else None,
                "expiry_date": subscription.get('expiry_date').isoformat() if subscription.get('expiry_date') else None,
                "is_active": subscription.get('is_active', True),
                "days_remaining": (subscription.get('expiry_date') - datetime.utcnow()).days if subscription.get('expiry_date') and subscription.get('expiry_date') > datetime.utcnow() else 0
            },
            "usage": {
                "features": feature_usage,
                "reset_info": {
                    "next_reset": tomorrow.isoformat(),
                    "hours_until_reset": hours_until_reset,
                    "minutes_until_reset": minutes_until_reset,
                    "reset_message": f"Your daily usage resets in {hours_until_reset} hours and {minutes_until_reset} minutes"
                }
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting subscription status: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch subscription status"
        }), 500


@subscription_bp.route('/verify-expiry', methods=['POST'])
@jwt_required()
def verify_subscription_expiry():
    """
    Verify subscription expiry and auto-downgrade if needed
    Called on user login

    Returns:
        200: Expiry verification result
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Check subscription expiry
        result = subscription_service.check_subscription_expiry(user_id)

        if result.get('expired') and result.get('downgraded'):
            return jsonify({
                "success": True,
                "expired": True,
                "downgraded": True,
                "message": "Your subscription has expired and you have been downgraded to FREE tier"
            }), 200
        elif result.get('expired') and not result.get('downgraded'):
            return jsonify({
                "success": False,
                "expired": True,
                "downgraded": False,
                "message": "Subscription expired but failed to downgrade"
            }), 500
        else:
            return jsonify({
                "success": True,
                "expired": False,
                "message": "Subscription is active"
            }), 200

    except Exception as e:
        logger.error(f"Error verifying expiry: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to verify subscription expiry"
        }), 500


@subscription_bp.route('/payment-history', methods=['GET'])
@jwt_required()
def get_payment_history():
    """
    Get user's payment history with all transaction details

    Query Parameters:
        limit: Number of transactions to return (default: 50)
        skip: Number of transactions to skip (default: 0)

    Returns:
        200: List of transactions
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Get pagination parameters
        limit = request.args.get('limit', 50, type=int)
        skip = request.args.get('skip', 0, type=int)

        # Get transactions from database
        transactions = list(transactions_collection.find(
            {"user_id": ObjectId(user_id)}
        ).sort("created_at", -1).skip(skip).limit(limit))

        # Get total count
        total_count = transactions_collection.count_documents({"user_id": ObjectId(user_id)})

        # Format transactions
        formatted_transactions = []
        for txn in transactions:
            formatted_txn = {
                "transaction_id": str(txn['_id']),
                "order_id": txn.get('gateway_order_id'),
                "plan": txn.get('plan_id'),
                "plan_display_name": txn.get('plan_id', 'FREE').capitalize(),
                "duration": txn.get('plan_duration'),
                "amount": txn.get('amount'),
                "currency": txn.get('currency', 'INR'),
                "status": txn.get('status'),
                "payment_method": txn.get('payment_method'),
                "gateway": txn.get('gateway', 'CASHFREE'),
                "created_at": txn.get('created_at').isoformat() if txn.get('created_at') else None,
                "updated_at": txn.get('updated_at').isoformat() if txn.get('updated_at') else None,
                "payment_time": txn.get('payment_time'),
                "bank_reference": txn.get('bank_reference')
            }
            formatted_transactions.append(formatted_txn)

        return jsonify({
            "success": True,
            "transactions": formatted_transactions,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "skip": skip,
                "has_more": (skip + limit) < total_count
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting payment history: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch payment history"
        }), 500


@subscription_bp.route('/payment-history/<transaction_id>', methods=['GET'])
@jwt_required()
def get_transaction_details(transaction_id):
    """
    Get detailed information for a specific transaction
    Fetches additional details from Cashfree if available

    Args:
        transaction_id: Transaction ID

    Returns:
        200: Transaction details
        403: Unauthorized
        404: Transaction not found
        500: Server error
    """
    try:
        user_id = get_jwt_identity()

        # Find transaction
        transaction = transactions_collection.find_one({
            "_id": ObjectId(transaction_id),
            "user_id": ObjectId(user_id)
        })

        if not transaction:
            return jsonify({
                "success": False,
                "error": "Transaction not found or unauthorized"
            }), 404

        # Format basic transaction details
        details = {
            "transaction_id": str(transaction['_id']),
            "order_id": transaction.get('gateway_order_id'),
            "plan": transaction.get('plan_id'),
            "plan_display_name": transaction.get('plan_id', 'FREE').capitalize(),
            "duration": transaction.get('plan_duration'),
            "amount": transaction.get('amount'),
            "currency": transaction.get('currency', 'INR'),
            "status": transaction.get('status'),
            "gateway": transaction.get('gateway', 'CASHFREE'),
            "payment_method": transaction.get('payment_method'),
            "payment_session_id": transaction.get('payment_session_id'),
            "gateway_payment_id": transaction.get('gateway_payment_id'),
            "payment_status": transaction.get('payment_status'),
            "bank_reference": transaction.get('bank_reference'),
            "created_at": transaction.get('created_at').isoformat() if transaction.get('created_at') else None,
            "updated_at": transaction.get('updated_at').isoformat() if transaction.get('updated_at') else None,
            "payment_time": transaction.get('payment_time')
        }

        # Try to fetch additional details from Cashfree if payment is successful
        if transaction.get('status') == 'SUCCESS' and config.IS_PAYMENT_GATEWAY_ENABLED:
            order_id = transaction.get('gateway_order_id')
            if order_id:
                try:
                    success, order_data = cashfree_service.get_order_status(order_id)
                    if success:
                        details['cashfree_details'] = {
                            'order_status': order_data.get('order_status'),
                            'order_amount': order_data.get('order_amount'),
                            'order_currency': order_data.get('order_currency'),
                            'order_note': order_data.get('order_note')
                        }
                except Exception as e:
                    logger.warning(f"Could not fetch Cashfree details: {e}")

        return jsonify({
            "success": True,
            "transaction": details
        }), 200

    except Exception as e:
        logger.error(f"Error getting transaction details: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to fetch transaction details"
        }), 500


@subscription_bp.route('/usage/update', methods=['POST'])
@jwt_required()
def update_usage():
    """
    Update usage for a specific feature (increment counter)

    Request Body:
        {
            "feature_key": "welth-market-regime" | "welth-ai-assistant" | "backtest-beta"
        }

    Returns:
        200: Usage updated, allowed to proceed
        403: Usage limit exceeded
        400: Invalid request
        500: Server error
    """
    try:
        user_id = get_jwt_identity()
        data = request.json

        if not data or 'feature_key' not in data:
            return jsonify({
                "success": False,
                "error": "feature_key is required"
            }), 400

        feature_key = data['feature_key']

        # Validate feature key
        valid_features = ['welth-market-regime', 'welth-ai-assistant', 'backtest-beta']
        if feature_key not in valid_features:
            return jsonify({
                "success": False,
                "error": "Invalid feature key"
            }), 400

        # Get user's limit for this feature
        limits = subscription_service.get_limits_for_user(user_id)
        limit = limits.get(feature_key, 0)

        # Check and increment usage
        allowed, remaining = usage_service.check_and_increment(
            actor_id=user_id,
            feature_key=feature_key,
            limit=limit,
            is_anonymous=False
        )

        if allowed:
            return jsonify({
                "success": True,
                "allowed": True,
                "remaining": remaining,
                "limit": limit,
                "message": "Usage updated successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "allowed": False,
                "remaining": 0,
                "limit": limit,
                "message": f"Daily limit reached for {feature_key}"
            }), 403

    except Exception as e:
        logger.error(f"Error updating usage: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to update usage"
        }), 500


@subscription_bp.route('/reset', methods=['POST'])
@jwt_required()
def reset_usage():
    """
    Internal endpoint to reset daily usage for testing
    Should be protected in production

    Request Body:
        {
            "feature_key": "welth-market-regime" | "welth-ai-assistant" | "backtest-beta" | "all"
        }

    Returns:
        200: Usage reset
        400: Invalid request
        500: Server error
    """
    try:
        user_id = get_jwt_identity()
        data = request.json

        if not data or 'feature_key' not in data:
            return jsonify({
                "success": False,
                "error": "feature_key is required"
            }), 400

        feature_key = data['feature_key']

        if feature_key == 'all':
            # Reset all features
            usage_service.delete_all_usage(user_id, is_anonymous=False)
            return jsonify({
                "success": True,
                "message": "All usage reset successfully"
            }), 200
        else:
            # Reset specific feature
            valid_features = ['welth-market-regime', 'welth-ai-assistant', 'backtest-beta']
            if feature_key not in valid_features:
                return jsonify({
                    "success": False,
                    "error": "Invalid feature key"
                }), 400

            usage_service.reset_usage(user_id, feature_key, is_anonymous=False)
            return jsonify({
                "success": True,
                "message": f"Usage reset for {feature_key}"
            }), 200

    except Exception as e:
        logger.error(f"Error resetting usage: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to reset usage"
        }), 500


@subscription_bp.route('/create-test-transaction', methods=['POST'])
@jwt_required()
def create_test_transaction():
    """
    TEST ENDPOINT: Create a test transaction for testing payment history
    This should be removed or protected in production

    Request Body:
        {
            "plan": "PRO",
            "duration": "monthly",
            "amount": 499
        }

    Returns:
        200: Test transaction created
        400: Invalid request
        500: Server error
    """
    try:
        user_id = get_jwt_identity()
        data = request.json or {}

        plan = data.get('plan', 'PRO')
        duration = data.get('duration', 'monthly')
        amount = data.get('amount', 499)

        # Create test transaction
        import uuid
        test_transaction = {
            "user_id": ObjectId(user_id),
            "plan_id": plan,
            "plan_duration": duration,
            "amount": amount,
            "currency": "INR",
            "status": "SUCCESS",  # Mark as successful for testing
            "gateway": "CASHFREE",
            "gateway_order_id": f"TEST_ORDER_{uuid.uuid4().hex[:8].upper()}",
            "payment_method": "TEST_CARD",
            "gateway_payment_id": f"TEST_PAY_{uuid.uuid4().hex[:8].upper()}",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "payment_time": datetime.utcnow().isoformat()
        }

        result = transactions_collection.insert_one(test_transaction)

        logger.info(f"Created test transaction for user {user_id}")

        return jsonify({
            "success": True,
            "message": "Test transaction created successfully",
            "transaction_id": str(result.inserted_id),
            "order_id": test_transaction['gateway_order_id']
        }), 200

    except Exception as e:
        logger.error(f"Error creating test transaction: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to create test transaction"
        }), 500
