"""
Risk Calculator Phase 6 Routes: Scenario & Cost Simulation Engine
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase6_service import risk_phase6_service
from middleware.feature_limit import feature_limit

risk_phase6_bp = Blueprint('risk_phase6', __name__, url_prefix='/api/risk-calculator/phase6')


@risk_phase6_bp.route('/simulate-costs', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def simulate_costs():
    """Simulate monthly trading costs"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required parameters
        required_params = ['trades_per_month', 'avg_position_size', 'trade_type', 'broker']
        missing_params = [p for p in required_params if p not in data]

        if missing_params:
            return jsonify({
                'success': False,
                'error': f'Missing required parameters: {", ".join(missing_params)}'
            }), 400

        parameters = {
            'trades_per_month': int(data['trades_per_month']),
            'avg_position_size': float(data['avg_position_size']),
            'trade_type': data['trade_type'],
            'broker': data['broker']
        }

        simulation = risk_phase6_service.simulate_monthly_costs(user_id, parameters)

        # Convert ObjectId to string
        if '_id' in simulation:
            simulation['_id'] = str(simulation['_id'])

        return jsonify({
            'success': True,
            'message': 'Cost simulation completed',
            'simulation': simulation
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase6_bp.route('/simulate-risk', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def simulate_risk():
    """Simulate risk scenarios"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required parameters
        required_params = ['risk_per_trade_percent', 'win_rate', 'risk_reward_ratio']
        missing_params = [p for p in required_params if p not in data]

        if missing_params:
            return jsonify({
                'success': False,
                'error': f'Missing required parameters: {", ".join(missing_params)}'
            }), 400

        parameters = {
            'risk_per_trade_percent': float(data['risk_per_trade_percent']),
            'win_rate': float(data['win_rate']),
            'risk_reward_ratio': float(data['risk_reward_ratio']),
            'num_trades': int(data.get('num_trades', 100)),
            'starting_capital': float(data.get('starting_capital', 100000))
        }

        simulation = risk_phase6_service.simulate_risk_scenario(user_id, parameters)

        # Convert ObjectId to string
        if '_id' in simulation:
            simulation['_id'] = str(simulation['_id'])

        return jsonify({
            'success': True,
            'message': 'Risk scenario simulation completed',
            'simulation': simulation
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase6_bp.route('/simulate-drawdown', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def simulate_drawdown():
    """Run Monte Carlo drawdown simulation"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required parameters
        required_params = ['risk_per_trade_percent', 'win_rate']
        missing_params = [p for p in required_params if p not in data]

        if missing_params:
            return jsonify({
                'success': False,
                'error': f'Missing required parameters: {", ".join(missing_params)}'
            }), 400

        parameters = {
            'risk_per_trade_percent': float(data['risk_per_trade_percent']),
            'win_rate': float(data['win_rate']),
            'avg_win_percent': float(data.get('avg_win_percent', 2.0)),
            'avg_loss_percent': float(data.get('avg_loss_percent', 1.0)),
            'num_trades': int(data.get('num_trades', 100)),
            'iterations': int(data.get('iterations', 1000)),
            'starting_capital': float(data.get('starting_capital', 100000))
        }

        # Limit iterations for performance
        if parameters['iterations'] > 10000:
            return jsonify({
                'success': False,
                'error': 'Maximum 10,000 iterations allowed'
            }), 400

        simulation = risk_phase6_service.simulate_monte_carlo_drawdown(user_id, parameters)

        # Convert ObjectId to string
        if '_id' in simulation:
            simulation['_id'] = str(simulation['_id'])

        return jsonify({
            'success': True,
            'message': 'Monte Carlo simulation completed',
            'simulation': simulation
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase6_bp.route('/simulations/<simulation_type>', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_simulations(simulation_type):
    """Get saved simulations by type"""
    try:
        user_id = get_jwt_identity()
        limit = request.args.get('limit', 10, type=int)

        valid_types = ['cost_projection', 'risk_scenario', 'drawdown_montecarlo']
        if simulation_type not in valid_types:
            return jsonify({
                'success': False,
                'error': f'Invalid simulation type. Must be one of: {", ".join(valid_types)}'
            }), 400

        simulations = risk_phase6_service.get_simulations(user_id, simulation_type, limit)

        # Convert ObjectIds to strings
        for sim in simulations:
            sim['_id'] = str(sim['_id'])

        return jsonify({
            'success': True,
            'simulations': simulations,
            'count': len(simulations)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase6_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase6',
        'status': 'healthy'
    }), 200
