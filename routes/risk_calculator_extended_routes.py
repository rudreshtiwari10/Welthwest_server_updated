"""
Risk Calculator Extended Routes
Additional endpoints for pattern-based risk management
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from bson import ObjectId

risk_calc_ext_bp = Blueprint('risk_calculator_extended', __name__, url_prefix='/api/risk-calculator')


@risk_calc_ext_bp.route('/calculate-position', methods=['POST'])
def calculate_position():
    """
    Calculate optimal position size based on risk parameters

    Request Body:
    {
        "portfolio_value": 100000,
        "risk_percent": 2,
        "entry_price": 2450.50,
        "stop_loss": 2400.00
    }

    Response:
    {
        "success": true,
        "position": {
            "quantity": 40,
            "total_investment": 98020,
            "risk_amount": 2020,
            "position_percent": 98.02,
            "breakeven_price": 2451.45
        }
    }
    """
    try:
        data = request.get_json()

        portfolio_value = float(data.get('portfolio_value', 0))
        risk_percent = float(data.get('risk_percent', 0))
        entry_price = float(data.get('entry_price', 0))
        stop_loss = float(data.get('stop_loss', 0))

        # Validation
        if portfolio_value <= 0:
            return jsonify({'success': False, 'error': 'Portfolio value must be positive'}), 400

        if risk_percent <= 0 or risk_percent > 10:
            return jsonify({'success': False, 'error': 'Risk percent must be between 0.1 and 10'}), 400

        if entry_price <= 0:
            return jsonify({'success': False, 'error': 'Entry price must be positive'}), 400

        if stop_loss >= entry_price:
            return jsonify({'success': False, 'error': 'Stop loss must be below entry price'}), 400

        # Calculate position size
        risk_amount = portfolio_value * (risk_percent / 100)
        risk_per_share = entry_price - stop_loss
        quantity = int(risk_amount / risk_per_share)

        # Calculate metrics
        total_investment = quantity * entry_price
        position_percent = (total_investment / portfolio_value) * 100

        # Calculate breakeven with 0.1% commission
        commission = total_investment * 0.001
        breakeven_price = (total_investment + commission) / quantity

        position = {
            'quantity': quantity,
            'total_investment': round(total_investment, 2),
            'risk_amount': round(risk_amount, 2),
            'position_percent': round(position_percent, 2),
            'breakeven_price': round(breakeven_price, 2)
        }

        return jsonify({
            'success': True,
            'position': position
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_calc_ext_bp.route('/ai-suggestions', methods=['POST'])
def get_ai_suggestions():
    """
    Get AI-suggested stop loss and targets based on pattern analysis

    Request Body:
    {
        "symbol": "RELIANCE",
        "entry_price": 2450.50,
        "analysis_id": "60a1b2c3d4e5f6g7h8i9j0k1"
    }

    Response:
    {
        "success": true,
        "suggestions": {
            "stop_loss": 2400.00,
            "stop_loss_reason": "Below pattern support at 2405",
            "targets": [
                {"level": "T1", "price": 2500.00, "rr_ratio": 1.5},
                {"level": "T2", "price": 2550.00, "rr_ratio": 2.5},
                {"level": "T3", "price": 2600.00, "rr_ratio": 3.0}
            ]
        }
    }
    """
    try:
        data = request.get_json()

        symbol = data.get('symbol')
        entry_price = float(data.get('entry_price', 0))
        analysis_id = data.get('analysis_id')

        if not analysis_id:
            # If no analysis ID, calculate based on entry price only
            stop_loss = entry_price * 0.97  # 3% stop loss
            risk = entry_price - stop_loss

            suggestions = {
                'stop_loss': round(stop_loss, 2),
                'stop_loss_reason': 'Default 3% stop loss',
                'targets': [
                    {
                        'level': 'T1',
                        'price': round(entry_price + (risk * 1.5), 2),
                        'rr_ratio': 1.5
                    },
                    {
                        'level': 'T2',
                        'price': round(entry_price + (risk * 2.5), 2),
                        'rr_ratio': 2.5
                    },
                    {
                        'level': 'T3',
                        'price': round(entry_price + (risk * 3.5), 2),
                        'rr_ratio': 3.5
                    }
                ]
            }

            return jsonify({
                'success': True,
                'suggestions': suggestions
            }), 200

        # Fetch pattern analysis
        try:
            analysis = db.pattern_analysis.find_one({'_id': ObjectId(analysis_id)})
        except:
            analysis = None

        if not analysis:
            return jsonify({
                'success': False,
                'error': 'Analysis not found'
            }), 404

        # Extract suggestions from analysis
        classical = analysis.get('classical_patterns', {})
        price_action = analysis.get('price_action', {})

        # Use pattern-based stop loss
        suggested_stop_loss = classical.get('suggested_stop_loss', entry_price * 0.97)

        # Get support level for stop loss reason
        support_levels = price_action.get('support_levels', [])
        if support_levels:
            stop_loss_reason = f"Below support at ₹{support_levels[0]:.2f}"
        else:
            stop_loss_reason = "Pattern-based stop loss"

        # Calculate risk
        risk = entry_price - suggested_stop_loss

        # Generate targets
        targets = []
        for i, multiplier in enumerate([1.5, 2.5, 3.5], 1):
            target_price = entry_price + (risk * multiplier)
            targets.append({
                'level': f'T{i}',
                'price': round(target_price, 2),
                'rr_ratio': multiplier
            })

        suggestions = {
            'stop_loss': round(suggested_stop_loss, 2),
            'stop_loss_reason': stop_loss_reason,
            'targets': targets
        }

        return jsonify({
            'success': True,
            'suggestions': suggestions
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_calc_ext_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_extended',
        'status': 'healthy'
    }), 200
