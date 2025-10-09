"""
Advanced Risk Management and Position Sizing
Implements Kelly Criterion and multi-objective optimization
"""
import numpy as np
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class RiskManagementEngine:
    """Enhanced Kelly Criterion and position sizing"""

    def __init__(self):
        logger.info("Risk Management Engine initialized")

    def calculate_position_size(self, capital: float, win_rate: float, avg_win: float,
                                 avg_loss: float, confidence: float, volatility: float,
                                 regime: str, max_risk_per_trade: float = 0.02) -> Dict:
        """
        Calculate optimal position size using Enhanced Kelly Criterion

        Args:
            capital: Available trading capital
            win_rate: Historical win rate (0-1)
            avg_win: Average win amount
            avg_loss: Average loss amount
            confidence: Model confidence (0-1)
            volatility: Current volatility
            regime: Market regime ('Low', 'Normal', 'High')
            max_risk_per_trade: Maximum risk per trade (0.01-0.05)

        Returns:
            Dictionary with position sizing details
        """
        try:
            # Traditional Kelly Formula
            win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 2.0
            kelly_percentage = win_rate - ((1 - win_rate) / win_loss_ratio)

            # Volatility adjustment
            baseline_volatility = 0.02  # 2% baseline
            volatility_adjustment = np.sqrt(baseline_volatility / max(volatility, 0.01))

            # Regime factor
            regime_factor = {
                'Low': 1.1,      # More aggressive in low volatility
                'Normal': 1.0,   # Standard sizing
                'High': 0.8      # Conservative in high volatility
            }.get(regime, 1.0)

            # Enhanced Kelly with adjustments
            enhanced_kelly = (kelly_percentage * confidence *
                              volatility_adjustment * regime_factor)

            # Apply safety constraints (never risk more than half Kelly)
            safe_kelly = min(enhanced_kelly * 0.5, max_risk_per_trade)
            safe_kelly = max(safe_kelly, 0.0)  # No negative positions

            # Calculate position size
            position_size = safe_kelly * capital

            # Calculate shares based on expected price
            shares = 0  # Will be calculated with entry price

            return {
                'position_size_value': float(position_size),
                'position_size_percentage': float(safe_kelly * 100),
                'kelly_percentage': float(kelly_percentage * 100),
                'enhanced_kelly': float(enhanced_kelly * 100),
                'safe_kelly': float(safe_kelly * 100),
                'volatility_adjustment': float(volatility_adjustment),
                'regime_factor': float(regime_factor),
                'max_risk_amount': float(position_size * max_risk_per_trade),
                'recommendation': self._get_position_recommendation(safe_kelly)
            }

        except Exception as e:
            logger.error(f"Error calculating position size: {str(e)}")
            return {
                'position_size_value': capital * 0.02,
                'position_size_percentage': 2.0,
                'kelly_percentage': 0.0,
                'enhanced_kelly': 0.0,
                'safe_kelly': 2.0,
                'volatility_adjustment': 1.0,
                'regime_factor': 1.0,
                'max_risk_amount': capital * 0.02 * 0.02,
                'recommendation': 'Use conservative position sizing'
            }

    def calculate_stop_loss(self, entry_price: float, atr: float, support_level: float,
                            volatility: float, stop_type: str = 'atr_based',
                            regime: str = 'Normal') -> Dict:
        """
        Calculate optimal stop-loss levels

        Args:
            entry_price: Entry price for the trade
            atr: Average True Range value
            support_level: Nearest support level
            volatility: Current volatility
            stop_type: Type of stop-loss ('fixed', 'atr_based', 'support_based', 'volatility_based')
            regime: Market regime

        Returns:
            Dictionary with stop-loss levels
        """
        try:
            # Calculate different stop-loss types
            stops = {}

            # Fixed percentage stop
            stops['fixed'] = entry_price * 0.97  # 3% below entry

            # ATR-based stop
            atr_multiplier = {'Low': 1.5, 'Normal': 2.0, 'High': 2.5}.get(regime, 2.0)
            stops['atr_based'] = entry_price - (atr * atr_multiplier)

            # Support-based stop
            stops['support_based'] = support_level * 0.995  # Slightly below support

            # Volatility-based stop
            vol_multiplier = 2.0
            stops['volatility_based'] = entry_price - (entry_price * volatility * vol_multiplier)

            # Select optimal stop-loss
            optimal_stop = stops.get(stop_type, stops['atr_based'])

            # Ensure stop-loss is reasonable (not more than 10% below entry)
            min_stop = entry_price * 0.90
            optimal_stop = max(optimal_stop, min_stop)

            return {
                'optimal_stop_loss': float(optimal_stop),
                'stop_loss_percentage': float((entry_price - optimal_stop) / entry_price * 100),
                'all_stops': {k: float(v) for k, v in stops.items()},
                'stop_type': stop_type,
                'trailing_activation': entry_price * 1.02,  # Activate trailing at 2% profit
                'trailing_distance': atr * atr_multiplier
            }

        except Exception as e:
            logger.error(f"Error calculating stop-loss: {str(e)}")
            return {
                'optimal_stop_loss': entry_price * 0.97,
                'stop_loss_percentage': 3.0,
                'all_stops': {},
                'stop_type': 'fixed',
                'trailing_activation': entry_price * 1.02,
                'trailing_distance': entry_price * 0.02
            }

    def calculate_take_profit(self, entry_price: float, expected_move: float,
                               confidence: float, resistance_level: float) -> Dict:
        """
        Calculate take-profit targets using Fibonacci levels

        Args:
            entry_price: Entry price
            expected_move: Expected price move (as decimal)
            confidence: Model confidence
            resistance_level: Key resistance level

        Returns:
            Dictionary with take-profit targets
        """
        try:
            # Fibonacci-based targets
            targets = {
                'T1': entry_price * (1 + 0.618 * expected_move),
                'T2': entry_price * (1 + 1.000 * expected_move),
                'T3': entry_price * (1 + 1.618 * expected_move)
            }

            # Probability-weighted targets
            probabilities = {
                'P_T1': confidence * 0.85,
                'P_T2': confidence * 0.60,
                'P_T3': confidence * 0.35
            }

            # Partial exit strategy
            partial_exits = {
                'T1_reached': '50% of position',
                'T2_reached': '30% of position',
                'T3_reached': 'Remaining 20%'
            }

            # Adjust targets if they exceed resistance
            if resistance_level > 0 and targets['T1'] > resistance_level:
                targets['T1'] = resistance_level * 0.99  # Just below resistance

            return {
                'targets': {k: float(v) for k, v in targets.items()},
                'probabilities': {k: float(v) for k, v in probabilities.items()},
                'partial_exits': partial_exits,
                'target_percentages': {
                    'T1': float((targets['T1'] - entry_price) / entry_price * 100),
                    'T2': float((targets['T2'] - entry_price) / entry_price * 100),
                    'T3': float((targets['T3'] - entry_price) / entry_price * 100)
                },
                'expected_return': float(expected_move * 100)
            }

        except Exception as e:
            logger.error(f"Error calculating take-profit: {str(e)}")
            return {
                'targets': {'T1': entry_price * 1.05, 'T2': entry_price * 1.10, 'T3': entry_price * 1.15},
                'probabilities': {'P_T1': 0.7, 'P_T2': 0.5, 'P_T3': 0.3},
                'partial_exits': {},
                'target_percentages': {'T1': 5.0, 'T2': 10.0, 'T3': 15.0},
                'expected_return': 10.0
            }

    def assess_risk_level(self, volatility: float, regime: str, pattern_confidence: float,
                          market_sentiment: float) -> Dict:
        """
        Comprehensive risk assessment

        Args:
            volatility: Current volatility
            regime: Market regime
            pattern_confidence: Pattern recognition confidence
            market_sentiment: Overall market sentiment

        Returns:
            Risk assessment dictionary
        """
        try:
            # Calculate risk score (0-10)
            risk_components = {
                'volatility': min(volatility * 100, 10),
                'regime': {'Low': 2, 'Normal': 5, 'High': 8}.get(regime, 5),
                'pattern_uncertainty': (1 - pattern_confidence) * 10,
                'sentiment_risk': abs(market_sentiment) * 5
            }

            # Weighted average
            weights = {'volatility': 0.35, 'regime': 0.30, 'pattern_uncertainty': 0.20, 'sentiment_risk': 0.15}
            risk_score = sum(risk_components[k] * weights[k] for k in risk_components)

            # Determine risk level
            if risk_score < 3.5:
                level = 'Low'
                description = 'Favorable conditions with stable market regime and high pattern confidence. Recommended position sizing: 3-5% of portfolio.'
            elif risk_score < 6.5:
                level = 'Medium'
                description = 'Moderate risk due to market volatility. The market shows mixed signals. Recommended position sizing: 2-3% of portfolio.'
            else:
                level = 'High'
                description = 'Elevated risk from high volatility or uncertain market conditions. Consider reducing position size. Recommended position sizing: 1-2% of portfolio.'

            return {
                'level': level,
                'score': float(risk_score),
                'description': description,
                'components': {k: float(v) for k, v in risk_components.items()},
                'recommendation': self._get_risk_recommendation(level)
            }

        except Exception as e:
            logger.error(f"Error assessing risk: {str(e)}")
            return {
                'level': 'Medium',
                'score': 5.0,
                'description': 'Unable to assess risk accurately. Use conservative position sizing.',
                'components': {},
                'recommendation': 'Trade with caution'
            }

    def _get_position_recommendation(self, kelly: float) -> str:
        """Get position sizing recommendation"""
        if kelly > 0.05:
            return 'Strong confidence - Consider larger position (up to 5% of portfolio)'
        elif kelly > 0.03:
            return 'Moderate confidence - Standard position size (2-3% of portfolio)'
        elif kelly > 0.01:
            return 'Low confidence - Small position size (1-2% of portfolio)'
        else:
            return 'Very low confidence - Consider skipping this trade'

    def _get_risk_recommendation(self, level: str) -> str:
        """Get risk-based recommendation"""
        if level == 'Low':
            return 'Favorable risk/reward - Consider full position size'
        elif level == 'Medium':
            return 'Moderate risk - Use standard position sizing with tight stops'
        else:
            return 'High risk - Reduce position size or wait for better setup'


# Singleton instance
risk_engine = RiskManagementEngine()
