"""
New Lows Detector Module for SHORT Trade Detection

Detects stocks making NEW LOWS with momentum analysis:
- Fresh period lows (52-week, 20-day, etc.)
- Cascading breakdown potential
- Volume-confirmed capitulation
- Multiple support level targets

Why New Lows Matter:
- No support below = panic selling potential
- Price can cascade another 3-8% easily
- High probability breakdown continuation
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewLowsDetector:
    """
    Detects new lows and cascade potential for SHORT trades
    """

    # Lookback periods for different timeframes
    LOOKBACK_PERIODS = {
        '5m': 50,       # ~4 hours
        '15m': 100,     # ~25 hours
        '1h': 252,      # ~1 year in trading hours
        '1d': 252       # 1 year
    }

    def __init__(self, df: pd.DataFrame, timeframe: str = '1d'):
        """
        Initialize with OHLCV data

        Args:
            df: DataFrame with Open, High, Low, Close, Volume columns
            timeframe: One of '5m', '15m', '1h', '1d'
        """
        self.df = df.copy() if df is not None else pd.DataFrame()
        self.timeframe = timeframe
        self.period = self.LOOKBACK_PERIODS.get(timeframe, 252)

    def find_all_swing_lows(self, data: pd.Series, window: int = 5) -> List[float]:
        """Find all swing low points (support levels)"""
        lows = []
        if len(data) < window * 2:
            return [float(data.min())] if len(data) > 0 else []

        for i in range(window, len(data) - window):
            if data.iloc[i] == data.iloc[i-window:i+window+1].min():
                lows.append(float(data.iloc[i]))

        return sorted(set(lows), reverse=True)  # Highest to lowest

    def detect_new_lows_momentum(self) -> Optional[Dict]:
        """
        Detect when stock is making NEW LOWS with momentum

        FIX #2: PANIC/ACCELERATION CONFIRMATION
        Requires:
        1. RVOL >= 1.3 (relative volume spike)
        2. Accelerating downside returns (recent decline steeper than prior)
        3. Close near lows (avoid wick-only candles)

        Returns:
            Dictionary with new low analysis or None
        """
        if self.df is None or len(self.df) < 20:
            return None

        try:
            period = min(self.period, len(self.df))
            recent_lows = self.df['Low'].iloc[-period:]
            lowest_price = recent_lows.min()

            current_low = self.df['Low'].iloc[-1]
            current_close = self.df['Close'].iloc[-1]
            current_high = self.df['High'].iloc[-1]
            current_open = self.df['Open'].iloc[-1]
            prev_low = self.df['Low'].iloc[-2] if len(self.df) > 1 else current_low

            # Check for new low
            is_new_low = current_low < lowest_price * 0.999

            if not is_new_low:
                return None

            # ========== FIX #2: 3 PANIC GATES ==========

            # GATE 1: RVOL >= 1.3 (relative volume spike)
            avg_vol = self.df['Volume'].iloc[-20:].mean()
            current_vol = self.df['Volume'].iloc[-1]
            volume_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
            gate1_rvol = volume_ratio >= 1.3

            # GATE 2: Accelerating downside (recent decline steeper than prior)
            if len(self.df) >= 10:
                recent_return = (self.df['Close'].iloc[-1] - self.df['Close'].iloc[-5]) / self.df['Close'].iloc[-5]
                prior_return = (self.df['Close'].iloc[-5] - self.df['Close'].iloc[-10]) / self.df['Close'].iloc[-10]
                # Acceleration = recent decline is more negative than prior
                gate2_acceleration = recent_return < prior_return and recent_return < -0.02
            else:
                gate2_acceleration = False

            # GATE 3: Close near lows (avoid wick-only candles)
            candle_range = current_high - current_low
            if candle_range > 0:
                close_position = (current_close - current_low) / candle_range
            else:
                close_position = 0.5
            gate3_close_near_low = close_position < 0.35  # Close in lower 35% of candle

            # Count gates passed
            gates_passed = sum([gate1_rvol, gate2_acceleration, gate3_close_near_low])

            # Must pass at least 2 of 3 gates for new low confirmation
            if gates_passed < 2:
                return None

            # Calculate momentum metrics
            days_since_prev_low = int(np.argmin(recent_lows.values))
            momentum_decay = 1.0 - (days_since_prev_low / period)
            momentum_decay = max(0.3, momentum_decay)  # Floor at 0.3

            # Calculate confidence based on gates passed
            if gates_passed == 3:
                base_confidence = 0.85  # High confidence - all gates passed
            else:
                base_confidence = 0.72  # Moderate confidence - 2 gates passed

            confidence = base_confidence
            if current_low < prev_low:
                confidence += 0.05
            confidence *= momentum_decay
            confidence = min(0.95, max(0.55, confidence))

            # Cascade targets (typically 3-5% further down)
            cascade_pct = 0.05 if gates_passed == 3 else 0.04 if gate1_rvol else 0.03
            cascade_target = current_low * (1 - cascade_pct)

            # Stop loss above recent swing high
            recent_high = self.df['High'].iloc[-10:].max()
            stop_loss = recent_high * 1.01

            # Risk-reward calculation
            risk = current_close - stop_loss  # Negative for shorts
            reward = current_close - cascade_target  # Positive for shorts
            risk_reward = abs(reward / risk) if risk != 0 else 0

            return {
                'type': 'NEW_LOW_CASCADE',
                'is_new_low': True,
                'entry': round(current_close, 2),
                'target': round(cascade_target, 2),
                'stop_loss': round(stop_loss, 2),
                'confidence': round(confidence, 2),
                'risk_reward': round(risk_reward, 2),
                'urgency': 'CRITICAL' if gates_passed == 3 else 'HIGH',
                'momentum_decay': round(momentum_decay, 2),
                'volume_confirmed': gate1_rvol,
                'acceleration_confirmed': gate2_acceleration,
                'close_near_low': gate3_close_near_low,
                'gates_passed': gates_passed,
                'volume_ratio': round(volume_ratio, 2),
                'days_since_low': days_since_prev_low,
                'period_low': round(lowest_price, 2),
                'expected_drop_pct': round(cascade_pct * 100, 1),
                'description': f'New {self.period}-period low ({gates_passed}/3 panic gates) - cascade potential {cascade_pct*100:.1f}%'
            }

        except Exception as e:
            logger.debug(f"Error detecting new lows momentum: {e}")
            return None

    def identify_cascade_targets(self) -> Optional[Dict]:
        """
        After breakdown, identify multiple support levels for
        scaling into SHORT positions (or taking partial profits)

        Theory: Breakdowns often cascade through multiple levels
        """
        if self.df is None or len(self.df) < 50:
            return None

        try:
            current_close = self.df['Close'].iloc[-1]

            # Find all swing lows (support levels)
            swing_lows = self.find_all_swing_lows(self.df['Low'].iloc[-50:])

            if not swing_lows:
                return None

            # Filter to levels below current price
            targets_below = [l for l in swing_lows if l < current_close]

            if not targets_below:
                return None

            # Sort from nearest to furthest
            targets_below = sorted(targets_below, reverse=True)

            # Check if price already broke the nearest support
            nearest_support = targets_below[0] if targets_below else current_close * 0.98
            is_broken = current_close < nearest_support

            # Calculate cascade targets
            tp1 = targets_below[0] if len(targets_below) > 0 else None
            tp2 = targets_below[1] if len(targets_below) > 1 else None
            tp3 = targets_below[2] if len(targets_below) > 2 else None

            # Calculate potential drop percentages
            if tp1:
                drop_to_tp1 = ((current_close - tp1) / current_close) * 100
            else:
                drop_to_tp1 = 0

            return {
                'type': 'CASCADE_TARGETS',
                'current_price': round(current_close, 2),
                'cascade_levels': [round(l, 2) for l in targets_below[:5]],
                'is_support_broken': is_broken,
                'entry': round(current_close, 2),
                'tp1': round(tp1, 2) if tp1 else None,
                'tp2': round(tp2, 2) if tp2 else None,
                'tp3': round(tp3, 2) if tp3 else None,
                'drop_to_tp1_pct': round(drop_to_tp1, 2),
                'total_levels': len(targets_below),
                'strategy': 'SCALE_SHORT' if is_broken else 'WAIT_BREAK',
                'urgency': 'HIGH' if is_broken else 'MEDIUM',
                'description': f'{len(targets_below)} support levels below - cascade potential'
            }

        except Exception as e:
            logger.debug(f"Error identifying cascade targets: {e}")
            return None

    def detect_acceleration(self) -> Optional[Dict]:
        """
        Detect if downtrend is accelerating (panic selling)

        Signs of acceleration:
        - Increasing ATR (volatility expanding)
        - Volume spikes
        - Consecutive lower closes
        - Price below all major EMAs
        """
        if self.df is None or len(self.df) < 20:
            return None

        try:
            # ATR trend (volatility expansion)
            high_low = self.df['High'] - self.df['Low']
            high_close = abs(self.df['High'] - self.df['Close'].shift(1))
            low_close = abs(self.df['Low'] - self.df['Close'].shift(1))
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()

            atr_recent = atr.iloc[-5:].mean()
            atr_older = atr.iloc[-15:-5].mean() if len(atr) >= 15 else atr_recent
            atr_expanding = atr_recent > atr_older * 1.2

            # Volume trend
            vol_recent = self.df['Volume'].iloc[-5:].mean()
            vol_older = self.df['Volume'].iloc[-15:-5].mean() if len(self.df) >= 15 else vol_recent
            vol_increasing = vol_recent > vol_older * 1.3

            # Consecutive lower closes
            closes = self.df['Close'].iloc[-5:]
            lower_closes = sum(closes.diff().dropna() < 0)
            consecutive_down = lower_closes >= 3

            # Price below EMAs
            ema_20 = self.df['Close'].ewm(span=20).mean().iloc[-1]
            ema_50 = self.df['Close'].ewm(span=50).mean().iloc[-1] if len(self.df) >= 50 else ema_20
            current_close = self.df['Close'].iloc[-1]
            below_emas = current_close < ema_20 and current_close < ema_50

            # Acceleration score
            acceleration_score = 0
            if atr_expanding:
                acceleration_score += 25
            if vol_increasing:
                acceleration_score += 30
            if consecutive_down:
                acceleration_score += 25
            if below_emas:
                acceleration_score += 20

            is_accelerating = acceleration_score >= 50

            if not is_accelerating:
                return None

            return {
                'type': 'DOWNTREND_ACCELERATION',
                'is_accelerating': True,
                'acceleration_score': acceleration_score,
                'atr_expanding': atr_expanding,
                'volume_increasing': vol_increasing,
                'consecutive_down_days': lower_closes,
                'below_major_emas': below_emas,
                'urgency': 'CRITICAL' if acceleration_score >= 75 else 'HIGH',
                'description': f'Downtrend accelerating (score: {acceleration_score}/100)'
            }

        except Exception as e:
            logger.debug(f"Error detecting acceleration: {e}")
            return None

    def get_comprehensive_analysis(self) -> Dict[str, Any]:
        """
        Get comprehensive new lows analysis

        Returns:
            Dictionary with all new lows signals and cascade analysis
        """
        if self.df is None or self.df.empty:
            return {
                'has_new_lows': False,
                'new_lows_signal': None,
                'cascade_targets': None,
                'acceleration': None
            }

        new_lows = self.detect_new_lows_momentum()
        cascade = self.identify_cascade_targets()
        acceleration = self.detect_acceleration()

        # Overall assessment
        has_signal = new_lows is not None or cascade is not None

        # Combined confidence
        if new_lows and acceleration:
            combined_confidence = min(0.95, new_lows['confidence'] + 0.10)
        elif new_lows:
            combined_confidence = new_lows['confidence']
        elif cascade and cascade.get('is_support_broken'):
            combined_confidence = 0.70
        else:
            combined_confidence = 0.50

        return {
            'has_new_lows': new_lows is not None,
            'has_cascade_setup': cascade is not None and cascade.get('is_support_broken', False),
            'new_lows_signal': new_lows,
            'cascade_targets': cascade,
            'acceleration': acceleration,
            'combined_confidence': round(combined_confidence, 2),
            'overall_urgency': 'CRITICAL' if (new_lows and acceleration) else 'HIGH' if new_lows else 'MEDIUM',
            'timestamp': datetime.now().isoformat()
        }


def get_new_lows_detector(df: pd.DataFrame, timeframe: str = '1d') -> NewLowsDetector:
    """Factory function for NewLowsDetector"""
    return NewLowsDetector(df, timeframe)
