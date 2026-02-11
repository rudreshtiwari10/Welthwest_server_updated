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
import warnings

# Suppress common warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=FutureWarning)
pd.options.mode.chained_assignment = None

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

    # Pattern definitions - COMPREHENSIVE COLLECTION
    # Enhanced with 20+ candlestick patterns for complete market coverage
    CANDLE_PATTERNS = {
        # Single Candle Patterns
        'bullish_marubozu': {'bias': 'LONG', 'base_score': 18, 'reliability': 0.70},
        'bearish_marubozu': {'bias': 'SHORT', 'base_score': 18, 'reliability': 0.70},
        'hammer': {'bias': 'LONG', 'base_score': 12, 'reliability': 0.60},
        'inverted_hammer': {'bias': 'LONG', 'base_score': 11, 'reliability': 0.58},
        'hanging_man': {'bias': 'SHORT', 'base_score': 13, 'reliability': 0.62},
        'shooting_star': {'bias': 'SHORT', 'base_score': 12, 'reliability': 0.60},
        'doji': {'bias': 'NEUTRAL', 'base_score': 8, 'reliability': 0.50},
        'dragonfly_doji': {'bias': 'LONG', 'base_score': 14, 'reliability': 0.63},
        'gravestone_doji': {'bias': 'SHORT', 'base_score': 14, 'reliability': 0.63},

        # Two Candle Patterns
        'bullish_engulfing': {'bias': 'LONG', 'base_score': 15, 'reliability': 0.65},
        'bearish_engulfing': {'bias': 'SHORT', 'base_score': 15, 'reliability': 0.65},
        'bearish_engulfing_volume': {'bias': 'SHORT', 'base_score': 20, 'reliability': 0.75},
        'bullish_harami': {'bias': 'LONG', 'base_score': 13, 'reliability': 0.61},
        'bearish_harami': {'bias': 'SHORT', 'base_score': 13, 'reliability': 0.61},
        'piercing_pattern': {'bias': 'LONG', 'base_score': 16, 'reliability': 0.67},
        'dark_cloud_cover': {'bias': 'SHORT', 'base_score': 16, 'reliability': 0.67},
        'tweezer_top': {'bias': 'SHORT', 'base_score': 14, 'reliability': 0.64},
        'tweezer_bottom': {'bias': 'LONG', 'base_score': 14, 'reliability': 0.64},
        'bullish_belt_hold': {'bias': 'LONG', 'base_score': 12, 'reliability': 0.59},
        'bearish_belt_hold': {'bias': 'SHORT', 'base_score': 12, 'reliability': 0.59},
        'inside_bar': {'bias': 'NEUTRAL', 'base_score': 10, 'reliability': 0.55},

        # Three Candle Patterns
        'morning_star': {'bias': 'LONG', 'base_score': 20, 'reliability': 0.73},
        'evening_star': {'bias': 'SHORT', 'base_score': 20, 'reliability': 0.73},
        'three_white_soldiers': {'bias': 'LONG', 'base_score': 22, 'reliability': 0.72},
        'three_black_crows': {'bias': 'SHORT', 'base_score': 22, 'reliability': 0.72},
        'morning_doji_star': {'bias': 'LONG', 'base_score': 19, 'reliability': 0.71},
        'evening_doji_star': {'bias': 'SHORT', 'base_score': 19, 'reliability': 0.71},
        'three_inside_up': {'bias': 'LONG', 'base_score': 17, 'reliability': 0.68},
        'three_inside_down': {'bias': 'SHORT', 'base_score': 17, 'reliability': 0.68},
        'three_outside_up': {'bias': 'LONG', 'base_score': 18, 'reliability': 0.69},
        'three_outside_down': {'bias': 'SHORT', 'base_score': 18, 'reliability': 0.69},

        # Advanced Patterns
        'upper_wick_rejection': {'bias': 'SHORT', 'base_score': 16, 'reliability': 0.68},
        'lower_wick_rejection': {'bias': 'LONG', 'base_score': 16, 'reliability': 0.68},
        'island_reversal_up': {'bias': 'LONG', 'base_score': 24, 'reliability': 0.78},
        'island_reversal_down': {'bias': 'SHORT', 'base_score': 24, 'reliability': 0.78},
        'abandoned_baby_bullish': {'bias': 'LONG', 'base_score': 23, 'reliability': 0.76},
        'abandoned_baby_bearish': {'bias': 'SHORT', 'base_score': 23, 'reliability': 0.76},
    }

    # Chart patterns - COMPREHENSIVE COLLECTION
    # Enhanced with classic continuation and reversal patterns
    CHART_PATTERNS = {
        # Continuation Patterns
        'bull_flag': {'bias': 'LONG', 'base_score': 20, 'reliability': 0.70},
        'bear_flag': {'bias': 'SHORT', 'base_score': 20, 'reliability': 0.70},
        'bull_pennant': {'bias': 'LONG', 'base_score': 19, 'reliability': 0.69},
        'bear_pennant': {'bias': 'SHORT', 'base_score': 19, 'reliability': 0.69},
        'rising_wedge': {'bias': 'SHORT', 'base_score': 17, 'reliability': 0.66},  # Bearish continuation
        'falling_wedge': {'bias': 'LONG', 'base_score': 17, 'reliability': 0.66},  # Bullish continuation
        'ascending_channel': {'bias': 'LONG', 'base_score': 16, 'reliability': 0.64},
        'descending_channel': {'bias': 'SHORT', 'base_score': 16, 'reliability': 0.64},

        # Triangle Patterns
        'ascending_triangle': {'bias': 'LONG', 'base_score': 18, 'reliability': 0.68},
        'descending_triangle': {'bias': 'SHORT', 'base_score': 18, 'reliability': 0.68},
        'symmetrical_triangle': {'bias': 'NEUTRAL', 'base_score': 15, 'reliability': 0.60},

        # Reversal Patterns
        'double_top': {'bias': 'SHORT', 'base_score': 21, 'reliability': 0.72},
        'double_bottom': {'bias': 'LONG', 'base_score': 21, 'reliability': 0.72},
        'triple_top': {'bias': 'SHORT', 'base_score': 23, 'reliability': 0.74},
        'triple_bottom': {'bias': 'LONG', 'base_score': 23, 'reliability': 0.74},
        'head_and_shoulders': {'bias': 'SHORT', 'base_score': 24, 'reliability': 0.76},
        'inverse_head_and_shoulders': {'bias': 'LONG', 'base_score': 24, 'reliability': 0.76},
        'cup_and_handle': {'bias': 'LONG', 'base_score': 22, 'reliability': 0.73},
        'inverse_cup_and_handle': {'bias': 'SHORT', 'base_score': 22, 'reliability': 0.73},
        'rounding_bottom': {'bias': 'LONG', 'base_score': 20, 'reliability': 0.71},
        'rounding_top': {'bias': 'SHORT', 'base_score': 20, 'reliability': 0.71},

        # Breakout Patterns
        'range_breakout': {'bias': 'NEUTRAL', 'base_score': 16, 'reliability': 0.65},
        'support_breakout': {'bias': 'LONG', 'base_score': 18, 'reliability': 0.67},
        'resistance_breakdown': {'bias': 'SHORT', 'base_score': 18, 'reliability': 0.67},
        'consolidation_breakout': {'bias': 'NEUTRAL', 'base_score': 17, 'reliability': 0.66},
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
                prev_high = previous['High']
                prev_low = previous['Low']
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

                # ========== MORE SINGLE CANDLE PATTERNS ==========

                # Inverted Hammer (bullish at support)
                if (current_range > 0 and
                    current_body < current_range * 0.3 and  # Small body
                    (current_high - max(current_close, current_open)) > current_body * 2 and  # Long upper wick
                    (min(current_close, current_open) - current_low) < current_body * 0.5):  # Short lower wick
                    patterns.append(self._create_pattern(
                        'inverted_hammer', i, current_close, 'LONG'
                    ))

                # Hanging Man (bearish at resistance, looks like hammer)
                if (current_range > 0 and
                    current_body < current_range * 0.3 and
                    (current_low - min(current_open, current_close)) > current_body * 2 and
                    (current_high - max(current_open, current_close)) < current_body * 0.5 and
                    i > 0 and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]):  # After uptrend
                    patterns.append(self._create_pattern(
                        'hanging_man', i, current_close, 'SHORT'
                    ))

                # Dragonfly Doji (long lower shadow, no upper shadow)
                if (current_range > 0 and
                    current_body < current_range * 0.1 and
                    (min(current_close, current_open) - current_low) > current_range * 0.6 and
                    (current_high - max(current_close, current_open)) < current_range * 0.1):
                    patterns.append(self._create_pattern(
                        'dragonfly_doji', i, current_close, 'LONG'
                    ))

                # Gravestone Doji (long upper shadow, no lower shadow)
                if (current_range > 0 and
                    current_body < current_range * 0.1 and
                    (current_high - max(current_close, current_open)) > current_range * 0.6 and
                    (min(current_close, current_open) - current_low) < current_range * 0.1):
                    patterns.append(self._create_pattern(
                        'gravestone_doji', i, current_close, 'SHORT'
                    ))

                # ========== TWO CANDLE PATTERNS ==========

                # Bullish Harami (small candle inside previous large bearish candle)
                if (prev_close < prev_open and  # Previous bearish
                    current_close > current_open and  # Current bullish
                    current_open > prev_close and
                    current_close < prev_open and
                    current_body < prev_body * 0.7):
                    patterns.append(self._create_pattern(
                        'bullish_harami', i, current_close, 'LONG'
                    ))

                # Bearish Harami (small candle inside previous large bullish candle)
                if (prev_close > prev_open and  # Previous bullish
                    current_close < current_open and  # Current bearish
                    current_open < prev_close and
                    current_close > prev_open and
                    current_body < prev_body * 0.7):
                    patterns.append(self._create_pattern(
                        'bearish_harami', i, current_close, 'SHORT'
                    ))

                # Piercing Pattern (bullish reversal)
                if (prev_close < prev_open and  # Previous bearish
                    current_close > current_open and  # Current bullish
                    current_open < prev_low and
                    current_close > (prev_open + prev_close) / 2 and
                    current_close < prev_open):
                    patterns.append(self._create_pattern(
                        'piercing_pattern', i, current_close, 'LONG'
                    ))

                # Dark Cloud Cover (bearish reversal)
                if (prev_close > prev_open and  # Previous bullish
                    current_close < current_open and  # Current bearish
                    current_open > prev_high and
                    current_close < (prev_open + prev_close) / 2 and
                    current_close > prev_open):
                    patterns.append(self._create_pattern(
                        'dark_cloud_cover', i, current_close, 'SHORT'
                    ))

                # Tweezer Bottom (two candles with same low)
                if (prev_low > 0 and abs(current_low - prev_low) / prev_low < 0.002 and  # Same lows
                    prev_close < prev_open and  # First bearish
                    current_close > current_open):  # Second bullish
                    patterns.append(self._create_pattern(
                        'tweezer_bottom', i, current_close, 'LONG'
                    ))

                # Tweezer Top (two candles with same high)
                if (prev_high > 0 and abs(current_high - prev_high) / prev_high < 0.002 and  # Same highs
                    prev_close > prev_open and  # First bullish
                    current_close < current_open):  # Second bearish
                    patterns.append(self._create_pattern(
                        'tweezer_top', i, current_close, 'SHORT'
                    ))

                # Bullish Belt Hold (strong bullish marubozu opening at low)
                if (current_close > current_open and
                    current_body > current_range * 0.85 and
                    current_open == current_low and
                    i > 0 and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]):
                    patterns.append(self._create_pattern(
                        'bullish_belt_hold', i, current_close, 'LONG'
                    ))

                # Bearish Belt Hold (strong bearish marubozu opening at high)
                if (current_close < current_open and
                    current_body > current_range * 0.85 and
                    current_open == current_high and
                    i > 0 and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]):
                    patterns.append(self._create_pattern(
                        'bearish_belt_hold', i, current_close, 'SHORT'
                    ))

                # Lower Wick Rejection (bullish at support)
                lower_shadow = min(current_close, current_open) - current_low

                if (current_range > 0 and
                    lower_shadow > current_body * 2.0 and
                    lower_shadow > (current_high - max(current_close, current_open)) * 2.0 and
                    current_close > current_open):
                    patterns.append(self._create_pattern(
                        'lower_wick_rejection', i, current_close, 'LONG'
                    ))

            # ========== THREE CANDLE PATTERNS ==========

            # Three White Soldiers (3 consecutive green candles)
            if len(df) >= 3:
                last_3 = df.tail(3)
                all_green = all(last_3['Close'].iloc[j] > last_3['Open'].iloc[j] for j in range(3))
                higher_closes = all(last_3['Close'].iloc[j] > last_3['Close'].iloc[j-1] for j in range(1, 3))
                higher_opens = all(last_3['Open'].iloc[j] > last_3['Open'].iloc[j-1] for j in range(1, 3))

                if all_green and higher_closes and higher_opens:
                    patterns.append(self._create_pattern(
                        'three_white_soldiers', len(df) - 1, df['Close'].iloc[-1], 'LONG'
                    ))

            # Three Black Crows (3 consecutive red candles)
            if len(df) >= 3:
                last_3 = df.tail(3)
                all_red = all(last_3['Close'].iloc[j] < last_3['Open'].iloc[j] for j in range(3))
                lower_closes = all(last_3['Close'].iloc[j] < last_3['Close'].iloc[j-1] for j in range(1, 3))
                lower_opens = all(last_3['Open'].iloc[j] < last_3['Open'].iloc[j-1] for j in range(1, 3))

                if all_red and lower_closes and lower_opens:
                    patterns.append(self._create_pattern(
                        'three_black_crows', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

            # Morning Star (3-candle bullish reversal)
            if len(df) >= 3:
                c1_open, c1_close = df['Open'].iloc[-3], df['Close'].iloc[-3]
                c2_open, c2_close = df['Open'].iloc[-2], df['Close'].iloc[-2]
                c3_open, c3_close = df['Open'].iloc[-1], df['Close'].iloc[-1]
                c2_body = abs(c2_close - c2_open)
                c1_body = abs(c1_close - c1_open)

                if (c1_close < c1_open and  # First bearish
                    c2_body < c1_body * 0.3 and  # Small middle candle
                    c3_close > c3_open and  # Third bullish
                    c3_close > (c1_open + c1_close) / 2):  # Closes above midpoint of first
                    patterns.append(self._create_pattern(
                        'morning_star', len(df) - 1, df['Close'].iloc[-1], 'LONG'
                    ))

            # Evening Star (3-candle bearish reversal)
            if len(df) >= 3:
                c1_open, c1_close = df['Open'].iloc[-3], df['Close'].iloc[-3]
                c2_open, c2_close = df['Open'].iloc[-2], df['Close'].iloc[-2]
                c3_open, c3_close = df['Open'].iloc[-1], df['Close'].iloc[-1]
                c2_body = abs(c2_close - c2_open)
                c1_body = abs(c1_close - c1_open)

                if (c1_close > c1_open and  # First bullish
                    c2_body < c1_body * 0.3 and  # Small middle candle
                    c3_close < c3_open and  # Third bearish
                    c3_close < (c1_open + c1_close) / 2):  # Closes below midpoint of first
                    patterns.append(self._create_pattern(
                        'evening_star', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

            # Three Inside Up (bullish harami followed by confirmation)
            if len(df) >= 3:
                c1_open, c1_close = df['Open'].iloc[-3], df['Close'].iloc[-3]
                c2_open, c2_close = df['Open'].iloc[-2], df['Close'].iloc[-2]
                c3_close = df['Close'].iloc[-1]

                if (c1_close < c1_open and  # First bearish
                    c2_close > c2_open and  # Second bullish (harami)
                    c2_open > c1_close and c2_close < c1_open and
                    c3_close > c2_close):  # Third confirms
                    patterns.append(self._create_pattern(
                        'three_inside_up', len(df) - 1, df['Close'].iloc[-1], 'LONG'
                    ))

            # Three Inside Down (bearish harami followed by confirmation)
            if len(df) >= 3:
                c1_open, c1_close = df['Open'].iloc[-3], df['Close'].iloc[-3]
                c2_open, c2_close = df['Open'].iloc[-2], df['Close'].iloc[-2]
                c3_close = df['Close'].iloc[-1]

                if (c1_close > c1_open and  # First bullish
                    c2_close < c2_open and  # Second bearish (harami)
                    c2_open < c1_close and c2_close > c1_open and
                    c3_close < c2_close):  # Third confirms
                    patterns.append(self._create_pattern(
                        'three_inside_down', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

            # Island Reversal Up (gap down then gap up)
            if len(df) >= 3:
                gap_down = df['High'].iloc[-2] < df['Low'].iloc[-3]
                gap_up = df['Low'].iloc[-1] > df['High'].iloc[-2]

                if gap_down and gap_up:
                    patterns.append(self._create_pattern(
                        'island_reversal_up', len(df) - 1, df['Close'].iloc[-1], 'LONG'
                    ))

            # Island Reversal Down (gap up then gap down)
            if len(df) >= 3:
                gap_up = df['Low'].iloc[-2] > df['High'].iloc[-3]
                gap_down = df['High'].iloc[-1] < df['Low'].iloc[-2]

                if gap_up and gap_down:
                    patterns.append(self._create_pattern(
                        'island_reversal_down', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

            # Abandoned Baby Bullish (gap down doji gap up)
            if len(df) >= 3:
                c1_close = df['Close'].iloc[-3]
                c2_high, c2_low = df['High'].iloc[-2], df['Low'].iloc[-2]
                c2_body = abs(df['Close'].iloc[-2] - df['Open'].iloc[-2])
                c2_range = c2_high - c2_low
                c3_open = df['Open'].iloc[-1]

                if (c2_body < c2_range * 0.1 and  # Middle is doji
                    c2_high < df['Low'].iloc[-3] and  # Gap down from first
                    c3_open > c2_high):  # Gap up to third
                    patterns.append(self._create_pattern(
                        'abandoned_baby_bullish', len(df) - 1, df['Close'].iloc[-1], 'LONG'
                    ))

            # Abandoned Baby Bearish (gap up doji gap down)
            if len(df) >= 3:
                c1_close = df['Close'].iloc[-3]
                c2_high, c2_low = df['High'].iloc[-2], df['Low'].iloc[-2]
                c2_body = abs(df['Close'].iloc[-2] - df['Open'].iloc[-2])
                c2_range = c2_high - c2_low
                c3_open = df['Open'].iloc[-1]

                if (c2_body < c2_range * 0.1 and  # Middle is doji
                    c2_low > df['High'].iloc[-3] and  # Gap up from first
                    c3_open < c2_low):  # Gap down to third
                    patterns.append(self._create_pattern(
                        'abandoned_baby_bearish', len(df) - 1, df['Close'].iloc[-1], 'SHORT'
                    ))

        except Exception as e:
            logger.error(f"Error detecting candle patterns: {str(e)}")

        return patterns

    def detect_chart_patterns(self) -> List[Dict[str, Any]]:
        """
        Detect chart patterns (flags, triangles, ranges, reversals)

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

            # Detect flags and pennants
            flag_result = self._detect_flag(df)
            if flag_result:
                patterns.append(flag_result)

            # Detect double tops/bottoms
            double_result = self._detect_double_patterns(df)
            if double_result:
                patterns.append(double_result)

            # Detect head and shoulders
            hs_result = self._detect_head_shoulders(df)
            if hs_result:
                patterns.append(hs_result)

            # Detect cup and handle
            cup_result = self._detect_cup_handle(df)
            if cup_result:
                patterns.append(cup_result)

            # Detect wedges
            wedge_result = self._detect_wedge(df)
            if wedge_result:
                patterns.append(wedge_result)

            # Detect channels
            channel_result = self._detect_channel(df)
            if channel_result:
                patterns.append(channel_result)

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

    def _detect_double_patterns(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect double top/bottom patterns"""
        try:
            if len(df) < 30:
                return None

            highs = df['High'].values
            lows = df['Low'].values
            current = df['Close'].iloc[-1]

            # Find peaks and troughs
            window = 5
            peaks = []
            troughs = []

            for i in range(window, len(df) - window):
                if highs[i] == max(highs[i-window:i+window+1]):
                    peaks.append((i, highs[i]))
                if lows[i] == min(lows[i-window:i+window+1]):
                    troughs.append((i, lows[i]))

            # Double Top: Two peaks at similar levels
            if len(peaks) >= 2:
                last_two_peaks = peaks[-2:]
                peak1_price = last_two_peaks[0][1]
                peak2_price = last_two_peaks[1][1]

                if peak1_price > 0 and abs(peak1_price - peak2_price) / peak1_price < 0.03:  # Within 3%
                    # Safely get neckline
                    neckline_values = []
                    for p in last_two_peaks:
                        if p[0] < len(lows):
                            neckline_values.extend(lows[p[0]:])
                    neckline = min(neckline_values) if neckline_values else current

                    if neckline > 0 and current < neckline * 0.98:  # Breakdown confirmed
                        return self._create_pattern(
                            'double_top', len(df) - 1, current, 'SHORT',
                            extra={'peaks': [peak1_price, peak2_price], 'neckline': neckline}
                        )

            # Double Bottom: Two troughs at similar levels
            if len(troughs) >= 2:
                last_two_troughs = troughs[-2:]
                trough1_price = last_two_troughs[0][1]
                trough2_price = last_two_troughs[1][1]

                if trough1_price > 0 and abs(trough1_price - trough2_price) / trough1_price < 0.03:
                    # Safely get neckline
                    neckline_values = []
                    for t in last_two_troughs:
                        if t[0] < len(highs):
                            neckline_values.extend(highs[t[0]:])
                    neckline = max(neckline_values) if neckline_values else current

                    if neckline > 0 and current > neckline * 1.02:  # Breakout confirmed
                        return self._create_pattern(
                            'double_bottom', len(df) - 1, current, 'LONG',
                            extra={'troughs': [trough1_price, trough2_price], 'neckline': neckline}
                        )

        except Exception as e:
            logger.warning(f"Double pattern detection error: {str(e)}")

        return None

    def _detect_head_shoulders(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect head and shoulders / inverse head and shoulders"""
        try:
            if len(df) < 40:
                return None

            highs = df['High'].values
            lows = df['Low'].values
            current = df['Close'].iloc[-1]

            # Find peaks and troughs
            window = 5
            peaks = []
            troughs = []

            for i in range(window, len(df) - window):
                if highs[i] == max(highs[i-window:i+window+1]):
                    peaks.append((i, highs[i]))
                if lows[i] == min(lows[i-window:i+window+1]):
                    troughs.append((i, lows[i]))

            # Head and Shoulders: left shoulder < head > right shoulder
            if len(peaks) >= 3:
                last_three = peaks[-3:]
                left = last_three[0][1]
                head = last_three[1][1]
                right = last_three[2][1]

                if (left > 0 and head > left * 1.05 and head > right * 1.05 and
                    abs(left - right) / left < 0.05):  # Shoulders similar
                    # Safely get neckline
                    neckline_values = []
                    for p in last_three:
                        if p[0] < len(lows):
                            neckline_values.extend(lows[p[0]:])
                    neckline = min(neckline_values) if neckline_values else current

                    if neckline > 0 and current < neckline * 0.98:
                        return self._create_pattern(
                            'head_and_shoulders', len(df) - 1, current, 'SHORT',
                            extra={'left_shoulder': left, 'head': head, 'right_shoulder': right, 'neckline': neckline}
                        )

            # Inverse Head and Shoulders
            if len(troughs) >= 3:
                last_three = troughs[-3:]
                left = last_three[0][1]
                head = last_three[1][1]
                right = last_three[2][1]

                if (left > 0 and head < left * 0.95 and head < right * 0.95 and
                    abs(left - right) / left < 0.05):
                    # Safely get neckline
                    neckline_values = []
                    for t in last_three:
                        if t[0] < len(highs):
                            neckline_values.extend(highs[t[0]:])
                    neckline = max(neckline_values) if neckline_values else current

                    if neckline > 0 and current > neckline * 1.02:
                        return self._create_pattern(
                            'inverse_head_and_shoulders', len(df) - 1, current, 'LONG',
                            extra={'left_shoulder': left, 'head': head, 'right_shoulder': right, 'neckline': neckline}
                        )

        except Exception as e:
            logger.warning(f"Head and shoulders detection error: {str(e)}")

        return None

    def _detect_cup_handle(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect cup and handle pattern"""
        try:
            if len(df) < 40:
                return None

            closes = df['Close'].values
            current = df['Close'].iloc[-1]

            # Cup: U-shaped recovery (first 30 bars)
            cup_data = closes[-40:-10]
            if len(cup_data) < 20:
                return None

            cup_high = max(cup_data[:10])
            cup_low = min(cup_data[10:20])
            cup_recovery = max(cup_data[20:])

            # Handle: Small consolidation (last 10 bars)
            handle_data = closes[-10:]
            handle_high = max(handle_data)
            handle_low = min(handle_data)

            # Cup and Handle bullish
            if (cup_low < cup_high * 0.9 and  # Significant cup depth
                cup_recovery > cup_high * 0.95 and  # Recovery near high
                handle_high < cup_recovery * 1.02 and  # Handle below cup
                current > handle_high * 1.01):  # Breakout
                return self._create_pattern(
                    'cup_and_handle', len(df) - 1, current, 'LONG',
                    extra={'cup_depth': (cup_high - cup_low) / cup_high * 100}
                )

            # Inverse cup and handle (bearish)
            cup_low_inv = min(cup_data[:10])
            cup_high_inv = max(cup_data[10:20])
            cup_decline = min(cup_data[20:])

            if (cup_high_inv > cup_low_inv * 1.1 and
                cup_decline < cup_low_inv * 1.05 and
                handle_low > cup_decline * 0.98 and
                current < handle_low * 0.99):
                return self._create_pattern(
                    'inverse_cup_and_handle', len(df) - 1, current, 'SHORT'
                )

        except Exception as e:
            logger.warning(f"Cup and handle detection error: {str(e)}")

        return None

    def _detect_wedge(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect rising/falling wedge patterns"""
        try:
            if len(df) < 30:
                return None

            highs = df['High'].values
            lows = df['Low'].values
            x = np.arange(len(highs))
            current = df['Close'].iloc[-1]

            # Linear regression for highs and lows
            high_slope = np.polyfit(x[-20:], highs[-20:], 1)[0]
            low_slope = np.polyfit(x[-20:], lows[-20:], 1)[0]

            # Rising Wedge: Both slopes positive but converging (bearish)
            if (high_slope > 0 and low_slope > 0 and
                low_slope > high_slope * 1.2):  # Lower line rising faster
                recent_high = max(highs[-10:])
                if current < recent_high * 0.97:  # Breakdown
                    return self._create_pattern(
                        'rising_wedge', len(df) - 1, current, 'SHORT'
                    )

            # Falling Wedge: Both slopes negative but converging (bullish)
            elif (high_slope < 0 and low_slope < 0 and
                  high_slope < low_slope * 1.2):  # Upper line falling faster
                recent_low = min(lows[-10:])
                if current > recent_low * 1.03:  # Breakout
                    return self._create_pattern(
                        'falling_wedge', len(df) - 1, current, 'LONG'
                    )

        except Exception as e:
            logger.warning(f"Wedge detection error: {str(e)}")

        return None

    def _detect_channel(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect ascending/descending channels"""
        try:
            if len(df) < 30:
                return None

            highs = df['High'].values
            lows = df['Low'].values
            x = np.arange(len(highs))
            current = df['Close'].iloc[-1]

            # Linear regression
            high_slope = np.polyfit(x[-20:], highs[-20:], 1)[0]
            low_slope = np.polyfit(x[-20:], lows[-20:], 1)[0]

            # Ascending Channel: Parallel upward slopes
            if (high_slope > 0.2 and low_slope > 0.2 and
                high_slope != 0 and abs(high_slope - low_slope) / abs(high_slope) < 0.3):  # Parallel
                return self._create_pattern(
                    'ascending_channel', len(df) - 1, current, 'LONG'
                )

            # Descending Channel: Parallel downward slopes
            elif (high_slope < -0.2 and low_slope < -0.2 and
                  high_slope != 0 and abs(high_slope - low_slope) / abs(high_slope) < 0.3):
                return self._create_pattern(
                    'descending_channel', len(df) - 1, current, 'SHORT'
                )

        except Exception as e:
            logger.warning(f"Channel detection error: {str(e)}")

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
