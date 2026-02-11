"""
Risk Calculator Phase 9 Routes: Broker API Integration (Read-Only)
"""

from flask import Blueprint, request, jsonify, redirect
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase9_service import risk_phase9_service
from middleware.feature_limit import feature_limit
from datetime import datetime

risk_phase9_bp = Blueprint('risk_phase9', __name__, url_prefix='/api/risk-calculator/phase9')


@risk_phase9_bp.route('/connect/<broker>', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def connect_broker(broker):
    """Initiate OAuth flow for broker connection"""
    try:
        user_id = get_jwt_identity()

        # Validate broker
        if broker.lower() not in risk_phase9_service.SUPPORTED_BROKERS:
            return jsonify({
                'success': False,
                'error': f'Broker "{broker}" not supported',
                'supported_brokers': risk_phase9_service.SUPPORTED_BROKERS
            }), 400

        # Initiate OAuth
        oauth_data = risk_phase9_service.initiate_broker_oauth(user_id, broker)

        return jsonify({
            'success': True,
            'message': f'OAuth flow initiated for {broker}',
            'oauth_url': oauth_data['oauth_url'],
            'state': oauth_data['state'],
            'broker': oauth_data['broker']
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/oauth-callback', methods=['GET'])
def oauth_callback():
    """
    OAuth redirect handler

    This endpoint receives the OAuth callback from the broker.
    Query parameters: code, state, broker (custom param we add)
    """
    try:
        # Get query parameters
        code = request.args.get('code')
        state = request.args.get('state')
        broker = request.args.get('broker')  # Custom parameter we'll include in redirect_uri

        if not code or not state or not broker:
            return jsonify({
                'success': False,
                'error': 'Missing required OAuth parameters'
            }), 400

        # Extract user_id from JWT (if available) or from state
        # In production, you'd decode the state to get user_id
        # For now, we'll require the frontend to handle this with a logged-in session

        # For this example, we'll return a page that posts to the complete endpoint
        # In production, the frontend should handle the callback

        return f"""
        <html>
        <head><title>Connecting to {broker}...</title></head>
        <body>
            <h2>Connecting to {broker}...</h2>
            <p>Please wait while we complete the connection...</p>
            <script>
                // Send to frontend callback handler
                window.location.href = window.location.origin + '/broker-callback?' +
                    'broker={broker}&code={code}&state={state}';
            </script>
        </body>
        </html>
        """

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/complete-oauth', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def complete_oauth():
    """Complete OAuth flow after receiving callback"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required fields
        if 'broker' not in data or 'code' not in data or 'state' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: broker, code, state'
            }), 400

        # Complete OAuth
        result = risk_phase9_service.complete_broker_oauth(
            user_id=user_id,
            broker=data['broker'],
            code=data['code'],
            state=data['state']
        )

        return jsonify({
            'success': True,
            'message': f'Successfully connected to {data["broker"]}',
            'connection': result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/disconnect/<broker>', methods=['DELETE'])
@jwt_required()
@feature_limit('risk-calculator')
def disconnect_broker(broker):
    """Disconnect broker and remove stored tokens"""
    try:
        user_id = get_jwt_identity()

        result = risk_phase9_service.disconnect_broker(user_id, broker)

        return jsonify({
            'success': True,
            'message': result['message'],
            'broker': result['broker'],
            'status': result['status']
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/sync-positions', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def sync_positions():
    """Sync positions from broker to portfolio"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        if 'broker' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: broker'
            }), 400

        result = risk_phase9_service.sync_broker_positions(user_id, data['broker'])

        return jsonify({
            'success': True,
            'message': f'Successfully synced positions from {data["broker"]}',
            'broker': result['broker'],
            'synced_positions': result['synced_positions'],
            'count': result['count'],
            'synced_at': result['synced_at'].isoformat()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/sync-trades', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def sync_trades():
    """Sync trades from broker to trade journal"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        if 'broker' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: broker'
            }), 400

        # Parse date range if provided
        from_date = None
        to_date = None

        if 'from_date' in data:
            try:
                from_date = datetime.fromisoformat(data['from_date'])
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid from_date format. Use ISO format (YYYY-MM-DD)'
                }), 400

        if 'to_date' in data:
            try:
                to_date = datetime.fromisoformat(data['to_date'])
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid to_date format. Use ISO format (YYYY-MM-DD)'
                }), 400

        result = risk_phase9_service.sync_broker_trades(
            user_id=user_id,
            broker=data['broker'],
            from_date=from_date,
            to_date=to_date
        )

        return jsonify({
            'success': True,
            'message': f'Successfully synced trades from {data["broker"]}',
            'broker': result['broker'],
            'synced_trades': result['synced_trades'],
            'date_range': result['date_range'],
            'synced_at': result['synced_at'].isoformat()
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/connection-status', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_connection_status():
    """Get broker connection status"""
    try:
        user_id = get_jwt_identity()
        broker = request.args.get('broker')  # Optional filter

        result = risk_phase9_service.get_connection_status(user_id, broker)

        # Convert datetime objects to ISO format
        for connection in result['connections']:
            if connection.get('connected_at'):
                connection['connected_at'] = connection['connected_at'].isoformat()
            if connection.get('last_synced'):
                connection['last_synced'] = connection['last_synced'].isoformat()

        return jsonify({
            'success': True,
            'connections': result['connections'],
            'total_connections': result['total_connections'],
            'supported_brokers': risk_phase9_service.SUPPORTED_BROKERS
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/sync-history', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_sync_history():
    """Get sync history logs"""
    try:
        user_id = get_jwt_identity()
        broker = request.args.get('broker')  # Optional filter
        limit = request.args.get('limit', 20, type=int)

        # Validate limit
        if limit > 100:
            limit = 100

        result = risk_phase9_service.get_sync_history(user_id, broker, limit)

        # Convert datetime objects to ISO format
        for log in result['sync_history']:
            if log.get('sync_timestamp'):
                log['sync_timestamp'] = log['sync_timestamp'].isoformat()

        return jsonify({
            'success': True,
            'sync_history': result['sync_history'],
            'count': result['count']
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase9_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase9',
        'status': 'healthy',
        'supported_brokers': risk_phase9_service.SUPPORTED_BROKERS
    }), 200
