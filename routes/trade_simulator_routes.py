"""
Trade Simulator Routes
Endpoints for logging and tracking paper trades
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from bson import ObjectId
from datetime import datetime, timedelta
import secrets

trade_simulator_bp = Blueprint('trade_simulator', __name__, url_prefix='/api/trade-simulator')


def generate_trade_id(user_id: str) -> str:
    """Generate unique trade ID"""
    date_str = datetime.now().strftime('%Y%m%d')
    random_suffix = secrets.token_hex(3).upper()
    return f"TR-{date_str}-{random_suffix}"


@trade_simulator_bp.route('/log-trade', methods=['POST'])
@jwt_required()
def log_trade():
    """
    Log a new simulated trade

    Request Body:
    {
        "symbol": "RELIANCE",
        "entry_price": 2450.50,
        "quantity": 40,
        "stop_loss": 2400.00,
        "targets": [2500, 2550, 2600],
        "portfolio_value": 100000,
        "risk_percent": 2,
        "pattern_analysis_id": "...",
        "notes": "Cup and Handle breakout",
        "tags": ["swing", "breakout"]
    }

    Response:
    {
        "success": true,
        "trade": {...},
        "trade_id": "TR-20260130-A1B2C3"
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Validate required fields
        required = ['symbol', 'entry_price', 'quantity', 'stop_loss', 'targets', 'portfolio_value', 'risk_percent']
        for field in required:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'}), 400

        # Generate trade ID
        trade_id = generate_trade_id(user_id)

        # Get pattern analysis if provided
        ai_confidence = 0
        primary_pattern = 'N/A'
        signal_type = 'NEUTRAL'

        if 'pattern_analysis_id' in data and data['pattern_analysis_id']:
            try:
                analysis = db.pattern_analysis.find_one({'_id': ObjectId(data['pattern_analysis_id'])})
                if analysis:
                    combined = analysis.get('combined_analysis', {})
                    ai_confidence = combined.get('score', 0)
                    signal_type = combined.get('signal', 'NEUTRAL')

                    classical = analysis.get('classical_patterns', {})
                    patterns = classical.get('detected_patterns', [])
                    if patterns:
                        primary_pattern = patterns[0].get('name', 'N/A')
            except:
                pass

        # Calculate metrics
        entry_price = float(data['entry_price'])
        quantity = int(data['quantity'])
        stop_loss = float(data['stop_loss'])
        portfolio_value = float(data['portfolio_value'])
        risk_percent = float(data['risk_percent'])

        total_investment = entry_price * quantity
        risk_amount = (entry_price - stop_loss) * quantity
        stop_loss_percent = ((entry_price - stop_loss) / entry_price) * 100
        position_size_percent = (total_investment / portfolio_value) * 100

        # Process targets
        targets = []
        for i, target_price in enumerate(data['targets'], 1):
            if target_price > 0:
                percent_gain = ((target_price - entry_price) / entry_price) * 100
                targets.append({
                    'level': i,
                    'price': float(target_price),
                    'percent_gain': round(percent_gain, 2),
                    'quantity_to_exit': quantity // len(data['targets']),
                    'hit': False,
                    'hit_date': None
                })

        # Calculate risk-reward ratio
        risk_reward_ratio = 0
        if targets:
            reward = targets[0]['price'] - entry_price
            risk = entry_price - stop_loss
            if risk > 0:
                risk_reward_ratio = reward / risk

        # Create trade document
        trade_doc = {
            'trade_id': trade_id,
            'user_id': user_id,
            'symbol': data['symbol'],
            'company_name': data['symbol'],  # TODO: Fetch actual name
            'exchange': 'NSE',
            'entry_date': datetime.now(),
            'entry_price': entry_price,
            'quantity': quantity,
            'total_investment': round(total_investment, 2),
            'entry_type': 'MARKET',
            'stop_loss': stop_loss,
            'stop_loss_percent': round(stop_loss_percent, 2),
            'targets': targets,
            'trailing_stop': False,
            'trailing_stop_percent': 0,
            'portfolio_value_at_entry': portfolio_value,
            'risk_percent': risk_percent,
            'risk_amount': round(risk_amount, 2),
            'position_size_percent': round(position_size_percent, 2),
            'risk_reward_ratio': round(risk_reward_ratio, 2),
            'expected_value': 0,
            'breakeven_price': round(entry_price * 1.001, 2),
            'pattern_analysis_id': data.get('pattern_analysis_id'),
            'ai_confidence_score': ai_confidence,
            'primary_pattern': primary_pattern,
            'signal_type': signal_type,
            'tags': data.get('tags', []),
            'strategy': data.get('strategy', ''),
            'notes': data.get('notes', ''),
            'status': 'OPEN',
            'current_price': entry_price,
            'unrealized_pnl': 0,
            'unrealized_pnl_percent': 0,
            'days_in_trade': 0,
            'trade_log': [{
                'timestamp': datetime.now(),
                'action': 'ENTRY',
                'details': {
                    'entry_price': entry_price,
                    'quantity': quantity
                },
                'price_at_action': entry_price
            }],
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }

        # Insert into database
        result = db.simulated_trades.insert_one(trade_doc)
        trade_doc['_id'] = str(result.inserted_id)

        return jsonify({
            'success': True,
            'trade': trade_doc,
            'trade_id': trade_id,
            'message': 'Trade logged successfully!'
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@trade_simulator_bp.route('/active-positions', methods=['GET'])
@jwt_required()
def get_active_positions():
    """
    Get all active positions for user

    Response:
    {
        "success": true,
        "positions": [...],
        "total_positions": 5,
        "total_unrealized_pnl": 12500
    }
    """
    try:
        user_id = get_jwt_identity()

        # Fetch open trades
        trades = list(db.simulated_trades.find({
            'user_id': user_id,
            'status': 'OPEN'
        }).sort('entry_date', -1))

        # Convert ObjectId to string and update metrics
        total_unrealized_pnl = 0
        for trade in trades:
            trade['_id'] = str(trade['_id'])

            # Calculate days in trade
            days_in_trade = (datetime.now() - trade['entry_date']).days
            trade['days_in_trade'] = days_in_trade

            # Update current price (in real scenario, fetch live price)
            # For now, keep it same as entry
            trade['current_price'] = trade['entry_price']
            trade['unrealized_pnl'] = 0
            trade['unrealized_pnl_percent'] = 0

            total_unrealized_pnl += trade['unrealized_pnl']

        return jsonify({
            'success': True,
            'positions': trades,
            'total_positions': len(trades),
            'total_unrealized_pnl': round(total_unrealized_pnl, 2)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@trade_simulator_bp.route('/update-trade/<trade_id>', methods=['PUT'])
@jwt_required()
def update_trade(trade_id):
    """
    Update trade parameters

    Request Body:
    {
        "stop_loss": 2420.00,
        "targets": [2510, 2560, 2610],
        "trailing_stop": true,
        "trailing_stop_percent": 5
    }

    Response:
    {
        "success": true,
        "message": "Trade updated successfully"
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        # Find trade
        trade = db.simulated_trades.find_one({
            'trade_id': trade_id,
            'user_id': user_id,
            'status': 'OPEN'
        })

        if not trade:
            return jsonify({'success': False, 'error': 'Trade not found'}), 404

        # Prepare updates
        update_fields = {'updated_at': datetime.now()}
        log_entry = {
            'timestamp': datetime.now(),
            'action': 'PARAMETERS_UPDATED',
            'details': {},
            'price_at_action': trade['current_price']
        }

        if 'stop_loss' in data:
            update_fields['stop_loss'] = float(data['stop_loss'])
            log_entry['details']['new_stop_loss'] = float(data['stop_loss'])

        if 'targets' in data:
            targets = []
            for i, price in enumerate(data['targets'], 1):
                if price > 0:
                    percent_gain = ((price - trade['entry_price']) / trade['entry_price']) * 100
                    targets.append({
                        'level': i,
                        'price': float(price),
                        'percent_gain': round(percent_gain, 2),
                        'quantity_to_exit': trade['quantity'] // len(data['targets']),
                        'hit': False,
                        'hit_date': None
                    })
            update_fields['targets'] = targets
            log_entry['details']['new_targets'] = [float(p) for p in data['targets']]

        if 'trailing_stop' in data:
            update_fields['trailing_stop'] = bool(data['trailing_stop'])
            update_fields['trailing_stop_percent'] = float(data.get('trailing_stop_percent', 0))
            log_entry['details']['trailing_stop'] = bool(data['trailing_stop'])

        # Update trade
        db.simulated_trades.update_one(
            {'trade_id': trade_id},
            {
                '$set': update_fields,
                '$push': {'trade_log': log_entry}
            }
        )

        return jsonify({
            'success': True,
            'message': 'Trade updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@trade_simulator_bp.route('/close-position', methods=['POST'])
@jwt_required()
def close_position():
    """
    Close a trade

    Request Body:
    {
        "trade_id": "TR-20260130-A1B2C3",
        "exit_price": 2520.00,
        "exit_type": "MANUAL",
        "notes": "Target hit"
    }

    Response:
    {
        "success": true,
        "message": "Position closed successfully",
        "realized_pnl": 2780,
        "realized_pnl_percent": 2.84
    }
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        trade_id = data.get('trade_id')
        exit_price = float(data.get('exit_price', 0))
        exit_type = data.get('exit_type', 'MANUAL')

        # Find trade
        trade = db.simulated_trades.find_one({
            'trade_id': trade_id,
            'user_id': user_id,
            'status': 'OPEN'
        })

        if not trade:
            return jsonify({'success': False, 'error': 'Trade not found or already closed'}), 404

        # Calculate P&L
        realized_pnl = (exit_price - trade['entry_price']) * trade['quantity']
        realized_pnl_percent = ((exit_price - trade['entry_price']) / trade['entry_price']) * 100

        # Calculate actual risk-reward
        risk = trade['entry_price'] - trade['stop_loss']
        reward = exit_price - trade['entry_price']
        actual_risk_reward = reward / risk if risk > 0 else 0

        # Determine pattern outcome
        pattern_outcome = 'SUCCESS' if realized_pnl > 0 else 'FAILURE'
        pattern_accuracy = any(target['price'] <= exit_price for target in trade['targets'])

        # Update trade
        db.simulated_trades.update_one(
            {'trade_id': trade_id},
            {
                '$set': {
                    'status': 'CLOSED',
                    'exit_date': datetime.now(),
                    'exit_price': exit_price,
                    'exit_type': exit_type,
                    'realized_pnl': round(realized_pnl, 2),
                    'realized_pnl_percent': round(realized_pnl_percent, 2),
                    'actual_risk_reward': round(actual_risk_reward, 2),
                    'pattern_outcome': pattern_outcome,
                    'pattern_accuracy': pattern_accuracy,
                    'closed_at': datetime.now(),
                    'updated_at': datetime.now()
                },
                '$push': {
                    'trade_log': {
                        'timestamp': datetime.now(),
                        'action': 'FULL_EXIT',
                        'details': {
                            'exit_price': exit_price,
                            'exit_type': exit_type,
                            'realized_pnl': round(realized_pnl, 2),
                            'notes': data.get('notes', '')
                        },
                        'price_at_action': exit_price
                    }
                }
            }
        )

        return jsonify({
            'success': True,
            'message': 'Position closed successfully',
            'realized_pnl': round(realized_pnl, 2),
            'realized_pnl_percent': round(realized_pnl_percent, 2)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@trade_simulator_bp.route('/trade-journal', methods=['GET'])
@jwt_required()
def get_trade_journal():
    """
    Get trade journal with filters

    Query Params:
        status: 'OPEN' or 'CLOSED'
        symbol: Stock symbol
        pattern: Pattern name
        start_date: ISO date string
        end_date: ISO date string

    Response:
    {
        "success": true,
        "trades": [...],
        "total": 25
    }
    """
    try:
        user_id = get_jwt_identity()

        # Build query
        query = {'user_id': user_id}

        status = request.args.get('status')
        if status:
            query['status'] = status

        symbol = request.args.get('symbol')
        if symbol:
            query['symbol'] = symbol

        pattern = request.args.get('pattern')
        if pattern:
            query['primary_pattern'] = pattern

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        if start_date and end_date:
            query['entry_date'] = {
                '$gte': datetime.fromisoformat(start_date),
                '$lte': datetime.fromisoformat(end_date)
            }

        # Fetch trades
        trades = list(db.simulated_trades.find(query).sort('entry_date', -1))

        # Convert ObjectId to string
        for trade in trades:
            trade['_id'] = str(trade['_id'])

        return jsonify({
            'success': True,
            'trades': trades,
            'total': len(trades)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@trade_simulator_bp.route('/performance-analytics', methods=['GET'])
@jwt_required()
def get_performance_analytics():
    """
    Get performance analytics

    Response:
    {
        "success": true,
        "analytics": {
            "total_trades": 25,
            "win_rate": 68.5,
            "profit_factor": 2.3,
            ...
        }
    }
    """
    try:
        user_id = get_jwt_identity()

        # Fetch closed trades
        closed_trades = list(db.simulated_trades.find({
            'user_id': user_id,
            'status': 'CLOSED'
        }))

        if not closed_trades:
            return jsonify({
                'success': True,
                'analytics': {
                    'total_trades': 0,
                    'message': 'No closed trades yet'
                }
            }), 200

        # Calculate metrics
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t['realized_pnl'] > 0]
        losing_trades = [t for t in closed_trades if t['realized_pnl'] < 0]

        win_rate = (len(winning_trades) / total_trades) * 100

        total_gains = sum(t['realized_pnl'] for t in winning_trades)
        total_losses = abs(sum(t['realized_pnl'] for t in losing_trades))
        profit_factor = total_gains / total_losses if total_losses > 0 else float('inf')

        avg_win = total_gains / len(winning_trades) if winning_trades else 0
        avg_loss = total_losses / len(losing_trades) if losing_trades else 0

        # Best and worst trades
        best_trade = max(closed_trades, key=lambda t: t['realized_pnl'])
        worst_trade = min(closed_trades, key=lambda t: t['realized_pnl'])

        # Equity curve
        equity_curve = []
        cumulative_pnl = 0
        for trade in sorted(closed_trades, key=lambda t: t['closed_at']):
            cumulative_pnl += trade['realized_pnl']
            equity_curve.append({
                'date': trade['closed_at'].isoformat(),
                'pnl': round(cumulative_pnl, 2)
            })

        # Pattern performance
        pattern_performance = {}
        for trade in closed_trades:
            pattern = trade.get('primary_pattern', 'Unknown')
            if pattern not in pattern_performance:
                pattern_performance[pattern] = {
                    'total': 0,
                    'wins': 0,
                    'losses': 0,
                    'total_pnl': 0
                }

            pattern_performance[pattern]['total'] += 1
            if trade['realized_pnl'] > 0:
                pattern_performance[pattern]['wins'] += 1
            else:
                pattern_performance[pattern]['losses'] += 1
            pattern_performance[pattern]['total_pnl'] += trade['realized_pnl']

        # Calculate win rate per pattern
        for pattern in pattern_performance:
            stats = pattern_performance[pattern]
            stats['win_rate'] = (stats['wins'] / stats['total']) * 100 if stats['total'] > 0 else 0

        analytics = {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'total_pnl': round(sum(t['realized_pnl'] for t in closed_trades), 2),
            'total_gains': round(total_gains, 2),
            'total_losses': round(total_losses, 2),
            'average_win': round(avg_win, 2),
            'average_loss': round(avg_loss, 2),
            'best_trade': {
                'symbol': best_trade['symbol'],
                'pnl': round(best_trade['realized_pnl'], 2),
                'date': best_trade['closed_at'].isoformat()
            },
            'worst_trade': {
                'symbol': worst_trade['symbol'],
                'pnl': round(worst_trade['realized_pnl'], 2),
                'date': worst_trade['closed_at'].isoformat()
            },
            'equity_curve': equity_curve,
            'pattern_performance': pattern_performance
        }

        return jsonify({
            'success': True,
            'analytics': analytics
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@trade_simulator_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'trade_simulator',
        'status': 'healthy'
    }), 200
