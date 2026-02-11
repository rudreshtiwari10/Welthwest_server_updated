"""
Risk Calculator Phase 3 Routes: Session-Level Risk & Behavior Tracking
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase3_service import risk_phase3_service
from middleware.feature_limit import feature_limit
from datetime import datetime
from bson import ObjectId

risk_phase3_bp = Blueprint('risk_phase3', __name__, url_prefix='/api/risk-calculator/phase3')


@risk_phase3_bp.route('/session-dashboard', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_session_dashboard():
    """Get today's session dashboard data"""
    try:
        user_id = get_jwt_identity()
        dashboard = risk_phase3_service.get_session_dashboard(user_id)

        return jsonify({
            'success': True,
            'dashboard': dashboard
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase3_bp.route('/close-trade', methods=['PUT'])
@jwt_required()
@feature_limit('risk-calculator')
def close_trade():
    """Close a trade and update session"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required fields
        required_fields = ['trade_id', 'exit_price']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400

        trade_id = data['trade_id']
        exit_price = float(data['exit_price'])
        exit_timestamp = datetime.now()

        # Optional fields
        if 'exit_timestamp' in data:
            exit_timestamp = datetime.fromisoformat(data['exit_timestamp'])

        # Update session
        updated_session = risk_phase3_service.update_session_on_trade_close(
            user_id=user_id,
            trade_id=trade_id,
            exit_price=exit_price,
            exit_timestamp=exit_timestamp
        )

        return jsonify({
            'success': True,
            'message': 'Trade closed successfully',
            'session': {
                'trades_count': updated_session.get('trades_count', 0),
                'net_pnl': updated_session.get('net_pnl', 0),
                'current_streak': updated_session.get('current_streak', {})
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase3_bp.route('/behavior-history', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_behavior_history():
    """Get historical behavior patterns"""
    try:
        user_id = get_jwt_identity()
        days = request.args.get('days', 7, type=int)

        if days < 1 or days > 90:
            return jsonify({
                'success': False,
                'error': 'Days must be between 1 and 90'
            }), 400

        history = risk_phase3_service.get_behavior_history(user_id, days)

        # Convert ObjectIds to strings for JSON serialization
        for session in history['sessions']:
            session['_id'] = str(session['_id'])
            if 'session_id' in session:
                session['session_id'] = str(session['session_id'])

        return jsonify({
            'success': True,
            'history': history
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase3_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase3',
        'status': 'healthy'
    }), 200
