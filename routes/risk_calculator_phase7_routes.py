"""
Risk Calculator Phase 7 Routes: Portfolio Risk Analytics
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase7_service import risk_phase7_service
from middleware.feature_limit import feature_limit
from datetime import datetime

risk_phase7_bp = Blueprint('risk_phase7', __name__, url_prefix='/api/risk-calculator/phase7')


@risk_phase7_bp.route('/equity-curve', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_equity_curve():
    """Get equity curve data"""
    try:
        user_id = get_jwt_identity()

        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))
        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        equity_curve = risk_phase7_service.calculate_equity_curve(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        return jsonify({
            'success': True,
            'equity_curve': equity_curve
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase7_bp.route('/drawdown-analysis', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_drawdown_analysis():
    """Get drawdown analysis metrics"""
    try:
        user_id = get_jwt_identity()

        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))
        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        # First get equity curve
        equity_curve = risk_phase7_service.calculate_equity_curve(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        # Then calculate drawdown metrics
        drawdown_metrics = risk_phase7_service.calculate_drawdown_metrics(equity_curve)

        return jsonify({
            'success': True,
            'drawdown_metrics': drawdown_metrics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase7_bp.route('/volatility-metrics', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_volatility_metrics():
    """Get volatility and risk-adjusted return metrics"""
    try:
        user_id = get_jwt_identity()

        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))
        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        # Get equity curve
        equity_curve = risk_phase7_service.calculate_equity_curve(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        # Calculate returns from equity curve
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1]['equity'] != 0:
                ret = (equity_curve[i]['equity'] - equity_curve[i-1]['equity']) / equity_curve[i-1]['equity']
                returns.append(ret)

        volatility_metrics = risk_phase7_service.calculate_volatility_metrics(returns)

        return jsonify({
            'success': True,
            'volatility_metrics': volatility_metrics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase7_bp.route('/rolling-metrics', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_rolling_metrics():
    """Get rolling window metrics"""
    try:
        user_id = get_jwt_identity()
        window = request.args.get('window', 30, type=int)

        if window < 5 or window > 100:
            return jsonify({
                'success': False,
                'error': 'Window must be between 5 and 100'
            }), 400

        start_date = None
        end_date = None

        if request.args.get('start_date'):
            start_date = datetime.fromisoformat(request.args.get('start_date'))
        if request.args.get('end_date'):
            end_date = datetime.fromisoformat(request.args.get('end_date'))

        # Get equity curve
        equity_curve = risk_phase7_service.calculate_equity_curve(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        rolling_metrics = risk_phase7_service.calculate_rolling_metrics(
            equity_curve=equity_curve,
            window_days=window
        )

        return jsonify({
            'success': True,
            'rolling_metrics': rolling_metrics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase7_bp.route('/stress-test', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def stress_test():
    """Run portfolio stress test"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        scenario = data.get('scenario', 'market_crash_10')

        valid_scenarios = [
            'market_crash_10',
            'market_crash_20',
            'market_crash_30',
            'bull_rally_15',
            'individual_sl_hit'
        ]

        if scenario not in valid_scenarios:
            return jsonify({
                'success': False,
                'error': f'Invalid scenario. Must be one of: {", ".join(valid_scenarios)}'
            }), 400

        stress_results = risk_phase7_service.stress_test_portfolio(user_id, scenario)

        return jsonify({
            'success': True,
            'stress_test': stress_results
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase7_bp.route('/comprehensive-analytics', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_comprehensive_analytics():
    """Get all analytics in one call"""
    try:
        user_id = get_jwt_identity()

        period = request.args.get('period', 'all')  # 'all', '1m', '3m', '6m', '1y'

        analytics = risk_phase7_service.get_comprehensive_analytics(user_id, period)

        return jsonify({
            'success': True,
            'analytics': analytics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase7_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase7',
        'status': 'healthy'
    }), 200
