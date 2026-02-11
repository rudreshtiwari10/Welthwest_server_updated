"""
Risk Calculator Phase 4 Routes: Simple Portfolio View
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase4_service import risk_phase4_service
from middleware.feature_limit import feature_limit

risk_phase4_bp = Blueprint('risk_phase4', __name__, url_prefix='/api/risk-calculator/phase4')


@risk_phase4_bp.route('/add-position', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def add_position():
    """Add or update a position in portfolio"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required fields
        required_fields = ['symbol', 'quantity', 'avg_entry_price', 'current_price', 'stop_loss']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400

        portfolio = risk_phase4_service.add_position(user_id, data)

        # Convert ObjectId to string
        portfolio['_id'] = str(portfolio['_id'])

        return jsonify({
            'success': True,
            'message': 'Position added/updated successfully',
            'portfolio': portfolio
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/update-price', methods=['PUT'])
@jwt_required()
@feature_limit('risk-calculator')
def update_price():
    """Update current price for a position"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if 'symbol' not in data or 'current_price' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing symbol or current_price'
            }), 400

        portfolio = risk_phase4_service.update_position_prices(
            user_id=user_id,
            symbol=data['symbol'],
            current_price=float(data['current_price'])
        )

        # Convert ObjectId to string
        portfolio['_id'] = str(portfolio['_id'])

        return jsonify({
            'success': True,
            'message': 'Price updated successfully',
            'portfolio': portfolio
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/remove-position/<symbol>', methods=['DELETE'])
@jwt_required()
@feature_limit('risk-calculator')
def remove_position(symbol):
    """Remove a position from portfolio"""
    try:
        user_id = get_jwt_identity()

        portfolio = risk_phase4_service.remove_position(user_id, symbol)

        # Convert ObjectId to string
        portfolio['_id'] = str(portfolio['_id'])

        return jsonify({
            'success': True,
            'message': f'Position {symbol} removed successfully',
            'portfolio': portfolio
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/portfolio-analytics', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_portfolio_analytics():
    """Get comprehensive portfolio analytics"""
    try:
        user_id = get_jwt_identity()
        analytics = risk_phase4_service.get_portfolio_analytics(user_id)

        return jsonify({
            'success': True,
            'analytics': analytics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/realtime-prices', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def get_realtime_prices():
    """Get real-time prices for symbols"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if 'symbols' not in data or not isinstance(data['symbols'], list):
            return jsonify({
                'success': False,
                'error': 'Missing symbols array'
            }), 400

        prices = risk_phase4_service.get_realtime_prices(data['symbols'])

        return jsonify({
            'success': True,
            'prices': prices
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/historical-returns', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_historical_returns():
    """Get historical returns for 3m, 6m, 1y"""
    try:
        user_id = get_jwt_identity()
        returns_data = risk_phase4_service.get_historical_returns(user_id)

        return jsonify({
            'success': True,
            'returns': returns_data
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/pnl-graph', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_pnl_graph():
    """Get portfolio PnL graph data"""
    try:
        user_id = get_jwt_identity()
        days = request.args.get('days', 30, type=int)

        if days < 1 or days > 365:
            return jsonify({
                'success': False,
                'error': 'Days must be between 1 and 365'
            }), 400

        graph_data = risk_phase4_service.get_portfolio_pnl_graph(user_id, days)

        return jsonify({
            'success': True,
            'data': graph_data
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/market-sentiment', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def get_market_sentiment():
    """Get market sentiment and pattern analysis"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if 'symbols' not in data or not isinstance(data['symbols'], list):
            return jsonify({
                'success': False,
                'error': 'Missing symbols array'
            }), 400

        sentiment = risk_phase4_service.get_market_sentiment(data['symbols'])

        return jsonify({
            'success': True,
            'sentiment': sentiment
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/yearly-monthly-analysis', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_yearly_monthly_analysis():
    """Get 1-year monthly PnL analysis with graph and table data"""
    try:
        user_id = get_jwt_identity()
        analysis = risk_phase4_service.get_yearly_monthly_pnl_analysis(user_id)

        return jsonify({
            'success': True,
            'analysis': analysis
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase4_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase4',
        'status': 'healthy'
    }), 200
