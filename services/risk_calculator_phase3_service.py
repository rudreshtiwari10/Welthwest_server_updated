"""
Risk Calculator Phase 3: Session-Level Risk & Behavior Tracking Service

Tracks intraday trading behavior and detects patterns like overtrading,
revenge trading, and position sizing anomalies.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
from database import db

class RiskCalculatorPhase3Service:
    """Service for session-level risk and behavior tracking"""

    def __init__(self):
        self.sessions_collection = db['risk_calculator_sessions']
        self.trades_collection = db['risk_calculator_trades']

    def get_or_create_session(self, user_id: str) -> Dict[str, Any]:
        """Get today's session or create a new one"""
        try:
            # Get today's date (start of day)
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

            # Find existing session for today
            session = self.sessions_collection.find_one({
                'user_id': user_id,
                'session_date': today
            })

            if session:
                return session

            # Create new session
            new_session = {
                'user_id': user_id,
                'session_date': today,
                'session_start': datetime.now(),
                'session_end': None,
                'trades_count': 0,
                'total_capital_deployed': 0,
                'total_risk_amount': 0,
                'gross_pnl': 0,
                'net_pnl': 0,
                'total_costs': 0,
                'behavior_flags': {
                    'overtrading': False,
                    'revenge_trading': False,
                    'position_sizing_anomaly': False,
                    'profit_target_violation': False,
                    'loss_limit_violation': False
                },
                'behavior_events': [],
                'avg_trade_duration_minutes': 0,
                'longest_winning_streak': 0,
                'longest_losing_streak': 0,
                'current_streak': {
                    'type': 'neutral',
                    'count': 0
                },
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }

            result = self.sessions_collection.insert_one(new_session)
            new_session['_id'] = result.inserted_id

            return new_session

        except Exception as e:
            raise Exception(f"Error getting/creating session: {str(e)}")

    def update_session_on_trade(self, user_id: str, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update session when a new trade is logged"""
        try:
            session = self.get_or_create_session(user_id)

            # Get user settings for behavior checks
            user_settings = db['risk_calculator_settings'].find_one({'user_id': user_id}) or {}

            # Update basic metrics
            updates = {
                'trades_count': session['trades_count'] + 1,
                'total_capital_deployed': session['total_capital_deployed'] + trade_data.get('position_size', 0),
                'total_risk_amount': session['total_risk_amount'] + trade_data.get('risk_amount', 0),
                'total_costs': session['total_costs'] + trade_data.get('total_cost', 0),
                'updated_at': datetime.now()
            }

            # Check for behavior patterns
            behavior_events = list(session.get('behavior_events', []))
            behavior_flags = session.get('behavior_flags', {}).copy()

            # Check overtrading
            if self._check_overtrading(session, user_settings):
                behavior_flags['overtrading'] = True
                behavior_events.append({
                    'timestamp': datetime.now(),
                    'event_type': 'overtrading',
                    'description': f"Trade #{updates['trades_count']} exceeds daily limit",
                    'trade_id': trade_data.get('_id')
                })

            # Check revenge trading
            if self._check_revenge_trading(user_id, session):
                behavior_flags['revenge_trading'] = True
                behavior_events.append({
                    'timestamp': datetime.now(),
                    'event_type': 'revenge_trading',
                    'description': "Trade placed within 15 minutes of a loss",
                    'trade_id': trade_data.get('_id')
                })

            # Check position sizing anomaly
            if self._check_position_sizing_anomaly(session, trade_data):
                behavior_flags['position_sizing_anomaly'] = True
                behavior_events.append({
                    'timestamp': datetime.now(),
                    'event_type': 'position_sizing_anomaly',
                    'description': "Position size increased by 2x or more",
                    'trade_id': trade_data.get('_id')
                })

            updates['behavior_flags'] = behavior_flags
            updates['behavior_events'] = behavior_events

            # Update session
            self.sessions_collection.update_one(
                {'_id': session['_id']},
                {'$set': updates}
            )

            # Return updated session
            return self.sessions_collection.find_one({'_id': session['_id']})

        except Exception as e:
            raise Exception(f"Error updating session on trade: {str(e)}")

    def update_session_on_trade_close(self, user_id: str, trade_id: str,
                                       exit_price: float, exit_timestamp: datetime) -> Dict[str, Any]:
        """Update session when a trade is closed"""
        try:
            # Get trade details
            trade = self.trades_collection.find_one({'_id': ObjectId(trade_id)})
            if not trade:
                raise Exception("Trade not found")

            # Calculate actual P&L
            entry_price = trade.get('entry_price', 0)
            quantity = trade.get('quantity', 0)
            trade_type = trade.get('trade_type', 'long')

            if trade_type == 'long':
                actual_pnl = (exit_price - entry_price) * quantity
            else:
                actual_pnl = (entry_price - exit_price) * quantity

            # Calculate trade duration
            entry_timestamp = trade.get('created_at', datetime.now())
            duration_minutes = (exit_timestamp - entry_timestamp).total_seconds() / 60

            # Update trade record
            self.trades_collection.update_one(
                {'_id': ObjectId(trade_id)},
                {'$set': {
                    'exit_price': exit_price,
                    'exit_timestamp': exit_timestamp,
                    'actual_pnl': actual_pnl,
                    'trade_duration_minutes': duration_minutes,
                    'updated_at': datetime.now()
                }}
            )

            # Update session
            session = self.get_or_create_session(user_id)

            # Update P&L
            updates = {
                'gross_pnl': session.get('gross_pnl', 0) + actual_pnl,
                'net_pnl': session.get('net_pnl', 0) + actual_pnl - trade.get('total_cost', 0),
                'updated_at': datetime.now()
            }

            # Update streaks
            updated_session = self._update_streaks(session, actual_pnl)
            updates['current_streak'] = updated_session['current_streak']
            updates['longest_winning_streak'] = updated_session['longest_winning_streak']
            updates['longest_losing_streak'] = updated_session['longest_losing_streak']

            # Update average trade duration
            closed_trades = list(self.trades_collection.find({
                'user_id': user_id,
                'session_id': session['_id'],
                'exit_timestamp': {'$ne': None}
            }))

            if closed_trades:
                total_duration = sum(t.get('trade_duration_minutes', 0) for t in closed_trades)
                updates['avg_trade_duration_minutes'] = total_duration / len(closed_trades)

            self.sessions_collection.update_one(
                {'_id': session['_id']},
                {'$set': updates}
            )

            return self.sessions_collection.find_one({'_id': session['_id']})

        except Exception as e:
            raise Exception(f"Error updating session on trade close: {str(e)}")

    def get_session_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive session dashboard data"""
        try:
            session = self.get_or_create_session(user_id)
            user_settings = db['risk_calculator_settings'].find_one({'user_id': user_id}) or {}

            # Calculate additional metrics
            max_trades = user_settings.get('max_trades_per_day', 10)
            max_daily_loss = user_settings.get('max_daily_loss', 0)

            trades_remaining = max(0, max_trades - session.get('trades_count', 0))
            loss_utilization_percent = 0

            if max_daily_loss > 0:
                current_loss = abs(min(0, session.get('net_pnl', 0)))
                loss_utilization_percent = (current_loss / max_daily_loss) * 100

            # Generate nudges based on behavior
            nudges = []

            if session['behavior_flags'].get('overtrading'):
                nudges.append({
                    'type': 'warning',
                    'title': 'Overtrading Detected',
                    'message': f"You've reached {session['trades_count']} trades today. Consider taking a break."
                })

            if session['behavior_flags'].get('revenge_trading'):
                nudges.append({
                    'type': 'warning',
                    'title': 'Potential Revenge Trading',
                    'message': "You placed a trade shortly after a loss. Take a moment to review your strategy."
                })

            if session['behavior_flags'].get('position_sizing_anomaly'):
                nudges.append({
                    'type': 'warning',
                    'title': 'Position Size Anomaly',
                    'message': "Your position size has increased significantly. Ensure this aligns with your risk management."
                })

            if loss_utilization_percent > 75:
                nudges.append({
                    'type': 'danger',
                    'title': 'Daily Loss Limit Warning',
                    'message': f"You've used {loss_utilization_percent:.1f}% of your daily loss limit."
                })

            dashboard = {
                'session': {
                    'date': session['session_date'].strftime('%Y-%m-%d'),
                    'trades_count': session.get('trades_count', 0),
                    'max_trades': max_trades,
                    'trades_remaining': trades_remaining,
                    'total_capital_deployed': session.get('total_capital_deployed', 0),
                    'total_risk_amount': session.get('total_risk_amount', 0),
                    'gross_pnl': session.get('gross_pnl', 0),
                    'net_pnl': session.get('net_pnl', 0),
                    'total_costs': session.get('total_costs', 0),
                    'loss_utilization_percent': loss_utilization_percent,
                    'avg_trade_duration_minutes': session.get('avg_trade_duration_minutes', 0),
                    'current_streak': session.get('current_streak', {'type': 'neutral', 'count': 0}),
                    'longest_winning_streak': session.get('longest_winning_streak', 0),
                    'longest_losing_streak': session.get('longest_losing_streak', 0)
                },
                'behavior_flags': session.get('behavior_flags', {}),
                'behavior_events': session.get('behavior_events', []),
                'nudges': nudges,
                'disclaimer': "This is an analytical tool based on your own trading rules. It does not provide investment advice."
            }

            return dashboard

        except Exception as e:
            raise Exception(f"Error getting session dashboard: {str(e)}")

    def get_behavior_history(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """Get historical behavior patterns"""
        try:
            start_date = datetime.now() - timedelta(days=days)

            sessions = list(self.sessions_collection.find({
                'user_id': user_id,
                'session_date': {'$gte': start_date}
            }).sort('session_date', -1))

            # Aggregate behavior patterns
            total_sessions = len(sessions)
            overtrading_count = sum(1 for s in sessions if s.get('behavior_flags', {}).get('overtrading', False))
            revenge_trading_count = sum(1 for s in sessions if s.get('behavior_flags', {}).get('revenge_trading', False))
            position_anomaly_count = sum(1 for s in sessions if s.get('behavior_flags', {}).get('position_sizing_anomaly', False))

            return {
                'period_days': days,
                'total_sessions': total_sessions,
                'sessions': sessions,
                'behavior_summary': {
                    'overtrading_sessions': overtrading_count,
                    'revenge_trading_sessions': revenge_trading_count,
                    'position_anomaly_sessions': position_anomaly_count
                }
            }

        except Exception as e:
            raise Exception(f"Error getting behavior history: {str(e)}")

    # Private helper methods

    def _check_overtrading(self, session: Dict[str, Any], user_settings: Dict[str, Any]) -> bool:
        """Detect overtrading based on max trades per day"""
        max_trades = user_settings.get('max_trades_per_day', 10)
        return session.get('trades_count', 0) >= max_trades

    def _check_revenge_trading(self, user_id: str, session: Dict[str, Any]) -> bool:
        """Detect revenge trading (trade within 15 min of a loss)"""
        try:
            # Get recent trades in last 15 minutes
            fifteen_min_ago = datetime.now() - timedelta(minutes=15)

            recent_trades = list(self.trades_collection.find({
                'user_id': user_id,
                'session_id': session['_id'],
                'exit_timestamp': {'$ne': None},
                'exit_timestamp': {'$gte': fifteen_min_ago}
            }).sort('exit_timestamp', -1).limit(1))

            if recent_trades:
                last_trade = recent_trades[0]
                # Check if last trade was a loss
                if last_trade.get('actual_pnl', 0) < 0:
                    return True

            return False

        except Exception:
            return False

    def _check_position_sizing_anomaly(self, session: Dict[str, Any], trade_data: Dict[str, Any]) -> bool:
        """Detect 2x+ position size increase"""
        try:
            if session.get('trades_count', 0) == 0:
                return False

            # Get average position size from previous trades
            avg_position_size = session.get('total_capital_deployed', 0) / max(1, session.get('trades_count', 1))
            current_position_size = trade_data.get('position_size', 0)

            if avg_position_size > 0 and current_position_size >= (avg_position_size * 2):
                return True

            return False

        except Exception:
            return False

    def _update_streaks(self, session: Dict[str, Any], pnl: float) -> Dict[str, Any]:
        """Update winning/losing streaks"""
        current_streak = session.get('current_streak', {'type': 'neutral', 'count': 0}).copy()
        longest_winning_streak = session.get('longest_winning_streak', 0)
        longest_losing_streak = session.get('longest_losing_streak', 0)

        if pnl > 0:
            # Winning trade
            if current_streak['type'] == 'win':
                current_streak['count'] += 1
            else:
                current_streak = {'type': 'win', 'count': 1}

            longest_winning_streak = max(longest_winning_streak, current_streak['count'])

        elif pnl < 0:
            # Losing trade
            if current_streak['type'] == 'loss':
                current_streak['count'] += 1
            else:
                current_streak = {'type': 'loss', 'count': 1}

            longest_losing_streak = max(longest_losing_streak, current_streak['count'])

        return {
            **session,
            'current_streak': current_streak,
            'longest_winning_streak': longest_winning_streak,
            'longest_losing_streak': longest_losing_streak
        }


# Singleton instance
risk_phase3_service = RiskCalculatorPhase3Service()
