"""
Risk Calculator Phase 2 Routes
Trade Checklist & Discipline Guardrails API
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase2_service import risk_phase2_service
from services.risk_calculator_service import RiskCalculatorService
from middleware.feature_limit import feature_limit
from functools import wraps

# Create blueprint
risk_phase2_bp = Blueprint('risk_calculator_phase2', __name__, url_prefix='/api/risk-calculator/phase2')


@risk_phase2_bp.route('/settings', methods=['GET'])
@jwt_required()
def get_user_settings():
    """
    Get user's risk management settings

    Returns user's configured limits and preferences
    """
    try:
        user_id = get_jwt_identity()
        settings = risk_phase2_service.get_user_settings(user_id)

        # Convert ObjectId to string if present
        if '_id' in settings:
            settings['_id'] = str(settings['_id'])

        return jsonify({
            'success': True,
            'settings': settings
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase2_bp.route('/settings', methods=['PUT'])
@jwt_required()
def update_user_settings():
    """
    Update user's risk management settings

    Request Body:
    {
        "max_daily_loss_percent": 4.0,
        "max_trades_per_day": 5,
        "preferred_risk_reward_min": 1.5,
        "max_risk_per_trade_percent": 2.0,
        "capital_baseline": 100000
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate numeric fields
        numeric_fields = [
            'max_daily_loss_percent',
            'max_trades_per_day',
            'preferred_risk_reward_min',
            'max_risk_per_trade_percent',
            'capital_baseline'
        ]

        for field in numeric_fields:
            if field in data:
                try:
                    value = float(data[field])
                    if value <= 0:
                        return jsonify({
                            'error': f'{field} must be positive'
                        }), 400
                except (ValueError, TypeError):
                    return jsonify({
                        'error': f'{field} must be a valid number'
                    }), 400

        settings = risk_phase2_service.update_user_settings(user_id, data)

        # Convert ObjectId to string
        if '_id' in settings:
            settings['_id'] = str(settings['_id'])

        return jsonify({
            'success': True,
            'settings': settings,
            'message': 'Settings updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase2_bp.route('/daily-exposure', methods=['GET'])
@jwt_required()
def get_daily_exposure():
    """
    Get current daily risk exposure and trade count

    Returns analytics about today's trading activity
    """
    try:
        user_id = get_jwt_identity()
        exposure = risk_phase2_service.calculate_daily_risk_exposure(user_id)

        return jsonify({
            'success': True,
            'exposure': exposure
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase2_bp.route('/trade-quality', methods=['POST'])
@jwt_required()
def calculate_trade_quality():
    """
    Calculate trade quality score based on user's rules

    Request Body:
    {
        "risk_reward_ratio": 2.0,
        "risk_per_trade_percent": 1.5
    }

    Returns quality score (0-10) with factors
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        risk_reward_ratio = float(data.get('risk_reward_ratio', 0))
        risk_per_trade_percent = float(data.get('risk_per_trade_percent', 0))

        user_settings = risk_phase2_service.get_user_settings(user_id)

        quality = risk_phase2_service.calculate_trade_quality_score(
            risk_reward_ratio=risk_reward_ratio,
            risk_per_trade_percent=risk_per_trade_percent,
            user_settings=user_settings
        )

        return jsonify({
            'success': True,
            'quality': quality
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase2_bp.route('/pre-trade-checklist', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def generate_checklist():
    """
    Generate pre-trade checklist with enhanced Phase 2 analytics

    Request Body: Same as Phase 1 calculate endpoint

    Returns: Phase 1 calculation + Phase 2 checklist and quality score
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Required fields validation
        required_fields = [
            'symbol', 'trade_type', 'buy_price', 'stop_loss_price',
            'capital_available', 'max_risk_per_trade', 'max_risk_type', 'broker'
        ]

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields
            }), 400

        # Prepare parameters for Phase 1 calculation
        params = {
            'symbol': data['symbol'].strip().upper(),
            'trade_type': data['trade_type'].lower(),
            'buy_price': float(data['buy_price']),
            'stop_loss_price': float(data['stop_loss_price']),
            'target_price': float(data['target_price']) if data.get('target_price') else None,
            'capital_available': float(data['capital_available']),
            'max_risk_per_trade': float(data['max_risk_per_trade']),
            'max_risk_type': data['max_risk_type'].lower(),
            'broker': data['broker'].lower()
        }

        # Run Phase 1 calculation
        phase1_result = RiskCalculatorService.generate_phase1_response(**params)

        # Generate Phase 2 checklist
        checklist = risk_phase2_service.generate_pre_trade_checklist(
            user_id=user_id,
            calculation_result=phase1_result
        )

        # Calculate trade quality score
        risk_reward_ratio = phase1_result.get('risk_reward', {}).get('ratio', 0)
        if isinstance(risk_reward_ratio, str):
            risk_reward_ratio = 0

        risk_per_trade_percent = phase1_result.get('risk_analysis', {}).get('risk_percentage', 0)

        user_settings = risk_phase2_service.get_user_settings(user_id)

        quality_score = risk_phase2_service.calculate_trade_quality_score(
            risk_reward_ratio=risk_reward_ratio,
            risk_per_trade_percent=risk_per_trade_percent,
            user_settings=user_settings
        )

        # Combine Phase 1 and Phase 2 data
        response = {
            **phase1_result,
            'phase2': {
                'pre_trade_checklist': checklist,
                'trade_quality_score': quality_score,
                'user_settings': {
                    'max_daily_loss_percent': user_settings.get('max_daily_loss_percent'),
                    'max_trades_per_day': user_settings.get('max_trades_per_day'),
                    'preferred_risk_reward_min': user_settings.get('preferred_risk_reward_min'),
                    'max_risk_per_trade_percent': user_settings.get('max_risk_per_trade_percent')
                }
            }
        }

        return jsonify({
            'success': True,
            'data': response
        }), 200

    except ValueError as ve:
        return jsonify({
            'success': False,
            'error': str(ve)
        }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }), 500


@risk_phase2_bp.route('/log-trade', methods=['POST'])
@jwt_required()
def log_trade():
    """
    Log a trade for tracking purposes (not execution)

    Request Body:
    {
        "symbol": "RELIANCE",
        "trade_type": "delivery",
        "entry_price": 2500,
        "stop_loss": 2450,
        "target": 2600,
        "quantity": 40,
        "risk_amount": 2000,
        "risk_percent": 2.0,
        "expected_costs": 223.16
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        trade_log = risk_phase2_service.log_trade(user_id, data)

        # Get updated daily exposure
        exposure = risk_phase2_service.calculate_daily_risk_exposure(user_id)

        return jsonify({
            'success': True,
            'trade_log': trade_log,
            'daily_exposure': exposure,
            'message': 'Trade logged successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase2_bp.route('/daily-trades', methods=['GET'])
@jwt_required()
def get_daily_trades():
    """
    Get all trades logged today

    Returns list of trades with analytics
    """
    try:
        user_id = get_jwt_identity()
        trades = risk_phase2_service.get_daily_trades(user_id)

        # Convert ObjectId to string
        for trade in trades:
            if '_id' in trade:
                trade['_id'] = str(trade['_id'])

        # Get daily exposure summary
        exposure = risk_phase2_service.calculate_daily_risk_exposure(user_id)

        return jsonify({
            'success': True,
            'trades': trades,
            'summary': exposure
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase2_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check for Phase 2 service
    """
    return jsonify({
        'success': True,
        'service': 'Risk Calculator - Phase 2',
        'status': 'operational',
        'features': [
            'User risk management settings',
            'Daily risk exposure tracking',
            'Trade quality scoring',
            'Pre-trade checklist generation',
            'Trade logging (non-execution)',
            'Behavioral nudges and warnings'
        ]
    }), 200
