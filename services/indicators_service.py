"""
Enhanced Indicator Service - Advanced Technical Analysis
Provides comprehensive technical indicators with interpretations

Supported Indicators:
- SMA (Simple Moving Average) 20/50/200
- EMA (Exponential Moving Average) 20/50
- RSI (Relative Strength Index) 14
- MACD (Moving Average Convergence Divergence) 12/26/9
- Bollinger Bands (20, 2 std dev)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
# yfinance imported lazily inside methods to avoid slow startup

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IndicatorEngine:
    """
    Technical indicator calculation and interpretation engine
    """

    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = timedelta(minutes=15)

    def calculate_sma(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return data.rolling(window=period).mean()

    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return data.ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, data: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index

        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        """
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_macd(self, data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Returns:
        - macd: MACD line (fast EMA - slow EMA)
        - signal: Signal line (EMA of MACD)
        - histogram: MACD histogram (MACD - Signal)
        """
        ema_fast = self.calculate_ema(data, fast)
        ema_slow = self.calculate_ema(data, slow)

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }

    def calculate_bollinger_bands(self, data: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """
        Calculate Bollinger Bands

        Returns:
        - upper: Upper band (SMA + std_dev * standard deviation)
        - middle: Middle band (SMA)
        - lower: Lower band (SMA - std_dev * standard deviation)
        """
        sma = self.calculate_sma(data, period)
        std = data.rolling(window=period).std()

        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)

        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        }

    def interpret_rsi(self, rsi_value: float) -> Dict[str, Any]:
        """
        Interpret RSI value

        RSI < 30: Oversold (potential buy signal)
        RSI > 70: Overbought (potential sell signal)
        30 <= RSI <= 70: Neutral
        """
        if rsi_value < 30:
            signal = "oversold"
            interpretation = "Potentially oversold - may indicate buying opportunity, but confirm with other indicators"
            strength = "strong" if rsi_value < 20 else "moderate"
        elif rsi_value > 70:
            signal = "overbought"
            interpretation = "Potentially overbought - may indicate selling pressure, but confirm with other indicators"
            strength = "strong" if rsi_value > 80 else "moderate"
        else:
            signal = "neutral"
            interpretation = "RSI in neutral range - no clear overbought/oversold signal"
            strength = "weak"

        return {
            "value": round(rsi_value, 2),
            "signal": signal,
            "strength": strength,
            "interpretation": interpretation
        }

    def interpret_macd(self, macd_value: float, signal_value: float, histogram_value: float) -> Dict[str, Any]:
        """
        Interpret MACD indicator

        MACD > Signal: Bullish momentum
        MACD < Signal: Bearish momentum
        Histogram: Shows momentum strength
        """
        if macd_value > signal_value:
            signal = "bullish"
            interpretation = "MACD above signal line - bullish momentum"
        else:
            signal = "bearish"
            interpretation = "MACD below signal line - bearish momentum"

        # Check for crossovers (recent change in trend)
        crossover = None
        if abs(macd_value - signal_value) < 0.1:  # Very close
            if histogram_value > 0:
                crossover = "bullish_crossover"
                interpretation += " - Possible bullish crossover forming"
            else:
                crossover = "bearish_crossover"
                interpretation += " - Possible bearish crossover forming"

        return {
            "macd": round(macd_value, 2),
            "signal": round(signal_value, 2),
            "histogram": round(histogram_value, 2),
            "trend": signal,
            "crossover": crossover,
            "interpretation": interpretation
        }

    def interpret_bollinger_bands(self, current_price: float, upper: float, middle: float, lower: float) -> Dict[str, Any]:
        """
        Interpret Bollinger Bands position

        Price near upper band: Potentially overbought
        Price near lower band: Potentially oversold
        Price at middle: Neutral
        """
        # Calculate position within bands (0 = lower, 0.5 = middle, 1 = upper)
        band_width = upper - lower
        if band_width > 0:
            position = (current_price - lower) / band_width
        else:
            position = 0.5

        if position > 0.9:
            signal = "overbought"
            interpretation = "Price near upper Bollinger Band - potentially overbought"
        elif position < 0.1:
            signal = "oversold"
            interpretation = "Price near lower Bollinger Band - potentially oversold"
        else:
            signal = "neutral"
            interpretation = f"Price within Bollinger Bands - neutral position ({int(position*100)}% of range)"

        return {
            "current_price": round(current_price, 2),
            "upper_band": round(upper, 2),
            "middle_band": round(middle, 2),
            "lower_band": round(lower, 2),
            "position": round(position, 2),
            "signal": signal,
            "interpretation": interpretation
        }

    def interpret_moving_averages(self, price: float, sma_20: float, sma_50: float, sma_200: float = None) -> Dict[str, Any]:
        """
        Interpret moving average trends

        Golden Cross: SMA 50 crosses above SMA 200 (bullish)
        Death Cross: SMA 50 crosses below SMA 200 (bearish)
        """
        trend = "neutral"
        interpretation = []

        # Short-term trend (price vs SMA 20)
        if price > sma_20:
            interpretation.append("Price above 20-day SMA - short-term uptrend")
            short_term = "bullish"
        else:
            interpretation.append("Price below 20-day SMA - short-term downtrend")
            short_term = "bearish"

        # Medium-term trend (price vs SMA 50)
        if price > sma_50:
            interpretation.append("Price above 50-day SMA - medium-term uptrend")
            medium_term = "bullish"
        else:
            interpretation.append("Price below 50-day SMA - medium-term downtrend")
            medium_term = "bearish"

        # Long-term trend (price vs SMA 200 if available)
        long_term = None
        if sma_200:
            if price > sma_200:
                interpretation.append("Price above 200-day SMA - long-term uptrend")
                long_term = "bullish"
            else:
                interpretation.append("Price below 200-day SMA - long-term downtrend")
                long_term = "bearish"

        # Overall trend
        if short_term == "bullish" and medium_term == "bullish":
            trend = "bullish"
        elif short_term == "bearish" and medium_term == "bearish":
            trend = "bearish"
        else:
            trend = "mixed"

        result = {
            "price": round(price, 2),
            "sma_20": round(sma_20, 2),
            "sma_50": round(sma_50, 2),
            "short_term_trend": short_term,
            "medium_term_trend": medium_term,
            "overall_trend": trend,
            "interpretation": " | ".join(interpretation)
        }

        if sma_200:
            result["sma_200"] = round(sma_200, 2)
            result["long_term_trend"] = long_term

        return result

    def calculate_all_indicators(self, symbol: str, period: str = "6mo") -> Dict[str, Any]:
        """
        Calculate all indicators for a given symbol

        Args:
            symbol: Stock ticker symbol (e.g., "RELIANCE.NS", "AAPL")
            period: Data period (1mo, 3mo, 6mo, 1y, 2y, 5y, max)

        Returns:
            Dictionary containing all indicators and interpretations
        """
        try:
            # Check cache
            cache_key = f"{symbol}_{period}"
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                if datetime.now() - cached_time < self.cache_duration:
                    logger.info(f"Using cached indicators for {symbol}")
                    return cached_data

            # Fetch data — try symbol as-is first, then .NS/.BO fallbacks
            logger.info(f"Fetching data for {symbol}")
            import yfinance as yf
            # Disable SQLite timezone cache — prevents "database or disk is full" on EC2
            try:
                yf.set_tz_cache_location(None)
            except Exception:
                pass
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)

            # If no data and symbol has no exchange suffix, try NSE then BSE
            if hist.empty and not symbol.endswith('.NS') and not symbol.endswith('.BO'):
                logger.info(f"No data for {symbol}, retrying as {symbol}.NS")
                ticker = yf.Ticker(f"{symbol}.NS")
                hist = ticker.history(period=period)
                if not hist.empty:
                    symbol = f"{symbol}.NS"
                else:
                    logger.info(f"No data for {symbol}.NS, retrying as {symbol.split('.')[0]}.BO")
                    base = symbol.split('.')[0]
                    ticker = yf.Ticker(f"{base}.BO")
                    hist = ticker.history(period=period)
                    if not hist.empty:
                        symbol = f"{base}.BO"

            if hist.empty:
                return {
                    "error": f"No data available for {symbol}. Please verify the NSE/BSE ticker symbol.",
                    "symbol": symbol
                }

            close_prices = hist['Close']
            current_price = float(close_prices.iloc[-1])

            # Calculate indicators
            sma_20 = self.calculate_sma(close_prices, 20)
            sma_50 = self.calculate_sma(close_prices, 50)
            sma_200 = self.calculate_sma(close_prices, 200) if len(close_prices) >= 200 else None

            ema_20 = self.calculate_ema(close_prices, 20)
            ema_50 = self.calculate_ema(close_prices, 50)

            rsi = self.calculate_rsi(close_prices, 14)
            macd_data = self.calculate_macd(close_prices)
            bb_data = self.calculate_bollinger_bands(close_prices, 20, 2.0)

            # Get latest values
            latest_sma_20 = float(sma_20.iloc[-1])
            latest_sma_50 = float(sma_50.iloc[-1])
            latest_sma_200 = float(sma_200.iloc[-1]) if sma_200 is not None else None

            latest_ema_20 = float(ema_20.iloc[-1])
            latest_ema_50 = float(ema_50.iloc[-1])

            latest_rsi = float(rsi.iloc[-1])
            latest_macd = float(macd_data['macd'].iloc[-1])
            latest_signal = float(macd_data['signal'].iloc[-1])
            latest_histogram = float(macd_data['histogram'].iloc[-1])

            latest_bb_upper = float(bb_data['upper'].iloc[-1])
            latest_bb_middle = float(bb_data['middle'].iloc[-1])
            latest_bb_lower = float(bb_data['lower'].iloc[-1])

            # Generate interpretations
            rsi_interpretation = self.interpret_rsi(latest_rsi)
            macd_interpretation = self.interpret_macd(latest_macd, latest_signal, latest_histogram)
            bb_interpretation = self.interpret_bollinger_bands(current_price, latest_bb_upper, latest_bb_middle, latest_bb_lower)
            ma_interpretation = self.interpret_moving_averages(current_price, latest_sma_20, latest_sma_50, latest_sma_200)

            # Compile results
            result = {
                "symbol": symbol,
                "current_price": round(current_price, 2),
                "timestamp": datetime.now().isoformat(),
                "data_period": period,
                "indicators": {
                    "moving_averages": {
                        "sma_20": round(latest_sma_20, 2),
                        "sma_50": round(latest_sma_50, 2),
                        "sma_200": round(latest_sma_200, 2) if latest_sma_200 else None,
                        "ema_20": round(latest_ema_20, 2),
                        "ema_50": round(latest_ema_50, 2)
                    },
                    "rsi": rsi_interpretation,
                    "macd": macd_interpretation,
                    "bollinger_bands": bb_interpretation,
                    "trend_analysis": ma_interpretation
                },
                "raw_data": {
                    "dates": hist.index.strftime('%Y-%m-%d').tolist()[-60:],  # Last 60 days
                    "close": close_prices.tail(60).round(2).tolist(),
                    "sma_20": sma_20.tail(60).round(2).tolist(),
                    "sma_50": sma_50.tail(60).round(2).tolist(),
                    "ema_20": ema_20.tail(60).round(2).tolist(),
                    "ema_50": ema_50.tail(60).round(2).tolist(),
                    "rsi": rsi.tail(60).round(2).tolist(),
                    "macd": macd_data['macd'].tail(60).round(2).tolist(),
                    "macd_signal": macd_data['signal'].tail(60).round(2).tolist(),
                    "bb_upper": bb_data['upper'].tail(60).round(2).tolist(),
                    "bb_middle": bb_data['middle'].tail(60).round(2).tolist(),
                    "bb_lower": bb_data['lower'].tail(60).round(2).tolist()
                }
            }

            # Cache the result
            self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {str(e)}")
            return {
                "error": str(e),
                "symbol": symbol
            }

    def get_signal_summary(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate an overall trading signal summary from all indicators

        Returns:
        - overall_signal: bullish, bearish, or neutral
        - confidence: high, medium, low
        - summary: text summary
        """
        if "error" in indicators:
            return {
                "overall_signal": "unknown",
                "confidence": "none",
                "summary": f"Cannot generate signal: {indicators['error']}"
            }

        signals = []

        # RSI signal
        rsi_signal = indicators['indicators']['rsi']['signal']
        if rsi_signal == "oversold":
            signals.append(1)  # Bullish
        elif rsi_signal == "overbought":
            signals.append(-1)  # Bearish
        else:
            signals.append(0)  # Neutral

        # MACD signal
        macd_trend = indicators['indicators']['macd']['trend']
        if macd_trend == "bullish":
            signals.append(1)
        elif macd_trend == "bearish":
            signals.append(-1)
        else:
            signals.append(0)

        # Bollinger Bands signal
        bb_signal = indicators['indicators']['bollinger_bands']['signal']
        if bb_signal == "oversold":
            signals.append(1)
        elif bb_signal == "overbought":
            signals.append(-1)
        else:
            signals.append(0)

        # Trend analysis
        trend = indicators['indicators']['trend_analysis']['overall_trend']
        if trend == "bullish":
            signals.append(1)
        elif trend == "bearish":
            signals.append(-1)
        else:
            signals.append(0)

        # Calculate overall signal
        avg_signal = sum(signals) / len(signals)

        if avg_signal > 0.3:
            overall_signal = "bullish"
            confidence = "high" if avg_signal > 0.6 else "medium"
            summary = f"Multiple indicators suggest bullish sentiment for {indicators['symbol']}"
        elif avg_signal < -0.3:
            overall_signal = "bearish"
            confidence = "high" if avg_signal < -0.6 else "medium"
            summary = f"Multiple indicators suggest bearish sentiment for {indicators['symbol']}"
        else:
            overall_signal = "neutral"
            confidence = "low"
            summary = f"Mixed signals - no clear directional bias for {indicators['symbol']}"

        return {
            "overall_signal": overall_signal,
            "confidence": confidence,
            "summary": summary,
            "signal_score": round(avg_signal, 2)
        }


# Singleton instance
indicator_engine = IndicatorEngine()


# Helper functions for easy access
def get_indicators(symbol: str, period: str = "6mo") -> Dict[str, Any]:
    """Get all indicators for a symbol"""
    return indicator_engine.calculate_all_indicators(symbol, period)


def get_signal_summary(symbol: str, period: str = "6mo") -> Dict[str, Any]:
    """Get overall trading signal summary"""
    indicators = indicator_engine.calculate_all_indicators(symbol, period)
    return indicator_engine.get_signal_summary(indicators)
