"""
Risk Calculator Phase 8 Routes: Notifications & Periodic Reports
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase8_service import risk_phase8_service
from middleware.feature_limit import feature_limit
from datetime import datetime
from bson import ObjectId

risk_phase8_bp = Blueprint('risk_phase8', __name__, url_prefix='/api/risk-calculator/phase8')


@risk_phase8_bp.route('/notification-preferences', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_notification_preferences():
    """Get user's notification preferences"""
    try:
        user_id = get_jwt_identity()

        preferences = risk_phase8_service.get_notification_preferences(user_id)

        # Convert ObjectId to string
        if '_id' in preferences:
            preferences['_id'] = str(preferences['_id'])

        return jsonify({
            'success': True,
            'preferences': preferences
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase8_bp.route('/notification-preferences', methods=['PUT'])
@jwt_required()
@feature_limit('risk-calculator')
def update_notification_preferences():
    """Update user's notification preferences"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        preferences = risk_phase8_service.update_notification_preferences(user_id, data)

        # Convert ObjectId to string
        if '_id' in preferences:
            preferences['_id'] = str(preferences['_id'])

        return jsonify({
            'success': True,
            'message': 'Notification preferences updated successfully',
            'preferences': preferences
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase8_bp.route('/generate-report', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def generate_report():
    """Manually trigger report generation"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        report_type = data.get('report_type', 'daily').lower()

        if report_type not in ['daily', 'weekly', 'monthly']:
            return jsonify({
                'success': False,
                'error': 'Invalid report_type. Must be daily, weekly, or monthly'
            }), 400

        # Parse date if provided
        report_date = None
        if 'date' in data:
            try:
                report_date = datetime.fromisoformat(data['date'])
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date format. Use ISO format (YYYY-MM-DD)'
                }), 400

        # Generate report based on type
        if report_type == 'daily':
            report = risk_phase8_service.generate_daily_report(user_id, report_date)
        elif report_type == 'weekly':
            report = risk_phase8_service.generate_weekly_report(user_id, report_date)
        else:  # monthly
            report = risk_phase8_service.generate_monthly_report(user_id, report_date)

        # Convert ObjectId to string and datetime to ISO
        report['_id'] = str(report['_id'])
        if 'report_date' in report:
            report['report_date'] = report['report_date'].isoformat()
        if 'report_start_date' in report:
            report['report_start_date'] = report['report_start_date'].isoformat()
        if 'report_end_date' in report:
            report['report_end_date'] = report['report_end_date'].isoformat()
        if 'generated_at' in report:
            report['generated_at'] = report['generated_at'].isoformat()

        # Convert top trades ObjectIds
        if 'top_trades' in report:
            for trade in report['top_trades']:
                if '_id' in trade:
                    trade['_id'] = str(trade['_id'])

        if 'top_10_trades' in report:
            for trade in report['top_10_trades']:
                if '_id' in trade:
                    trade['_id'] = str(trade['_id'])

        return jsonify({
            'success': True,
            'message': f'{report_type.capitalize()} report generated successfully',
            'report': report
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase8_bp.route('/reports', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_past_reports():
    """Get past reports with filters"""
    try:
        user_id = get_jwt_identity()

        # Get query parameters
        report_type = request.args.get('type')  # daily, weekly, monthly
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)

        # Validate limit
        if limit > 100:
            limit = 100

        result = risk_phase8_service.get_past_reports(
            user_id=user_id,
            report_type=report_type,
            limit=limit,
            offset=offset
        )

        # Convert ObjectIds to strings
        for report in result['reports']:
            report['_id'] = str(report['_id'])
            if 'report_date' in report and isinstance(report['report_date'], datetime):
                report['report_date'] = report['report_date'].isoformat()
            if 'report_start_date' in report and isinstance(report['report_start_date'], datetime):
                report['report_start_date'] = report['report_start_date'].isoformat()
            if 'report_end_date' in report and isinstance(report['report_end_date'], datetime):
                report['report_end_date'] = report['report_end_date'].isoformat()
            if 'generated_at' in report and isinstance(report['generated_at'], datetime):
                report['generated_at'] = report['generated_at'].isoformat()

        return jsonify({
            'success': True,
            'reports': result['reports'],
            'total_count': result['total_count'],
            'limit': result['limit'],
            'offset': result['offset'],
            'has_more': result['has_more']
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase8_bp.route('/send-test-email', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def send_test_email():
    """Send a test report email"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required fields
        if 'email' not in data or 'name' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: email, name'
            }), 400

        # Get the most recent report or generate a daily one
        from database import db
        recent_report = db['risk_calculator_reports'].find_one(
            {'user_id': user_id},
            sort=[('generated_at', -1)]
        )

        if not recent_report:
            # Generate a daily report
            recent_report = risk_phase8_service.generate_daily_report(user_id)

        # Send email
        success = risk_phase8_service.send_report_email(
            user_id=user_id,
            report_id=str(recent_report['_id']),
            user_email=data['email'],
            user_name=data['name']
        )

        if success:
            return jsonify({
                'success': True,
                'message': f'Test email sent successfully to {data["email"]}'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send email. Please check email service configuration.'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase8_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase8',
        'status': 'healthy'
    }), 200
