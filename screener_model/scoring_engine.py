"""
Stock Scoring Engine - 0-100 Quantitative Scoring System with DUAL Scoring (LONG + SHORT)

LONG Score Categories:
1. Regime Alignment (0-25 pts) - Market regime vs signal alignment
2. Trend Quality (0-20 pts) - EMA alignment, VWAP, trend strength
3. Pattern Strength (0-20 pts) - Candle/chart patterns with location
4. Volume Confirmation (0-15 pts) - RVOL, CMF, institutional activity
5. Momentum (0-10 pts) - RSI, Stochastic RSI conditions
6. Execution Quality (0-10 pts) - R:R ratio, stop distance, risk level

SHORT Score Categories:
1. Breakdown Signals (0-30 pts) - Resistance breakdowns, new lows
2. Resistance Proximity (0-25 pts) - Distance to key resistance
3. Bearish Indicators (0-20 pts) - RSI overbought, MACD bearish
4. Volume Confirmation (0-15 pts) - Distribution volume
5. Bearish Patterns (0-10 pts) - Double top, wedge breakdown, etc.

Direction: LONG if LONG_SCORE > SHORT_SCORE * 1.1, else SHORT
Eligibility: Score >= 75 (for selected direction)
Sector Diversity: Max 2 stocks per sector
Output: Top 5 stocks per timeframe with direction
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Import SHORT scoring components
try:
    from screener_model.selling_signal_aggregator import SellingSignalAggregator
except ImportError:
    SellingSignalAggregator = None
    logger.warning("SellingSignalAggregator not available - SHORT scoring disabled")


class ScoringEngine:
    """
    0-100 Stock Scoring System for MTF Screener with DUAL Scoring (LONG + SHORT)
    """

    # LONG Score weights by category
    SCORE_WEIGHTS = {
        'regime_alignment': 25,
        'trend_quality': 20,
        'pattern_strength': 20,
        'volume_confirmation': 15,
        'momentum': 10,
        'execution_quality': 10
    }

    # SHORT Score weights by category (FIX #5: Updated to match aggregator)
    SHORT_SCORE_WEIGHTS = {
        'volume_confirmation': 30,    # FIX #5: Increased (was 15)
        'breakdown_signals': 25,      # FIX #5: Adjusted (was 30)
        'bearish_indicators': 20,
        'resistance_proximity': 15,   # FIX #5: Decreased (was 25)
        'bearish_patterns': 10
    }

    # FIX #7: Direction selection parameters
    DIRECTION_MARGIN = 1.2  # 20% margin (was 10%)
    MIN_SCORE_FOR_DIRECTION = 55  # Minimum score to consider a direction

    # Market regime multipliers for direction
    REGIME_MULTIPLIERS = {
        'Bullish Trend': {'LONG': 1.3, 'SHORT': 0.7},
        'Bearish Trend': {'LONG': 0.7, 'SHORT': 1.5},
        'High Volatility': {'LONG': 0.85, 'SHORT': 1.2},
        'Low Volatility': {'LONG': 1.2, 'SHORT': 1.0}
    }

    # Eligibility threshold
    ELIGIBILITY_THRESHOLD = 75

    # SHORT eligibility threshold (lowered to 50 for SHORT-focused screening)
    SHORT_ELIGIBILITY_THRESHOLD = 50

    # LONG eligibility threshold (for high-performance stocks)
    LONG_ELIGIBILITY_THRESHOLD = 65

    # Sector diversity limits
    MAX_PER_SECTOR = 2
    TOP_N = 5

    def __init__(self):
        """Initialize scoring engine"""
        self.total_max_score = sum(self.SCORE_WEIGHTS.values())
        self.short_max_score = sum(self.SHORT_SCORE_WEIGHTS.values())

    def calculate_regime_score(self, regime_data: Dict, signal_bias: str) -> Tuple[int, Dict]:
        """
        Calculate regime alignment score (0-25)

        Perfect alignment: 25 pts
        Partial alignment: 15-20 pts
        Neutral regime: 10-15 pts
        Conflict: 0-10 pts

        Args:
            regime_data: Regime detection results
            signal_bias: Signal direction ('LONG' or 'SHORT')

        Returns:
            Tuple of (score, breakdown dict)
        """
        max_score = self.SCORE_WEIGHTS['regime_alignment']
        score = 0
        breakdown = {}

        try:
            regime_name = regime_data.get('regime_name', 'Unknown')
            regime_bias = regime_data.get('bias', 'NEUTRAL')
            confidence = regime_data.get('confidence', 0.25)
            multiplier = regime_data.get('multiplier', 1.0)

            # Base score based on alignment
            if regime_bias == signal_bias:
                # Perfect alignment
                base = 20
                breakdown['alignment'] = 'perfect'
            elif regime_bias == 'NEUTRAL':
                # Neutral regime
                base = 12
                breakdown['alignment'] = 'neutral'
            else:
                # Conflict
                base = 5
                breakdown['alignment'] = 'conflict'

            score = base

            # Confidence bonus (max 5 pts)
            if confidence > 0.7:
                score += 5
                breakdown['confidence_bonus'] = 5
            elif confidence > 0.5:
                score += 3
                breakdown['confidence_bonus'] = 3
            elif confidence > 0.3:
                score += 1
                breakdown['confidence_bonus'] = 1

            # Low volatility breakout bonus
            if regime_name == 'Low Volatility' and signal_bias != 'NEUTRAL':
                score = min(score + 3, max_score)
                breakdown['breakout_bonus'] = 3

            breakdown['regime'] = regime_name
            breakdown['signal_bias'] = signal_bias
            breakdown['regime_bias'] = regime_bias
            breakdown['raw_score'] = score

        except Exception as e:
            logger.error(f"Error calculating regime score: {str(e)}")
            score = 10  # Default neutral score

        return min(int(score), max_score), breakdown

    def calculate_trend_score(self, trend_data: Dict) -> Tuple[int, Dict]:
        """
        Calculate trend quality score (0-20)

        EMA alignment: 0-12 pts
        VWAP position: 0-5 pts
        Trend strength: 0-3 pts

        Args:
            trend_data: Trend indicator results

        Returns:
            Tuple of (score, breakdown dict)
        """
        max_score = self.SCORE_WEIGHTS['trend_quality']
        score = 0
        breakdown = {}

        try:
            # EMA Crossover alignment (max 12 pts)
            ema_crossovers = trend_data.get('ema_crossovers', {})
            ema_score = 0

            for cross_name, cross_data in ema_crossovers.items():
                if cross_data.get('bullish', False) or cross_data.get('signal') == 'golden_cross':
                    ema_score += 4
                elif cross_data.get('signal') == 'death_cross':
                    ema_score += 4  # Bearish alignment also counts

            breakdown['ema_alignment'] = min(ema_score, 12)
            score += min(ema_score, 12)

            # VWAP position (max 5 pts)
            vwap_data = trend_data.get('vwap', {})
            vwap_deviation = abs(vwap_data.get('deviation_pct', 0))

            if vwap_data.get('signal') in ['bullish', 'bearish']:
                score += 3
                breakdown['vwap_position'] = 3

                # Deviation bonus
                if vwap_deviation > 1:
                    score += 1
                    breakdown['vwap_deviation_bonus'] = 1
                if vwap_deviation > 2:
                    score += 1
                    breakdown['vwap_deviation_bonus'] = 2

            # Trend strength (max 3 pts)
            tqs = trend_data.get('trend_quality_score', 50)
            if tqs >= 80:
                score += 3
                breakdown['trend_strength'] = 3
            elif tqs >= 60:
                score += 2
                breakdown['trend_strength'] = 2
            elif tqs >= 40:
                score += 1
                breakdown['trend_strength'] = 1

            breakdown['overall_trend'] = trend_data.get('overall_trend', 'neutral')
            breakdown['raw_score'] = score

        except Exception as e:
            logger.error(f"Error calculating trend score: {str(e)}")
            score = 10

        return min(int(score), max_score), breakdown

    def calculate_pattern_score(self, pattern_data: Dict) -> Tuple[int, Dict]:
        """
        Calculate pattern strength score (0-20)

        Based on:
        - Pattern quality and type
        - Location multiplier
        - Historical reliability

        Args:
            pattern_data: Pattern detection results

        Returns:
            Tuple of (score, breakdown dict)
        """
        max_score = self.SCORE_WEIGHTS['pattern_strength']
        score = 0
        breakdown = {}

        try:
            best_pattern = pattern_data.get('best_pattern')
            total_patterns = pattern_data.get('total_patterns', 0)

            if not best_pattern:
                breakdown['status'] = 'no_patterns'
                return 5, breakdown  # Minimum score

            # Best pattern contribution (max 12 pts)
            pattern_score = min(best_pattern.get('final_score', 0), 12)
            score += pattern_score
            breakdown['best_pattern_score'] = pattern_score
            breakdown['best_pattern_type'] = best_pattern.get('type', 'unknown')
            breakdown['location'] = best_pattern.get('location', 'neutral')

            # Multiple pattern confirmation (max 5 pts)
            if total_patterns >= 3:
                score += 5
                breakdown['multi_pattern_bonus'] = 5
            elif total_patterns >= 2:
                score += 3
                breakdown['multi_pattern_bonus'] = 3
            elif total_patterns >= 1:
                score += 1
                breakdown['multi_pattern_bonus'] = 1

            # Reliability bonus (max 3 pts)
            reliability = best_pattern.get('reliability', 0.5)
            if reliability >= 0.7:
                score += 3
                breakdown['reliability_bonus'] = 3
            elif reliability >= 0.6:
                score += 2
                breakdown['reliability_bonus'] = 2

            breakdown['dominant_bias'] = pattern_data.get('dominant_bias', 'NEUTRAL')
            breakdown['raw_score'] = score

        except Exception as e:
            logger.error(f"Error calculating pattern score: {str(e)}")
            score = 5

        return min(int(score), max_score), breakdown

    def calculate_volume_score(self, volume_data: Dict) -> Tuple[int, Dict]:
        """
        Calculate volume confirmation score (0-15)

        RVOL: 0-6 pts
        CMF: 0-5 pts
        Institutional activity: 0-4 pts

        Args:
            volume_data: Volume indicator results

        Returns:
            Tuple of (score, breakdown dict)
        """
        max_score = self.SCORE_WEIGHTS['volume_confirmation']
        score = 0
        breakdown = {}

        try:
            # RVOL contribution (max 6 pts)
            rvol_data = volume_data.get('rvol', {})
            rvol_value = rvol_data.get('value', 1.0)

            if rvol_value >= 2.0:
                score += 6
                breakdown['rvol_score'] = 6
            elif rvol_value >= 1.5:
                score += 4
                breakdown['rvol_score'] = 4
            elif rvol_value >= 1.0:
                score += 2
                breakdown['rvol_score'] = 2
            else:
                breakdown['rvol_score'] = 0

            breakdown['rvol_value'] = round(rvol_value, 2)

            # CMF contribution (max 5 pts)
            cmf_data = volume_data.get('cmf', {})
            cmf_signal = cmf_data.get('signal', 'neutral')

            if cmf_signal == 'strong_accumulation':
                score += 5
                breakdown['cmf_score'] = 5
            elif cmf_signal == 'accumulation':
                score += 3
                breakdown['cmf_score'] = 3
            elif cmf_signal == 'strong_distribution':
                score += 5  # Strong distribution also confirms bearish moves
                breakdown['cmf_score'] = 5
            elif cmf_signal == 'distribution':
                score += 3
                breakdown['cmf_score'] = 3
            else:
                score += 1
                breakdown['cmf_score'] = 1

            breakdown['cmf_signal'] = cmf_signal

            # Institutional activity (max 4 pts)
            inst_data = volume_data.get('institutional_proxy', {})
            if inst_data.get('high_activity', False):
                score += 4
                breakdown['institutional_score'] = 4
            else:
                score += 1
                breakdown['institutional_score'] = 1

            breakdown['raw_score'] = score

        except Exception as e:
            logger.error(f"Error calculating volume score: {str(e)}")
            score = 7

        return min(int(score), max_score), breakdown

    def calculate_momentum_score(self, momentum_data: Dict) -> Tuple[int, Dict]:
        """
        Calculate momentum score (0-10)

        RSI condition: 0-5 pts
        Stochastic RSI: 0-3 pts
        ROC: 0-2 pts

        Args:
            momentum_data: Momentum indicator results

        Returns:
            Tuple of (score, breakdown dict)
        """
        max_score = self.SCORE_WEIGHTS['momentum']
        score = 0
        breakdown = {}

        try:
            # RSI contribution (max 5 pts)
            rsi_data = momentum_data.get('rsi', {})
            rsi_signal = rsi_data.get('signal', 'neutral')
            rsi_value = rsi_data.get('value', 50)

            if rsi_signal in ['bullish_momentum', 'bearish_momentum']:
                score += 4
                breakdown['rsi_score'] = 4
            elif rsi_signal in ['oversold', 'overbought']:
                score += 5  # Extreme readings
                breakdown['rsi_score'] = 5
            else:
                score += 2
                breakdown['rsi_score'] = 2

            breakdown['rsi_value'] = round(rsi_value, 2)
            breakdown['rsi_signal'] = rsi_signal

            # Stochastic RSI contribution (max 3 pts)
            stoch_data = momentum_data.get('stochastic_rsi', {})
            stoch_signal = stoch_data.get('signal', 'neutral')

            if stoch_signal in ['buy', 'sell']:
                score += 3
                breakdown['stoch_score'] = 3
            else:
                score += 1
                breakdown['stoch_score'] = 1

            # ROC contribution (max 2 pts)
            roc_data = momentum_data.get('roc', {})
            roc_signal = roc_data.get('signal', 'neutral')

            if roc_signal in ['strong_bullish', 'strong_bearish']:
                score += 2
                breakdown['roc_score'] = 2
            elif roc_signal in ['bullish', 'bearish']:
                score += 1
                breakdown['roc_score'] = 1

            breakdown['raw_score'] = score

        except Exception as e:
            logger.error(f"Error calculating momentum score: {str(e)}")
            score = 5

        return min(int(score), max_score), breakdown

    def calculate_execution_score(self, trade_setup: Dict) -> Tuple[int, Dict]:
        """
        Calculate execution quality score (0-10)

        R:R ratio: 0-4 pts
        Stop distance: 0-3 pts
        Risk level: 0-3 pts

        Args:
            trade_setup: Trade setup from risk-reward engine

        Returns:
            Tuple of (score, breakdown dict)
        """
        max_score = self.SCORE_WEIGHTS['execution_quality']
        score = 0
        breakdown = {}

        try:
            # R:R ratio (max 4 pts)
            rr_ratio = trade_setup.get('rr_ratio', 0)
            min_rr = trade_setup.get('min_rr_required', 3.0)

            if rr_ratio >= min_rr * 1.5:
                score += 4
                breakdown['rr_score'] = 4
            elif rr_ratio >= min_rr:
                score += 3
                breakdown['rr_score'] = 3
            elif rr_ratio >= min_rr * 0.8:
                score += 2
                breakdown['rr_score'] = 2
            else:
                score += 1
                breakdown['rr_score'] = 1

            breakdown['rr_ratio'] = round(rr_ratio, 2)

            # Stop distance / risk percentage (max 3 pts)
            risk_pct = trade_setup.get('risk_percentage', 5)

            if risk_pct < 1.5:
                score += 3
                breakdown['risk_score'] = 3
            elif risk_pct < 2.5:
                score += 2
                breakdown['risk_score'] = 2
            elif risk_pct < 3.5:
                score += 1
                breakdown['risk_score'] = 1

            breakdown['risk_percentage'] = round(risk_pct, 2)

            # Validation / risk level (max 3 pts)
            validation = trade_setup.get('validation', {})
            risk_level = validation.get('risk_level', 'medium')

            if risk_level == 'low':
                score += 3
                breakdown['validation_score'] = 3
            elif risk_level == 'medium':
                score += 2
                breakdown['validation_score'] = 2
            elif risk_level == 'high':
                score += 1
                breakdown['validation_score'] = 1

            breakdown['risk_level'] = risk_level
            breakdown['raw_score'] = score

        except Exception as e:
            logger.error(f"Error calculating execution score: {str(e)}")
            score = 5

        return min(int(score), max_score), breakdown

    def calculate_total_score(self, stock_data: Dict) -> Dict[str, Any]:
        """
        Calculate total score (0-100) with complete breakdown

        Args:
            stock_data: Dictionary containing all analysis data:
                - regime_data: Regime detection results
                - signal_bias: Trade direction
                - trend_data: Trend indicators
                - pattern_data: Pattern detection
                - volume_data: Volume indicators
                - momentum_data: Momentum indicators
                - trade_setup: Risk-reward setup

        Returns:
            Complete scoring result
        """
        try:
            # Extract data
            regime_data = stock_data.get('regime_data', {})
            signal_bias = stock_data.get('signal_bias', 'NEUTRAL')
            trend_data = stock_data.get('trend_data', {})
            pattern_data = stock_data.get('pattern_data', {})
            volume_data = stock_data.get('volume_data', {})
            momentum_data = stock_data.get('momentum_data', {})
            trade_setup = stock_data.get('trade_setup', {})

            # Calculate individual scores
            regime_score, regime_breakdown = self.calculate_regime_score(regime_data, signal_bias)
            trend_score, trend_breakdown = self.calculate_trend_score(trend_data)
            pattern_score, pattern_breakdown = self.calculate_pattern_score(pattern_data)
            volume_score, volume_breakdown = self.calculate_volume_score(volume_data)
            momentum_score, momentum_breakdown = self.calculate_momentum_score(momentum_data)
            execution_score, execution_breakdown = self.calculate_execution_score(trade_setup)

            # Calculate total
            total_score = (
                regime_score +
                trend_score +
                pattern_score +
                volume_score +
                momentum_score +
                execution_score
            )

            # Determine eligibility
            is_eligible = total_score >= self.ELIGIBILITY_THRESHOLD

            # Score category
            if total_score >= 85:
                category = 'A'
                category_name = 'Excellent'
            elif total_score >= 75:
                category = 'B'
                category_name = 'Good'
            elif total_score >= 65:
                category = 'C'
                category_name = 'Average'
            elif total_score >= 50:
                category = 'D'
                category_name = 'Below Average'
            else:
                category = 'F'
                category_name = 'Poor'

            return {
                'total_score': total_score,
                'long_score': total_score,  # Alias for clarity
                'max_score': self.total_max_score,
                'percentage': round((total_score / self.total_max_score) * 100, 1),
                'eligible': is_eligible,
                'threshold': self.ELIGIBILITY_THRESHOLD,
                'category': category,
                'category_name': category_name,
                'breakdown': {
                    'regime_alignment': {
                        'score': regime_score,
                        'max': self.SCORE_WEIGHTS['regime_alignment'],
                        'details': regime_breakdown
                    },
                    'trend_quality': {
                        'score': trend_score,
                        'max': self.SCORE_WEIGHTS['trend_quality'],
                        'details': trend_breakdown
                    },
                    'pattern_strength': {
                        'score': pattern_score,
                        'max': self.SCORE_WEIGHTS['pattern_strength'],
                        'details': pattern_breakdown
                    },
                    'volume_confirmation': {
                        'score': volume_score,
                        'max': self.SCORE_WEIGHTS['volume_confirmation'],
                        'details': volume_breakdown
                    },
                    'momentum': {
                        'score': momentum_score,
                        'max': self.SCORE_WEIGHTS['momentum'],
                        'details': momentum_breakdown
                    },
                    'execution_quality': {
                        'score': execution_score,
                        'max': self.SCORE_WEIGHTS['execution_quality'],
                        'details': execution_breakdown
                    }
                },
                'signal_bias': signal_bias,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error calculating total score: {str(e)}")
            return {
                'total_score': 50,
                'long_score': 50,
                'eligible': False,
                'error': str(e)
            }

    def calculate_short_score(self, stock_data: Dict) -> Dict[str, Any]:
        """
        Calculate SHORT score (0-100) using SellingSignalAggregator

        Args:
            stock_data: Dictionary containing:
                - df: OHLCV DataFrame
                - timeframe: Timeframe string
                - regime_data: Regime detection results

        Returns:
            SHORT scoring result
        """
        try:
            if SellingSignalAggregator is None:
                return {
                    'short_score': 30,
                    'eligible': False,
                    'error': 'SHORT scoring not available'
                }

            df = stock_data.get('df')
            timeframe = stock_data.get('timeframe', '1d')
            regime_data = stock_data.get('regime_data', {})
            regime_name = regime_data.get('regime_name', regime_data.get('current_regime', 'Unknown'))

            if df is None or df.empty:
                return {
                    'short_score': 30,
                    'eligible': False,
                    'error': 'No data available'
                }

            # Use SellingSignalAggregator (FIX #6: Pass regime early)
            aggregator = SellingSignalAggregator(df, timeframe, regime_name)
            short_result = aggregator.calculate_short_score(regime_name)

            short_score = short_result.get('short_score', 30)
            is_eligible = short_score >= self.SHORT_ELIGIBILITY_THRESHOLD

            return {
                'short_score': short_score,
                'eligible': is_eligible,
                'threshold': self.SHORT_ELIGIBILITY_THRESHOLD,
                'strength': short_result.get('strength', 'NONE'),
                'breakdown': short_result.get('breakdown', {}),
                'trade_setup': short_result.get('trade_setup', {}),
                'regime_multiplier': short_result.get('regime_multiplier', 1.0)
            }

        except Exception as e:
            logger.error(f"Error calculating SHORT score: {str(e)}")
            return {
                'short_score': 30,
                'eligible': False,
                'error': str(e)
            }

    def calculate_long_score(self, stock_data: Dict) -> Dict[str, Any]:
        """
        Calculate LONG/BUY score (High-Performance Momentum Stocks)

        Scoring Components:
        - Trend Strength (30pts): Strong uptrend, price > moving averages
        - Momentum (25pts): RSI bullish, MACD positive, increasing volume
        - Breakout Patterns (20pts): Bullish patterns, new highs
        - Volume Confirmation (15pts): High volume on up days
        - Risk-Reward (10pts): Good entry with defined stop-loss

        Args:
            stock_data: Dictionary containing all analysis data

        Returns:
            LONG scoring result with breakdown
        """
        try:
            score = 0
            breakdown = {}

            # Get data
            trend_data = stock_data.get('trend_data', {})
            momentum_data = stock_data.get('momentum_data', {})
            volume_data = stock_data.get('volume_data', {})
            pattern_data = stock_data.get('pattern_data', {})
            df = stock_data.get('df')
            regime_name = stock_data.get('regime_data', {}).get('regime_name', 'Unknown')

            # 1. Trend Strength (30 points)
            trend_score = 0
            if trend_data:
                overall_trend = trend_data.get('overall_trend', 'neutral')
                if overall_trend == 'bullish':
                    trend_score += 30
                elif overall_trend == 'neutral':
                    trend_score += 15
            breakdown['trend'] = {'score': trend_score, 'max': 30, 'status': 'bullish' if trend_score >= 20 else 'neutral'}
            score += trend_score

            # 2. Momentum (25 points)
            momentum_score = 0
            rsi_value = None
            if momentum_data:
                rsi = momentum_data.get('rsi')

                # Extract RSI value - could be number or dict with 'value' key
                if isinstance(rsi, dict):
                    rsi_value = rsi.get('value')
                elif isinstance(rsi, (int, float)):
                    rsi_value = rsi

                macd_signal = momentum_data.get('macd_signal', 'neutral')

                # RSI in bullish zone (40-70)
                if rsi_value is not None and isinstance(rsi_value, (int, float)):
                    if 40 <= rsi_value <= 70:
                        momentum_score += 12

                # MACD bullish
                if macd_signal == 'bullish':
                    momentum_score += 13
            breakdown['momentum'] = {'score': momentum_score, 'max': 25, 'rsi': rsi_value}
            score += momentum_score

            # 3. Breakout Patterns (20 points)
            pattern_score = 0
            if pattern_data:
                best_pattern = pattern_data.get('best_pattern', {})
                if best_pattern:
                    pattern_type = best_pattern.get('type', '')
                    # Bullish patterns
                    if any(bullish in pattern_type.lower() for bullish in ['bull', 'hammer', 'morning', 'piercing', 'engulf']):
                        pattern_score += 20
                    elif pattern_type != 'none':
                        pattern_score += 10
            breakdown['patterns'] = {'score': pattern_score, 'max': 20}
            score += pattern_score

            # 4. Volume Confirmation (15 points)
            volume_score = 0
            if df is not None and len(df) > 0:
                try:
                    # Check if volume increased on up days
                    df['price_change'] = df['Close'].diff()
                    df['volume_change'] = df['Volume'].diff()

                    # Last 5 days correlation
                    recent = df.tail(5)
                    if len(recent) > 3:
                        # Volume spike on up days is bullish
                        current_volume = df['Volume'].iloc[-1]
                        avg_volume = df['Volume'].rolling(20).mean().iloc[-1]

                        if current_volume > avg_volume * 1.2:
                            volume_score += 15
                        elif current_volume > avg_volume:
                            volume_score += 8
                except:
                    pass
            breakdown['volume'] = {'score': volume_score, 'max': 15}
            score += volume_score

            # 5. Risk-Reward (10 points)
            rr_score = 0
            trade_setup = stock_data.get('trade_setup', {})
            if trade_setup:
                rr_ratio = trade_setup.get('rr_ratio', 0)
                if rr_ratio >= 2.0:
                    rr_score += 10
                elif rr_ratio >= 1.5:
                    rr_score += 5
            breakdown['risk_reward'] = {'score': rr_score, 'max': 10, 'rr_ratio': rr_ratio if 'rr_ratio' in locals() else 0}
            score += rr_score

            # Check eligibility
            is_eligible = score >= self.LONG_ELIGIBILITY_THRESHOLD

            # Determine strength
            if score >= 80:
                strength = 'STRONG'
            elif score >= 65:
                strength = 'MODERATE'
            elif score >= 50:
                strength = 'WEAK'
            else:
                strength = 'NONE'

            return {
                'long_score': score,
                'eligible': is_eligible,
                'threshold': self.LONG_ELIGIBILITY_THRESHOLD,
                'strength': strength,
                'breakdown': breakdown,
                'trade_setup': trade_setup,
                'regime_multiplier': self.REGIME_MULTIPLIERS.get(regime_name, {}).get('LONG', 1.0)
            }

        except Exception as e:
            logger.error(f"Error calculating LONG score: {str(e)}")
            return {
                'long_score': 30,
                'eligible': False,
                'error': str(e)
            }

    def calculate_dual_score(self, stock_data: Dict) -> Dict[str, Any]:
        """
        Calculate BOTH LONG and SHORT scores (Dual-Directional Screener)

        Args:
            stock_data: Dictionary containing all analysis data

        Returns:
            Dual scoring result with direction recommendation
        """
        try:
            # Calculate BOTH scores
            long_result = self.calculate_long_score(stock_data)
            short_result = self.calculate_short_score(stock_data)

            long_score = long_result.get('long_score', 30)
            short_score = short_result.get('short_score', 30)

            # Get regime info for multipliers
            regime_data = stock_data.get('regime_data', {})
            regime_name = regime_data.get('regime_name', 'Unknown')

            # Apply regime multipliers to both scores
            multipliers = self.REGIME_MULTIPLIERS.get(regime_name, {'LONG': 1.0, 'SHORT': 1.0})
            adjusted_long = int(min(100, long_score * multipliers['LONG']))
            adjusted_short = int(min(100, short_score * multipliers['SHORT']))

            # Determine direction based on stronger signal
            long_meets_min = adjusted_long >= self.MIN_SCORE_FOR_DIRECTION
            short_meets_min = adjusted_short >= self.MIN_SCORE_FOR_DIRECTION

            # Calculate margin (20% difference required to declare direction)
            score_difference = abs(adjusted_long - adjusted_short)
            margin_threshold = 20

            if long_meets_min and adjusted_long > adjusted_short + margin_threshold:
                # LONG is significantly stronger
                direction = 'LONG'
                final_score = adjusted_long
                eligible = long_result.get('eligible', False)
            elif short_meets_min and adjusted_short > adjusted_long + margin_threshold:
                # SHORT is significantly stronger
                direction = 'SHORT'
                final_score = adjusted_short
                eligible = short_result.get('eligible', False)
            elif long_meets_min and short_meets_min:
                # Both strong, pick higher score
                if adjusted_long > adjusted_short:
                    direction = 'LONG'
                    final_score = adjusted_long
                    eligible = long_result.get('eligible', False)
                else:
                    direction = 'SHORT'
                    final_score = adjusted_short
                    eligible = short_result.get('eligible', False)
            elif long_meets_min:
                direction = 'LONG'
                final_score = adjusted_long
                eligible = long_result.get('eligible', False)
            elif short_meets_min:
                direction = 'SHORT'
                final_score = adjusted_short
                eligible = short_result.get('eligible', False)
            else:
                # Neither meets minimum - HOLD
                direction = 'HOLD'
                final_score = max(adjusted_long, adjusted_short)
                eligible = False

            # Category based on final score
            if final_score >= 85:
                category = 'A'
                category_name = 'Excellent'
            elif final_score >= 75:
                category = 'B'
                category_name = 'Good'
            elif final_score >= 60:  # Updated threshold
                category = 'C'
                category_name = 'Average'
            elif final_score >= 50:
                category = 'D'
                category_name = 'Below Average'
            else:
                category = 'F'
                category_name = 'Poor'

            return {
                'total_score': final_score,
                'long_score': long_score,
                'short_score': short_score,
                'adjusted_long_score': adjusted_long,
                'adjusted_short_score': adjusted_short,
                'direction': direction,
                'signal_bias': direction if direction != 'HOLD' else 'NEUTRAL',
                'eligible': eligible,
                'category': category,
                'category_name': category_name,
                'regime_name': regime_name,
                'regime_multipliers': multipliers,
                'long_breakdown': long_result.get('breakdown', {}),
                'short_breakdown': short_result.get('breakdown', {}),
                'long_trade_setup': long_result.get('trade_setup', {}),
                'short_trade_setup': short_result.get('trade_setup', {}),
                'long_strength': long_result.get('strength', 'NONE'),
                'short_strength': short_result.get('strength', 'NONE'),
                'score_difference': score_difference,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error calculating dual score: {str(e)}")
            return {
                'total_score': 30,
                'long_score': 30,
                'short_score': 30,
                'direction': 'HOLD',
                'eligible': False,
                'error': str(e)
            }

    def rank_stocks(self, stocks: List[Dict], sector_map: Dict[str, str]) -> List[Dict]:
        """
        Rank and filter stocks with sector diversity

        Args:
            stocks: List of stock scoring results
            sector_map: Mapping of ticker to sector

        Returns:
            Top N stocks with sector diversity applied
        """
        try:
            # Filter eligible stocks
            eligible = [s for s in stocks if s.get('eligible', False)]

            if not eligible:
                # Return top scores even if below threshold
                eligible = sorted(stocks, key=lambda x: x.get('total_score', 0), reverse=True)

            # Sort by score
            eligible.sort(key=lambda x: x.get('total_score', 0), reverse=True)

            # Apply sector diversity
            final_list = []
            sector_counts = {}

            for stock in eligible:
                ticker = stock.get('ticker', '')
                sector = sector_map.get(ticker, 'Unknown')

                # Check sector limit
                if sector_counts.get(sector, 0) < self.MAX_PER_SECTOR:
                    stock['sector'] = sector
                    stock['rank'] = len(final_list) + 1
                    final_list.append(stock)
                    sector_counts[sector] = sector_counts.get(sector, 0) + 1

                # Stop at TOP_N
                if len(final_list) >= self.TOP_N:
                    break

            return final_list

        except Exception as e:
            logger.error(f"Error ranking stocks: {str(e)}")
            return stocks[:self.TOP_N]


# Singleton instance
_scoring_engine = None

def get_scoring_engine() -> ScoringEngine:
    """Get singleton scoring engine instance"""
    global _scoring_engine
    if _scoring_engine is None:
        _scoring_engine = ScoringEngine()
    return _scoring_engine
