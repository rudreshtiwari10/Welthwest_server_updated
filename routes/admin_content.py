"""
Admin Content Management Routes
Module 4: Content Management (Blogs, Alerts, Comments, Categories)
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from bson import ObjectId
from datetime import datetime
import json
from middleware.feature_limit import admin_required
from pymongo import MongoClient
from config import get_config

# Create blueprint
admin_content_bp = Blueprint('admin_content', __name__)

# Get MongoDB connection
config = get_config()
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]

def get_db():
    """Get database instance"""
    return db

def get_models():
    """Get model instances"""
    from models.blog import Blog
    from models.alert import Alert
    from models.comment import Comment
    from models.category import Category
    from models.activity_log import ActivityLog

    db = get_db()
    return {
        'blog': Blog(db),
        'alert': Alert(db),
        'comment': Comment(db),
        'category': Category(db),
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
# BLOG MANAGEMENT ENDPOINTS
# ============================================================================

@admin_content_bp.route('/api/admin/content/blogs/analytics/<blog_id>', methods=['GET'])
@admin_required
def get_blog_analytics(blog_id):
    """Get blog analytics"""
    try:
        models = get_models()
        analytics = models['blog'].get_analytics(blog_id)

        if not analytics:
            return jsonify({
                'success': False,
                'error': 'Blog not found'
            }), 404

        return jsonify({
            'success': True,
            'analytics': analytics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/blogs/<blog_id>/submit', methods=['POST'])
@admin_required
def submit_blog_for_approval(blog_id):
    """Submit blog for approval"""
    try:
        models = get_models()
        success = models['blog'].submit_for_approval(blog_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to submit blog'
            }), 400

        log_activity('submit', 'content', f'Submitted blog {blog_id} for approval',
                    targetType='blog', targetId=blog_id)

        return jsonify({
            'success': True,
            'message': 'Blog submitted for approval'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/blogs/<blog_id>/approve', methods=['POST'])
@admin_required
def approve_blog(blog_id):
    """Approve a blog post"""
    try:
        data = request.get_json() or {}
        comment = data.get('comment', '')
        user = request.current_user

        models = get_models()
        success = models['blog'].approve_blog(blog_id, user.get('username'), comment)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to approve blog'
            }), 400

        log_activity('approve', 'content', f'Approved blog {blog_id}',
                    targetType='blog', targetId=blog_id, severity='info')

        return jsonify({
            'success': True,
            'message': 'Blog approved successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/blogs/<blog_id>/reject', methods=['POST'])
@admin_required
def reject_blog(blog_id):
    """Reject a blog post"""
    try:
        data = request.get_json()
        comment = data.get('comment', '')

        if not comment:
            return jsonify({
                'success': False,
                'error': 'Rejection comment is required'
            }), 400

        user = request.current_user
        models = get_models()
        success = models['blog'].reject_blog(blog_id, user.get('username'), comment)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to reject blog'
            }), 400

        log_activity('reject', 'content', f'Rejected blog {blog_id}: {comment}',
                    targetType='blog', targetId=blog_id, severity='warning')

        return jsonify({
            'success': True,
            'message': 'Blog rejected'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/blogs/<blog_id>/comment', methods=['POST'])
@admin_required
def add_blog_approval_comment(blog_id):
    """Add internal comment to blog"""
    try:
        data = request.get_json()
        comment = data.get('comment', '')

        if not comment:
            return jsonify({
                'success': False,
                'error': 'Comment is required'
            }), 400

        user = request.current_user
        models = get_models()
        success = models['blog'].add_approval_comment(blog_id, user.get('username'), comment)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to add comment'
            }), 400

        return jsonify({
            'success': True,
            'message': 'Comment added'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# MARKET ALERTS ENDPOINTS
# ============================================================================

@admin_content_bp.route('/api/admin/content/alerts', methods=['GET'])
@admin_required
def get_alerts():
    """Get all alerts"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status')

        models = get_models()
        result = models['alert'].get_all(page, limit, status)

        # Convert ObjectId to string
        for alert in result['alerts']:
            alert['_id'] = str(alert['_id'])
            if alert.get('scheduledFor'):
                alert['scheduledFor'] = alert['scheduledFor'].isoformat()
            if alert.get('sentAt'):
                alert['sentAt'] = alert['sentAt'].isoformat()
            alert['createdAt'] = alert['createdAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/alerts', methods=['POST'])
@admin_required
def create_alert():
    """Create new market alert"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('title') or not data.get('message'):
            return jsonify({
                'success': False,
                'error': 'Title and message are required'
            }), 400

        user = request.current_user
        data['createdBy'] = str(user['_id'])

        # Parse scheduledFor if provided
        if data.get('scheduledFor'):
            try:
                data['scheduledFor'] = datetime.fromisoformat(data['scheduledFor'].replace('Z', '+00:00'))
                data['status'] = 'scheduled'
            except:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format for scheduledFor'
                }), 400

        models = get_models()
        alert = models['alert'].create(data)

        alert['_id'] = str(alert['_id'])
        alert['createdAt'] = alert['createdAt'].isoformat()

        log_activity('create', 'alerts', f'Created alert: {data["title"]}',
                    targetType='alert', targetId=str(alert['_id']))

        return jsonify({
            'success': True,
            'alert': alert,
            'message': 'Alert created successfully'
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/alerts/<alert_id>', methods=['GET'])
@admin_required
def get_alert(alert_id):
    """Get alert by ID"""
    try:
        models = get_models()
        alert = models['alert'].get_by_id(alert_id)

        if not alert:
            return jsonify({
                'success': False,
                'error': 'Alert not found'
            }), 404

        alert['_id'] = str(alert['_id'])
        if alert.get('scheduledFor'):
            alert['scheduledFor'] = alert['scheduledFor'].isoformat()
        if alert.get('sentAt'):
            alert['sentAt'] = alert['sentAt'].isoformat()
        alert['createdAt'] = alert['createdAt'].isoformat()

        return jsonify({
            'success': True,
            'alert': alert
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/alerts/<alert_id>', methods=['PUT'])
@admin_required
def update_alert(alert_id):
    """Update alert"""
    try:
        data = request.get_json()

        # Parse scheduledFor if provided
        if data.get('scheduledFor'):
            try:
                data['scheduledFor'] = datetime.fromisoformat(data['scheduledFor'].replace('Z', '+00:00'))
            except:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format'
                }), 400

        models = get_models()
        success = models['alert'].update(alert_id, data)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Alert not found or update failed'
            }), 404

        log_activity('update', 'alerts', f'Updated alert {alert_id}',
                    targetType='alert', targetId=alert_id)

        return jsonify({
            'success': True,
            'message': 'Alert updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/alerts/<alert_id>', methods=['DELETE'])
@admin_required
def delete_alert(alert_id):
    """Delete alert"""
    try:
        models = get_models()
        success = models['alert'].delete(alert_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Alert not found'
            }), 404

        log_activity('delete', 'alerts', f'Deleted alert {alert_id}',
                    targetType='alert', targetId=alert_id, severity='warning')

        return jsonify({
            'success': True,
            'message': 'Alert deleted successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/alerts/<alert_id>/send', methods=['POST'])
@admin_required
def send_alert_now(alert_id):
    """Send alert immediately"""
    try:
        models = get_models()
        success = models['alert'].send_now(alert_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to send alert'
            }), 400

        log_activity('send', 'alerts', f'Sent alert {alert_id} immediately',
                    targetType='alert', targetId=alert_id, severity='info')

        return jsonify({
            'success': True,
            'message': 'Alert sent successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# COMMENTS & MODERATION ENDPOINTS
# ============================================================================

@admin_content_bp.route('/api/admin/content/comments', methods=['GET'])
@admin_required
def get_all_comments():
    """Get all comments (with filtering)"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'pending')

        models = get_models()

        if status == 'pending':
            result = models['comment'].get_all_pending(page, limit)
        else:
            # Get by blog would need blog_id, so for admin we'll need to add a get_all method
            # For now, return pending
            result = models['comment'].get_all_pending(page, limit)

        # Convert ObjectId to string
        for comment in result['comments']:
            comment['_id'] = str(comment['_id'])
            comment['createdAt'] = comment['createdAt'].isoformat()
            if comment.get('moderatedAt'):
                comment['moderatedAt'] = comment['moderatedAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/comments/<comment_id>/approve', methods=['POST'])
@admin_required
def approve_comment(comment_id):
    """Approve a comment"""
    try:
        user = request.current_user
        models = get_models()
        success = models['comment'].approve(comment_id, user.get('username'))

        if not success:
            return jsonify({
                'success': False,
                'error': 'Comment not found'
            }), 404

        log_activity('approve', 'comments', f'Approved comment {comment_id}',
                    targetType='comment', targetId=comment_id)

        return jsonify({
            'success': True,
            'message': 'Comment approved'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/comments/<comment_id>/reject', methods=['POST'])
@admin_required
def reject_comment(comment_id):
    """Reject a comment"""
    try:
        data = request.get_json() or {}
        reason = data.get('reason', 'Inappropriate content')

        user = request.current_user
        models = get_models()
        success = models['comment'].reject(comment_id, user.get('username'), reason)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Comment not found'
            }), 404

        log_activity('reject', 'comments', f'Rejected comment {comment_id}: {reason}',
                    targetType='comment', targetId=comment_id)

        return jsonify({
            'success': True,
            'message': 'Comment rejected'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/comments/<comment_id>/flag', methods=['POST'])
@admin_required
def flag_comment(comment_id):
    """Flag a comment as abusive"""
    try:
        data = request.get_json()
        reason = data.get('reason', '')

        if not reason:
            return jsonify({
                'success': False,
                'error': 'Reason is required'
            }), 400

        user = request.current_user
        models = get_models()
        success = models['comment'].flag(comment_id, user.get('username'), reason)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Comment not found'
            }), 404

        log_activity('flag', 'comments', f'Flagged comment {comment_id}: {reason}',
                    targetType='comment', targetId=comment_id, severity='warning')

        return jsonify({
            'success': True,
            'message': 'Comment flagged'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/comments/<comment_id>', methods=['DELETE'])
@admin_required
def delete_comment(comment_id):
    """Delete a comment"""
    try:
        models = get_models()
        success = models['comment'].delete(comment_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Comment not found'
            }), 404

        log_activity('delete', 'comments', f'Deleted comment {comment_id}',
                    targetType='comment', targetId=comment_id, severity='warning')

        return jsonify({
            'success': True,
            'message': 'Comment deleted'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/comments/flagged-users', methods=['GET'])
@admin_required
def get_flagged_users():
    """Get repeat offenders with multiple flagged comments"""
    try:
        models = get_models()
        users = models['comment'].get_flagged_users()

        # Convert ObjectId to string
        for user in users:
            user['_id'] = str(user['_id'])
            if user.get('lastFlagged'):
                user['lastFlagged'] = user['lastFlagged'].isoformat()

        return jsonify({
            'success': True,
            'users': users
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# CATEGORY MANAGEMENT ENDPOINTS
# ============================================================================

@admin_content_bp.route('/api/admin/content/categories', methods=['GET'])
@admin_required
def get_categories():
    """Get all categories"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        models = get_models()
        result = models['category'].get_all(page, limit)

        # Convert ObjectId to string
        for category in result['categories']:
            category['_id'] = str(category['_id'])
            category['createdAt'] = category['createdAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/categories', methods=['POST'])
@admin_required
def create_category():
    """Create new category"""
    try:
        data = request.get_json()

        if not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'Category name is required'
            }), 400

        user = request.current_user
        data['createdBy'] = str(user['_id'])

        models = get_models()
        category = models['category'].create(data)

        category['_id'] = str(category['_id'])
        category['createdAt'] = category['createdAt'].isoformat()

        log_activity('create', 'categories', f'Created category: {data["name"]}',
                    targetType='category', targetId=str(category['_id']))

        return jsonify({
            'success': True,
            'category': category,
            'message': 'Category created successfully'
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/categories/<category_id>', methods=['PUT'])
@admin_required
def update_category(category_id):
    """Update category"""
    try:
        data = request.get_json()

        models = get_models()
        success = models['category'].update(category_id, data)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Category not found'
            }), 404

        log_activity('update', 'categories', f'Updated category {category_id}',
                    targetType='category', targetId=category_id)

        return jsonify({
            'success': True,
            'message': 'Category updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/categories/<category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    """Delete category"""
    try:
        models = get_models()
        success = models['category'].delete(category_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Category not found'
            }), 404

        log_activity('delete', 'categories', f'Deleted category {category_id}',
                    targetType='category', targetId=category_id, severity='warning')

        return jsonify({
            'success': True,
            'message': 'Category deleted successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_content_bp.route('/api/admin/content/categories/popular', methods=['GET'])
@admin_required
def get_popular_categories():
    """Get popular categories by post count"""
    try:
        limit = int(request.args.get('limit', 10))

        models = get_models()
        categories = models['category'].get_popular_categories(limit)

        # Convert ObjectId to string
        for category in categories:
            category['_id'] = str(category['_id'])

        return jsonify({
            'success': True,
            'categories': categories
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
