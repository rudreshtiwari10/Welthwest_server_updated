"""
Risk Calculator Routes - Phase 1
API endpoints for position sizing and cost calculation
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_service import RiskCalculatorService
from middleware.feature_limit import feature_limit
from functools import wraps

# Create blueprint
risk_calculator_bp = Blueprint('risk_calculator', __name__, url_prefix='/api/risk-calculator')


def validate_risk_calculator_input(f):
    """
    Decorator to validate input for risk calculator endpoint
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No input data provided'}), 400

        # Required fields
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

        # Validate trade type
        valid_trade_types = ['delivery', 'intraday', 'fno']
        if data['trade_type'].lower() not in valid_trade_types:
            return jsonify({
                'error': 'Invalid trade type',
                'valid_types': valid_trade_types
            }), 400

        # Validate max risk type
        valid_risk_types = ['percentage', 'rupees']
        if data['max_risk_type'].lower() not in valid_risk_types:
            return jsonify({
                'error': 'Invalid max risk type',
                'valid_types': valid_risk_types
            }), 400

        # Validate broker
        valid_brokers = ['zerodha', 'upstox', 'custom']
        if data['broker'].lower() not in valid_brokers:
            return jsonify({
                'error': 'Invalid broker',
                'valid_brokers': valid_brokers
            }), 400

        # Validate numeric fields
        numeric_fields = {
            'buy_price': data.get('buy_price'),
            'stop_loss_price': data.get('stop_loss_price'),
            'capital_available': data.get('capital_available'),
            'max_risk_per_trade': data.get('max_risk_per_trade')
        }

        for field_name, value in numeric_fields.items():
            try:
                float_value = float(value)
                if float_value <= 0:
                    return jsonify({
                        'error': f'{field_name} must be a positive number'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'error': f'{field_name} must be a valid number'
                }), 400

        # Validate target price if provided
        if 'target_price' in data and data['target_price'] is not None:
            try:
                target = float(data['target_price'])
                if target <= 0:
                    return jsonify({
                        'error': 'target_price must be a positive number'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'error': 'target_price must be a valid number'
                }), 400

        # Validate stop loss is below buy price
        if float(data['stop_loss_price']) >= float(data['buy_price']):
            return jsonify({
                'error': 'Stop loss price must be below buy price for long positions'
            }), 400

        # Validate max risk percentage
        if data['max_risk_type'].lower() == 'percentage':
            if float(data['max_risk_per_trade']) > 100:
                return jsonify({
                    'error': 'Risk percentage cannot exceed 100%'
                }), 400

        return f(*args, **kwargs)

    return decorated_function


@risk_calculator_bp.route('/calculate', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
@validate_risk_calculator_input
def calculate_position_and_costs():
    """
    Calculate position size, risk, and trading costs for Phase 1.

    Request Body:
    {
        "symbol": "RELIANCE",
        "trade_type": "delivery",  // delivery | intraday | fno
        "buy_price": 2500,
        "stop_loss_price": 2450,
        "target_price": 2600,  // optional
        "capital_available": 100000,
        "max_risk_per_trade": 2,  // 2% or ₹2000 based on max_risk_type
        "max_risk_type": "percentage",  // percentage | rupees
        "broker": "zerodha"  // zerodha | upstox | custom
    }

    Returns:
        Complete risk analysis with position sizing, costs, and scenarios
    """
    try:
        data = request.get_json()
        user_id = get_jwt_identity()

        # Extract and normalize inputs
        symbol = data['symbol'].strip().upper()
        trade_type = data['trade_type'].lower()
        buy_price = float(data['buy_price'])
        stop_loss_price = float(data['stop_loss_price'])
        target_price = float(data['target_price']) if data.get('target_price') else None
        capital_available = float(data['capital_available'])
        max_risk_per_trade = float(data['max_risk_per_trade'])
        max_risk_type = data['max_risk_type'].lower()
        broker = data['broker'].lower()

        # Generate complete Phase 1 response
        result = RiskCalculatorService.generate_phase1_response(
            symbol=symbol,
            trade_type=trade_type,
            buy_price=buy_price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            capital_available=capital_available,
            max_risk_per_trade=max_risk_per_trade,
            max_risk_type=max_risk_type,
            broker=broker
        )

        return jsonify({
            'success': True,
            'data': result,
            'timestamp': request.environ.get('REQUEST_START_TIME')
        }), 200

    except ValueError as ve:
        return jsonify({
            'success': False,
            'error': str(ve)
        }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'An error occurred during calculation: {str(e)}'
        }), 500


@risk_calculator_bp.route('/brokers', methods=['GET'])
@jwt_required()
def get_available_brokers():
    """
    Get list of available brokers and their cost profiles.

    Returns:
        List of brokers with their cost structures
    """
    try:
        brokers = []
        for broker_name, profile in RiskCalculatorService.BROKER_PROFILES.items():
            brokers.append({
                'broker': broker_name,
                'name': broker_name.capitalize(),
                'profiles': {
                    'delivery': {
                        'brokerage': profile.get('equity_delivery_brokerage', 0),
                        'brokerage_type': 'percentage' if profile.get('equity_delivery_brokerage', 0) > 0 else 'flat',
                        'max_brokerage': profile.get('equity_delivery_brokerage_max', 0)
                    },
                    'intraday': {
                        'brokerage': profile.get('equity_intraday_brokerage', 0),
                        'brokerage_type': 'percentage',
                        'max_brokerage': profile.get('equity_intraday_brokerage_max', 20)
                    },
                    'fno': {
                        'brokerage': profile.get('fno_brokerage', 20),
                        'brokerage_type': 'flat'
                    }
                }
            })

        return jsonify({
            'success': True,
            'brokers': brokers
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_calculator_bp.route('/validate-trade', methods=['POST'])
@jwt_required()
def validate_trade_parameters():
    """
    Quick validation of trade parameters without full calculation.
    Useful for frontend validation before submitting.

    Request Body:
    {
        "buy_price": 2500,
        "stop_loss_price": 2450,
        "target_price": 2600,
        "capital_available": 100000,
        "max_risk_per_trade": 2,
        "max_risk_type": "percentage"
    }

    Returns:
        Validation result with any errors or warnings
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No input data provided'}), 400

        buy_price = float(data.get('buy_price', 0))
        stop_loss_price = float(data.get('stop_loss_price', 0))
        target_price = data.get('target_price')
        capital_available = float(data.get('capital_available', 0))
        max_risk_per_trade = float(data.get('max_risk_per_trade', 0))
        max_risk_type = data.get('max_risk_type', 'percentage')

        errors = []
        warnings = []

        # Validate prices
        if buy_price <= 0:
            errors.append('Buy price must be positive')

        if stop_loss_price <= 0:
            errors.append('Stop loss price must be positive')

        if stop_loss_price >= buy_price:
            errors.append('Stop loss must be below buy price for long positions')

        if target_price:
            try:
                target = float(target_price)
                if target <= buy_price:
                    warnings.append('Target price should be above buy price for potential profit')
            except:
                errors.append('Invalid target price')

        # Validate capital
        if capital_available <= 0:
            errors.append('Capital available must be positive')

        # Validate risk
        if max_risk_per_trade <= 0:
            errors.append('Max risk per trade must be positive')

        if max_risk_type == 'percentage' and max_risk_per_trade > 100:
            errors.append('Risk percentage cannot exceed 100%')

        # Calculate quick metrics if valid
        is_valid = len(errors) == 0

        result = {
            'is_valid': is_valid,
            'errors': errors,
            'warnings': warnings
        }

        if is_valid and stop_loss_price < buy_price:
            # Quick position size estimate
            risk_per_share = buy_price - stop_loss_price
            if max_risk_type == 'percentage':
                max_risk_rupees = capital_available * (max_risk_per_trade / 100)
            else:
                max_risk_rupees = max_risk_per_trade

            estimated_quantity = int(max_risk_rupees / risk_per_share)

            result['quick_estimate'] = {
                'estimated_quantity': estimated_quantity,
                'estimated_position_value': round(estimated_quantity * buy_price, 2),
                'estimated_risk': round(estimated_quantity * risk_per_share, 2)
            }

            # Risk warnings
            if max_risk_type == 'percentage' and max_risk_per_trade > 5:
                warnings.append('Risk per trade exceeds 5% - consider reducing position size')

            if target_price:
                target = float(target_price)
                risk = buy_price - stop_loss_price
                reward = target - buy_price
                rr_ratio = reward / risk

                if rr_ratio < 1:
                    warnings.append(f'Risk:Reward ratio is {round(rr_ratio, 2)}:1 - consider better target or tighter stop loss')
                elif rr_ratio < 1.5:
                    warnings.append(f'Risk:Reward ratio is {round(rr_ratio, 2)}:1 - acceptable but could be improved')

        return jsonify({
            'success': True,
            'validation': result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_calculator_bp.route('/cost-breakdown', methods=['POST'])
@jwt_required()
def get_cost_breakdown():
    """
    Get detailed cost breakdown for a specific trade without position sizing.
    Useful when user wants to see costs for a specific quantity.

    Request Body:
    {
        "trade_type": "delivery",
        "broker": "zerodha",
        "buy_price": 2500,
        "sell_price": 2600,
        "quantity": 10
    }

    Returns:
        Detailed cost breakdown
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No input data provided'}), 400

        trade_type = data.get('trade_type', '').lower()
        broker = data.get('broker', '').lower()
        buy_price = float(data.get('buy_price', 0))
        sell_price = float(data.get('sell_price', 0))
        quantity = int(data.get('quantity', 0))

        if trade_type not in ['delivery', 'intraday', 'fno']:
            return jsonify({'error': 'Invalid trade type'}), 400

        if broker not in ['zerodha', 'upstox', 'custom']:
            return jsonify({'error': 'Invalid broker'}), 400

        if buy_price <= 0 or sell_price <= 0 or quantity <= 0:
            return jsonify({'error': 'Prices and quantity must be positive'}), 400

        # Calculate costs
        costs = RiskCalculatorService.calculate_trading_costs(
            trade_type=trade_type,
            broker=broker,
            buy_price=buy_price,
            quantity=quantity,
            sell_price=sell_price
        )

        # Calculate P&L
        pl = RiskCalculatorService.calculate_net_profit_loss(
            buy_price=buy_price,
            sell_price=sell_price,
            quantity=quantity,
            trading_costs=costs['total_cost']
        )

        # Calculate breakeven
        breakeven = RiskCalculatorService.calculate_breakeven_price(
            buy_price=buy_price,
            quantity=quantity,
            total_costs=costs['total_cost']
        )

        return jsonify({
            'success': True,
            'data': {
                'cost_breakdown': costs,
                'profit_loss': pl,
                'breakeven_price': breakeven,
                'trade_details': {
                    'trade_type': trade_type,
                    'broker': broker,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'quantity': quantity
                }
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_calculator_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for risk calculator service
    """
    return jsonify({
        'success': True,
        'service': 'Risk Calculator - Phase 1',
        'status': 'operational',
        'features': [
            'Position sizing based on risk parameters',
            'Complete cost breakdown (brokerage, STT, charges)',
            'Risk:Reward ratio calculation',
            'Net P&L estimation with costs',
            'Breakeven price calculation',
            'Multi-broker support (Zerodha, Upstox, Custom)'
        ]
    }), 200
