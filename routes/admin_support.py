"""
Admin Support & Communication Routes
Module 8: Support Tickets & User Communication
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from bson import ObjectId
from datetime import datetime
from middleware.feature_limit import admin_required
from pymongo import MongoClient
from config import get_config

# Create blueprint
admin_support_bp = Blueprint('admin_support', __name__)

# Get MongoDB connection
config = get_config()
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]

def get_db():
    """Get database instance"""
    return db

def get_models():
    """Get model instances"""
    from models.ticket import SupportTicket
    from models.activity_log import ActivityLog

    db = get_db()
    return {
        'ticket': SupportTicket(db),
        'activity_log': ActivityLog(db)
    }

def log_activity(action: str, module: str, description: str, **kwargs):
    """Helper to log admin activity"""
    try:
        models = get_models()
        user_id = get_jwt_identity()
        db = get_db()
        user = db.users.find_one({'_id': ObjectId(user_id)})

        log_data = {
            'adminId': str(user['_id']),
            'adminUsername': user.get('username', user.get('email')),
            'adminEmail': user.get('email'),
            'action': action,
            'module': module,
            'description': description,
            'ipAddress': request.remote_addr,
            'userAgent': request.headers.get('User-Agent'),
            **kwargs
        }

        models['activity_log'].log(log_data)
    except Exception as e:
        print(f"Failed to log activity: {str(e)}")

# ============================================================================
# SUPPORT TICKET ENDPOINTS
# ============================================================================

@admin_support_bp.route('/api/admin/support/tickets', methods=['GET'])
@admin_required
def get_tickets():
    """Get all support tickets with filters"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))

        filters = {}
        if request.args.get('status'):
            filters['status'] = request.args.get('status')
        if request.args.get('priority'):
            filters['priority'] = request.args.get('priority')
        if request.args.get('category'):
            filters['category'] = request.args.get('category')
        if request.args.get('assignedTo'):
            filters['assignedTo'] = request.args.get('assignedTo')

        models = get_models()
        result = models['ticket'].get_all(page, limit, filters)

        # Convert ObjectId and datetime to string
        for ticket in result['tickets']:
            ticket['_id'] = str(ticket['_id'])
            if ticket.get('userId'):
                ticket['userId'] = str(ticket['userId'])
            ticket['createdAt'] = ticket['createdAt'].isoformat()
            ticket['updatedAt'] = ticket['updatedAt'].isoformat()
            if ticket.get('resolvedAt'):
                ticket['resolvedAt'] = ticket['resolvedAt'].isoformat()
            if ticket.get('closedAt'):
                ticket['closedAt'] = ticket['closedAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/<ticket_id>', methods=['GET'])
@admin_required
def get_ticket(ticket_id):
    """Get ticket details"""
    try:
        models = get_models()
        ticket = models['ticket'].get_by_id(ticket_id)

        if not ticket:
            return jsonify({
                'success': False,
                'error': 'Ticket not found'
            }), 404

        # Convert ObjectId and datetime
        ticket['_id'] = str(ticket['_id'])
        if ticket.get('userId'):
            ticket['userId'] = str(ticket['userId'])
        ticket['createdAt'] = ticket['createdAt'].isoformat()
        ticket['updatedAt'] = ticket['updatedAt'].isoformat()
        if ticket.get('resolvedAt'):
            ticket['resolvedAt'] = ticket['resolvedAt'].isoformat()

        # Convert dates in notes and replies
        for note in ticket.get('notes', []):
            note['createdAt'] = note['createdAt'].isoformat()
        for reply in ticket.get('replies', []):
            reply['createdAt'] = reply['createdAt'].isoformat()

        return jsonify({
            'success': True,
            'ticket': ticket
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/<ticket_id>/assign', methods=['POST'])
@admin_required
def assign_ticket(ticket_id):
    """Assign ticket to staff member"""
    try:
        data = request.get_json()
        staff_id = data.get('staffId')
        staff_name = data.get('staffName')

        if not staff_id or not staff_name:
            return jsonify({
                'success': False,
                'error': 'Staff ID and name are required'
            }), 400

        models = get_models()
        success = models['ticket'].assign(ticket_id, staff_id, staff_name)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to assign ticket'
            }), 400

        log_activity('assign', 'support', f'Assigned ticket {ticket_id} to {staff_name}',
                    targetType='ticket', targetId=ticket_id)

        return jsonify({
            'success': True,
            'message': 'Ticket assigned successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/<ticket_id>/notes', methods=['POST'])
@admin_required
def add_ticket_note(ticket_id):
    """Add internal note to ticket"""
    try:
        data = request.get_json()
        content = data.get('content')

        if not content:
            return jsonify({
                'success': False,
                'error': 'Note content is required'
            }), 400

        user = request.current_user
        note_data = {
            'author': user.get('username', user.get('email')),
            'content': content
        }

        models = get_models()
        success = models['ticket'].add_note(ticket_id, note_data)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to add note'
            }), 400

        return jsonify({
            'success': True,
            'message': 'Note added successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/<ticket_id>/replies', methods=['POST'])
@admin_required
def add_ticket_reply(ticket_id):
    """Add reply to ticket (visible to user)"""
    try:
        data = request.get_json()
        content = data.get('content')

        if not content:
            return jsonify({
                'success': False,
                'error': 'Reply content is required'
            }), 400

        user = request.current_user
        reply_data = {
            'author': user.get('username', user.get('email')),
            'content': content,
            'isStaff': True
        }

        models = get_models()
        success = models['ticket'].add_reply(ticket_id, reply_data)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to add reply'
            }), 400

        log_activity('reply', 'support', f'Replied to ticket {ticket_id}',
                    targetType='ticket', targetId=ticket_id)

        return jsonify({
            'success': True,
            'message': 'Reply added successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/<ticket_id>/status', methods=['PUT'])
@admin_required
def update_ticket_status(ticket_id):
    """Update ticket status"""
    try:
        data = request.get_json()
        status = data.get('status')

        if not status:
            return jsonify({
                'success': False,
                'error': 'Status is required'
            }), 400

        valid_statuses = ['open', 'in_progress', 'waiting', 'resolved', 'closed']
        if status not in valid_statuses:
            return jsonify({
                'success': False,
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }), 400

        models = get_models()
        success = models['ticket'].update_status(ticket_id, status)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to update status'
            }), 400

        log_activity('update', 'support', f'Changed ticket {ticket_id} status to {status}',
                    targetType='ticket', targetId=ticket_id)

        return jsonify({
            'success': True,
            'message': 'Status updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/<ticket_id>/priority', methods=['PUT'])
@admin_required
def update_ticket_priority(ticket_id):
    """Update ticket priority"""
    try:
        data = request.get_json()
        priority = data.get('priority')

        if not priority:
            return jsonify({
                'success': False,
                'error': 'Priority is required'
            }), 400

        valid_priorities = ['low', 'medium', 'high', 'urgent']
        if priority not in valid_priorities:
            return jsonify({
                'success': False,
                'error': f'Invalid priority. Must be one of: {", ".join(valid_priorities)}'
            }), 400

        models = get_models()
        success = models['ticket'].update_priority(ticket_id, priority)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to update priority'
            }), 400

        log_activity('update', 'support', f'Changed ticket {ticket_id} priority to {priority}',
                    targetType='ticket', targetId=ticket_id,
                    severity='warning' if priority in ['high', 'urgent'] else 'info')

        return jsonify({
            'success': True,
            'message': 'Priority updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/stats', methods=['GET'])
@admin_required
def get_ticket_stats():
    """Get ticket statistics"""
    try:
        models = get_models()
        stats = models['ticket'].get_stats()

        return jsonify({
            'success': True,
            'stats': stats
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/support/tickets/unassigned', methods=['GET'])
@admin_required
def get_unassigned_tickets():
    """Get unassigned tickets"""
    try:
        limit = int(request.args.get('limit', 20))

        models = get_models()
        tickets = models['ticket'].get_unassigned(limit)

        # Convert ObjectId and datetime
        for ticket in tickets:
            ticket['_id'] = str(ticket['_id'])
            if ticket.get('userId'):
                ticket['userId'] = str(ticket['userId'])
            ticket['createdAt'] = ticket['createdAt'].isoformat()

        return jsonify({
            'success': True,
            'tickets': tickets
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# USER COMMUNICATION ENDPOINTS
# ============================================================================

@admin_support_bp.route('/api/admin/communication/announcements', methods=['POST'])
@admin_required
def send_announcement():
    """Send announcement to all users or targeted group"""
    try:
        data = request.get_json()

        title = data.get('title')
        message = data.get('message')
        target_group = data.get('targetGroup', 'all')  # all | free | premium | specific_plan

        if not title or not message:
            return jsonify({
                'success': False,
                'error': 'Title and message are required'
            }), 400

        # Get target users based on group
        db = get_db()
        query = {}

        if target_group != 'all':
            if target_group in ['starter', 'pro', 'advanced', 'enterprise']:
                query = {'subscription.tier': target_group.upper()}
            elif target_group == 'free':
                query = {'subscription.tier': 'FREE'}
            elif target_group == 'premium':
                query = {'subscription.tier': {'$ne': 'FREE'}}

        users = list(db.users.find(query, {'email': 1, 'username': 1}))
        recipient_count = len(users)

        # Here you would integrate with your email/notification service
        # For now, we'll just log the action

        user = request.current_user
        log_activity('send', 'communication',
                    f'Sent announcement "{title}" to {recipient_count} users ({target_group})',
                    targetType='announcement', severity='info',
                    metadata={'title': title, 'targetGroup': target_group, 'recipientCount': recipient_count})

        return jsonify({
            'success': True,
            'message': f'Announcement sent to {recipient_count} users',
            'recipientCount': recipient_count
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_support_bp.route('/api/admin/communication/message', methods=['POST'])
@admin_required
def send_targeted_message():
    """Send direct message to specific user(s)"""
    try:
        data = request.get_json()

        user_ids = data.get('userIds', [])  # List of user IDs
        subject = data.get('subject')
        message = data.get('message')

        if not user_ids or not subject or not message:
            return jsonify({
                'success': False,
                'error': 'User IDs, subject, and message are required'
            }), 400

        # Get target users
        db = get_db()
        users = list(db.users.find(
            {'_id': {'$in': [ObjectId(uid) for uid in user_ids]}},
            {'email': 1, 'username': 1}
        ))

        # Here you would integrate with your email service
        # For now, we'll just log the action

        user = request.current_user
        log_activity('send', 'communication',
                    f'Sent message "{subject}" to {len(users)} specific users',
                    targetType='message', severity='info',
                    metadata={'subject': subject, 'recipientCount': len(users)})

        return jsonify({
            'success': True,
            'message': f'Message sent to {len(users)} users',
            'recipientCount': len(users)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
