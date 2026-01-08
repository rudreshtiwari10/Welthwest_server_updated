"""
Breakdown Detector Module for SHORT Trade Detection

Detects potential SHORT opportunities through:
1. Resistance Breakdown - Price breaking below key resistance
2. New Low Breach - Fresh 52-week/period lows
3. Bearish Wedge Breakout - Consolidation breaking bearish
4. Double Top Pattern - Distribution reversal pattern
5. Momentum Exhaustion - Rejection at resistance

Used by the Selling Screener to identify high-probability short setups.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BreakdownDetector:
    """
    Detects breakdown patterns for SHORT trade opportunities
    """

    def __init__(self, df: pd.DataFrame, timeframe: str = '1d'):
        """
        Initialize with OHLCV data

        Args:
            df: DataFrame with Open, High, Low, Close, Volume columns
            timeframe: One of '5m', '15m', '1h', '1d'
        """
        self.df = df.copy() if df is not None else pd.DataFrame()
        self.timeframe = timeframe

        # Timeframe-specific lookback periods
        self.lookback_config = {
            '5m': {'swing': 50, 'year_low': 50, 'trend': 15, 'vol_avg': 20},
            '15m': {'swing': 100, 'year_low': 100, 'trend': 20, 'vol_avg': 20},
            '1h': {'swing': 100, 'year_low': 252, 'trend': 20, 'vol_avg': 20},
            '1d': {'swing': 40, 'year_low': 252, 'trend': 15, 'vol_avg': 20}
        }
        self.config = self.lookback_config.get(timeframe, self.lookback_config['1d'])

    def find_swing_highs(self, data: pd.Series, window: int = 5) -> List[float]:
        """Find swing high points (local maxima)"""
        highs = []
        if len(data) < window * 2:
            return highs

        for i in range(window, len(data) - window):
            if data.iloc[i] == data.iloc[i-window:i+window+1].max():
                highs.append(float(data.iloc[i]))
        return highs

    def find_swing_lows(self, data: pd.Series, window: int = 5) -> List[float]:
        """Find swing low points (local minima)"""
        lows = []
        if len(data) < window * 2:
            return lows

        for i in range(window, len(data) - window):
            if data.iloc[i] == data.iloc[i-window:i+window+1].min():
                lows.append(float(data.iloc[i]))
        return lows

    def calculate_rsi(self, data: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = data.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def calculate_rr(self, entry: float, target: float, stop: float) -> float:
        """Calculate Risk:Reward ratio"""
        risk = abs(entry - stop)
        reward = abs(entry - target)
        if risk == 0:
            return 0
        return round(reward / risk, 2)

    def detect_resistance_breakdown(self) -> Optional[Dict]:
        """
        Detect breakdown below key resistance level

        3-GATE CONFIRMATION (FIX #1):
        1. Volume spike: vol > MA20(vol) * 1.5
        2. Conviction close: close in lower 30% of candle range
        3. Body size: body >= 30% of range (avoid wick-only)

        ALL 3 gates must pass for high-confidence breakdown.
        At least 2 gates for moderate-confidence.
        """
        if len(self.df) < 20:
            return None

        try:
            swing_period = min(self.config['swing'], len(self.df) - 1)
            recent_highs = self.df['High'].iloc[-swing_period:]
            resistances = self.find_swing_highs(recent_highs)

            if not resistances:
                return None

            nearest_resistance = resistances[-1] if resistances else self.df['High'].iloc[-20:].max()
            current_close = self.df['Close'].iloc[-1]
            current_open = self.df['Open'].iloc[-1]
            current_high = self.df['High'].iloc[-1]
            current_low = self.df['Low'].iloc[-1]
            current_volume = self.df['Volume'].iloc[-1]

            # Calculate candle metrics
            candle_range = current_high - current_low
            body_size = abs(current_close - current_open)

            # ========== 3-GATE CONFIRMATION ==========

            # GATE 1: Volume spike (vol > MA20(vol) * 1.5)
            vol_avg = self.df['Volume'].iloc[-20:].mean()
            gate1_volume = current_volume > vol_avg * 1.5

            # GATE 2: Conviction close (close in lower 30% of candle range)
            if candle_range > 0:
                close_position = (current_close - current_low) / candle_range
            else:
                close_position = 0.5
            gate2_conviction = close_position < 0.30

            # GATE 3: Body size (body >= 30% of range - avoid wick-only)
            if candle_range > 0:
                body_ratio = body_size / candle_range
            else:
                body_ratio = 0
            gate3_body = body_ratio >= 0.30

            # Count gates passed
            gates_passed = sum([gate1_volume, gate2_conviction, gate3_body])

            # Must pass at least 2 gates for breakdown
            if gates_passed < 2:
                return None

            # Check if price broke below resistance recently
            price_below_resistance = current_close < nearest_resistance

            if price_below_resistance:
                # Calculate breakdown strength
                break_strength = (nearest_resistance - current_close) / nearest_resistance * 100

                # Confidence based on gates passed
                if gates_passed == 3:
                    base_confidence = 0.85  # High confidence
                else:
                    base_confidence = 0.70  # Moderate confidence

                confidence = min(0.95, base_confidence + (break_strength * 0.02))

                # Find next support (target)
                swing_lows = self.find_swing_lows(self.df['Low'].iloc[-40:])
                if swing_lows:
                    next_support = min([l for l in swing_lows if l < current_close], default=current_close * 0.97)
                else:
                    next_support = current_close * 0.97

                # Stop loss above recent high
                stop_loss = current_high * 1.01

                return {
                    'type': 'RESISTANCE_BREAKDOWN',
                    'entry': round(current_close, 2),
                    'confidence': round(confidence, 2),
                    'target_price': round(next_support, 2),
                    'stop_loss': round(stop_loss, 2),
                    'risk_reward': self.calculate_rr(current_close, next_support, stop_loss),
                    'urgency': 'HIGH' if gates_passed == 3 else 'MEDIUM',
                    'volume_confirmed': gate1_volume,
                    'conviction_close': gate2_conviction,
                    'body_confirmed': gate3_body,
                    'gates_passed': gates_passed,
                    'break_strength_pct': round(break_strength, 2),
                    'resistance_level': round(nearest_resistance, 2),
                    'description': f'Breakdown confirmed ({gates_passed}/3 gates) below {nearest_resistance:.2f}'
                }

        except Exception as e:
            logger.debug(f"Error detecting resistance breakdown: {e}")

        return None

    def detect_new_low_breach(self) -> Optional[Dict]:
        """
        Detect new period low (52-week or equivalent)

        New lows = no support below = panic selling potential
        Price can cascade another 3-8% easily
        """
        if len(self.df) < 20:
            return None

        try:
            year_low_period = min(self.config['year_low'], len(self.df))
            year_low = self.df['Low'].iloc[-year_low_period:].min()
            current_low = self.df['Low'].iloc[-1]
            current_close = self.df['Close'].iloc[-1]
            prev_low = self.df['Low'].iloc[-2] if len(self.df) > 1 else current_low

            # Volume confirmation
            vol_avg = self.df['Volume'].iloc[-5:].mean()
            current_volume = self.df['Volume'].iloc[-1]
            volume_confirmed = current_volume > vol_avg * 1.3

            # Check for new low
            if current_low < year_low and current_low < prev_low:
                below_low_pct = (year_low - current_low) / year_low * 100

                # New lows often cascade 3-8% further
                cascade_target = current_low * 0.95  # 5% more down

                # Momentum decay (recency matters)
                days_since_prev_low = np.argmin(self.df['Low'].iloc[-year_low_period:].values)
                momentum_decay = 1.0 - (days_since_prev_low / year_low_period)

                confidence = 0.72
                if volume_confirmed:
                    confidence += 0.10
                confidence *= max(0.5, momentum_decay)
                confidence = min(0.88, confidence)

                # Stop above recent swing high
                recent_high = self.df['High'].iloc[-10:].max()
                stop_loss = recent_high * 1.01

                return {
                    'type': 'NEW_LOW_BREACH',
                    'entry': round(current_close, 2),
                    'confidence': round(confidence, 2),
                    'target_price': round(cascade_target, 2),
                    'stop_loss': round(stop_loss, 2),
                    'risk_reward': self.calculate_rr(current_close, cascade_target, stop_loss),
                    'urgency': 'CRITICAL',
                    'volume_confirmed': volume_confirmed,
                    'below_low_pct': round(below_low_pct, 2),
                    'year_low': round(year_low, 2),
                    'momentum_decay': round(momentum_decay, 2),
                    'expected_cascade_pct': 5.0,
                    'description': f'Fresh low below {year_low:.2f} - momentum capitulation'
                }

        except Exception as e:
            logger.debug(f"Error detecting new low breach: {e}")

        return None

    def detect_bearish_wedge(self) -> Optional[Dict]:
        """
        Detect bearish wedge breakout

        Price consolidating in narrowing wedge, breaks lower
        """
        if len(self.df) < 15:
            return None

        try:
            # Calculate trendlines for last 15 periods
            highs = self.df['High'].iloc[-15:].values
            lows = self.df['Low'].iloc[-15:].values
            closes = self.df['Close'].iloc[-15:].values
            x = np.arange(len(highs))

            # Linear regression for trendlines
            upper_slope = np.polyfit(x, highs, 1)[0]
            lower_slope = np.polyfit(x, lows, 1)[0]

            upper_trendline = np.polyval(np.polyfit(x, highs, 1), x)
            lower_trendline = np.polyval(np.polyfit(x, lows, 1), x)

            # Check for wedge convergence
            wedge_width_start = upper_trendline[0] - lower_trendline[0]
            wedge_width_end = upper_trendline[-1] - lower_trendline[-1]

            wedge_converging = wedge_width_end < wedge_width_start * 0.8

            # Current price breaking below lower trendline
            current_close = self.df['Close'].iloc[-1]
            current_volume = self.df['Volume'].iloc[-1]
            vol_avg = self.df['Volume'].iloc[-10:].mean()

            price_below_lower = current_close < lower_trendline[-1]
            volume_confirmed = current_volume > vol_avg

            if wedge_converging and price_below_lower and volume_confirmed:
                # Wedge breakout target = wedge height x 1.3
                wedge_height = upper_trendline[0] - lower_trendline[0]
                wedge_target = lower_trendline[-1] - (wedge_height * 1.3)

                # Stop above upper trendline
                stop_loss = upper_trendline[-1] * 1.01

                return {
                    'type': 'BEARISH_WEDGE',
                    'entry': round(current_close, 2),
                    'confidence': 0.80,
                    'target_price': round(wedge_target, 2),
                    'stop_loss': round(stop_loss, 2),
                    'risk_reward': self.calculate_rr(current_close, wedge_target, stop_loss),
                    'urgency': 'HIGH',
                    'wedge_height': round(wedge_height, 2),
                    'convergence_ratio': round(wedge_width_end / wedge_width_start, 2),
                    'description': 'Consolidation breaking bearish - wedge breakdown'
                }

        except Exception as e:
            logger.debug(f"Error detecting bearish wedge: {e}")

        return None

    def detect_double_top(self) -> Optional[Dict]:
        """
        Detect double top distribution pattern

        Two similar highs followed by breakdown = reversal signal
        """
        if len(self.df) < 40:
            return None

        try:
            # Find recent swing highs
            recent_highs = self.find_swing_highs(self.df['High'].iloc[-40:], window=3)

            if len(recent_highs) < 2:
                return None

            high1 = recent_highs[-2]
            high2 = recent_highs[-1]
            current_close = self.df['Close'].iloc[-1]

            # Check if highs are similar (within 0.5%)
            height_diff = abs(high1 - high2) / high1
            similar_heights = height_diff < 0.005

            # Price breaking below both highs
            breaking_below = current_close < min(high1, high2) * 0.995

            if similar_heights and breaking_below:
                # Find neckline (lowest point between the two tops)
                # Simplified: use recent swing lows
                swing_lows = self.find_swing_lows(self.df['Low'].iloc[-40:], window=3)
                if swing_lows:
                    neckline = min(swing_lows)
                else:
                    neckline = self.df['Low'].iloc[-40:].min()

                # Double top target = neckline - (high - neckline)
                avg_high = (high1 + high2) / 2
                drop_distance = avg_high - neckline
                target = neckline - drop_distance

                # Stop above the higher top
                stop_loss = max(high1, high2) * 1.01

                return {
                    'type': 'DOUBLE_TOP',
                    'entry': round(current_close, 2),
                    'confidence': 0.85,
                    'target_price': round(target, 2),
                    'stop_loss': round(stop_loss, 2),
                    'risk_reward': self.calculate_rr(current_close, target, stop_loss),
                    'urgency': 'HIGH',
                    'top1': round(high1, 2),
                    'top2': round(high2, 2),
                    'neckline': round(neckline, 2),
                    'description': 'Distribution pattern - double top reversal'
                }

        except Exception as e:
            logger.debug(f"Error detecting double top: {e}")

        return None

    def detect_momentum_exhaustion(self) -> Optional[Dict]:
        """
        Detect momentum exhaustion at resistance

        Conditions:
        - Price near recent high (resistance)
        - Volume declining (fewer buyers)
        - RSI overbought
        - Rejection candle (upper shadow > body)
        """
        if len(self.df) < 20:
            return None

        try:
            current_close = self.df['Close'].iloc[-1]
            current_open = self.df['Open'].iloc[-1]
            current_high = self.df['High'].iloc[-1]
            current_low = self.df['Low'].iloc[-1]

            # Check if at resistance (within 2% of recent high)
            recent_high = self.df['High'].iloc[-20:].max()
            at_resistance = current_close > recent_high * 0.98

            # Volume declining
            recent_vol_avg = self.df['Volume'].iloc[-5:].mean()
            older_vol_avg = self.df['Volume'].iloc[-10:-5].mean()
            volume_declining = recent_vol_avg < older_vol_avg

            # RSI overbought
            rsi = self.calculate_rsi(self.df['Close'])
            rsi_overbought = rsi.iloc[-1] > 65

            # Rejection candle (upper shadow > body * 2)
            body_size = abs(current_close - current_open)
            upper_shadow = current_high - max(current_close, current_open)
            is_rejection_candle = upper_shadow > body_size * 2

            if at_resistance and volume_declining and rsi_overbought and is_rejection_candle:
                target = current_close * 0.95  # 5% down target
                stop_loss = current_high * 1.01

                return {
                    'type': 'MOMENTUM_EXHAUSTION',
                    'entry': round(current_close, 2),
                    'confidence': 0.72,
                    'target_price': round(target, 2),
                    'stop_loss': round(stop_loss, 2),
                    'risk_reward': self.calculate_rr(current_close, target, stop_loss),
                    'urgency': 'MEDIUM',
                    'rsi': round(float(rsi.iloc[-1]), 2),
                    'resistance_level': round(recent_high, 2),
                    'volume_declining': volume_declining,
                    'description': 'Exhaustion at resistance - fade trade'
                }

        except Exception as e:
            logger.debug(f"Error detecting momentum exhaustion: {e}")

        return None

    def detect_all_breakdowns(self) -> Dict[str, Any]:
        """
        Run all breakdown detection methods

        Returns:
            Dictionary with all detected breakdown signals
        """
        if self.df is None or self.df.empty:
            return {
                'has_breakdown': False,
                'signals': [],
                'best_signal': None,
                'total_signals': 0
            }

        signals = []

        # Run all detectors
        detectors = [
            self.detect_resistance_breakdown,
            self.detect_new_low_breach,
            self.detect_bearish_wedge,
            self.detect_double_top,
            self.detect_momentum_exhaustion
        ]

        for detector in detectors:
            try:
                result = detector()
                if result:
                    signals.append(result)
            except Exception as e:
                logger.debug(f"Error in breakdown detector: {e}")

        # Sort by confidence
        signals.sort(key=lambda x: x.get('confidence', 0), reverse=True)

        best_signal = signals[0] if signals else None

        return {
            'has_breakdown': len(signals) > 0,
            'signals': signals,
            'best_signal': best_signal,
            'total_signals': len(signals),
            'timestamp': datetime.now().isoformat()
        }


def get_breakdown_detector(df: pd.DataFrame, timeframe: str = '1d') -> BreakdownDetector:
    """Factory function for BreakdownDetector"""
    return BreakdownDetector(df, timeframe)
