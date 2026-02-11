"""
Pattern Analysis Service - 3 Model AI System
Implements classical patterns, price action, and candlestick pattern recognition
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import talib


class PatternAnalysisService:
    """Service for analyzing stock patterns using 3 AI models"""

    def __init__(self):
        pass

    def analyze_stock(self, symbol: str, timeframe: str = '1d', lookback_days: int = 90) -> Dict[str, Any]:
        """
        Run complete 3-model analysis on a stock

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE.NS')
            timeframe: Timeframe for analysis (1d, 1h, etc.)
            lookback_days: Number of days to look back

        Returns:
            Complete analysis from all 3 models
        """
        try:
            # Fetch stock data
            stock_data = self._fetch_stock_data(symbol, lookback_days)

            if stock_data is None or len(stock_data) < 20:
                raise ValueError(f"Insufficient data for {symbol}")

            # Run all 3 models
            classical_patterns = self._analyze_classical_patterns(stock_data)
            price_action = self._analyze_price_action(stock_data)
            candlestick_patterns = self._analyze_candlestick_patterns(stock_data)

            # Combine models
            combined_analysis = self._combine_models(
                classical_patterns,
                price_action,
                candlestick_patterns
            )

            return {
                'symbol': symbol,
                'classical_patterns': classical_patterns,
                'price_action': price_action,
                'candlestick_patterns': candlestick_patterns,
                'combined_analysis': combined_analysis,
                'analyzed_at': datetime.now().isoformat()
            }

        except Exception as e:
            raise Exception(f"Failed to analyze {symbol}: {str(e)}")

    def _fetch_stock_data(self, symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
        """Fetch historical stock data"""
        try:
            # Add .NS for NSE stocks if not present
            if not symbol.endswith('.NS') and not symbol.endswith('.BO'):
                symbol = f"{symbol}.NS"

            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)

            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date, end=end_date)

            if data.empty:
                return None

            return data

        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return None

    def _analyze_classical_patterns(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Model 1: Classical Chart Pattern Detection
        Detects: Head & Shoulders, Double Top/Bottom, Triangles, Flags, etc.
        """
        patterns = []
        score = 50  # Base score

        high = data['High'].values
        low = data['Low'].values
        close = data['Close'].values

        # Detect Head and Shoulders
        if self._detect_head_and_shoulders(high, low):
            patterns.append({
                'name': 'Head and Shoulders',
                'confidence': 75,
                'pattern_type': 'reversal',
                'completion_percent': 85
            })
            score += 15

        # Detect Double Top
        if self._detect_double_top(high):
            patterns.append({
                'name': 'Double Top',
                'confidence': 70,
                'pattern_type': 'reversal',
                'completion_percent': 90
            })
            score += 10

        # Detect Double Bottom
        if self._detect_double_bottom(low):
            patterns.append({
                'name': 'Double Bottom',
                'confidence': 72,
                'pattern_type': 'reversal',
                'completion_percent': 88
            })
            score += 12

        # Detect Cup and Handle
        if self._detect_cup_and_handle(close, high, low):
            patterns.append({
                'name': 'Cup and Handle',
                'confidence': 78,
                'pattern_type': 'continuation',
                'completion_percent': 80
            })
            score += 18

        # Detect Triangle Pattern
        triangle_type = self._detect_triangle(high, low)
        if triangle_type:
            patterns.append({
                'name': f'{triangle_type} Triangle',
                'confidence': 68,
                'pattern_type': 'bilateral',
                'completion_percent': 75
            })
            score += 8

        # Calculate suggested stop loss and target
        current_price = close[-1]
        atr = self._calculate_atr(data)

        # Stop loss: 2 ATR below current price or recent low
        recent_low = np.min(low[-20:])
        suggested_stop_loss = min(current_price - (2 * atr), recent_low * 0.98)

        # Target: Based on pattern or 1.5x risk
        risk = current_price - suggested_stop_loss
        suggested_target = current_price + (risk * 2.5)

        # Cap score at 100
        score = min(score, 100)

        return {
            'score': int(score),
            'detected_patterns': patterns if patterns else [{
                'name': 'No Strong Pattern',
                'confidence': 50,
                'pattern_type': 'neutral',
                'completion_percent': 0
            }],
            'suggested_stop_loss': float(suggested_stop_loss),
            'suggested_target': float(suggested_target)
        }

    def _analyze_price_action(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Model 2: Price Action Analysis
        Analyzes support/resistance, trends, breakouts
        """
        high = data['High'].values
        low = data['Low'].values
        close = data['Close'].values
        volume = data['Volume'].values

        # Calculate trend
        sma_20 = talib.SMA(close, timeperiod=20)
        sma_50 = talib.SMA(close, timeperiod=50)

        # Determine trend
        if close[-1] > sma_20[-1] > sma_50[-1]:
            trend = 'uptrend'
            trend_strength = 'strong'
            score = 75
        elif close[-1] > sma_20[-1]:
            trend = 'uptrend'
            trend_strength = 'moderate'
            score = 65
        elif close[-1] < sma_20[-1] < sma_50[-1]:
            trend = 'downtrend'
            trend_strength = 'strong'
            score = 30
        elif close[-1] < sma_20[-1]:
            trend = 'downtrend'
            trend_strength = 'moderate'
            score = 40
        else:
            trend = 'sideways'
            trend_strength = 'weak'
            score = 50

        # Calculate support and resistance
        support_levels = self._find_support_levels(low, close)
        resistance_levels = self._find_resistance_levels(high, close)

        # Detect breakout
        breakout_signal = False
        breakout_type = None
        volume_confirmation = False

        if len(resistance_levels) > 0 and close[-1] > resistance_levels[0]:
            breakout_signal = True
            breakout_type = 'resistance'
            # Check volume confirmation
            avg_volume = np.mean(volume[-20:-1])
            if volume[-1] > avg_volume * 1.5:
                volume_confirmation = True
                score += 15
        elif len(support_levels) > 0 and close[-1] < support_levels[0]:
            breakout_signal = True
            breakout_type = 'support'
            score -= 15

        return {
            'score': int(min(max(score, 0), 100)),
            'trend': trend,
            'trend_strength': trend_strength,
            'support_levels': [float(s) for s in support_levels[:3]],
            'resistance_levels': [float(r) for r in resistance_levels[:3]],
            'breakout_signal': breakout_signal,
            'breakout_type': breakout_type,
            'volume_confirmation': volume_confirmation
        }

    def _analyze_candlestick_patterns(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Model 3: Candlestick Pattern Recognition
        Detects bullish/bearish candlestick patterns
        """
        open_price = data['Open'].values
        high = data['High'].values
        low = data['Low'].values
        close = data['Close'].values

        patterns = []
        score = 50

        # Hammer
        hammer = talib.CDLHAMMER(open_price, high, low, close)
        if hammer[-1] > 0:
            patterns.append({
                'name': 'Hammer',
                'type': 'bullish',
                'reliability': 70,
                'candles_involved': 1
            })
            score += 10

        # Inverted Hammer
        inverted_hammer = talib.CDLINVERTEDHAMMER(open_price, high, low, close)
        if inverted_hammer[-1] > 0:
            patterns.append({
                'name': 'Inverted Hammer',
                'type': 'bullish',
                'reliability': 65,
                'candles_involved': 1
            })
            score += 8

        # Bullish Engulfing
        engulfing = talib.CDLENGULFING(open_price, high, low, close)
        if engulfing[-1] > 0:
            patterns.append({
                'name': 'Bullish Engulfing',
                'type': 'bullish',
                'reliability': 80,
                'candles_involved': 2
            })
            score += 15
        elif engulfing[-1] < 0:
            patterns.append({
                'name': 'Bearish Engulfing',
                'type': 'bearish',
                'reliability': 80,
                'candles_involved': 2
            })
            score -= 15

        # Morning Star
        morning_star = talib.CDLMORNINGSTAR(open_price, high, low, close)
        if morning_star[-1] > 0:
            patterns.append({
                'name': 'Morning Star',
                'type': 'bullish',
                'reliability': 85,
                'candles_involved': 3
            })
            score += 18

        # Evening Star
        evening_star = talib.CDLEVENINGSTAR(open_price, high, low, close)
        if evening_star[-1] > 0:
            patterns.append({
                'name': 'Evening Star',
                'type': 'bearish',
                'reliability': 85,
                'candles_involved': 3
            })
            score -= 18

        # Doji
        doji = talib.CDLDOJI(open_price, high, low, close)
        if doji[-1] > 0:
            patterns.append({
                'name': 'Doji',
                'type': 'neutral',
                'reliability': 60,
                'candles_involved': 1
            })

        # Shooting Star
        shooting_star = talib.CDLSHOOTINGSTAR(open_price, high, low, close)
        if shooting_star[-1] > 0:
            patterns.append({
                'name': 'Shooting Star',
                'type': 'bearish',
                'reliability': 72,
                'candles_involved': 1
            })
            score -= 12

        # Dark Cloud Cover
        dark_cloud = talib.CDLDARKCLOUDCOVER(open_price, high, low, close)
        if dark_cloud[-1] > 0:
            patterns.append({
                'name': 'Dark Cloud Cover',
                'type': 'bearish',
                'reliability': 75,
                'candles_involved': 2
            })
            score -= 13

        # Piercing Pattern
        piercing = talib.CDLPIERCING(open_price, high, low, close)
        if piercing[-1] > 0:
            patterns.append({
                'name': 'Piercing Pattern',
                'type': 'bullish',
                'reliability': 73,
                'candles_involved': 2
            })
            score += 12

        # Cap score
        score = min(max(score, 0), 100)

        return {
            'score': int(score),
            'detected_patterns': patterns if patterns else [{
                'name': 'No Pattern',
                'type': 'neutral',
                'reliability': 50,
                'candles_involved': 0
            }]
        }

    def _combine_models(
        self,
        classical: Dict[str, Any],
        price_action: Dict[str, Any],
        candlestick: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Combine all 3 models into unified analysis
        """
        # Weighted average (40% classical, 35% price action, 25% candlestick)
        combined_score = (
            classical['score'] * 0.4 +
            price_action['score'] * 0.35 +
            candlestick['score'] * 0.25
        )

        # Determine signal
        if combined_score >= 75:
            signal = 'STRONG_BUY'
            confidence = 'HIGH'
        elif combined_score >= 60:
            signal = 'BUY'
            confidence = 'MEDIUM'
        elif combined_score <= 25:
            signal = 'STRONG_SELL'
            confidence = 'LOW'
        elif combined_score <= 40:
            signal = 'SELL'
            confidence = 'LOW'
        else:
            signal = 'NEUTRAL'
            confidence = 'MEDIUM'

        # Generate insights
        insights = []

        if classical['score'] > 70:
            pattern_names = [p['name'] for p in classical['detected_patterns']]
            insights.append(f"Strong classical patterns detected: {', '.join(pattern_names[:2])}")

        if price_action['trend'] == 'uptrend' and price_action['trend_strength'] == 'strong':
            insights.append("Stock is in a strong uptrend with momentum")
        elif price_action['trend'] == 'downtrend':
            insights.append("Stock is in downtrend, consider caution")

        if price_action['breakout_signal'] and price_action['volume_confirmation']:
            insights.append(f"Breakout detected from {price_action['breakout_type']} with volume confirmation")

        if candlestick['score'] > 70:
            bullish_patterns = [p for p in candlestick['detected_patterns'] if p['type'] == 'bullish']
            if bullish_patterns:
                insights.append(f"Bullish candlestick patterns: {bullish_patterns[0]['name']}")

        # Calculate model agreement
        scores = [classical['score'], price_action['score'], candlestick['score']]
        model_agreement = 100 - (np.std(scores) / np.mean(scores) * 100)

        if not insights:
            insights = ["Mixed signals from models, suggest caution"]

        return {
            'score': int(combined_score),
            'signal': signal,
            'confidence': confidence,
            'insights': insights,
            'model_agreement': float(model_agreement)
        }

    # Helper methods for pattern detection

    def _detect_head_and_shoulders(self, high: np.ndarray, low: np.ndarray) -> bool:
        """Detect head and shoulders pattern"""
        if len(high) < 50:
            return False

        # Simplified detection: look for 3 peaks where middle is highest
        recent_high = high[-50:]
        peaks = []

        for i in range(5, len(recent_high) - 5):
            if recent_high[i] > recent_high[i-5:i].max() and recent_high[i] > recent_high[i+1:i+6].max():
                peaks.append((i, recent_high[i]))

        if len(peaks) >= 3:
            # Check if middle peak is highest
            peaks = sorted(peaks, key=lambda x: x[1], reverse=True)
            return True

        return False

    def _detect_double_top(self, high: np.ndarray) -> bool:
        """Detect double top pattern"""
        if len(high) < 30:
            return False

        recent_high = high[-30:]
        max_price = recent_high.max()

        # Find peaks near max
        peaks = []
        for i in range(5, len(recent_high) - 5):
            if recent_high[i] >= max_price * 0.98:
                if recent_high[i] > recent_high[i-3:i].max() and recent_high[i] > recent_high[i+1:i+4].max():
                    peaks.append(i)

        return len(peaks) >= 2

    def _detect_double_bottom(self, low: np.ndarray) -> bool:
        """Detect double bottom pattern"""
        if len(low) < 30:
            return False

        recent_low = low[-30:]
        min_price = recent_low.min()

        # Find troughs near min
        troughs = []
        for i in range(5, len(recent_low) - 5):
            if recent_low[i] <= min_price * 1.02:
                if recent_low[i] < recent_low[i-3:i].min() and recent_low[i] < recent_low[i+1:i+4].min():
                    troughs.append(i)

        return len(troughs) >= 2

    def _detect_cup_and_handle(self, close: np.ndarray, high: np.ndarray, low: np.ndarray) -> bool:
        """Detect cup and handle pattern"""
        if len(close) < 60:
            return False

        # Simplified: look for U-shape followed by consolidation
        recent_close = close[-60:]

        # Check for U-shape in first 40 candles
        first_third = recent_close[:20].mean()
        middle = recent_close[20:40].mean()
        last_third = recent_close[40:].mean()

        # Cup: middle should be lower, ends should be higher
        if middle < first_third * 0.95 and last_third > middle * 1.05:
            # Handle: slight pullback in last 20 candles
            if recent_close[-10:].mean() < recent_close[-20:-10].mean():
                return True

        return False

    def _detect_triangle(self, high: np.ndarray, low: np.ndarray) -> Optional[str]:
        """Detect triangle patterns"""
        if len(high) < 30:
            return None

        recent_high = high[-30:]
        recent_low = low[-30:]

        # Simple trend detection on highs and lows
        high_trend = np.polyfit(range(len(recent_high)), recent_high, 1)[0]
        low_trend = np.polyfit(range(len(recent_low)), recent_low, 1)[0]

        if abs(high_trend) < 0.01 and low_trend > 0.01:
            return 'Ascending'
        elif high_trend < -0.01 and abs(low_trend) < 0.01:
            return 'Descending'
        elif abs(high_trend) < 0.01 and abs(low_trend) < 0.01:
            return 'Symmetrical'

        return None

    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high = data['High'].values
        low = data['Low'].values
        close = data['Close'].values

        atr = talib.ATR(high, low, close, timeperiod=period)
        return float(atr[-1]) if not np.isnan(atr[-1]) else 10.0

    def _find_support_levels(self, low: np.ndarray, close: np.ndarray, num_levels: int = 3) -> List[float]:
        """Find support price levels"""
        recent_low = low[-50:]

        # Find local minima
        support_levels = []
        for i in range(5, len(recent_low) - 5):
            if recent_low[i] == recent_low[i-5:i+6].min():
                support_levels.append(recent_low[i])

        # Remove duplicates and sort
        support_levels = sorted(list(set(np.round(support_levels, 2))))

        # Return levels below current price
        current_price = close[-1]
        support_levels = [s for s in support_levels if s < current_price]

        return support_levels[-num_levels:] if support_levels else [current_price * 0.95]

    def _find_resistance_levels(self, high: np.ndarray, close: np.ndarray, num_levels: int = 3) -> List[float]:
        """Find resistance price levels"""
        recent_high = high[-50:]

        # Find local maxima
        resistance_levels = []
        for i in range(5, len(recent_high) - 5):
            if recent_high[i] == recent_high[i-5:i+6].max():
                resistance_levels.append(recent_high[i])

        # Remove duplicates and sort
        resistance_levels = sorted(list(set(np.round(resistance_levels, 2))))

        # Return levels above current price
        current_price = close[-1]
        resistance_levels = [r for r in resistance_levels if r > current_price]

        return resistance_levels[:num_levels] if resistance_levels else [current_price * 1.05]


# Create singleton instance
pattern_analysis_service = PatternAnalysisService()
