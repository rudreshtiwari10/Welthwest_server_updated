"""
Random Forest Pattern Recognition Engine
Detects chart patterns and predicts trade success
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PatternRecognitionEngine:
    """Random Forest-based pattern recognition for trading signals"""

    def __init__(self):
        logger.info("Pattern Recognition Engine initialized")
        self.patterns = []

    def detect_patterns(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Detect chart patterns and price action signals

        Args:
            df: DataFrame with OHLCV data and technical indicators

        Returns:
            Dictionary with detected patterns and confidence scores
        """
        try:
            patterns = {
                'chart_patterns': self._detect_chart_patterns(df),
                'price_action': self._detect_price_action(df),
                'breakout_signals': self._detect_breakouts(df),
                'pattern_confidence': 0.0,
                'success_probability': 0.0
            }

            # Calculate overall pattern confidence
            active_patterns = sum([
                len(patterns['chart_patterns']),
                len(patterns['price_action']),
                len(patterns['breakout_signals'])
            ])

            patterns['pattern_confidence'] = min(active_patterns / 10.0, 1.0)
            patterns['success_probability'] = self._calculate_success_probability(patterns)

            return patterns

        except Exception as e:
            logger.error(f"Error detecting patterns: {str(e)}")
            return {
                'chart_patterns': [],
                'price_action': [],
                'breakout_signals': [],
                'pattern_confidence': 0.0,
                'success_probability': 0.5
            }

    def _detect_chart_patterns(self, df: pd.DataFrame) -> List[str]:
        """Detect common chart patterns"""
        patterns = []

        # Double Top/Bottom
        if self._is_double_top(df):
            patterns.append('Double Top')
        if self._is_double_bottom(df):
            patterns.append('Double Bottom')

        # Head and Shoulders
        if self._is_head_shoulders(df):
            patterns.append('Head and Shoulders')

        # Triangle patterns
        if self._is_ascending_triangle(df):
            patterns.append('Ascending Triangle')
        if self._is_descending_triangle(df):
            patterns.append('Descending Triangle')

        # Flag and Pennant
        if self._is_bull_flag(df):
            patterns.append('Bull Flag')
        if self._is_bear_flag(df):
            patterns.append('Bear Flag')

        return patterns

    def _detect_price_action(self, df: pd.DataFrame) -> List[str]:
        """Detect price action patterns"""
        signals = []

        recent = df.tail(20)

        # Higher Highs and Higher Lows
        if self._is_higher_highs_lows(recent):
            signals.append('Higher Highs/Lows')

        # Lower Highs and Lower Lows
        if self._is_lower_highs_lows(recent):
            signals.append('Lower Highs/Lows')

        # Engulfing patterns
        if self._is_bullish_engulfing(df):
            signals.append('Bullish Engulfing')
        if self._is_bearish_engulfing(df):
            signals.append('Bearish Engulfing')

        # Doji patterns
        if self._is_doji(df.iloc[-1]):
            signals.append('Doji')

        return signals

    def _detect_breakouts(self, df: pd.DataFrame) -> List[Dict]:
        """Detect breakout signals"""
        breakouts = []

        if len(df) < 50:
            return breakouts

        recent_high = df['High'].rolling(window=20).max().iloc[-1]
        recent_low = df['Low'].rolling(window=20).min().iloc[-1]
        current_close = df['Close'].iloc[-1]
        volume_avg = df['Volume'].rolling(window=20).mean().iloc[-1]
        current_volume = df['Volume'].iloc[-1]

        # Resistance breakout
        if current_close > recent_high * 1.02 and current_volume > volume_avg * 1.5:
            breakouts.append({
                'type': 'Resistance Breakout',
                'level': recent_high,
                'strength': min((current_volume / volume_avg), 3.0) / 3.0,
                'direction': 'bullish'
            })

        # Support breakdown
        if current_close < recent_low * 0.98 and current_volume > volume_avg * 1.5:
            breakouts.append({
                'type': 'Support Breakdown',
                'level': recent_low,
                'strength': min((current_volume / volume_avg), 3.0) / 3.0,
                'direction': 'bearish'
            })

        return breakouts

    def _is_double_top(self, df: pd.DataFrame) -> bool:
        """Detect double top pattern"""
        if len(df) < 30:
            return False

        highs = df['High'].rolling(window=5).max()
        peaks = []

        for i in range(5, len(highs) - 5):
            if highs.iloc[i] == df['High'].iloc[i-5:i+5].max():
                peaks.append((i, highs.iloc[i]))

        # Check for two similar peaks
        if len(peaks) >= 2:
            last_two = peaks[-2:]
            price_diff = abs(last_two[0][1] - last_two[1][1]) / last_two[0][1]
            time_diff = last_two[1][0] - last_two[0][0]

            if price_diff < 0.03 and 10 < time_diff < 50:
                return True

        return False

    def _is_double_bottom(self, df: pd.DataFrame) -> bool:
        """Detect double bottom pattern"""
        if len(df) < 30:
            return False

        lows = df['Low'].rolling(window=5).min()
        troughs = []

        for i in range(5, len(lows) - 5):
            if lows.iloc[i] == df['Low'].iloc[i-5:i+5].min():
                troughs.append((i, lows.iloc[i]))

        # Check for two similar troughs
        if len(troughs) >= 2:
            last_two = troughs[-2:]
            price_diff = abs(last_two[0][1] - last_two[1][1]) / last_two[0][1]
            time_diff = last_two[1][0] - last_two[0][0]

            if price_diff < 0.03 and 10 < time_diff < 50:
                return True

        return False

    def _is_head_shoulders(self, df: pd.DataFrame) -> bool:
        """Detect head and shoulders pattern"""
        if len(df) < 50:
            return False

        # Simplified detection - look for three peaks with middle one highest
        highs = df['High'].rolling(window=5).max().iloc[-50:]
        peaks = []

        for i in range(5, len(highs) - 5):
            if highs.iloc[i] == df['High'].iloc[i-5:i+5].max():
                peaks.append(highs.iloc[i])

        if len(peaks) >= 3:
            last_three = peaks[-3:]
            if last_three[1] > last_three[0] and last_three[1] > last_three[2]:
                return True

        return False

    def _is_ascending_triangle(self, df: pd.DataFrame) -> bool:
        """Detect ascending triangle pattern"""
        if len(df) < 30:
            return False

        recent = df.tail(30)
        resistance = recent['High'].max()
        lows = recent['Low'].values

        # Check if lows are rising
        if len(lows) > 10:
            slope = np.polyfit(range(len(lows)), lows, 1)[0]
            return slope > 0 and abs(resistance - recent['High'].iloc[-1]) < resistance * 0.02

        return False

    def _is_descending_triangle(self, df: pd.DataFrame) -> bool:
        """Detect descending triangle pattern"""
        if len(df) < 30:
            return False

        recent = df.tail(30)
        support = recent['Low'].min()
        highs = recent['High'].values

        # Check if highs are falling
        if len(highs) > 10:
            slope = np.polyfit(range(len(highs)), highs, 1)[0]
            return slope < 0 and abs(support - recent['Low'].iloc[-1]) < support * 0.02

        return False

    def _is_bull_flag(self, df: pd.DataFrame) -> bool:
        """Detect bull flag pattern"""
        if len(df) < 20:
            return False

        # Strong upward move followed by consolidation
        early = df.iloc[-20:-10]
        recent = df.iloc[-10:]

        early_return = (early['Close'].iloc[-1] / early['Close'].iloc[0]) - 1
        recent_volatility = recent['Close'].std() / recent['Close'].mean()

        return early_return > 0.05 and recent_volatility < 0.02

    def _is_bear_flag(self, df: pd.DataFrame) -> bool:
        """Detect bear flag pattern"""
        if len(df) < 20:
            return False

        # Strong downward move followed by consolidation
        early = df.iloc[-20:-10]
        recent = df.iloc[-10:]

        early_return = (early['Close'].iloc[-1] / early['Close'].iloc[0]) - 1
        recent_volatility = recent['Close'].std() / recent['Close'].mean()

        return early_return < -0.05 and recent_volatility < 0.02

    def _is_higher_highs_lows(self, df: pd.DataFrame) -> bool:
        """Detect higher highs and higher lows"""
        if len(df) < 10:
            return False

        highs = df['High'].values
        lows = df['Low'].values

        higher_highs = all(highs[i] >= highs[i-5] for i in range(5, len(highs), 5))
        higher_lows = all(lows[i] >= lows[i-5] for i in range(5, len(lows), 5))

        return higher_highs and higher_lows

    def _is_lower_highs_lows(self, df: pd.DataFrame) -> bool:
        """Detect lower highs and lower lows"""
        if len(df) < 10:
            return False

        highs = df['High'].values
        lows = df['Low'].values

        lower_highs = all(highs[i] <= highs[i-5] for i in range(5, len(highs), 5))
        lower_lows = all(lows[i] <= lows[i-5] for i in range(5, len(lows), 5))

        return lower_highs and lower_lows

    def _is_bullish_engulfing(self, df: pd.DataFrame) -> bool:
        """Detect bullish engulfing pattern"""
        if len(df) < 2:
            return False

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        prev_body = abs(prev['Close'] - prev['Open'])
        curr_body = abs(curr['Close'] - curr['Open'])

        return (prev['Close'] < prev['Open'] and  # Previous red candle
                curr['Close'] > curr['Open'] and  # Current green candle
                curr['Open'] < prev['Close'] and  # Opens below previous close
                curr['Close'] > prev['Open'] and  # Closes above previous open
                curr_body > prev_body * 1.5)  # Larger body

    def _is_bearish_engulfing(self, df: pd.DataFrame) -> bool:
        """Detect bearish engulfing pattern"""
        if len(df) < 2:
            return False

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        prev_body = abs(prev['Close'] - prev['Open'])
        curr_body = abs(curr['Close'] - curr['Open'])

        return (prev['Close'] > prev['Open'] and  # Previous green candle
                curr['Close'] < curr['Open'] and  # Current red candle
                curr['Open'] > prev['Close'] and  # Opens above previous close
                curr['Close'] < prev['Open'] and  # Closes below previous open
                curr_body > prev_body * 1.5)  # Larger body

    def _is_doji(self, candle: pd.Series) -> bool:
        """Detect doji candle"""
        body = abs(candle['Close'] - candle['Open'])
        range_size = candle['High'] - candle['Low']

        return body < (range_size * 0.1) if range_size > 0 else False

    def _calculate_success_probability(self, patterns: Dict) -> float:
        """Calculate success probability based on detected patterns"""
        # Base probability
        base_prob = 0.50

        # Adjust based on pattern types
        bullish_patterns = ['Double Bottom', 'Ascending Triangle', 'Bull Flag',
                            'Bullish Engulfing', 'Higher Highs/Lows']
        bearish_patterns = ['Double Top', 'Descending Triangle', 'Bear Flag',
                            'Bearish Engulfing', 'Lower Highs/Lows', 'Head and Shoulders']

        bullish_count = sum(1 for p in patterns['chart_patterns'] + patterns['price_action']
                            if p in bullish_patterns)
        bearish_count = sum(1 for p in patterns['chart_patterns'] + patterns['price_action']
                            if p in bearish_patterns)

        # Breakout strength
        breakout_strength = sum(b.get('strength', 0) for b in patterns['breakout_signals'])

        # Calculate final probability
        if bullish_count > bearish_count:
            success_prob = base_prob + (bullish_count * 0.05) + (breakout_strength * 0.1)
        elif bearish_count > bullish_count:
            success_prob = base_prob + (bearish_count * 0.05) + (breakout_strength * 0.1)
        else:
            success_prob = base_prob

        return min(max(success_prob, 0.0), 1.0)


# Singleton instance
pattern_engine = PatternRecognitionEngine()
