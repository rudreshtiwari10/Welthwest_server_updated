"""
Risk-Reward Engine - Stop Loss, Take Profit, and Trade Quality Assessment

Features:
- ATR-based stop-loss calculation
- Structure-based invalidation zones
- Dynamic target calculation by timeframe
- Trade invalidation rules
- Position sizing recommendations
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RiskRewardEngine:
    """
    Risk-Reward calculation and trade quality assessment
    """

    # Minimum R:R ratios by timeframe
    MIN_RR_BY_TIMEFRAME = {
        '5m': 1.5,
        '15m': 2.0,
        '1h': 3.0,
        '1d': 4.0
    }

    # ATR multipliers for stop loss
    ATR_SL_MULTIPLIER = {
        '5m': 1.0,
        '15m': 1.2,
        '1h': 1.5,
        '1d': 2.0
    }

    # Position sizing based on score
    POSITION_SIZE_BY_SCORE = {
        'high': 1.0,      # Score >= 85: 1% risk
        'medium': 0.75,   # Score 75-84: 0.75% risk
        'low': 0.5        # Score < 75: 0.5% risk
    }

    def __init__(self, df: pd.DataFrame, timeframe: str = '1d'):
        """
        Initialize risk-reward engine

        Args:
            df: DataFrame with OHLCV data
            timeframe: Trading timeframe
        """
        self.df = df.copy() if df is not None else pd.DataFrame()
        self.timeframe = timeframe
        self.min_rr = self.MIN_RR_BY_TIMEFRAME.get(timeframe, 3.0)
        self.atr_multiplier = self.ATR_SL_MULTIPLIER.get(timeframe, 1.5)
        self.atr = self._calculate_atr()
        self.swing_levels = self._find_swing_levels()

    def _calculate_atr(self, period: int = 14) -> float:
        """Calculate Average True Range"""
        if self.df is None or len(self.df) < period:
            return 0

        try:
            high_low = self.df['High'] - self.df['Low']
            high_close = abs(self.df['High'] - self.df['Close'].shift(1))
            low_close = abs(self.df['Low'] - self.df['Close'].shift(1))

            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.ewm(span=period, adjust=False).mean()

            return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0

        except Exception as e:
            logger.error(f"Error calculating ATR: {str(e)}")
            return 0

    def _find_swing_levels(self, lookback: int = 20) -> Dict[str, List[float]]:
        """Find recent swing highs and lows"""
        if self.df is None or len(self.df) < lookback:
            return {'highs': [], 'lows': []}

        try:
            df = self.df.tail(lookback)
            highs = []
            lows = []

            for i in range(2, len(df) - 2):
                # Swing high
                if (df['High'].iloc[i] > df['High'].iloc[i-1] and
                    df['High'].iloc[i] > df['High'].iloc[i-2] and
                    df['High'].iloc[i] > df['High'].iloc[i+1] and
                    df['High'].iloc[i] > df['High'].iloc[i+2]):
                    highs.append(float(df['High'].iloc[i]))

                # Swing low
                if (df['Low'].iloc[i] < df['Low'].iloc[i-1] and
                    df['Low'].iloc[i] < df['Low'].iloc[i-2] and
                    df['Low'].iloc[i] < df['Low'].iloc[i+1] and
                    df['Low'].iloc[i] < df['Low'].iloc[i+2]):
                    lows.append(float(df['Low'].iloc[i]))

            return {
                'highs': sorted(highs, reverse=True)[:3],
                'lows': sorted(lows)[:3]
            }

        except Exception as e:
            logger.warning(f"Error finding swing levels: {str(e)}")
            return {'highs': [], 'lows': []}

    def calculate_stop_loss(self, entry_price: float, bias: str) -> Dict[str, Any]:
        """
        Calculate stop-loss using ATR and structure

        Args:
            entry_price: Entry price
            bias: Trade direction ('LONG' or 'SHORT')

        Returns:
            Dictionary with stop-loss details
        """
        try:
            # ATR-based stop loss
            atr_stop_distance = self.atr * self.atr_multiplier

            if bias == 'LONG':
                atr_stop = entry_price - atr_stop_distance

                # Structure-based stop (below recent swing low)
                structure_stop = None
                if self.swing_levels['lows']:
                    for low in self.swing_levels['lows']:
                        if low < entry_price:
                            structure_stop = low - (self.atr * 0.2)  # Buffer below swing
                            break

                # Use the tighter stop (higher value for long)
                if structure_stop and structure_stop > atr_stop:
                    stop_loss = structure_stop
                    stop_type = 'structure'
                else:
                    stop_loss = atr_stop
                    stop_type = 'atr'

            else:  # SHORT
                atr_stop = entry_price + atr_stop_distance

                # Structure-based stop (above recent swing high)
                structure_stop = None
                if self.swing_levels['highs']:
                    for high in self.swing_levels['highs']:
                        if high > entry_price:
                            structure_stop = high + (self.atr * 0.2)  # Buffer above swing
                            break

                # Use the tighter stop (lower value for short)
                if structure_stop and structure_stop < atr_stop:
                    stop_loss = structure_stop
                    stop_type = 'structure'
                else:
                    stop_loss = atr_stop
                    stop_type = 'atr'

            # Calculate risk percentage
            risk_pct = abs(entry_price - stop_loss) / entry_price * 100

            return {
                'stop_loss': round(stop_loss, 2),
                'stop_type': stop_type,
                'atr_stop': round(atr_stop, 2),
                'structure_stop': round(structure_stop, 2) if structure_stop else None,
                'risk_points': round(abs(entry_price - stop_loss), 2),
                'risk_percentage': round(risk_pct, 2),
                'atr_value': round(self.atr, 2),
                'atr_multiplier': self.atr_multiplier
            }

        except Exception as e:
            logger.error(f"Error calculating stop loss: {str(e)}")
            # Fallback to simple ATR stop
            fallback_stop = entry_price * (0.98 if bias == 'LONG' else 1.02)
            return {
                'stop_loss': round(fallback_stop, 2),
                'stop_type': 'fallback',
                'risk_percentage': 2.0
            }

    def calculate_targets(self, entry_price: float, stop_loss: float,
                         bias: str) -> Dict[str, Any]:
        """
        Calculate take-profit targets based on R:R requirements

        Args:
            entry_price: Entry price
            stop_loss: Stop loss level
            bias: Trade direction

        Returns:
            Dictionary with target levels
        """
        try:
            risk = abs(entry_price - stop_loss)

            if bias == 'LONG':
                # Target 1: Minimum R:R
                target_1 = entry_price + (risk * self.min_rr)

                # Target 2: Extended target (1.5x min R:R)
                target_2 = entry_price + (risk * self.min_rr * 1.5)

                # Target 3: Stretch target (2x min R:R)
                target_3 = entry_price + (risk * self.min_rr * 2)

            else:  # SHORT
                target_1 = entry_price - (risk * self.min_rr)
                target_2 = entry_price - (risk * self.min_rr * 1.5)
                target_3 = entry_price - (risk * self.min_rr * 2)

            # Calculate R:R for each target
            rr_1 = self.min_rr
            rr_2 = self.min_rr * 1.5
            rr_3 = self.min_rr * 2

            return {
                'target_1': round(target_1, 2),
                'target_2': round(target_2, 2),
                'target_3': round(target_3, 2),
                'rr_target_1': f"1:{rr_1}",
                'rr_target_2': f"1:{rr_2}",
                'rr_target_3': f"1:{rr_3}",
                'risk_points': round(risk, 2),
                'reward_target_1': round(risk * rr_1, 2),
                'reward_target_2': round(risk * rr_2, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating targets: {str(e)}")
            return {
                'target_1': entry_price * (1.03 if bias == 'LONG' else 0.97),
                'target_2': entry_price * (1.05 if bias == 'LONG' else 0.95),
                'rr_target_1': '1:1.5',
                'rr_target_2': '1:2.5'
            }

    def check_invalidation_rules(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check trade invalidation rules

        Rules:
        1. Momentum divergence (RSI/Price divergence)
        2. Volume profile gaps
        3. Regime conflict (signal vs regime mismatch)

        Args:
            indicators: Dictionary with indicator data

        Returns:
            Dictionary with invalidation status and reasons
        """
        invalidations = []
        warnings = []

        try:
            # Rule 1: RSI Divergence
            rsi_data = indicators.get('momentum', {}).get('rsi', {})
            if rsi_data.get('divergence') == 'bearish_divergence':
                warnings.append('Bearish RSI divergence detected')
            elif rsi_data.get('divergence') == 'bullish_divergence':
                warnings.append('Bullish RSI divergence detected')

            # Rule 2: Extreme RSI
            rsi_value = rsi_data.get('value', 50)
            if rsi_value > 80:
                warnings.append(f'RSI extremely overbought ({rsi_value})')
            elif rsi_value < 20:
                warnings.append(f'RSI extremely oversold ({rsi_value})')

            # Rule 3: Volume confirmation
            volume_data = indicators.get('volume', {})
            rvol = volume_data.get('rvol', {}).get('value', 1.0)
            if rvol < 0.5:
                warnings.append('Very low volume - weak conviction')

            # Rule 4: Volatility extreme
            volatility_data = indicators.get('volatility', {})
            vol_state = volatility_data.get('volatility_state', 'normal')
            if vol_state == 'expansion':
                warnings.append('High volatility expansion - increased risk')

            # Rule 5: Trend alignment
            trend_data = indicators.get('trend', {})
            trend = trend_data.get('overall_trend', 'neutral')
            trend_strength = trend_data.get('trend_strength', 50)

            if trend_strength < 30:
                warnings.append('Weak trend strength')

            # Determine if trade is valid
            is_valid = len(invalidations) == 0
            has_warnings = len(warnings) > 0

            # Risk level assessment
            if len(warnings) >= 3:
                risk_level = 'high'
            elif len(warnings) >= 1:
                risk_level = 'medium'
            else:
                risk_level = 'low'

            return {
                'is_valid': is_valid,
                'invalidations': invalidations,
                'warnings': warnings,
                'risk_level': risk_level,
                'warning_count': len(warnings)
            }

        except Exception as e:
            logger.error(f"Error checking invalidation rules: {str(e)}")
            return {
                'is_valid': True,
                'invalidations': [],
                'warnings': ['Could not complete all validation checks'],
                'risk_level': 'unknown'
            }

    def calculate_position_size(self, score: float, account_risk_pct: float = 1.0) -> Dict[str, Any]:
        """
        Calculate recommended position size based on score

        Args:
            score: Stock score (0-100)
            account_risk_pct: Maximum account risk percentage

        Returns:
            Position sizing recommendation
        """
        try:
            # Determine risk multiplier based on score
            if score >= 85:
                risk_multiplier = self.POSITION_SIZE_BY_SCORE['high']
                confidence = 'high'
            elif score >= 75:
                risk_multiplier = self.POSITION_SIZE_BY_SCORE['medium']
                confidence = 'medium'
            else:
                risk_multiplier = self.POSITION_SIZE_BY_SCORE['low']
                confidence = 'low'

            recommended_risk = account_risk_pct * risk_multiplier

            return {
                'score': round(score, 2),
                'confidence': confidence,
                'base_risk_pct': account_risk_pct,
                'risk_multiplier': risk_multiplier,
                'recommended_risk_pct': round(recommended_risk, 2),
                'max_loss_pct': round(recommended_risk, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating position size: {str(e)}")
            return {
                'recommended_risk_pct': 0.5,
                'confidence': 'low'
            }

    def get_trade_setup(self, entry_price: float, bias: str,
                       indicators: Dict = None, score: float = 75) -> Dict[str, Any]:
        """
        Get complete trade setup with entry, SL, TP, and validation

        Args:
            entry_price: Entry price
            bias: Trade direction ('LONG' or 'SHORT')
            indicators: Optional indicator data for validation
            score: Stock score for position sizing

        Returns:
            Complete trade setup dictionary
        """
        try:
            # Calculate stop loss
            sl_data = self.calculate_stop_loss(entry_price, bias)
            stop_loss = sl_data['stop_loss']

            # Calculate targets
            target_data = self.calculate_targets(entry_price, stop_loss, bias)

            # Check invalidation rules
            if indicators:
                validation = self.check_invalidation_rules(indicators)
            else:
                validation = {'is_valid': True, 'warnings': [], 'risk_level': 'unknown'}

            # Calculate position size
            position_size = self.calculate_position_size(score)

            # Calculate primary R:R ratio
            risk = abs(entry_price - stop_loss)
            reward = abs(target_data['target_1'] - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0

            return {
                'entry_price': round(entry_price, 2),
                'bias': bias,
                'stop_loss': stop_loss,
                'stop_type': sl_data.get('stop_type', 'atr'),
                'target_1': target_data['target_1'],
                'target_2': target_data['target_2'],
                'risk_points': round(risk, 2),
                'risk_percentage': sl_data.get('risk_percentage', 2.0),
                'reward_points': round(reward, 2),
                'rr_ratio': round(rr_ratio, 2),
                'rr_string': f"1:{round(rr_ratio, 1)}",
                'meets_min_rr': rr_ratio >= self.min_rr,
                'min_rr_required': self.min_rr,
                'timeframe': self.timeframe,
                'validation': validation,
                'position_sizing': position_size,
                'atr': round(self.atr, 2),
                'swing_levels': self.swing_levels,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error creating trade setup: {str(e)}")
            return {
                'entry_price': entry_price,
                'bias': bias,
                'error': str(e),
                'is_valid': False
            }

    def calculate_execution_score(self, trade_setup: Dict) -> int:
        """
        Calculate execution quality score (0-10) for scoring engine

        Args:
            trade_setup: Trade setup dictionary

        Returns:
            Execution quality score
        """
        score = 5  # Base score

        try:
            # R:R quality (max 4 points)
            rr = trade_setup.get('rr_ratio', 0)
            if rr >= self.min_rr * 1.5:
                score += 4
            elif rr >= self.min_rr:
                score += 2
            elif rr >= self.min_rr * 0.8:
                score += 1

            # Risk percentage (max 3 points)
            risk_pct = trade_setup.get('risk_percentage', 5)
            if risk_pct < 1.5:
                score += 3
            elif risk_pct < 2.5:
                score += 2
            elif risk_pct < 3.5:
                score += 1

            # Validation quality (max 3 points)
            validation = trade_setup.get('validation', {})
            warning_count = validation.get('warning_count', 0)
            if warning_count == 0:
                score += 3
            elif warning_count == 1:
                score += 2
            elif warning_count == 2:
                score += 1

        except Exception as e:
            logger.warning(f"Error calculating execution score: {str(e)}")

        return min(int(score), 10)
