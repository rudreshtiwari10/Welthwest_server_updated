"""
Admin Monitoring & Logs Routes
Module 10: System Logs & Admin Activity Logs
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity
from bson import ObjectId
from datetime import datetime
import csv
import io
from middleware.feature_limit import admin_required
from pymongo import MongoClient
from config import get_config

# Create blueprint
admin_monitoring_bp = Blueprint('admin_monitoring', __name__)

# Get MongoDB connection
config = get_config()
db = MongoClient(config.MONGODB_URI)[config.DB_NAME]

def get_db():
    """Get database instance"""
    return db

def get_models():
    """Get model instances"""
    from models.activity_log import ActivityLog

    db = get_db()
    return {
        'activity_log': ActivityLog(db)
    }

# ============================================================================
# ACTIVITY LOGS ENDPOINTS
# ============================================================================

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs', methods=['GET'])
@admin_required
def get_activity_logs():
    """Get activity logs with filters"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        filters = {}
        if request.args.get('adminId'):
            filters['adminId'] = request.args.get('adminId')
        if request.args.get('module'):
            filters['module'] = request.args.get('module')
        if request.args.get('action'):
            filters['action'] = request.args.get('action')
        if request.args.get('severity'):
            filters['severity'] = request.args.get('severity')
        if request.args.get('dateFrom'):
            try:
                filters['dateFrom'] = datetime.fromisoformat(request.args.get('dateFrom'))
            except:
                pass
        if request.args.get('dateTo'):
            try:
                filters['dateTo'] = datetime.fromisoformat(request.args.get('dateTo'))
            except:
                pass

        models = get_models()
        result = models['activity_log'].get_all(page, limit, filters)

        # Convert ObjectId and datetime
        for log in result['logs']:
            log['_id'] = str(log['_id'])
            if log.get('adminId'):
                log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/<log_id>', methods=['GET'])
@admin_required
def get_activity_log(log_id):
    """Get specific activity log entry"""
    try:
        models = get_models()
        log = models['activity_log'].get_by_id(log_id)

        if not log:
            return jsonify({
                'success': False,
                'error': 'Log entry not found'
            }), 404

        # Convert ObjectId and datetime
        log['_id'] = str(log['_id'])
        if log.get('adminId'):
            log['adminId'] = str(log['adminId'])
        if log.get('targetId'):
            log['targetId'] = str(log['targetId'])
        log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            'log': log
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/admin/<admin_id>', methods=['GET'])
@admin_required
def get_logs_by_admin(admin_id):
    """Get activity logs for a specific admin"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        models = get_models()
        result = models['activity_log'].get_by_admin(admin_id, page, limit)

        # Convert ObjectId and datetime
        for log in result['logs']:
            log['_id'] = str(log['_id'])
            log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/module/<module>', methods=['GET'])
@admin_required
def get_logs_by_module(module):
    """Get activity logs for a specific module"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        models = get_models()
        result = models['activity_log'].get_by_module(module, page, limit)

        # Convert ObjectId and datetime
        for log in result['logs']:
            log['_id'] = str(log['_id'])
            log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/target/<target_type>/<target_id>', methods=['GET'])
@admin_required
def get_logs_by_target(target_type, target_id):
    """Get activity logs for a specific target"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        models = get_models()
        result = models['activity_log'].get_by_target(target_type, target_id, page, limit)

        # Convert ObjectId and datetime
        for log in result['logs']:
            log['_id'] = str(log['_id'])
            log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/critical', methods=['GET'])
@admin_required
def get_critical_logs():
    """Get critical severity logs"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        models = get_models()
        result = models['activity_log'].get_critical_logs(page, limit)

        # Convert ObjectId and datetime
        for log in result['logs']:
            log['_id'] = str(log['_id'])
            log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/recent', methods=['GET'])
@admin_required
def get_recent_logs():
    """Get most recent logs"""
    try:
        limit = int(request.args.get('limit', 100))

        models = get_models()
        logs = models['activity_log'].get_recent_logs(limit)

        # Convert ObjectId and datetime
        for log in logs:
            log['_id'] = str(log['_id'])
            log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            'logs': logs
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/stats', methods=['GET'])
@admin_required
def get_activity_stats():
    """Get activity log statistics"""
    try:
        models = get_models()
        stats = models['activity_log'].get_stats()

        # Convert ObjectId in stats
        for admin in stats.get('activeAdmins', []):
            if admin.get('_id'):
                admin['_id'] = str(admin['_id'])
            if admin.get('lastAction'):
                admin['lastAction'] = admin['lastAction'].isoformat()

        return jsonify({
            'success': True,
            'stats': stats
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/search', methods=['GET'])
@admin_required
def search_logs():
    """Search activity logs"""
    try:
        query = request.args.get('q', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))

        if not query:
            return jsonify({
                'success': False,
                'error': 'Search query is required'
            }), 400

        models = get_models()
        result = models['activity_log'].search(query, page, limit)

        # Convert ObjectId and datetime
        for log in result['logs']:
            log['_id'] = str(log['_id'])
            log['adminId'] = str(log['adminId'])
            if log.get('targetId'):
                log['targetId'] = str(log['targetId'])
            log['timestamp'] = log['timestamp'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/activity-logs/export', methods=['GET'])
@admin_required
def export_activity_logs():
    """Export activity logs to CSV"""
    try:
        filters = {}
        if request.args.get('adminId'):
            filters['adminId'] = request.args.get('adminId')
        if request.args.get('module'):
            filters['module'] = request.args.get('module')
        if request.args.get('dateFrom'):
            try:
                filters['dateFrom'] = datetime.fromisoformat(request.args.get('dateFrom'))
            except:
                pass
        if request.args.get('dateTo'):
            try:
                filters['dateTo'] = datetime.fromisoformat(request.args.get('dateTo'))
            except:
                pass

        models = get_models()
        logs = models['activity_log'].export_logs(filters)

        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Timestamp', 'Admin', 'Action', 'Module', 'Target Type',
            'Target ID', 'Description', 'Severity', 'IP Address'
        ])

        # Write data
        for log in logs:
            writer.writerow([
                log['timestamp'].isoformat(),
                log['adminUsername'],
                log['action'],
                log['module'],
                log.get('targetType', ''),
                str(log.get('targetId', '')),
                log['description'],
                log['severity'],
                log.get('ipAddress', '')
            ])

        # Log the export activity
        user_id = get_jwt_identity()
        db = get_db()
        user = db.users.find_one({'_id': ObjectId(user_id)})

        log_data = {
            'adminId': str(user['_id']),
            'adminUsername': user.get('username', user.get('email')),
            'adminEmail': user.get('email'),
            'action': 'export',
            'module': 'monitoring',
            'description': f'Exported {len(logs)} activity logs',
            'ipAddress': request.remote_addr,
            'userAgent': request.headers.get('User-Agent'),
            'severity': 'info',
            'metadata': {'count': len(logs), 'filters': str(filters)}
        }
        models['activity_log'].log(log_data)

        return jsonify({
            'success': True,
            'csv': output.getvalue(),
            'count': len(logs)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# SYSTEM LOGS ENDPOINTS
# ============================================================================

@admin_monitoring_bp.route('/api/admin/monitoring/system-logs', methods=['GET'])
@admin_required
def get_system_logs():
    """Get system logs (if logging to database)"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 100))
        severity = request.args.get('severity')  # debug | info | warning | error | critical

        # This would read from your system logs collection or file
        # For now, return empty as this depends on your logging setup
        return jsonify({
            'success': True,
            'logs': [],
            'total': 0,
            'page': page,
            'limit': limit,
            'totalPages': 0,
            'message': 'System logs endpoint - integrate with your logging system'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@admin_monitoring_bp.route('/api/admin/monitoring/system-logs/export', methods=['GET'])
@admin_required
def export_system_logs():
    """Export system logs"""
    try:
        # This would export system logs
        # Implementation depends on your logging setup
        return jsonify({
            'success': True,
            'message': 'System logs export - integrate with your logging system'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
