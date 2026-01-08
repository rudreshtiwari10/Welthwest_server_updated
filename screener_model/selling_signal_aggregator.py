"""
Selling Signal Aggregator - Combines All SHORT Signals

This module aggregates signals from:
- BreakdownDetector - Resistance breakdowns, new lows, patterns
- NewLowsDetector - New period lows, cascade targets
- ResistanceFader - Fade opportunities at resistance

Outputs a comprehensive SHORT score (0-100) with:
- Breakdown signals score
- Resistance proximity score
- Bearish technical indicators score
- Volume confirmation score
- Market regime alignment score
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

from screener_model.breakdown_detector import BreakdownDetector
from screener_model.new_lows_detector import NewLowsDetector
from screener_model.resistance_fader import ResistanceFader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SellingSignalAggregator:
    """
    Aggregates all selling signals into a comprehensive SHORT score

    FIX #5: VOLUME-LED SCORING
    Increased volume weight, decreased proximity weight
    Volume must be the primary driver, not proximity alone
    """

    # Score weights for SHORT calculation (FIX #5: Volume-led)
    SHORT_SCORE_WEIGHTS = {
        'volume_confirmation': 30,    # Volume supporting downmove (INCREASED from 15)
        'breakdown_signals': 25,      # Breakdown patterns (slightly reduced)
        'bearish_indicators': 20,     # RSI, MACD bearish signals
        'resistance_proximity': 15,   # Distance to resistance (DECREASED from 25)
        'bearish_patterns': 10        # Candlestick patterns
    }

    # Market regime multipliers for SHORT trades
    REGIME_MULTIPLIERS_SHORT = {
        'Bearish Trend': 1.5,        # Strongest for shorts
        'High Volatility': 1.2,      # Good for shorts
        'Low Volatility': 1.0,       # Neutral
        'Bullish Trend': 0.7         # Risky for shorts
    }

    def __init__(self, df: pd.DataFrame, timeframe: str = '1d', regime: str = 'Unknown'):
        """
        Initialize with OHLCV data

        Args:
            df: DataFrame with Open, High, Low, Close, Volume columns
            timeframe: One of '5m', '15m', '1h', '1d'
            regime: Current market regime for early application (FIX #6)
        """
        self.df = df.copy() if df is not None else pd.DataFrame()
        self.timeframe = timeframe
        self.regime = regime

        # Initialize sub-detectors (FIX #6: Pass regime early)
        self.breakdown_detector = BreakdownDetector(df, timeframe)
        self.new_lows_detector = NewLowsDetector(df, timeframe)
        self.resistance_fader = ResistanceFader(df, timeframe, regime)  # Pass regime for gating

    def calculate_breakdown_score(self) -> Tuple[int, Dict]:
        """
        Calculate score from breakdown signals (0-25 points) - FIX #5 adjusted
        """
        max_score = self.SHORT_SCORE_WEIGHTS['breakdown_signals']
        score = 0
        details = {}

        try:
            breakdown_result = self.breakdown_detector.detect_all_breakdowns()
            new_lows_result = self.new_lows_detector.get_comprehensive_analysis()
            fade_result = self.resistance_fader.get_all_fade_signals()

            # Breakdown signals (up to 15 points)
            if breakdown_result.get('has_breakdown'):
                best_breakdown = breakdown_result.get('best_signal', {})
                conf = best_breakdown.get('confidence', 0)
                score += int(15 * conf)
                details['breakdown_type'] = best_breakdown.get('type', 'Unknown')
                details['breakdown_confidence'] = conf

            # New lows signals (up to 8 points)
            if new_lows_result.get('has_new_lows'):
                new_lows_signal = new_lows_result.get('new_lows_signal', {})
                conf = new_lows_signal.get('confidence', 0)
                score += int(8 * conf)
                details['new_lows'] = True
                details['new_lows_confidence'] = conf

            # Fade signals (up to 7 points)
            if fade_result.get('has_fade_signal'):
                best_fade = fade_result.get('best_signal', {})
                conf = best_fade.get('confidence', 0)
                score += int(7 * conf)
                details['fade_signal'] = best_fade.get('type', 'Unknown')

            details['raw_score'] = min(score, max_score)

        except Exception as e:
            logger.debug(f"Error calculating breakdown score: {e}")
            score = 5  # Minimum score

        return min(score, max_score), details

    def calculate_resistance_proximity_score(self) -> Tuple[int, Dict]:
        """
        Calculate score based on proximity to resistance (0-15 points)

        FIX #5: REDUCED WEIGHT
        Proximity alone should NOT dominate the score
        Closer to resistance = higher SHORT potential, but needs volume confirmation
        """
        max_score = self.SHORT_SCORE_WEIGHTS['resistance_proximity']  # Now 15
        score = 0
        details = {}

        try:
            if self.df is None or self.df.empty:
                return 3, {'status': 'no_data'}

            current_close = self.df['Close'].iloc[-1]

            # Get resistance levels
            resistance_levels = self.resistance_fader.find_resistance_levels()

            if not resistance_levels:
                return 3, {'status': 'no_resistance_found'}

            nearest_resistance = resistance_levels[0]

            # Calculate distance to resistance (%)
            dist_to_resistance = ((nearest_resistance - current_close) / current_close) * 100

            # Score based on proximity (FIX #5: Reduced scores)
            if dist_to_resistance <= 0:  # At or above resistance
                score = 15  # Maximum
                details['position'] = 'at_resistance'
            elif dist_to_resistance < 1.0:
                score = 12
                details['position'] = 'very_close'
            elif dist_to_resistance < 2.5:
                score = 9
                details['position'] = 'close'
            elif dist_to_resistance < 5.0:
                score = 5
                details['position'] = 'moderate'
            else:
                score = 2
                details['position'] = 'far'

            details['nearest_resistance'] = round(nearest_resistance, 2)
            details['distance_pct'] = round(dist_to_resistance, 2)
            details['current_price'] = round(current_close, 2)

        except Exception as e:
            logger.debug(f"Error calculating resistance proximity: {e}")
            score = 3

        return min(score, max_score), details

    def calculate_bearish_indicators_score(self) -> Tuple[int, Dict]:
        """
        Calculate score from bearish technical indicators (0-20 points)

        RSI overbought: +8 pts
        MACD bearish: +10 pts
        ADX strong trend: +7 pts (only if bearish)
        """
        max_score = self.SHORT_SCORE_WEIGHTS['bearish_indicators']
        score = 0
        details = {}

        try:
            if self.df is None or len(self.df) < 26:
                return 5, {'status': 'insufficient_data'}

            closes = self.df['Close']

            # RSI calculation
            delta = closes.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = 100 - (100 / (1 + rs))
            rsi_current = float(rsi.iloc[-1])

            # RSI overbought scoring
            if rsi_current > 80:
                score += 8
                details['rsi_status'] = 'extreme_overbought'
            elif rsi_current > 70:
                score += 6
                details['rsi_status'] = 'overbought'
            elif rsi_current > 60:
                score += 2
                details['rsi_status'] = 'slightly_overbought'
            else:
                details['rsi_status'] = 'neutral'

            details['rsi'] = round(rsi_current, 2)

            # MACD calculation
            ema_12 = closes.ewm(span=12).mean()
            ema_26 = closes.ewm(span=26).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9).mean()

            macd_current = float(macd_line.iloc[-1])
            signal_current = float(signal_line.iloc[-1])
            macd_prev = float(macd_line.iloc[-2]) if len(macd_line) > 1 else macd_current

            # MACD bearish crossing
            if macd_current < signal_current:
                if macd_prev > signal_line.iloc[-2]:
                    # Fresh bearish cross (death cross)
                    score += 10
                    details['macd_status'] = 'death_cross'
                else:
                    score += 5
                    details['macd_status'] = 'bearish'
            else:
                details['macd_status'] = 'bullish'

            details['macd'] = round(macd_current, 4)
            details['macd_signal'] = round(signal_current, 4)

            # ADX for trend strength (simplified)
            if len(self.df) >= 14:
                # Price trend direction
                price_change_5d = (closes.iloc[-1] - closes.iloc[-5]) / closes.iloc[-5] * 100

                if price_change_5d < -2:  # Bearish trend
                    score += 5
                    details['trend_direction'] = 'bearish'
                elif price_change_5d < 0:
                    score += 2
                    details['trend_direction'] = 'slightly_bearish'
                else:
                    details['trend_direction'] = 'bullish'

                details['price_change_5d'] = round(price_change_5d, 2)

        except Exception as e:
            logger.debug(f"Error calculating bearish indicators: {e}")
            score = 5

        return min(score, max_score), details

    def calculate_volume_score(self) -> Tuple[int, Dict]:
        """
        Calculate volume confirmation score (0-30 points)

        FIX #5: VOLUME-LED SCORING
        High volume on down moves = distribution
        Volume is now the PRIMARY driver for SHORT signals
        """
        max_score = self.SHORT_SCORE_WEIGHTS['volume_confirmation']  # Now 30
        score = 0
        details = {}

        try:
            if self.df is None or len(self.df) < 20:
                return 5, {'status': 'insufficient_data'}

            current_volume = self.df['Volume'].iloc[-1]
            avg_volume = self.df['Volume'].iloc[-20:].mean()

            vol_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # Volume ratio scoring (FIX #5: Increased scoring)
            if vol_ratio > 2.5:
                score += 20
                details['volume_status'] = 'extreme_spike'
            elif vol_ratio > 2.0:
                score += 16
                details['volume_status'] = 'very_high'
            elif vol_ratio > 1.5:
                score += 12
                details['volume_status'] = 'high'
            elif vol_ratio > 1.3:
                score += 8
                details['volume_status'] = 'above_average'
            elif vol_ratio > 1.0:
                score += 4
                details['volume_status'] = 'average'
            else:
                score += 2
                details['volume_status'] = 'low'

            # Check if volume is on down move (distribution) - Bonus up to 10 pts
            price_down = self.df['Close'].iloc[-1] < self.df['Open'].iloc[-1]
            if price_down and vol_ratio > 1.5:
                score += 10  # Strong distribution signal
                details['distribution'] = 'strong'
            elif price_down and vol_ratio > 1.3:
                score += 6  # Moderate distribution
                details['distribution'] = 'moderate'
            elif price_down:
                score += 3  # Weak distribution
                details['distribution'] = 'weak'
            else:
                details['distribution'] = False

            details['volume_ratio'] = round(vol_ratio, 2)
            details['current_volume'] = int(current_volume)

        except Exception as e:
            logger.debug(f"Error calculating volume score: {e}")
            score = 5

        return min(score, max_score), details

    def calculate_pattern_score(self) -> Tuple[int, Dict]:
        """
        Calculate bearish pattern score (0-10 points)
        """
        max_score = self.SHORT_SCORE_WEIGHTS['bearish_patterns']
        score = 0
        details = {}

        try:
            # Get breakdown patterns
            breakdown_result = self.breakdown_detector.detect_all_breakdowns()

            if breakdown_result.get('has_breakdown'):
                signals = breakdown_result.get('signals', [])
                bearish_patterns = [s for s in signals if s.get('type') in
                                   ['DOUBLE_TOP', 'BEARISH_WEDGE', 'MOMENTUM_EXHAUSTION']]

                if bearish_patterns:
                    # Score based on pattern confidence
                    best_pattern = max(bearish_patterns, key=lambda x: x.get('confidence', 0))
                    conf = best_pattern.get('confidence', 0)
                    score = int(max_score * conf)
                    details['pattern_type'] = best_pattern.get('type')
                    details['pattern_confidence'] = conf
                else:
                    score = 3
                    details['pattern_type'] = 'generic_breakdown'
            else:
                score = 0
                details['pattern_type'] = 'none'

        except Exception as e:
            logger.debug(f"Error calculating pattern score: {e}")
            score = 0

        return min(score, max_score), details

    def calculate_short_score(self, regime_name: str = 'Unknown') -> Dict[str, Any]:
        """
        Calculate comprehensive SHORT score (0-100)

        Args:
            regime_name: Current market regime for multiplier

        Returns:
            Dictionary with SHORT score and breakdown
        """
        try:
            # Calculate individual scores
            breakdown_score, breakdown_details = self.calculate_breakdown_score()
            resistance_score, resistance_details = self.calculate_resistance_proximity_score()
            indicators_score, indicators_details = self.calculate_bearish_indicators_score()
            volume_score, volume_details = self.calculate_volume_score()
            pattern_score, pattern_details = self.calculate_pattern_score()

            # Sum base score
            base_score = (
                breakdown_score +
                resistance_score +
                indicators_score +
                volume_score +
                pattern_score
            )

            # Apply regime multiplier
            multiplier = self.REGIME_MULTIPLIERS_SHORT.get(regime_name, 1.0)
            final_score = int(min(100, base_score * multiplier))

            # Determine SHORT eligibility and strength
            if final_score >= 80:
                strength = 'STRONG'
                eligible = True
            elif final_score >= 65:
                strength = 'MODERATE'
                eligible = True
            elif final_score >= 50:
                strength = 'WEAK'
                eligible = True
            else:
                strength = 'NONE'
                eligible = False

            # Get best signal for entry/target info
            best_entry = None
            best_target = None
            best_stop = None
            best_rr = 0

            breakdown_result = self.breakdown_detector.detect_all_breakdowns()
            if breakdown_result.get('best_signal'):
                bs = breakdown_result['best_signal']
                best_entry = bs.get('entry')
                best_target = bs.get('target_price')
                best_stop = bs.get('stop_loss')
                best_rr = bs.get('risk_reward', 0)

            return {
                'short_score': final_score,
                'base_score': base_score,
                'regime_multiplier': multiplier,
                'strength': strength,
                'eligible': eligible,
                'breakdown': {
                    'breakdown_signals': {
                        'score': breakdown_score,
                        'max': self.SHORT_SCORE_WEIGHTS['breakdown_signals'],
                        'details': breakdown_details
                    },
                    'resistance_proximity': {
                        'score': resistance_score,
                        'max': self.SHORT_SCORE_WEIGHTS['resistance_proximity'],
                        'details': resistance_details
                    },
                    'bearish_indicators': {
                        'score': indicators_score,
                        'max': self.SHORT_SCORE_WEIGHTS['bearish_indicators'],
                        'details': indicators_details
                    },
                    'volume_confirmation': {
                        'score': volume_score,
                        'max': self.SHORT_SCORE_WEIGHTS['volume_confirmation'],
                        'details': volume_details
                    },
                    'bearish_patterns': {
                        'score': pattern_score,
                        'max': self.SHORT_SCORE_WEIGHTS['bearish_patterns'],
                        'details': pattern_details
                    }
                },
                'trade_setup': {
                    'entry': best_entry,
                    'target': best_target,
                    'stop_loss': best_stop,
                    'risk_reward': best_rr
                },
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error calculating short score: {e}")
            return {
                'short_score': 30,
                'strength': 'NONE',
                'eligible': False,
                'error': str(e)
            }

    def get_all_short_signals(self, regime_name: str = 'Unknown') -> Dict[str, Any]:
        """
        Get comprehensive SHORT analysis including all signals

        Returns:
            Complete SHORT trading analysis
        """
        try:
            # Calculate SHORT score
            short_score_result = self.calculate_short_score(regime_name)

            # Get detailed signals
            breakdown_result = self.breakdown_detector.detect_all_breakdowns()
            new_lows_result = self.new_lows_detector.get_comprehensive_analysis()
            fade_result = self.resistance_fader.get_all_fade_signals()

            # Aggregate all signals
            all_signals = []

            if breakdown_result.get('signals'):
                all_signals.extend(breakdown_result['signals'])

            if new_lows_result.get('new_lows_signal'):
                all_signals.append(new_lows_result['new_lows_signal'])

            if fade_result.get('signals'):
                all_signals.extend(fade_result['signals'])

            # Sort by confidence
            all_signals.sort(key=lambda x: x.get('confidence', 0), reverse=True)

            # Determine best overall signal
            best_signal = all_signals[0] if all_signals else None

            return {
                'short_score': short_score_result['short_score'],
                'strength': short_score_result['strength'],
                'eligible': short_score_result['eligible'],
                'score_breakdown': short_score_result['breakdown'],
                'best_signal': best_signal,
                'all_signals': all_signals[:5],  # Top 5 signals
                'total_signals': len(all_signals),
                'breakdown_analysis': breakdown_result,
                'new_lows_analysis': new_lows_result,
                'fade_analysis': fade_result,
                'trade_setup': short_score_result.get('trade_setup'),
                'regime_multiplier': short_score_result.get('regime_multiplier', 1.0),
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting all short signals: {e}")
            return {
                'short_score': 30,
                'strength': 'NONE',
                'eligible': False,
                'error': str(e)
            }


def get_selling_signal_aggregator(df: pd.DataFrame, timeframe: str = '1d', regime: str = 'Unknown') -> SellingSignalAggregator:
    """Factory function for SellingSignalAggregator"""
    return SellingSignalAggregator(df, timeframe, regime)


def calculate_short_score(df: pd.DataFrame, timeframe: str = '1d', regime_name: str = 'Unknown') -> Dict[str, Any]:
    """
    Convenience function to calculate SHORT score

    FIX #6: Regime is now applied EARLY (at initialization)

    Args:
        df: OHLCV DataFrame
        timeframe: One of '5m', '15m', '1h', '1d'
        regime_name: Current market regime

    Returns:
        SHORT score result dictionary
    """
    aggregator = SellingSignalAggregator(df, timeframe, regime_name)  # FIX #6: Pass regime early
    return aggregator.calculate_short_score(regime_name)
