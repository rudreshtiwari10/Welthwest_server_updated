"""
Pattern Detector - Candle and Chart Pattern Recognition

Candle Patterns:
- Bullish/Bearish Engulfing
- Pin Bar (Hammer, Shooting Star)
- Marubozu (Strong momentum candles)
- Inside Bar (Consolidation)

Chart Patterns:
- Flags/Pennants
- Triangles (Ascending, Descending, Symmetrical)
- Range Breakouts

Location Scoring:
- Demand Zone: 1.5x multiplier
- Supply Zone: 1.5x multiplier
- Mid-range: 0.5x multiplier
- Liquidity Void: 2.0x multiplier
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PatternDetector:
    """
    Candle and Chart Pattern Detection with Location Scoring
    """

    # Location multipliers for pattern strength
    LOCATION_MULTIPLIERS = {
        'demand_zone': 1.5,
        'supply_zone': 1.5,
        'mid_range': 0.5,
        'liquidity_void': 2.0,
        'neutral': 1.0
    }

    # Pattern definitions
    # FIX #3: Added missing bearish patterns (upper_wick_rejection, three_black_crows, island_reversal_down)
    CANDLE_PATTERNS = {
        'bullish_engulfing': {'bias': 'LONG', 'base_score': 15, 'reliability': 0.65},
        'bearish_engulfing': {'bias': 'SHORT', 'base_score': 15, 'reliability': 0.65},
        'bearish_engulfing_volume': {'bias': 'SHORT', 'base_score': 20, 'reliability': 0.75},  # FIX #3
        'hammer': {'bias': 'LONG', 'base_score': 12, 'reliability': 0.60},
        'shooting_star': {'bias': 'SHORT', 'base_score': 12, 'reliability': 0.60},
        'upper_wick_rejection': {'bias': 'SHORT', 'base_score': 16, 'reliability': 0.68},  # FIX #3
        'bullish_marubozu': {'bias': 'LONG', 'base_score': 18, 'reliability': 0.70},
        'bearish_marubozu': {'bias': 'SHORT', 'base_score': 18, 'reliability': 0.70},
        'three_black_crows': {'bias': 'SHORT', 'base_score': 22, 'reliability': 0.72},  # FIX #3
        'island_reversal_down': {'bias': 'SHORT', 'base_score': 24, 'reliability': 0.78},  # FIX #3
        'inside_bar': {'bias': 'NEUTRAL', 'base_score': 10, 'reliability': 0.55},
        'doji': {'bias': 'NEUTRAL', 'base_score': 8, 'reliability': 0.50},
    }

    CHART_PATTERNS = {
        'bull_flag': {'bias': 'LONG', 'base_score': 20, 'reliability': 0.70},
        'bear_flag': {'bias': 'SHORT', 'base_score': 20, 'reliability': 0.70},
        'ascending_triangle': {'bias': 'LONG', 'base_score': 18, 'reliability': 0.68},
        'descending_triangle': {'bias': 'SHORT', 'base_score': 18, 'reliability': 0.68},
        'symmetrical_triangle': {'bias': 'NEUTRAL', 'base_score': 15, 'reliability': 0.60},
        'range_breakout': {'bias': 'NEUTRAL', 'base_score': 16, 'reliability': 0.65},
    }

    def __init__(self, df: pd.DataFrame):
        """
        Initialize pattern detector with OHLCV data

        Args:
            df: DataFrame with OHLCV columns
        """
        self.df = df.copy() if df is not None else pd.DataFrame()
        self.patterns_detected = []
        self.support_levels = []
        self.resistance_levels = []

        if not self.df.empty:
            self._calculate_support_resistance()

    def _calculate_support_resistance(self):
        """Calculate support and resistance levels for location scoring"""
        try:
            if len(self.df) < 20:
                return

            highs = self.df['High'].values
            lows = self.df['Low'].values
            closes = self.df['Close'].values

            # Find swing highs and lows
            window = 5

            for i in range(window, len(self.df) - window):
                # Swing high
                if highs[i] == max(highs[i-window:i+window+1]):
                    self.resistance_levels.append(highs[i])

                # Swing low
                if lows[i] == min(lows[i-window:i+window+1]):
                    self.support_levels.append(lows[i])

            # Keep only significant levels (cluster similar levels)
            self.support_levels = self._cluster_levels(self.support_levels)
            self.resistance_levels = self._cluster_levels(self.resistance_levels)

        except Exception as e:
            logger.warning(f"Error calculating S/R levels: {str(e)}")

    def _cluster_levels(self, levels: List[float], threshold: float = 0.02) -> List[float]:
        """Cluster nearby price levels"""
        if not levels:
            return []

        levels = sorted(levels)
        clustered = [levels[0]]

        for level in levels[1:]:
            if abs(level - clustered[-1]) / clustered[-1] > threshold:
                clustered.append(level)
            else:
                # Average with existing cluster
                clustered[-1] = (clustered[-1] + level) / 2

        return clustered[-5:]  # Keep last 5 levels

    def detect_candle_patterns(self) -> List[Dict[str, Any]]:
        """
        Detect candle patterns in recent price action

        Returns:
            List of detected candle patterns with metadata
        """
        if self.df is None or len(self.df) < 3:
            return []

        patterns = []

        try:
            # Get last few candles
            df = self.df.tail(10).copy()

            for i in range(1, len(df)):
                current = df.iloc[i]
                previous = df.iloc[i-1]

                current_open = current['Open']
                current_close = current['Close']
                current_high = current['High']
                current_low = current['Low']
                current_body = abs(current_close - current_open)
                current_range = current_high - current_low

                prev_open = previous['Open']
                prev_close = previous['Close']
                prev_body = abs(prev_close - prev_open)

                # Bullish Engulfing
                if (current_close > current_open and  # Bullish candle
                    prev_close < prev_open and  # Previous bearish
                    current_open <= prev_close and
                    current_close >= prev_open and
                    current_body > prev_body * 1.1):

                    patterns.append(self._create_pattern(
                        'bullish_engulfing', i, current_close, 'LONG'
                    ))

                # Bearish Engulfing
                elif (current_close < current_open and  # Bearish candle
                      prev_close > prev_open and  # Previous bullish
                      current_open >= prev_close and
                      current_close <= prev_open and
                      current_body > prev_body * 1.1):

                    patterns.append(self._create_pattern(
                        'bearish_engulfing', i, current_close, 'SHORT'
                    ))

                # Hammer (Pin Bar - bullish)
                elif (current_range > 0 and
                      current_body < current_range * 0.3 and  # Small body
                      (current_low - min(current_open, current_close)) > current_body * 2 and  # Long lower wick
                      (current_high - max(current_open, current_close)) < current_body * 0.5):  # Short upper wick

                    patterns.append(self._create_pattern(
                        'hammer', i, current_close, 'LONG'
                    ))

                # Shooting Star (Pin Bar - bearish)
                elif (current_range > 0 and
                      current_body < current_range * 0.3 and  # Small body
                      (max(current_open, current_close) - current_high) < current_body * 0.5 and  # Short lower wick
                      (current_high - max(current_open, current_close)) > current_body * 2):  # Long upper wick

                    patterns.append(self._create_pattern(
                        'shooting_star', i, current_close, 'SHORT'
                    ))

                # Bullish Marubozu
                elif (current_close > current_open and
                      current_body > current_range * 0.9):  # Body is 90%+ of range

                    patterns.append(self._create_pattern(
                        'bullish_marubozu', i, current_close, 'LONG'
                    ))

                # Bearish Marubozu
                elif (current_close < current_open and
                      current_body > current_range * 0.9):

                    patterns.append(self._create_pattern(
                        'bearish_marubozu', i, current_close, 'SHORT'
                    ))

                # Inside Bar
                elif (current_high < prev_high and
                      current_low > prev_low):

                    patterns.append(self._create_pattern(
                        'inside_bar', i, current_close, 'NEUTRAL'
                    ))

                # Doji
                elif current_range > 0 and current_body < current_range * 0.1:

                    patterns.append(self._create_pattern(
                        'doji', i, current_close, 'NEUTRAL'
                    ))

                # ========== FIX #3: NEW BEARISH PATTERNS ==========

                # Upper Wick Rejection (bearish at resistance)
                upper_shadow = current_high - max(current_close, current_open)
                lower_shadow = min(current_close, current_open) - current_low

                if (current_range > 0 and
                    upper_shadow > current_body * 2.0 and  # Long upper wick
                    upper_shadow > lower_shadow * 2.0 and  # Upper much bigger than lower
                    current_close < current_open):  # Red candle
                    patterns.append(self._create_pattern(
                        'upper_wick_rejection', i, current_close, 'SHORT'
                    ))

                # Bearish Engulfing with Volume Confirmation
                if 'Volume' in df.columns and i >= 2:
                    current_volume = df.iloc[i].get('Volume', 0)
                    prev_volume = df.iloc[i-1].get('Volume', 0)

                    if (current_close < current_open and  # Bearish candle
                        prev_close > prev_open and  # Previous bullish
                        current_open >= prev_close and
                        current_close <= prev_open and
                        current_body > prev_body * 1.1 and
                        current_volume > prev_volume * 1.3):  # Volume confirmation

                        patterns.append(self._create_pattern(
                            'bearish_engulfing_volume', i, current_close, 'SHORT'
                        ))

            # FIX #3: Three Black Crows (3 consecutive red candles)
            if len(df) >= 3:
                last_3 = df.tail(3)
                all_red = all(last_3['Close'].iloc[j] < last_3['Open'].iloc[j] for j in range(3))
                lower_closes = all(last_3['Close'].iloc[j] < last_3['Close'].iloc[j-1] for j in range(1, 3))
                lower_opens = all(last_3['Open'].iloc[j] < last_3['Open'].iloc[j-1] for j in range(1, 3))

                if all_red and lower_closes and lower_opens:
                    patterns.append(self._create_pattern(
                        'three_black_crows', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

            # FIX #3: Island Reversal Down (gap up then gap down)
            if len(df) >= 3:
                # Gap up between 2nd last and 3rd last
                gap_up = df['Low'].iloc[-2] > df['High'].iloc[-3]
                # Gap down between last and 2nd last
                gap_down = df['High'].iloc[-1] < df['Low'].iloc[-2]

                if gap_up and gap_down:
                    patterns.append(self._create_pattern(
                        'island_reversal_down', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

        except Exception as e:
            logger.error(f"Error detecting candle patterns: {str(e)}")

        return patterns

    def detect_chart_patterns(self) -> List[Dict[str, Any]]:
        """
        Detect chart patterns (flags, triangles, ranges)

        Returns:
            List of detected chart patterns
        """
        if self.df is None or len(self.df) < 20:
            return []

        patterns = []

        try:
            df = self.df.tail(50).copy()
            current_price = df['Close'].iloc[-1]

            # Detect consolidation/range
            range_result = self._detect_range(df)
            if range_result:
                patterns.append(range_result)

            # Detect triangles
            triangle_result = self._detect_triangle(df)
            if triangle_result:
                patterns.append(triangle_result)

            # Detect flags
            flag_result = self._detect_flag(df)
            if flag_result:
                patterns.append(flag_result)

        except Exception as e:
            logger.error(f"Error detecting chart patterns: {str(e)}")

        return patterns

    def _detect_range(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect range/consolidation pattern"""
        try:
            # Look at last 20 candles
            recent = df.tail(20)
            high = recent['High'].max()
            low = recent['Low'].min()
            range_pct = ((high - low) / low) * 100

            # Range is consolidation if < 5% price range
            if range_pct < 5:
                current = df['Close'].iloc[-1]

                # Check for breakout
                if current > high * 0.99:
                    return self._create_pattern(
                        'range_breakout', len(df) - 1, current, 'LONG',
                        extra={'breakout_level': high, 'range_low': low}
                    )
                elif current < low * 1.01:
                    return self._create_pattern(
                        'range_breakout', len(df) - 1, current, 'SHORT',
                        extra={'breakdown_level': low, 'range_high': high}
                    )

        except Exception as e:
            logger.warning(f"Range detection error: {str(e)}")

        return None

    def _detect_triangle(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect triangle patterns"""
        try:
            recent = df.tail(30)

            # Calculate trendlines from highs and lows
            highs = recent['High'].values
            lows = recent['Low'].values

            # Simple linear regression for highs and lows
            x = np.arange(len(highs))

            high_slope = np.polyfit(x, highs, 1)[0]
            low_slope = np.polyfit(x, lows, 1)[0]

            current = df['Close'].iloc[-1]

            # Ascending triangle: flat highs, rising lows
            if abs(high_slope) < 0.1 and low_slope > 0.2:
                return self._create_pattern(
                    'ascending_triangle', len(df) - 1, current, 'LONG'
                )

            # Descending triangle: falling highs, flat lows
            elif high_slope < -0.2 and abs(low_slope) < 0.1:
                return self._create_pattern(
                    'descending_triangle', len(df) - 1, current, 'SHORT'
                )

            # Symmetrical triangle: converging highs and lows
            elif high_slope < -0.1 and low_slope > 0.1:
                return self._create_pattern(
                    'symmetrical_triangle', len(df) - 1, current, 'NEUTRAL'
                )

        except Exception as e:
            logger.warning(f"Triangle detection error: {str(e)}")

        return None

    def _detect_flag(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect flag/pennant patterns"""
        try:
            if len(df) < 30:
                return None

            # Look for strong move followed by consolidation
            # First 10 bars: strong move
            initial = df.iloc[:10]
            initial_move = (initial['Close'].iloc[-1] - initial['Close'].iloc[0]) / initial['Close'].iloc[0]

            # Last 10 bars: consolidation
            consolidation = df.tail(10)
            cons_range = (consolidation['High'].max() - consolidation['Low'].min()) / consolidation['Low'].min()

            current = df['Close'].iloc[-1]

            # Bull flag: Strong up move + tight consolidation
            if initial_move > 0.05 and cons_range < 0.03:
                return self._create_pattern(
                    'bull_flag', len(df) - 1, current, 'LONG'
                )

            # Bear flag: Strong down move + tight consolidation
            elif initial_move < -0.05 and cons_range < 0.03:
                return self._create_pattern(
                    'bear_flag', len(df) - 1, current, 'SHORT'
                )

        except Exception as e:
            logger.warning(f"Flag detection error: {str(e)}")

        return None

    def _create_pattern(self, pattern_type: str, index: int, price: float,
                       bias: str, extra: Dict = None) -> Dict[str, Any]:
        """Create standardized pattern dictionary"""

        # Get pattern info
        if pattern_type in self.CANDLE_PATTERNS:
            pattern_info = self.CANDLE_PATTERNS[pattern_type]
            category = 'candle'
        else:
            pattern_info = self.CHART_PATTERNS.get(pattern_type, {
                'bias': bias, 'base_score': 10, 'reliability': 0.5
            })
            category = 'chart'

        # Calculate location score
        location = self._determine_location(price)
        location_multiplier = self.LOCATION_MULTIPLIERS.get(location, 1.0)

        # Calculate final score
        base_score = pattern_info['base_score']
        final_score = base_score * location_multiplier

        result = {
            'type': pattern_type,
            'category': category,
            'bias': pattern_info['bias'],
            'price': round(float(price), 2),
            'base_score': base_score,
            'location': location,
            'location_multiplier': location_multiplier,
            'final_score': round(final_score, 2),
            'reliability': pattern_info['reliability'],
            'timestamp': datetime.now().isoformat()
        }

        if extra:
            result.update(extra)

        return result

    def _determine_location(self, price: float) -> str:
        """
        Determine price location relative to support/resistance

        Returns:
            Location type: 'demand_zone', 'supply_zone', 'mid_range', 'liquidity_void', 'neutral'
        """
        if not self.support_levels and not self.resistance_levels:
            return 'neutral'

        try:
            # Check proximity to support (demand zone)
            for support in self.support_levels:
                if abs(price - support) / support < 0.02:  # Within 2%
                    return 'demand_zone'

            # Check proximity to resistance (supply zone)
            for resistance in self.resistance_levels:
                if abs(price - resistance) / resistance < 0.02:
                    return 'supply_zone'

            # Check for mid-range (between support and resistance)
            if self.support_levels and self.resistance_levels:
                nearest_support = min(self.support_levels, key=lambda x: abs(x - price))
                nearest_resistance = min(self.resistance_levels, key=lambda x: abs(x - price))

                if nearest_support < price < nearest_resistance:
                    range_position = (price - nearest_support) / (nearest_resistance - nearest_support)
                    if 0.4 < range_position < 0.6:
                        return 'mid_range'

            # Check for liquidity void (price far from any level)
            all_levels = self.support_levels + self.resistance_levels
            if all_levels:
                nearest = min(all_levels, key=lambda x: abs(x - price))
                if abs(price - nearest) / nearest > 0.05:  # > 5% away from any level
                    return 'liquidity_void'

            return 'neutral'

        except Exception as e:
            logger.warning(f"Location determination error: {str(e)}")
            return 'neutral'

    def get_all_patterns(self) -> Dict[str, Any]:
        """
        Get all detected patterns with analysis

        Returns:
            Dictionary with candle patterns, chart patterns, and summary
        """
        candle_patterns = self.detect_candle_patterns()
        chart_patterns = self.detect_chart_patterns()

        all_patterns = candle_patterns + chart_patterns

        # Determine dominant bias
        long_score = sum(p['final_score'] for p in all_patterns if p['bias'] == 'LONG')
        short_score = sum(p['final_score'] for p in all_patterns if p['bias'] == 'SHORT')

        if long_score > short_score * 1.2:
            dominant_bias = 'LONG'
        elif short_score > long_score * 1.2:
            dominant_bias = 'SHORT'
        else:
            dominant_bias = 'NEUTRAL'

        # Get best pattern
        best_pattern = max(all_patterns, key=lambda x: x['final_score']) if all_patterns else None

        return {
            'candle_patterns': candle_patterns,
            'chart_patterns': chart_patterns,
            'total_patterns': len(all_patterns),
            'dominant_bias': dominant_bias,
            'long_score': round(long_score, 2),
            'short_score': round(short_score, 2),
            'best_pattern': best_pattern,
            'support_levels': [round(l, 2) for l in self.support_levels],
            'resistance_levels': [round(l, 2) for l in self.resistance_levels],
            'timestamp': datetime.now().isoformat()
        }

    def calculate_pattern_strength_score(self) -> int:
        """
        Calculate pattern strength score (0-20) for scoring engine

        Returns:
            Pattern strength score
        """
        patterns = self.get_all_patterns()

        if patterns['total_patterns'] == 0:
            return 5  # Minimum score

        score = 0

        # Best pattern contribution (max 10 points)
        if patterns['best_pattern']:
            score += min(patterns['best_pattern']['final_score'], 10)

        # Multiple pattern confirmation (max 5 points)
        if patterns['total_patterns'] >= 2:
            score += 3
        if patterns['total_patterns'] >= 3:
            score += 2

        # Bias alignment bonus (max 5 points)
        if patterns['dominant_bias'] != 'NEUTRAL':
            if patterns['long_score'] > 15 or patterns['short_score'] > 15:
                score += 5
            elif patterns['long_score'] > 10 or patterns['short_score'] > 10:
                score += 3

        return min(int(score), 20)
