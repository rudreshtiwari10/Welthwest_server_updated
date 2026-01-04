"""
Admin Support Routes
Allow admins to create and manage internal admin support tickets
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient
from config import get_config
from middleware.feature_limit import admin_required

# Create blueprint
support_bp = Blueprint('support', __name__)

# Get MongoDB connection
config = get_config()
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]

def get_models():
    """Get model instances"""
    from models.ticket import SupportTicket
    from models.activity_log import ActivityLog
    return {
        'ticket': SupportTicket(db),
        'activity_log': ActivityLog(db)
    }

# ============================================================================
# ADMIN TICKET ENDPOINTS (Admin-to-Admin Support)
# ============================================================================

@support_bp.route('/api/support/tickets', methods=['POST'])
@admin_required
def create_ticket():
    """Create a new internal admin support ticket (admin asking other admins for help)"""
    try:
        admin_id = get_jwt_identity()
        data = request.get_json()

        subject = data.get('subject')
        message = data.get('message')
        category = data.get('category', 'other')
        priority = data.get('priority', 'medium')

        if not subject or not message:
            return jsonify({
                'success': False,
                'error': 'Subject and message are required'
            }), 400

        # Get admin details
        admin = db.users.find_one({'_id': ObjectId(admin_id)})
        if not admin:
            return jsonify({
                'success': False,
                'error': 'Admin not found'
            }), 404

        # Create ticket data
        ticket_data = {
            'userId': admin_id,
            'userEmail': admin.get('email'),
            'userName': admin.get('username', admin.get('email')),
            'subject': subject,
            'description': message,  # Ticket model expects 'description' field
            'category': category,
            'priority': priority
        }

        models = get_models()
        ticket = models['ticket'].create(ticket_data)

        # Log activity
        models['activity_log'].log({
            'adminId': str(admin_id),
            'adminUsername': admin.get('username', admin.get('email')),
            'adminEmail': admin.get('email'),
            'action': 'create',
            'module': 'support',
            'targetType': 'ticket',
            'targetId': str(ticket['_id']),
            'description': f'Created support ticket: {subject}',
            'ipAddress': request.remote_addr,
            'userAgent': request.headers.get('User-Agent'),
            'severity': 'info'
        })

        # Convert ObjectId to string for JSON response
        ticket['_id'] = str(ticket['_id'])
        ticket['userId'] = str(ticket['userId'])
        ticket['createdAt'] = ticket['createdAt'].isoformat()
        ticket['updatedAt'] = ticket['updatedAt'].isoformat()

        return jsonify({
            'success': True,
            'message': 'Internal admin ticket created successfully',
            'ticket': ticket
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@support_bp.route('/api/support/categories', methods=['GET'])
@admin_required
def get_ticket_categories():
    """Get available ticket categories (public endpoint)"""
    return jsonify({
        'success': True,
        'categories': [
            {'value': 'technical', 'label': 'Technical Issue'},
            {'value': 'billing', 'label': 'Billing & Payments'},
            {'value': 'account', 'label': 'Account & Login'},
            {'value': 'feature', 'label': 'Feature Request'},
            {'value': 'bug', 'label': 'Bug Report'},
            {'value': 'other', 'label': 'Other'}
        ]
    }), 200
