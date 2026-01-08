"""
Resistance Fader Module for SHORT Trade Detection

Identifies stocks ready to fade (reverse) from resistance zones:
- Price touching/breaking above resistance with rejection
- Volume declining after touch (no follow-through)
- Rejection candles (upper shadow, small body)
- Failed breakout patterns

Fading = Trading against the initial move at key levels
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResistanceFader:
    """
    Identifies fade opportunities at resistance levels

    FIX #4: REGIME-GATED RESISTANCE FADING
    Skip fading resistance in Bullish Trend unless:
    - Failed breakout persists 2+ bars
    - Breakdown volume > breakout volume
    """

    # Regime definitions for gating
    BULLISH_REGIMES = ['Bullish Trend', 'Strong Bullish', 'Uptrend']
    BEARISH_REGIMES = ['Bearish Trend', 'Strong Bearish', 'Downtrend']

    def __init__(self, df: pd.DataFrame, timeframe: str = '1d', regime: str = 'Unknown'):
        """
        Initialize with OHLCV data

        Args:
            df: DataFrame with Open, High, Low, Close, Volume columns
            timeframe: One of '5m', '15m', '1h', '1d'
            regime: Current market regime for gating decisions
        """
        self.df = df.copy() if df is not None else pd.DataFrame()
        self.timeframe = timeframe
        self.regime = regime

        # Timeframe-specific configurations
        self.config = {
            '5m': {'swing_period': 50, 'vol_period': 20, 'atr_mult': 1.0},
            '15m': {'swing_period': 50, 'vol_period': 20, 'atr_mult': 1.2},
            '1h': {'swing_period': 40, 'vol_period': 20, 'atr_mult': 1.5},
            '1d': {'swing_period': 20, 'vol_period': 20, 'atr_mult': 2.0}
        }.get(timeframe, {'swing_period': 20, 'vol_period': 20, 'atr_mult': 2.0})

    def find_resistance_levels(self, lookback: int = None) -> List[float]:
        """Find key resistance levels (swing highs)"""
        if self.df is None or self.df.empty:
            return []

        lookback = lookback or self.config['swing_period']
        lookback = min(lookback, len(self.df) - 1)

        highs = self.df['High'].iloc[-lookback:]
        levels = []

        # Find local maxima
        for i in range(2, len(highs) - 2):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and \
               highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
                levels.append(float(highs.iloc[i]))

        # Also add the highest high as resistance
        if len(highs) > 0:
            levels.append(float(highs.max()))

        return sorted(set(levels), reverse=True)

    def find_support_levels(self, lookback: int = None) -> List[float]:
        """Find key support levels (swing lows)"""
        if self.df is None or self.df.empty:
            return []

        lookback = lookback or self.config['swing_period'] * 2
        lookback = min(lookback, len(self.df) - 1)

        lows = self.df['Low'].iloc[-lookback:]
        levels = []

        # Find local minima
        for i in range(2, len(lows) - 2):
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and \
               lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
                levels.append(float(lows.iloc[i]))

        # Also add the lowest low as support
        if len(lows) > 0:
            levels.append(float(lows.min()))

        return sorted(set(levels), reverse=True)

    def calculate_atr(self, period: int = 14) -> float:
        """Calculate Average True Range"""
        if len(self.df) < period:
            return 0

        high_low = self.df['High'] - self.df['Low']
        high_close = abs(self.df['High'] - self.df['Close'].shift(1))
        low_close = abs(self.df['Low'] - self.df['Close'].shift(1))

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def identify_fade_opportunity(self) -> Optional[Dict]:
        """
        Identify stocks ready to fade from resistance

        Fade signals:
        1. Price at or near resistance
        2. Volume declining after touch
        3. Rejection candle (upper shadow > body)

        FIX #4: REGIME GATING
        Skip fading in Bullish Trend unless confirmed failed breakout
        """
        if self.df is None or len(self.df) < 20:
            return None

        try:
            # Current candle data
            current_close = self.df['Close'].iloc[-1]
            current_open = self.df['Open'].iloc[-1]
            current_high = self.df['High'].iloc[-1]
            current_low = self.df['Low'].iloc[-1]
            current_volume = self.df['Volume'].iloc[-1]

            # Find recent resistance
            resistance_levels = self.find_resistance_levels()
            if not resistance_levels:
                return None

            recent_high = resistance_levels[0]

            # Check if price is at resistance (within 1%)
            at_resistance = current_close > recent_high * 0.99

            if not at_resistance:
                # Check if price touched resistance and retreated
                touched_and_fell = current_high > recent_high * 0.99 and current_close < recent_high
                if not touched_and_fell:
                    return None

            # Volume declining analysis
            vol_avg_recent = self.df['Volume'].iloc[-3:].mean()
            vol_avg_older = self.df['Volume'].iloc[-10:-3].mean() if len(self.df) >= 10 else vol_avg_recent
            volume_declining = vol_avg_recent < vol_avg_older * 0.9

            # Rejection candle analysis
            body_size = abs(current_close - current_open)
            upper_shadow = current_high - max(current_close, current_open)
            lower_shadow = min(current_close, current_open) - current_low

            is_rejection = upper_shadow > body_size * 1.5 and upper_shadow > lower_shadow

            # ========== FIX #4: REGIME GATING ==========
            # In bullish regime, require stronger confirmation
            is_bullish_regime = self.regime in self.BULLISH_REGIMES

            if is_bullish_regime:
                # In bullish regime, only fade if we have STRONG rejection signals
                # Require: rejection candle AND volume declining AND red candle
                if not (is_rejection and volume_declining and current_close < current_open):
                    return None  # Skip fade in bullish regime without strong confirmation

            # Score the fade setup
            fade_score = 0
            if at_resistance or (current_high > recent_high * 0.99):
                fade_score += 30
            if volume_declining:
                fade_score += 25
            if is_rejection:
                fade_score += 30
            if current_close < current_open:  # Red candle
                fade_score += 15

            # In bullish regime, require higher score threshold
            min_score = 70 if is_bullish_regime else 50

            if fade_score < min_score:
                return None

            # Find target (next support)
            support_levels = self.find_support_levels()
            if support_levels:
                next_support = max([s for s in support_levels if s < current_close], default=current_close * 0.97)
            else:
                next_support = current_close * 0.97

            # Calculate stop loss
            atr = self.calculate_atr()
            stop_loss = current_high + (atr * 0.2)  # Just above current high

            # Risk-reward
            risk = stop_loss - current_close
            reward = current_close - next_support
            risk_reward = reward / risk if risk > 0 else 0

            # Confidence based on fade score
            confidence = min(0.85, 0.50 + (fade_score / 200))

            return {
                'type': 'FADE_RESISTANCE',
                'entry': round(current_close, 2),
                'stop_loss': round(stop_loss, 2),
                'target': round(next_support, 2),
                'risk_reward': round(risk_reward, 2),
                'confidence': round(confidence, 2),
                'fade_score': fade_score,
                'resistance_level': round(recent_high, 2),
                'support_target': round(next_support, 2),
                'volume_declining': volume_declining,
                'is_rejection_candle': is_rejection,
                'urgency': 'HIGH' if fade_score >= 70 else 'MEDIUM',
                'description': f'Price rejected at {recent_high:.2f}, expect fade to {next_support:.2f}'
            }

        except Exception as e:
            logger.debug(f"Error identifying fade opportunity: {e}")
            return None

    def detect_failed_breakout(self) -> Optional[Dict]:
        """
        Detect failed breakout above resistance

        Failed breakout = price broke above resistance but couldn't hold
        Strong SHORT signal

        FIX #4: REGIME GATING
        In bullish regime, require:
        - Failed breakout persists 2+ bars
        - Breakdown volume > breakout volume
        """
        if self.df is None or len(self.df) < 20:
            return None

        try:
            # Need at least 3 candles to detect failed breakout with persistence
            current_close = self.df['Close'].iloc[-1]
            current_high = self.df['High'].iloc[-1]
            current_volume = self.df['Volume'].iloc[-1]
            prev_close = self.df['Close'].iloc[-2]
            prev_high = self.df['High'].iloc[-2]
            prev_volume = self.df['Volume'].iloc[-2]

            # Find resistance from before the potential breakout
            resistance_levels = self.find_resistance_levels(lookback=30)
            if not resistance_levels:
                return None

            # Use second highest as the "old" resistance (first might be the breakout)
            old_resistance = resistance_levels[1] if len(resistance_levels) > 1 else resistance_levels[0]

            # Check for failed breakout pattern:
            # 1. Previous candle broke above resistance
            # 2. Current candle fell back below
            prev_broke_above = prev_high > old_resistance
            current_fell_back = current_close < old_resistance

            if not (prev_broke_above and current_fell_back):
                return None

            # Volume analysis (breakout on low volume = likely to fail)
            breakout_vol = self.df['Volume'].iloc[-2]
            avg_vol = self.df['Volume'].iloc[-20:-2].mean()
            low_vol_breakout = breakout_vol < avg_vol * 1.2

            # ========== FIX #4: REGIME GATING FOR FAILED BREAKOUT ==========
            is_bullish_regime = self.regime in self.BULLISH_REGIMES

            if is_bullish_regime:
                # Requirement 1: Failed breakout must persist 2+ bars
                if len(self.df) >= 3:
                    two_bars_ago_close = self.df['Close'].iloc[-3]
                    # Check if the failure has persisted (both current and prev bar below resistance)
                    failure_persists = prev_close < old_resistance and current_close < old_resistance
                else:
                    failure_persists = False

                # Requirement 2: Breakdown volume > breakout volume
                breakdown_volume = current_volume
                breakout_volume = breakout_vol
                volume_confirms_breakdown = breakdown_volume > breakout_volume

                # In bullish regime, require BOTH conditions
                if not (failure_persists and volume_confirms_breakdown):
                    return None

            # Calculate targets and stops
            support_levels = self.find_support_levels()
            if support_levels:
                target = max([s for s in support_levels if s < current_close], default=current_close * 0.97)
            else:
                target = current_close * 0.97

            stop_loss = max(prev_high, current_high) * 1.01

            # Risk-reward
            risk = stop_loss - current_close
            reward = current_close - target
            risk_reward = reward / risk if risk > 0 else 0

            # Adjust confidence based on regime
            base_confidence = 0.82 if low_vol_breakout else 0.75
            if is_bullish_regime:
                confidence = base_confidence * 0.9  # Slightly lower confidence in bullish regime
            else:
                confidence = base_confidence

            return {
                'type': 'FAILED_BREAKOUT',
                'entry': round(current_close, 2),
                'stop_loss': round(stop_loss, 2),
                'target': round(target, 2),
                'risk_reward': round(risk_reward, 2),
                'confidence': round(confidence, 2),
                'resistance_level': round(old_resistance, 2),
                'breakout_high': round(prev_high, 2),
                'low_volume_breakout': low_vol_breakout,
                'regime_gated': is_bullish_regime,
                'urgency': 'HIGH',
                'description': f'Failed breakout above {old_resistance:.2f} - trapped bulls'
            }

        except Exception as e:
            logger.debug(f"Error detecting failed breakout: {e}")
            return None

    def detect_overbought_at_resistance(self) -> Optional[Dict]:
        """
        Detect overbought condition at resistance

        Combines:
        - Price at resistance
        - RSI overbought (>70)
        - Potential for mean reversion
        """
        if self.df is None or len(self.df) < 20:
            return None

        try:
            current_close = self.df['Close'].iloc[-1]

            # RSI calculation
            delta = self.df['Close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = 100 - (100 / (1 + rs))
            current_rsi = float(rsi.iloc[-1])

            if current_rsi < 70:
                return None

            # Check if at resistance
            resistance_levels = self.find_resistance_levels()
            if not resistance_levels:
                return None

            nearest_resistance = resistance_levels[0]
            at_resistance = current_close > nearest_resistance * 0.98

            if not at_resistance:
                return None

            # Target: mean reversion to moving average
            ma_20 = float(self.df['Close'].rolling(20).mean().iloc[-1])
            target = min(ma_20, current_close * 0.95)

            # Stop above resistance
            stop_loss = nearest_resistance * 1.02

            # Risk-reward
            risk = stop_loss - current_close
            reward = current_close - target
            risk_reward = reward / risk if risk > 0 else 0

            # Confidence increases with RSI
            confidence = 0.65 + ((current_rsi - 70) / 100)
            confidence = min(0.85, confidence)

            return {
                'type': 'OVERBOUGHT_AT_RESISTANCE',
                'entry': round(current_close, 2),
                'stop_loss': round(stop_loss, 2),
                'target': round(target, 2),
                'risk_reward': round(risk_reward, 2),
                'confidence': round(confidence, 2),
                'rsi': round(current_rsi, 2),
                'resistance_level': round(nearest_resistance, 2),
                'ma_20_target': round(ma_20, 2),
                'urgency': 'HIGH' if current_rsi > 80 else 'MEDIUM',
                'description': f'Overbought (RSI {current_rsi:.0f}) at resistance - mean reversion setup'
            }

        except Exception as e:
            logger.debug(f"Error detecting overbought at resistance: {e}")
            return None

    def get_all_fade_signals(self) -> Dict[str, Any]:
        """
        Get all fade/resistance signals

        Returns:
            Dictionary with all detected fade signals
        """
        if self.df is None or self.df.empty:
            return {
                'has_fade_signal': False,
                'signals': [],
                'best_signal': None,
                'resistance_levels': [],
                'support_levels': []
            }

        signals = []

        # Run all detectors
        fade_opp = self.identify_fade_opportunity()
        if fade_opp:
            signals.append(fade_opp)

        failed_breakout = self.detect_failed_breakout()
        if failed_breakout:
            signals.append(failed_breakout)

        overbought = self.detect_overbought_at_resistance()
        if overbought:
            signals.append(overbought)

        # Sort by confidence
        signals.sort(key=lambda x: x.get('confidence', 0), reverse=True)

        best_signal = signals[0] if signals else None

        return {
            'has_fade_signal': len(signals) > 0,
            'signals': signals,
            'best_signal': best_signal,
            'total_signals': len(signals),
            'resistance_levels': [round(r, 2) for r in self.find_resistance_levels()[:5]],
            'support_levels': [round(s, 2) for s in self.find_support_levels()[:5]],
            'timestamp': datetime.now().isoformat()
        }


def get_resistance_fader(df: pd.DataFrame, timeframe: str = '1d', regime: str = 'Unknown') -> ResistanceFader:
    """Factory function for ResistanceFader"""
    return ResistanceFader(df, timeframe, regime)
