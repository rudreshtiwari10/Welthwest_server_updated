"""
Admin Routes - Comprehensive admin dashboard API endpoints
Provides full administrative control over users, subscriptions, payments, content, and analytics
"""
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from bson import ObjectId
from pymongo import DESCENDING, ASCENDING
from middleware.feature_limit import admin_required
from services.user_service import UserService
from services.subscription_service import SubscriptionService
from config import get_config

logger = logging.getLogger(__name__)

# Initialize Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# Initialize services
user_service = UserService()
subscription_service = SubscriptionService()
config = get_config()

# Get MongoDB connection
from pymongo import MongoClient
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]


# Helper function to convert all ObjectIds to strings recursively
def serialize_mongodb_doc(doc):
    """
    Recursively convert all ObjectId instances to strings in a MongoDB document
    Also handles datetime objects
    """
    if doc is None:
        return None

    if isinstance(doc, ObjectId):
        return str(doc)

    if isinstance(doc, datetime):
        return doc.isoformat()

    if isinstance(doc, dict):
        return {key: serialize_mongodb_doc(value) for key, value in doc.items()}

    if isinstance(doc, list):
        return [serialize_mongodb_doc(item) for item in doc]

    return doc


# ==========================
# AUDIT LOGGING UTILITIES
# ==========================

def log_admin_action(admin_id, action, resource_type, resource_id, before_state=None, after_state=None, metadata=None):
    """Log all admin actions for audit trail"""
    try:
        # Get admin user details
        admin = db.users.find_one({'_id': ObjectId(admin_id)})
        admin_username = admin.get('username', admin.get('email', 'Unknown')) if admin else 'Unknown'
        admin_email = admin.get('email', '') if admin else ''

        # Legacy audit_logs collection (keep for backwards compatibility)
        audit_log = {
            "admin_id": admin_id,
            "action": action,  # create, update, delete, upgrade, downgrade, block, etc.
            "resource_type": resource_type,  # user, subscription, payment, content, etc.
            "resource_id": resource_id,
            "before_state": before_state,
            "after_state": after_state,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow(),
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get('User-Agent')
        }
        db.audit_logs.insert_one(audit_log)

        # NEW: Also log to activity_logs collection for the Activity Logs page
        from models.activity_log import ActivityLog
        activity_logger = ActivityLog(db)
        activity_logger.log({
            'adminId': str(admin_id),
            'adminUsername': admin_username,
            'adminEmail': admin_email,
            'action': action,
            'module': resource_type,  # maps to module (users, subscriptions, etc.)
            'targetType': resource_type,
            'targetId': str(resource_id),
            'description': f'{action.capitalize()} {resource_type} {resource_id}',
            'beforeState': before_state,
            'afterState': after_state,
            'ipAddress': request.remote_addr,
            'userAgent': request.headers.get('User-Agent'),
            'severity': 'warning' if action in ['delete', 'block'] else 'info',
            'metadata': metadata or {}
        })

        logger.info(f"Admin action logged: {action} on {resource_type} {resource_id} by admin {admin_id}")
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")


# ==========================
# DASHBOARD HOME / OVERVIEW
# ==========================

@admin_bp.route('/dashboard/overview', methods=['GET'])
@admin_required
def get_dashboard_overview():
    """
    Get dashboard overview with key metrics
    Returns: total users, active premium users, revenue, pending payments, recent signups, etc.
    """
    try:
        admin_id = get_jwt_identity()

        # Total Users
        total_users = db.users.count_documents({})

        # Active Premium Users (subscription.is_active = true and plan != FREE)
        active_premium_users = db.users.count_documents({
            'subscription.is_active': True,
            'subscription.plan': {'$ne': 'FREE'}
        })

        # Users by Plan
        pipeline = [
            {'$group': {
                '_id': '$subscription.plan',
                'count': {'$sum': 1}
            }}
        ]
        # Convert None to 'FREE' to avoid JSON serialization issues
        users_by_plan = {(item['_id'] or 'FREE'): item['count'] for item in db.users.aggregate(pipeline)}

        # Recent Signups (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_signups = db.users.count_documents({
            'created_at': {'$gte': seven_days_ago}
        })

        # Monthly Revenue (successful transactions in current month)
        first_day_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_revenue_pipeline = [
            {
                '$match': {
                    'status': 'SUCCESS',
                    'completed_at': {'$gte': first_day_of_month}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'total': {'$sum': '$amount'}
                }
            }
        ]
        monthly_revenue_result = list(db.transactions.aggregate(monthly_revenue_pipeline))
        monthly_revenue = monthly_revenue_result[0]['total'] if monthly_revenue_result else 0

        # Pending Payments
        pending_payments = db.transactions.count_documents({'status': 'PENDING'})

        # Subscription Churn (cancelled in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        churn_count = db.users.count_documents({
            'subscription.cancelled_at': {'$gte': thirty_days_ago}
        })

        # Total Revenue (all time)
        total_revenue_pipeline = [
            {'$match': {'status': 'SUCCESS'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]
        total_revenue_result = list(db.transactions.aggregate(total_revenue_pipeline))
        total_revenue = total_revenue_result[0]['total'] if total_revenue_result else 0

        # Recent Activity (last 10 users who joined)
        recent_users = list(db.users.find(
            {},
            {'first_name': 1, 'last_name': 1, 'email': 1, 'created_at': 1, 'subscription.plan': 1}
        ).sort('created_at', DESCENDING).limit(10))

        overview = {
            'total_users': total_users,
            'active_premium_users': active_premium_users,
            'users_by_plan': users_by_plan,
            'recent_signups_7d': recent_signups,
            'monthly_revenue': monthly_revenue,
            'total_revenue': total_revenue,
            'pending_payments': pending_payments,
            'subscription_churn_30d': churn_count,
            'recent_users': recent_users,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        overview = serialize_mongodb_doc(overview)

        log_admin_action(admin_id, 'view', 'dashboard_overview', 'overview', metadata={'metrics_count': len(overview)})

        return jsonify(overview), 200

    except Exception as e:
        logger.error(f"Error fetching dashboard overview: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch dashboard overview"}), 500


# ==========================
# USER MANAGEMENT
# ==========================

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """
    List all users with pagination, search, and filters
    Query params: page, limit, search, plan, status, sort_by, sort_order
    """
    try:
        admin_id = get_jwt_identity()

        # Pagination
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit

        # Search query
        search = request.args.get('search', '').strip()

        # Filters
        plan_filter = request.args.get('plan')  # FREE, STARTER, PRO, ADVANCED, ENTERPRISE
        status_filter = request.args.get('status')  # active, inactive, blocked
        role_filter = request.args.get('role')  # user, admin

        # Sort
        sort_by = request.args.get('sort_by', 'created_at')  # created_at, email, subscription.plan
        sort_order = request.args.get('sort_order', 'desc')  # asc, desc

        # Build query
        query = {}

        if search:
            query['$or'] = [
                {'email': {'$regex': search, '$options': 'i'}},
                {'first_name': {'$regex': search, '$options': 'i'}},
                {'last_name': {'$regex': search, '$options': 'i'}},
                {'username': {'$regex': search, '$options': 'i'}}
            ]

        if plan_filter:
            query['subscription.plan'] = plan_filter

        if status_filter == 'active':
            query['subscription.is_active'] = True
        elif status_filter == 'inactive':
            query['subscription.is_active'] = False

        if role_filter:
            query['role'] = role_filter

        # Count total matching documents
        total = db.users.count_documents(query)

        # Execute query with pagination
        sort_direction = DESCENDING if sort_order == 'desc' else ASCENDING
        users = list(db.users.find(query).sort(sort_by, sort_direction).skip(skip).limit(limit))

        # Clean up sensitive data
        for user in users:
            user.pop('password', None)  # Never send password hash

        # Serialize all MongoDB documents to JSON-safe format
        response = serialize_mongodb_doc({
            'users': users,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        })

        log_admin_action(admin_id, 'list', 'users', 'all', metadata={'count': len(users), 'filters': query})

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error listing users: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch users"}), 500


@admin_bp.route('/users/<user_id>', methods=['GET'])
@admin_required
def get_user_details(user_id):
    """
    Get detailed information about a specific user
    Includes: profile, subscription, usage stats, purchase history, activity timeline
    """
    try:
        admin_id = get_jwt_identity()

        # Get user
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Remove password
        user.pop('password', None)

        # Get purchase history (transactions)
        transactions = list(db.transactions.find({'user_id': ObjectId(user_id)}).sort('created_at', DESCENDING).limit(50))

        # Get saved backtests count
        backtests_count = db.backtests.count_documents({'user_id': user_id})

        # Get saved AI analyses count
        ai_analyses_count = db.ai_analyses.count_documents({'user_id': user_id})

        # Get chat history count
        chat_history_count = db.chat_history.count_documents({'user_id': user_id})

        # Get usage logs (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        usage_logs = list(db.usage_logs.find({
            'actor_id': user_id,
            'created_at': {'$gte': thirty_days_ago}
        }).sort('created_at', DESCENDING).limit(100))

        # Build activity timeline
        activity_timeline = {
            'backtests': backtests_count,
            'ai_analyses': ai_analyses_count,
            'chats': chat_history_count,
            'recent_usage': usage_logs
        }

        # Serialize all MongoDB documents to JSON-safe format
        response = serialize_mongodb_doc({
            'user': user,
            'transactions': transactions,
            'activity': activity_timeline,
            'last_fetched': datetime.utcnow()
        })

        log_admin_action(admin_id, 'view', 'user', user_id)

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error fetching user details: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch user details"}), 500


@admin_bp.route('/users/<user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """
    Update user information
    Allowed fields: first_name, last_name, email, role, billing_address, etc.
    """
    try:
        admin_id = get_jwt_identity()
        data = request.get_json()

        # Get current user state for audit log
        user_before = db.users.find_one({'_id': ObjectId(user_id)})
        if not user_before:
            return jsonify({"error": "User not found"}), 404

        # Define allowed fields for update
        allowed_fields = ['first_name', 'last_name', 'email', 'occupation', 'bio', 'billing_address', 'role']

        # Build update object
        update_data = {}
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]

        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        # Add update timestamp
        update_data['updated_at'] = datetime.utcnow()

        # Update user
        result = db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        )

        if result.modified_count == 0:
            return jsonify({"error": "No changes made"}), 400

        # Get updated user
        user_after = db.users.find_one({'_id': ObjectId(user_id)})
        user_after.pop('password', None)

        # Serialize all MongoDB objects
        user_after = serialize_mongodb_doc(user_after)

        # Log admin action
        log_admin_action(
            admin_id,
            'update',
            'user',
            user_id,
            before_state={k: user_before.get(k) for k in update_data.keys()},
            after_state=update_data
        )

        return jsonify({
            "message": "User updated successfully",
            "user": user_after
        }), 200

    except Exception as e:
        logger.error(f"Error updating user: {e}", exc_info=True)
        return jsonify({"error": "Failed to update user"}), 500


@admin_bp.route('/users/<user_id>/subscription', methods=['POST'])
@admin_required
def update_user_subscription(user_id):
    """
    Manually update/upgrade/downgrade user subscription
    Body: { "plan": "PRO", "duration": "monthly", "action": "upgrade" }
    """
    try:
        admin_id = get_jwt_identity()
        data = request.get_json()

        plan = data.get('plan')
        duration = data.get('duration', 'monthly')
        action = data.get('action', 'upgrade')  # upgrade, downgrade, extend, cancel

        if not plan:
            return jsonify({"error": "Plan is required"}), 400

        # Validate plan
        valid_plans = ['FREE', 'STARTER', 'PRO', 'ADVANCED', 'ENTERPRISE']
        if plan not in valid_plans:
            return jsonify({"error": f"Invalid plan. Must be one of: {', '.join(valid_plans)}"}), 400

        # Get user
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Get current subscription
        current_subscription = user.get('subscription', {})
        before_state = current_subscription.copy()

        # Calculate dates
        start_date = datetime.utcnow()
        if plan == 'FREE':
            expiry_date = None
            is_active = True
        else:
            # Calculate expiry based on duration
            if duration == 'weekly':
                expiry_date = start_date + timedelta(days=7)
            elif duration == 'monthly':
                expiry_date = start_date + timedelta(days=30)
            elif duration == 'annual':
                expiry_date = start_date + timedelta(days=365)
            else:
                return jsonify({"error": "Invalid duration"}), 400

            is_active = True

        # Prepare history entry
        history_entry = {
            'action': action,
            'from_plan': current_subscription.get('plan', 'FREE'),
            'to_plan': plan,
            'timestamp': datetime.utcnow(),
            'reason': f'Admin manual update by {admin_id}'
        }

        # Get existing history and append new entry
        existing_history = current_subscription.get('history', [])
        updated_history = existing_history + [history_entry]

        # Update subscription with history included
        new_subscription = {
            'plan': plan,
            'tier': plan,  # Legacy field
            'plan_duration': duration if plan != 'FREE' else None,
            'start_date': start_date,
            'expiry_date': expiry_date,
            'starts_at': start_date,  # Legacy field
            'expires_at': expiry_date,  # Legacy field
            'is_active': is_active,
            'updated_at': datetime.utcnow(),
            'usage': current_subscription.get('usage', {
                'daily': {
                    'backtest_count': 0,
                    'llm_query_count': 0,
                    'last_reset': datetime.utcnow()
                },
                'monthly': {
                    'backtest_count': 0,
                    'llm_query_count': 0,
                    'last_reset': datetime.utcnow()
                }
            }),
            'history': updated_history  # Include history in the subscription object
        }

        # Update user document - now we only use $set
        db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'subscription': new_subscription}}
        )

        # Log admin action
        log_admin_action(
            admin_id,
            action,
            'subscription',
            user_id,
            before_state=before_state,
            after_state=new_subscription,
            metadata={'admin_manual_update': True}
        )

        response = {
            "message": f"User subscription {action}d to {plan} successfully",
            "subscription": new_subscription
        }

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        response = serialize_mongodb_doc(response)

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error updating user subscription: {e}", exc_info=True)
        return jsonify({"error": "Failed to update subscription"}), 500


@admin_bp.route('/users/<user_id>/block', methods=['POST'])
@admin_required
def block_user(user_id):
    """
    Block or unblock a user
    Body: { "action": "block" | "unblock", "reason": "..." }
    """
    try:
        admin_id = get_jwt_identity()
        data = request.get_json()

        action = data.get('action')  # block or unblock
        reason = data.get('reason', 'No reason provided')

        if action not in ['block', 'unblock']:
            return jsonify({"error": "Action must be 'block' or 'unblock'"}), 400

        # Get user
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Update user status
        is_blocked = action == 'block'

        db.users.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'is_blocked': is_blocked,
                    'blocked_at': datetime.utcnow() if is_blocked else None,
                    'blocked_reason': reason if is_blocked else None,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        # Log admin action
        log_admin_action(
            admin_id,
            action,
            'user',
            user_id,
            before_state={'is_blocked': user.get('is_blocked', False)},
            after_state={'is_blocked': is_blocked, 'reason': reason}
        )

        return jsonify({
            "message": f"User {action}ed successfully",
            "user_id": user_id,
            "is_blocked": is_blocked
        }), 200

    except Exception as e:
        logger.error(f"Error blocking/unblocking user: {e}", exc_info=True)
        return jsonify({"error": f"Failed to {action} user"}), 500


@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """
    Delete a user account (soft delete by setting deleted flag)
    """
    try:
        admin_id = get_jwt_identity()

        # Get user
        user = db.users.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Soft delete - mark as deleted but keep data
        db.users.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'is_deleted': True,
                    'deleted_at': datetime.utcnow(),
                    'deleted_by': admin_id,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        # Log admin action
        log_admin_action(
            admin_id,
            'delete',
            'user',
            user_id,
            before_state={'is_deleted': False},
            after_state={'is_deleted': True}
        )

        return jsonify({
            "message": "User deleted successfully",
            "user_id": user_id
        }), 200

    except Exception as e:
        logger.error(f"Error deleting user: {e}", exc_info=True)
        return jsonify({"error": "Failed to delete user"}), 500


# ==========================
# SUBSCRIPTION ANALYTICS
# ==========================

@admin_bp.route('/subscriptions/analytics', methods=['GET'])
@admin_required
def get_subscription_analytics():
    """
    Get comprehensive subscription analytics
    """
    try:
        admin_id = get_jwt_identity()

        # Users by plan
        plan_pipeline = [
            {'$group': {
                '_id': '$subscription.plan',
                'count': {'$sum': 1}
            }}
        ]
        users_by_plan = {item['_id'] or 'FREE': item['count'] for item in db.users.aggregate(plan_pipeline)}

        # Active vs Inactive subscriptions
        active_subs = db.users.count_documents({'subscription.is_active': True})
        inactive_subs = db.users.count_documents({'subscription.is_active': False})

        # Recent upgrades (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        upgrades_pipeline = [
            {'$match': {
                'status': 'SUCCESS',
                'completed_at': {'$gte': thirty_days_ago}
            }},
            {'$group': {
                '_id': '$plan_id',
                'count': {'$sum': 1}
            }}
        ]
        # Convert None to 'UNKNOWN' to avoid JSON serialization issues
        recent_upgrades = {(item['_id'] or 'UNKNOWN'): item['count'] for item in db.transactions.aggregate(upgrades_pipeline)}

        # Churn rate (cancelled in last 30 days)
        churned_users = db.users.count_documents({
            'subscription.cancelled_at': {'$gte': thirty_days_ago}
        })

        # Revenue by plan (all time)
        revenue_pipeline = [
            {'$match': {'status': 'SUCCESS'}},
            {'$group': {
                '_id': '$plan_id',
                'total_revenue': {'$sum': '$amount'},
                'transaction_count': {'$sum': 1}
            }}
        ]
        # Convert None to 'UNKNOWN' to avoid JSON serialization issues
        revenue_by_plan = {(item['_id'] or 'UNKNOWN'): {
            'revenue': item['total_revenue'],
            'transactions': item['transaction_count']
        } for item in db.transactions.aggregate(revenue_pipeline)}

        # Subscription duration breakdown
        duration_pipeline = [
            {'$match': {'subscription.plan_duration': {'$ne': None}}},
            {'$group': {
                '_id': '$subscription.plan_duration',
                'count': {'$sum': 1}
            }}
        ]
        # Convert None to 'N/A' to avoid JSON serialization issues
        users_by_duration = {(item['_id'] or 'N/A'): item['count'] for item in db.users.aggregate(duration_pipeline)}

        analytics = {
            'users_by_plan': users_by_plan,
            'active_subscriptions': active_subs,
            'inactive_subscriptions': inactive_subs,
            'recent_upgrades_30d': recent_upgrades,
            'churned_users_30d': churned_users,
            'revenue_by_plan': revenue_by_plan,
            'users_by_duration': users_by_duration,
            'timestamp': datetime.utcnow().isoformat()
        }

        log_admin_action(admin_id, 'view', 'subscription_analytics', 'analytics')

        return jsonify(analytics), 200

    except Exception as e:
        logger.error(f"Error fetching subscription analytics: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch analytics"}), 500


# ==========================
# PAYMENT & TRANSACTION MANAGEMENT
# ==========================

@admin_bp.route('/transactions', methods=['GET'])
@admin_required
def list_transactions():
    """
    List all payment transactions with filters and pagination
    Query params: page, limit, status, user_id, plan_id, gateway
    """
    try:
        admin_id = get_jwt_identity()

        # Pagination
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        skip = (page - 1) * limit

        # Filters
        status = request.args.get('status')  # PENDING, SUCCESS, FAILED, CANCELLED
        user_id_filter = request.args.get('user_id')
        plan_filter = request.args.get('plan_id')
        gateway = request.args.get('gateway')  # CASHFREE, RAZORPAY

        # Build query
        query = {}
        if status:
            query['status'] = status
        if user_id_filter:
            query['user_id'] = ObjectId(user_id_filter)
        if plan_filter:
            query['plan_id'] = plan_filter
        if gateway:
            query['gateway'] = gateway

        # Count total
        total = db.transactions.count_documents(query)

        # Execute query
        transactions = list(db.transactions.find(query).sort('created_at', DESCENDING).skip(skip).limit(limit))

        response = {
            'transactions': transactions,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        response = serialize_mongodb_doc(response)

        log_admin_action(admin_id, 'list', 'transactions', 'all', metadata={'count': len(transactions), 'filters': query})

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error listing transactions: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch transactions"}), 500


@admin_bp.route('/transactions/<transaction_id>', methods=['GET'])
@admin_required
def get_transaction_details(transaction_id):
    """
    Get detailed information about a specific transaction
    """
    try:
        admin_id = get_jwt_identity()

        transaction = db.transactions.find_one({'_id': ObjectId(transaction_id)})
        if not transaction:
            return jsonify({"error": "Transaction not found"}), 404

        # Get associated user info
        user = db.users.find_one({'_id': ObjectId(transaction['user_id'])}, {'email': 1, 'first_name': 1, 'last_name': 1})
        if user:
            transaction['user_info'] = user

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        transaction = serialize_mongodb_doc(transaction)

        log_admin_action(admin_id, 'view', 'transaction', transaction_id)

        return jsonify(transaction), 200

    except Exception as e:
        logger.error(f"Error fetching transaction details: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch transaction"}), 500


@admin_bp.route('/transactions/<transaction_id>/refund', methods=['POST'])
@admin_required
def refund_transaction(transaction_id):
    """
    Issue a refund for a transaction
    Body: { "amount": 1000, "reason": "..." } (amount optional - defaults to full refund)
    """
    try:
        admin_id = get_jwt_identity()
        data = request.get_json()

        reason = data.get('reason', 'Admin refund')

        # Get transaction
        transaction = db.transactions.find_one({'_id': ObjectId(transaction_id)})
        if not transaction:
            return jsonify({"error": "Transaction not found"}), 404

        if transaction['status'] != 'SUCCESS':
            return jsonify({"error": "Can only refund successful transactions"}), 400

        # Determine refund amount
        refund_amount = data.get('amount', transaction['amount'])
        if refund_amount > transaction['amount']:
            return jsonify({"error": "Refund amount cannot exceed transaction amount"}), 400

        # Update transaction
        db.transactions.update_one(
            {'_id': ObjectId(transaction_id)},
            {
                '$set': {
                    'refund_status': 'REFUNDED',
                    'refund_amount': refund_amount,
                    'refund_reason': reason,
                    'refunded_at': datetime.utcnow(),
                    'refunded_by': admin_id,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        # Log admin action
        log_admin_action(
            admin_id,
            'refund',
            'transaction',
            transaction_id,
            before_state={'refund_status': None},
            after_state={'refund_status': 'REFUNDED', 'amount': refund_amount, 'reason': reason}
        )

        return jsonify({
            "message": "Refund processed successfully",
            "transaction_id": transaction_id,
            "refund_amount": refund_amount
        }), 200

    except Exception as e:
        logger.error(f"Error processing refund: {e}", exc_info=True)
        return jsonify({"error": "Failed to process refund"}), 500


# ==========================
# REPORTS & ANALYTICS
# ==========================

@admin_bp.route('/reports/revenue', methods=['GET'])
@admin_required
def get_revenue_report():
    """
    Get revenue analytics report
    Query params: start_date, end_date, group_by (day, week, month)
    """
    try:
        admin_id = get_jwt_identity()

        # Date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        group_by = request.args.get('group_by', 'day')  # day, week, month

        # Parse dates
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_date = datetime.utcnow() - timedelta(days=30)

        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_date = datetime.utcnow()

        # Build aggregation pipeline based on group_by
        if group_by == 'day':
            date_format = '%Y-%m-%d'
        elif group_by == 'week':
            date_format = '%Y-W%U'
        elif group_by == 'month':
            date_format = '%Y-%m'
        else:
            date_format = '%Y-%m-%d'

        pipeline = [
            {
                '$match': {
                    'status': 'SUCCESS',
                    'completed_at': {'$gte': start_date, '$lte': end_date}
                }
            },
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': date_format,
                            'date': '$completed_at'
                        }
                    },
                    'total_revenue': {'$sum': '$amount'},
                    'transaction_count': {'$sum': 1},
                    'unique_users': {'$addToSet': '$user_id'}
                }
            },
            {
                '$project': {
                    'date': '$_id',
                    'total_revenue': 1,
                    'transaction_count': 1,
                    'unique_users_count': {'$size': '$unique_users'}
                }
            },
            {'$sort': {'date': 1}}
        ]

        revenue_data = list(db.transactions.aggregate(pipeline))

        # Calculate summary
        total_revenue = sum(item['total_revenue'] for item in revenue_data)
        total_transactions = sum(item['transaction_count'] for item in revenue_data)

        report = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'group_by': group_by,
            'data': revenue_data,
            'summary': {
                'total_revenue': total_revenue,
                'total_transactions': total_transactions,
                'average_transaction_value': total_revenue / total_transactions if total_transactions > 0 else 0
            }
        }

        log_admin_action(admin_id, 'view', 'revenue_report', 'report', metadata={'date_range': f'{start_date} to {end_date}'})

        return jsonify(report), 200

    except Exception as e:
        logger.error(f"Error generating revenue report: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate report"}), 500


@admin_bp.route('/reports/usage', methods=['GET'])
@admin_required
def get_usage_report():
    """
    Get feature usage analytics report
    Query params: start_date, end_date, feature
    """
    try:
        admin_id = get_jwt_identity()

        # Date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        feature_filter = request.args.get('feature')

        # Parse dates
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start_date = datetime.utcnow() - timedelta(days=30)

        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end_date = datetime.utcnow()

        # Build query
        match_query = {
            'created_at': {'$gte': start_date, '$lte': end_date}
        }
        if feature_filter:
            match_query['feature'] = feature_filter

        # Usage by feature
        feature_pipeline = [
            {'$match': match_query},
            {'$group': {
                '_id': '$feature',
                'total_uses': {'$sum': 1},
                'unique_users': {'$addToSet': '$actor_id'},
                'anonymous_uses': {
                    '$sum': {'$cond': [{'$eq': ['$is_anonymous', True]}, 1, 0]}
                },
                'authenticated_uses': {
                    '$sum': {'$cond': [{'$eq': ['$is_anonymous', False]}, 1, 0]}
                }
            }},
            {'$project': {
                'feature': '$_id',
                'total_uses': 1,
                'unique_users_count': {'$size': '$unique_users'},
                'anonymous_uses': 1,
                'authenticated_uses': 1
            }}
        ]

        usage_by_feature = list(db.usage_logs.aggregate(feature_pipeline))

        # Total usage
        total_uses = sum(item['total_uses'] for item in usage_by_feature)

        report = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'usage_by_feature': usage_by_feature,
            'summary': {
                'total_uses': total_uses,
                'features_count': len(usage_by_feature)
            }
        }

        log_admin_action(admin_id, 'view', 'usage_report', 'report', metadata={'date_range': f'{start_date} to {end_date}'})

        return jsonify(report), 200

    except Exception as e:
        logger.error(f"Error generating usage report: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate report"}), 500


# ==========================
# AUDIT LOGS
# ==========================

@admin_bp.route('/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    """
    Get audit logs of admin actions
    Query params: page, limit, admin_id, action, resource_type, start_date, end_date
    """
    try:
        admin_id = get_jwt_identity()

        # Pagination
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        skip = (page - 1) * limit

        # Filters
        admin_filter = request.args.get('admin_id')
        action_filter = request.args.get('action')
        resource_type_filter = request.args.get('resource_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Build query
        query = {}
        if admin_filter:
            query['admin_id'] = admin_filter
        if action_filter:
            query['action'] = action_filter
        if resource_type_filter:
            query['resource_type'] = resource_type_filter

        if start_date or end_date:
            query['timestamp'] = {}
            if start_date:
                query['timestamp']['$gte'] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if end_date:
                query['timestamp']['$lte'] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        # Count total
        total = db.audit_logs.count_documents(query)

        # Execute query
        logs = list(db.audit_logs.find(query).sort('timestamp', DESCENDING).skip(skip).limit(limit))

        response = {
            'logs': logs,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        response = serialize_mongodb_doc(response)

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch audit logs"}), 500


# ==========================
# CONTENT MANAGEMENT
# ==========================

@admin_bp.route('/feedback', methods=['GET'])
@admin_required
def get_all_feedback():
    """
    Get all user feedback submissions
    Query params: page, limit, category, rating
    """
    try:
        admin_id = get_jwt_identity()

        # Pagination
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        skip = (page - 1) * limit

        # Filters
        category = request.args.get('category')
        rating = request.args.get('rating')

        # Build query
        query = {}
        if category:
            query['category'] = category
        if rating:
            query['rating'] = int(rating)

        # Count total
        total = db.feedback.count_documents(query)

        # Execute query
        feedback_list = list(db.feedback.find(query).sort('created_at', DESCENDING).skip(skip).limit(limit))

        response = {
            'feedback': feedback_list,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        response = serialize_mongodb_doc(response)

        log_admin_action(admin_id, 'list', 'feedback', 'all', metadata={'count': len(feedback_list)})

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error fetching feedback: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch feedback"}), 500


# ==========================
# SYSTEM SETTINGS
# ==========================

@admin_bp.route('/settings', methods=['GET'])
@admin_required
def get_system_settings():
    """
    Get current system settings and configuration
    """
    try:
        admin_id = get_jwt_identity()

        # Get plans
        plans = list(db.plans.find({}))

        # Get system stats
        stats = {
            'total_users': db.users.count_documents({}),
            'total_transactions': db.transactions.count_documents({}),
            'total_backtests': db.backtests.count_documents({}),
            'total_ai_analyses': db.ai_analyses.count_documents({}),
            'total_chats': db.chat_history.count_documents({}),
            'total_feedback': db.feedback.count_documents({})
        }

        settings = {
            'plans': plans,
            'system_stats': stats,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Serialize all MongoDB objects (ObjectIds, datetimes)
        settings = serialize_mongodb_doc(settings)

        log_admin_action(admin_id, 'view', 'system_settings', 'settings')

        return jsonify(settings), 200

    except Exception as e:
        logger.error(f"Error fetching system settings: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch settings"}), 500


@admin_bp.route('/settings/plans/<plan_id>', methods=['PUT'])
@admin_required
def update_plan(plan_id):
    """
    Update plan pricing or limits
    Body: { "prices": {...}, "limits": {...} }
    """
    try:
        admin_id = get_jwt_identity()
        data = request.get_json()

        # Get current plan
        plan_before = db.plans.find_one({'_id': plan_id})
        if not plan_before:
            return jsonify({"error": "Plan not found"}), 404

        # Build update
        update_data = {}
        if 'prices' in data:
            update_data['prices'] = data['prices']
        if 'limits' in data:
            update_data['limits'] = data['limits']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'features' in data:
            update_data['features'] = data['features']

        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        update_data['updated_at'] = datetime.utcnow()

        # Update plan
        db.plans.update_one(
            {'_id': plan_id},
            {'$set': update_data}
        )

        # Get updated plan
        plan_after = db.plans.find_one({'_id': plan_id})
        plan_after['_id'] = str(plan_after['_id'])

        # Log admin action
        log_admin_action(
            admin_id,
            'update',
            'plan',
            plan_id,
            before_state={k: plan_before.get(k) for k in update_data.keys()},
            after_state=update_data
        )

        return jsonify({
            "message": "Plan updated successfully",
            "plan": plan_after
        }), 200

    except Exception as e:
        logger.error(f"Error updating plan: {e}", exc_info=True)
        return jsonify({"error": "Failed to update plan"}), 500


# Export blueprint
__all__ = ['admin_bp']
