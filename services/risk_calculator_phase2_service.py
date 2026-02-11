"""
Risk Calculator Phase 2 Service
Trade Checklist & Discipline Guardrails

SEBI-Safe: No trading advice, only analytics and user-defined rule tracking
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import ObjectId
import os


class RiskCalculatorPhase2Service:
    """
    Service for Phase 2: Trade discipline and behavior tracking
    All outputs are analytical, not advisory
    """

    def __init__(self):
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('DB_NAME', 'welthwest')
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.user_settings = self.db['risk_calculator_settings']
        self.trade_logs = self.db['risk_calculator_trades']

    def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Get user's risk management settings
        """
        settings = self.user_settings.find_one({'user_id': user_id})

        if not settings:
            # Default settings
            return {
                'user_id': user_id,
                'max_daily_loss_percent': 4.0,
                'max_trades_per_day': 5,
                'preferred_risk_reward_min': 1.5,
                'max_risk_per_trade_percent': 2.0,
                'capital_baseline': 100000,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }

        return settings

    def update_user_settings(self, user_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update user's risk management settings
        """
        settings['user_id'] = user_id
        settings['updated_at'] = datetime.utcnow()

        result = self.user_settings.update_one(
            {'user_id': user_id},
            {'$set': settings},
            upsert=True
        )

        return self.get_user_settings(user_id)

    def calculate_trade_quality_score(
        self,
        risk_reward_ratio: float,
        risk_per_trade_percent: float,
        user_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate trade quality score based on user's own rules (not market prediction)
        Score: 0-10 based on adherence to user's preferences
        """
        score = 0
        max_score = 10
        factors = []

        # Factor 1: Risk:Reward ratio (0-4 points)
        preferred_rr = user_settings.get('preferred_risk_reward_min', 1.5)
        if risk_reward_ratio >= preferred_rr * 1.5:
            rr_score = 4
            factors.append("Excellent risk:reward ratio")
        elif risk_reward_ratio >= preferred_rr:
            rr_score = 3
            factors.append("Good risk:reward ratio")
        elif risk_reward_ratio >= 1.0:
            rr_score = 2
            factors.append("Acceptable risk:reward ratio")
        else:
            rr_score = 1
            factors.append("Risk:reward below your preference")

        score += rr_score

        # Factor 2: Risk per trade adherence (0-3 points)
        max_risk = user_settings.get('max_risk_per_trade_percent', 2.0)
        if risk_per_trade_percent <= max_risk * 0.7:
            risk_score = 3
            factors.append("Risk well within your limit")
        elif risk_per_trade_percent <= max_risk:
            risk_score = 2
            factors.append("Risk within your limit")
        elif risk_per_trade_percent <= max_risk * 1.2:
            risk_score = 1
            factors.append("Risk slightly above your limit")
        else:
            risk_score = 0
            factors.append("Risk exceeds your limit")

        score += risk_score

        # Factor 3: Position sizing reasonableness (0-3 points)
        # Conservative sizing gets higher score
        if risk_per_trade_percent <= 1.0:
            size_score = 3
            factors.append("Conservative position sizing")
        elif risk_per_trade_percent <= 2.0:
            size_score = 2
            factors.append("Moderate position sizing")
        else:
            size_score = 1
            factors.append("Aggressive position sizing")

        score += size_score

        # Determine quality level
        if score >= 8:
            quality_level = "Excellent"
            quality_color = "green"
        elif score >= 6:
            quality_level = "Good"
            quality_color = "blue"
        elif score >= 4:
            quality_level = "Acceptable"
            quality_color = "yellow"
        else:
            quality_level = "Needs Review"
            quality_color = "red"

        return {
            'score': score,
            'max_score': max_score,
            'quality_level': quality_level,
            'quality_color': quality_color,
            'factors': factors,
            'message': f"Trade quality score: {score}/{max_score} (based on your own rules)",
            'disclaimer': "This evaluates the risk profile of a trade you chose. It does not tell you whether to take the trade."
        }

    def get_daily_trades(self, user_id: str, date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Get all trades logged for a specific day
        """
        if date is None:
            date = datetime.utcnow()

        start_of_day = datetime(date.year, date.month, date.day, 0, 0, 0)
        end_of_day = start_of_day + timedelta(days=1)

        trades = list(self.trade_logs.find({
            'user_id': user_id,
            'timestamp': {'$gte': start_of_day, '$lt': end_of_day}
        }).sort('timestamp', -1))

        return trades

    def calculate_daily_risk_exposure(self, user_id: str) -> Dict[str, Any]:
        """
        Calculate current daily risk exposure based on logged trades
        """
        user_settings = self.get_user_settings(user_id)
        daily_trades = self.get_daily_trades(user_id)

        capital_baseline = user_settings.get('capital_baseline', 100000)
        max_daily_loss_percent = user_settings.get('max_daily_loss_percent', 4.0)
        max_trades_per_day = user_settings.get('max_trades_per_day', 5)

        # Calculate current exposure
        total_risk_amount = sum(trade.get('risk_amount', 0) for trade in daily_trades)
        total_risk_percent = (total_risk_amount / capital_baseline) * 100 if capital_baseline > 0 else 0

        trades_count = len(daily_trades)

        # Calculate realized P&L
        realized_pl = sum(trade.get('realized_pl', 0) for trade in daily_trades if trade.get('status') == 'closed')

        # Calculate warnings
        warnings = []

        # Risk exposure warning
        risk_utilization = (total_risk_percent / max_daily_loss_percent) * 100 if max_daily_loss_percent > 0 else 0
        if risk_utilization >= 80:
            warnings.append(f"You have reached {risk_utilization:.0f}% of your daily risk limit. Consider stopping for today.")
        elif risk_utilization >= 60:
            warnings.append(f"You have used {risk_utilization:.0f}% of your daily risk limit.")

        # Trade count warning
        if trades_count >= max_trades_per_day:
            warnings.append(f"You have reached your maximum trades per day ({max_trades_per_day}).")
        elif trades_count >= max_trades_per_day * 0.8:
            warnings.append(f"You have taken {trades_count} of your maximum {max_trades_per_day} trades today.")

        return {
            'trades_count': trades_count,
            'max_trades_per_day': max_trades_per_day,
            'total_risk_amount': round(total_risk_amount, 2),
            'total_risk_percent': round(total_risk_percent, 2),
            'max_daily_loss_percent': max_daily_loss_percent,
            'risk_utilization_percent': round(risk_utilization, 2),
            'realized_pl': round(realized_pl, 2),
            'warnings': warnings,
            'date': datetime.utcnow().strftime('%Y-%m-%d')
        }

    def log_trade(self, user_id: str, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Log a trade for tracking purposes (not execution)
        """
        trade_log = {
            'user_id': user_id,
            'symbol': trade_data.get('symbol'),
            'trade_type': trade_data.get('trade_type'),
            'entry_price': trade_data.get('entry_price'),
            'stop_loss': trade_data.get('stop_loss'),
            'target': trade_data.get('target'),
            'quantity': trade_data.get('quantity'),
            'risk_amount': trade_data.get('risk_amount'),
            'risk_percent': trade_data.get('risk_percent'),
            'expected_costs': trade_data.get('expected_costs'),
            'status': 'open',  # open, closed
            'realized_pl': None,
            'timestamp': datetime.utcnow(),
            'created_at': datetime.utcnow()
        }

        result = self.trade_logs.insert_one(trade_log)
        trade_log['_id'] = str(result.inserted_id)

        # Integrate with Phase 3: Update session tracking
        try:
            from services.risk_calculator_phase3_service import risk_phase3_service

            # Prepare data for session update
            session_trade_data = {
                '_id': result.inserted_id,
                'position_size': trade_data.get('quantity', 0) * trade_data.get('entry_price', 0),
                'risk_amount': trade_data.get('risk_amount', 0),
                'total_cost': trade_data.get('expected_costs', {}).get('total_cost', 0)
            }

            risk_phase3_service.update_session_on_trade(user_id, session_trade_data)
        except Exception as e:
            # Phase 3 integration is optional, don't fail the trade log if it fails
            print(f"Phase 3 integration warning: {str(e)}")

        return trade_log

    def generate_pre_trade_checklist(
        self,
        user_id: str,
        calculation_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate pre-trade checklist with key risk metrics
        SEBI-safe: purely informational, not directive
        """
        user_settings = self.get_user_settings(user_id)
        daily_exposure = self.calculate_daily_risk_exposure(user_id)

        # Extract key data
        risk_amount = calculation_result.get('risk_analysis', {}).get('risk_amount', 0)
        risk_percent = calculation_result.get('risk_analysis', {}).get('risk_percentage', 0)

        sl_loss = calculation_result.get('scenario_analysis', {}).get('at_stop_loss', {}).get('net_loss_after_costs', 0)
        target_gain = calculation_result.get('scenario_analysis', {}).get('at_target', {}).get('net_profit_after_costs', 0) if calculation_result.get('scenario_analysis', {}).get('at_target') else None

        # New total exposure if this trade is taken
        new_risk_percent = daily_exposure['total_risk_percent'] + risk_percent

        # Generate checklist items
        checklist = {
            'risk_metrics': {
                'risk_per_trade': {
                    'amount': round(risk_amount, 2),
                    'percent': round(risk_percent, 2),
                    'within_limit': risk_percent <= user_settings.get('max_risk_per_trade_percent', 2.0),
                    'message': f"Risk per trade: {risk_percent:.1f}% of your capital (your limit: {user_settings.get('max_risk_per_trade_percent', 2.0)}%)"
                },
                'stop_loss_impact': {
                    'amount': abs(sl_loss),
                    'message': f"If stop-loss hits, estimated loss (after costs): ₹{abs(sl_loss):,.2f}"
                },
                'target_impact': {
                    'amount': target_gain if target_gain else None,
                    'message': f"If target hits, estimated net gain (after costs): ₹{target_gain:,.2f}" if target_gain else "No target specified"
                },
                'daily_exposure': {
                    'current_percent': round(daily_exposure['total_risk_percent'], 2),
                    'after_trade_percent': round(new_risk_percent, 2),
                    'limit_percent': daily_exposure['max_daily_loss_percent'],
                    'message': f"This trade increases your daily risk exposure to {new_risk_percent:.1f}% (limit: {daily_exposure['max_daily_loss_percent']}%)"
                }
            },
            'daily_status': {
                'trades_today': daily_exposure['trades_count'],
                'max_trades': daily_exposure['max_trades_per_day'],
                'risk_utilization': round(daily_exposure['risk_utilization_percent'], 1)
            },
            'warnings': daily_exposure['warnings'],
            'disclaimer': "This is a risk and cost illustration based on your own rules. It is not a recommendation to take or avoid this trade."
        }

        return checklist


# Singleton instance
risk_phase2_service = RiskCalculatorPhase2Service()
