import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from ta import momentum, trend, volatility, volume
from services.stock_service import get_ohlc_data, format_indian_ticker
from services.cache_service import get_cached_data, set_cached_data
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TechnicalAnalysis:
    def __init__(self):
        self.default_period = "1y"
        self.default_interval = "1d"
        
    def _convert_period_to_dates(self, period_str):
        """Convert period string like '1y', '6mo', '3mo', '1mo' to start and end dates"""
        end_date = datetime.now()
        
        if period_str == "1y":
            start_date = end_date - timedelta(days=365)
        elif period_str == "6mo":
            start_date = end_date - timedelta(days=180)
        elif period_str == "3mo":
            start_date = end_date - timedelta(days=90)
        elif period_str == "1mo":
            start_date = end_date - timedelta(days=30)
        elif period_str == "1d":
            start_date = end_date - timedelta(days=1)
        else:
            start_date = end_date - timedelta(days=365)  # default to 1 year
            
        return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
        
    def calculate_indicators(self, ticker: str, indicators: List[str], params: Dict = None) -> Dict[str, Any]:
        """Calculate technical indicators for a given stock"""
        # Get historical data - convert period to proper date range
        start_date, end_date = self._convert_period_to_dates(self.default_period)
        df = get_ohlc_data(ticker, start_date, end_date, self.default_interval)
        if df.empty:
            return {"error": "No data available for the ticker"}
            
        results = {}
        dates = df.index.strftime('%Y-%m-%d').tolist()  # Get dates for all data points
        
        # Handle both params and parameters
        params = params.get("parameters", params) if params else {}
        
        for indicator in indicators:
            try:
                if indicator.lower() == "rsi":
                    period = params.get("rsi_period", 14) if params else 14
                    rsi_values = self._calculate_rsi(df, period)
                    
                    # RSI Signal Logic:
                    # Oversold (RSI < 40) + RSI turning up = Buy
                    # Overbought (RSI > 60) + RSI turning down = Sell
                    signal = "neutral"
                    if len(rsi_values) >= 2:
                        current_rsi = rsi_values[-1]
                        prev_rsi = rsi_values[-2]
                        if current_rsi < 40 and current_rsi > prev_rsi:
                            signal = "buy"
                        elif current_rsi > 60 and current_rsi < prev_rsi:
                            signal = "sell"
                    
                    results["rsi"] = {
                        "dates": dates,
                        "values": [float(x) for x in rsi_values],
                        "current": float(rsi_values[-1]),
                        "signal": signal
                    }

                elif indicator.lower() == "macd":
                    fastperiod = params.get("macd_fastperiod", 12) if params else 12
                    slowperiod = params.get("macd_slowperiod", 26) if params else 26
                    signalperiod = params.get("macd_signalperiod", 9) if params else 9
                    macd_data = self._calculate_macd(df, fastperiod, slowperiod, signalperiod)
                    
                    # MACD Signal Logic:
                    # MACD line crosses above signal line = Buy
                    # MACD line crosses below signal line = Sell
                    # Also consider histogram direction change
                    signal = "neutral"
                    if len(macd_data["macd"]) >= 2:
                        curr_macd = macd_data["macd"][-1]
                        curr_signal = macd_data["signal"][-1]
                        prev_macd = macd_data["macd"][-2]
                        prev_signal = macd_data["signal"][-2]
                        curr_hist = macd_data["histogram"][-1]
                        prev_hist = macd_data["histogram"][-2]
                        
                        if (prev_macd <= prev_signal and curr_macd > curr_signal) or \
                           (prev_hist < 0 and curr_hist > 0):
                            signal = "buy"
                        elif (prev_macd >= prev_signal and curr_macd < curr_signal) or \
                             (prev_hist > 0 and curr_hist < 0):
                            signal = "sell"
                    
                    results["macd"] = {
                        "dates": dates,
                        "macd": [float(x) for x in macd_data["macd"]],
                        "signal": [float(x) for x in macd_data["signal"]],
                        "histogram": [float(x) for x in macd_data["histogram"]],
                        "current": {
                            "macd": float(macd_data["macd"][-1]),
                            "signal": float(macd_data["signal"][-1]),
                            "histogram": float(macd_data["histogram"][-1])
                        },
                        "signal": signal
                    }

                elif indicator.lower() == "bollinger":
                    period = params.get("bb_period", 20) if params else 20
                    bb_data = self._calculate_bollinger_bands(df, period)
                    current_price = float(df['Close'].iloc[-1])
                    prev_price = float(df['Close'].iloc[-2])
                    
                    # Bollinger Bands Signal Logic:
                    # Price crosses above upper band = Potential sell (overbought)
                    # Price crosses below lower band = Potential buy (oversold)
                    # Price moves back inside bands = Reversal signal
                    # Band squeeze (bands narrow) followed by expansion = Breakout signal
                    signal = "neutral"
                    signal_reason = ""
                    
                    upper = bb_data["upper"][-1]
                    lower = bb_data["lower"][-1]
                    prev_upper = bb_data["upper"][-2]
                    prev_lower = bb_data["lower"][-2]
                    
                    # Calculate band width for squeeze detection
                    curr_bandwidth = (upper - lower) / bb_data["middle"][-1]
                    prev_bandwidth = (prev_upper - prev_lower) / bb_data["middle"][-2]
                    
                    if current_price > upper and prev_price <= prev_upper:
                        signal = "sell"
                        signal_reason = "price crossed above upper band"
                    elif current_price < lower and prev_price >= prev_lower:
                        signal = "buy"
                        signal_reason = "price crossed below lower band"
                    elif (prev_price > prev_upper and current_price <= upper) or \
                         (prev_price < prev_lower and current_price >= lower):
                        signal = "neutral"
                        signal_reason = "price moved back inside bands"
                    elif curr_bandwidth > prev_bandwidth * 1.1 and \
                         abs(current_price - prev_price) > abs(upper - lower) * 0.1:
                        signal = "buy" if current_price > prev_price else "sell"
                        signal_reason = "breakout from band squeeze"
                    
                    results["bollinger"] = {
                        "dates": dates,
                        "upper": [float(x) for x in bb_data["upper"]],
                        "middle": [float(x) for x in bb_data["middle"]],
                        "lower": [float(x) for x in bb_data["lower"]],
                        "current": {
                            "upper": float(bb_data["upper"][-1]),
                            "middle": float(bb_data["middle"][-1]),
                            "lower": float(bb_data["lower"][-1]),
                            "price": current_price
                        },
                        "signal": signal,
                        "signal_reason": signal_reason
                    }

                elif indicator.lower() == "stochastic":
                    k_period = params.get("stoch_k_period", 14) if params else 14
                    d_period = params.get("stoch_d_period", 3) if params else 3
                    stoch_data = self._calculate_stochastic(df, k_period, d_period)
                    
                    # Stochastic Signal Logic:
                    # K line crosses above D line in oversold territory = Strong buy
                    # K line crosses below D line in overbought territory = Strong sell
                    # K line crosses D line in neutral territory = Weak signal
                    signal = "neutral"
                    signal_strength = "weak"
                    
                    if len(stoch_data["k"]) >= 2:
                        curr_k = stoch_data["k"][-1]
                        curr_d = stoch_data["d"][-1]
                        prev_k = stoch_data["k"][-2]
                        prev_d = stoch_data["d"][-2]
                        
                        if prev_k <= prev_d and curr_k > curr_d:  # Bullish crossover
                            if curr_k < 20:
                                signal = "buy"
                                signal_strength = "strong"
                            else:
                                signal = "buy"
                                signal_strength = "weak"
                        elif prev_k >= prev_d and curr_k < curr_d:  # Bearish crossover
                            if curr_k > 80:
                                signal = "sell"
                                signal_strength = "strong"
                            else:
                                signal = "sell"
                                signal_strength = "weak"
                    
                    results["stochastic"] = {
                        "dates": dates,
                        "k": [float(x) for x in stoch_data["k"]],
                        "d": [float(x) for x in stoch_data["d"]],
                        "current": {
                            "k": float(stoch_data["k"][-1]),
                            "d": float(stoch_data["d"][-1])
                        },
                        "signal": signal,
                        "signal_strength": signal_strength
                    }

                elif indicator.lower() == "sma":
                    period = params.get("sma_period", 20) if params else 20
                    sma_values = self._calculate_sma(df, period)
                    current_price = float(df['Close'].iloc[-1])
                    prev_price = float(df['Close'].iloc[-2])
                    prev_sma = float(sma_values[-2])
                    curr_sma = float(sma_values[-1])
                    
                    # SMA Signal Logic:
                    # Price crosses above SMA = Buy
                    # Price crosses below SMA = Sell
                    # Also consider SMA slope for trend strength
                    signal = "neutral"
                    trend = "neutral"
                    
                    # Determine trend based on SMA slope
                    if curr_sma > prev_sma:
                        trend = "uptrend"
                    elif curr_sma < prev_sma:
                        trend = "downtrend"
                    
                    # Generate signal based on price crossover
                    if prev_price <= prev_sma and current_price > curr_sma:
                        signal = "buy"
                    elif prev_price >= prev_sma and current_price < curr_sma:
                        signal = "sell"
                    
                    results["sma"] = {
                        "dates": dates,
                        "values": [float(x) for x in sma_values],
                        "current": float(sma_values[-1]),
                        "signal": signal,
                        "trend": trend
                    }

                elif indicator.lower() == "ema":
                    period = params.get("ema_period", 20) if params else 20
                    ema_values = self._calculate_ema(df, period)
                    current_price = float(df['Close'].iloc[-1])
                    prev_price = float(df['Close'].iloc[-2])
                    prev_ema = float(ema_values[-2])
                    curr_ema = float(ema_values[-1])
                    
                    # EMA Signal Logic:
                    # Similar to SMA but more weight on recent prices
                    # Price crosses above EMA = Buy
                    # Price crosses below EMA = Sell
                    # Also consider EMA slope and distance from price
                    signal = "neutral"
                    trend = "neutral"
                    strength = "normal"
                    
                    # Determine trend based on EMA slope
                    if curr_ema > prev_ema:
                        trend = "uptrend"
                    elif curr_ema < prev_ema:
                        trend = "downtrend"
                    
                    # Generate signal based on price crossover
                    if prev_price <= prev_ema and current_price > curr_ema:
                        signal = "buy"
                        # Check signal strength based on distance from EMA
                        if (current_price - curr_ema) / curr_ema > 0.02:
                            strength = "strong"
                    elif prev_price >= prev_ema and current_price < curr_ema:
                        signal = "sell"
                        # Check signal strength based on distance from EMA
                        if (curr_ema - current_price) / curr_ema > 0.02:
                            strength = "strong"
                    
                    results["ema"] = {
                        "dates": dates,
                        "values": [float(x) for x in ema_values],
                        "current": float(ema_values[-1]),
                        "signal": signal,
                        "trend": trend,
                        "strength": strength
                    }

                elif indicator.lower() == "supertrend":
                    period = params.get("supertrend_period", 10) if params else 10
                    multiplier = params.get("supertrend_multiplier", 3) if params else 3
                    st_data = self._calculate_supertrend(df, period, multiplier)
                    current_price = float(df['Close'].iloc[-1])
                    prev_direction = int(st_data["direction"][-2]) if len(st_data["direction"]) >= 2 else 0
                    curr_direction = int(st_data["direction"][-1])

                    # Supertrend Signal Logic:
                    # Direction changes from -1 to 1 = Buy signal
                    # Direction changes from 1 to -1 = Sell signal
                    signal = "neutral"
                    if prev_direction != curr_direction:
                        signal = "buy" if curr_direction == 1 else "sell"
                    elif curr_direction == 1 and current_price > st_data["supertrend"][-1]:
                        signal = "buy"
                    elif curr_direction == -1 and current_price < st_data["supertrend"][-1]:
                        signal = "sell"

                    results["supertrend"] = {
                        "dates": dates,
                        "supertrend": [float(x) for x in st_data["supertrend"]],
                        "direction": [int(x) for x in st_data["direction"]],
                        "upper_band": [float(x) for x in st_data["upper_band"]],
                        "lower_band": [float(x) for x in st_data["lower_band"]],
                        "current": {
                            "supertrend": float(st_data["supertrend"][-1]),
                            "direction": int(st_data["direction"][-1]),
                            "price": current_price
                        },
                        "signal": signal
                    }

                elif indicator.lower() == "ichimoku":
                    period1 = params.get("ichimoku_period1", 9) if params else 9
                    period2 = params.get("ichimoku_period2", 26) if params else 26
                    period3 = params.get("ichimoku_period3", 52) if params else 52
                    ich_data = self._calculate_ichimoku(df, period1, period2, period3)
                    current_price = float(df['Close'].iloc[-1])

                    # Ichimoku Signal Logic:
                    # Buy: Price > Cloud AND Tenkan > Kijun AND Chikou > Price
                    # Sell: Price < Cloud AND Tenkan < Kijun AND Chikou < Price
                    signal = "neutral"
                    cloud_top = max(ich_data["senkou_a"][-1], ich_data["senkou_b"][-1])
                    cloud_bottom = min(ich_data["senkou_a"][-1], ich_data["senkou_b"][-1])

                    bullish_conditions = 0
                    bearish_conditions = 0

                    if current_price > cloud_top:
                        bullish_conditions += 1
                    elif current_price < cloud_bottom:
                        bearish_conditions += 1

                    if ich_data["tenkan"][-1] > ich_data["kijun"][-1]:
                        bullish_conditions += 1
                    elif ich_data["tenkan"][-1] < ich_data["kijun"][-1]:
                        bearish_conditions += 1

                    if ich_data["chikou"][-1] > current_price:
                        bullish_conditions += 1
                    elif ich_data["chikou"][-1] < current_price:
                        bearish_conditions += 1

                    if bullish_conditions >= 2:
                        signal = "buy"
                    elif bearish_conditions >= 2:
                        signal = "sell"

                    results["ichimoku"] = {
                        "dates": dates,
                        "tenkan": [float(x) for x in ich_data["tenkan"]],
                        "kijun": [float(x) for x in ich_data["kijun"]],
                        "senkou_a": [float(x) for x in ich_data["senkou_a"]],
                        "senkou_b": [float(x) for x in ich_data["senkou_b"]],
                        "chikou": [float(x) for x in ich_data["chikou"]],
                        "current": {
                            "tenkan": float(ich_data["tenkan"][-1]),
                            "kijun": float(ich_data["kijun"][-1]),
                            "senkou_a": float(ich_data["senkou_a"][-1]),
                            "senkou_b": float(ich_data["senkou_b"][-1]),
                            "chikou": float(ich_data["chikou"][-1]),
                            "price": current_price
                        },
                        "signal": signal
                    }

                elif indicator.lower() == "cci":
                    period = params.get("cci_period", 20) if params else 20
                    cci_values = self._calculate_cci(df, period)
                    curr_cci = float(cci_values[-1])
                    prev_cci = float(cci_values[-2]) if len(cci_values) >= 2 else 0

                    # CCI Signal Logic:
                    # CCI crosses above +100 = Buy (breakout)
                    # CCI crosses below -100 = Sell (breakdown)
                    # CCI crosses above 0 = Bullish momentum
                    # CCI crosses below 0 = Bearish momentum
                    signal = "neutral"
                    if prev_cci <= 100 and curr_cci > 100:
                        signal = "buy"
                    elif prev_cci >= -100 and curr_cci < -100:
                        signal = "sell"
                    elif prev_cci < 0 and curr_cci >= 0:
                        signal = "buy"
                    elif prev_cci > 0 and curr_cci <= 0:
                        signal = "sell"

                    results["cci"] = {
                        "dates": dates,
                        "values": [float(x) for x in cci_values],
                        "current": curr_cci,
                        "signal": signal
                    }

                elif indicator.lower() == "mfi":
                    period = params.get("mfi_period", 14) if params else 14
                    mfi_values = self._calculate_mfi(df, period)
                    curr_mfi = float(mfi_values[-1])
                    prev_mfi = float(mfi_values[-2]) if len(mfi_values) >= 2 else 50

                    # MFI Signal Logic:
                    # MFI crosses above 20 (from oversold) = Buy
                    # MFI crosses below 80 (from overbought) = Sell
                    # MFI < 20 = Oversold condition
                    # MFI > 80 = Overbought condition
                    signal = "neutral"
                    if prev_mfi < 20 and curr_mfi >= 20:
                        signal = "buy"
                    elif prev_mfi > 80 and curr_mfi <= 80:
                        signal = "sell"
                    elif curr_mfi < 20:
                        signal = "buy"  # Oversold
                    elif curr_mfi > 80:
                        signal = "sell"  # Overbought

                    results["mfi"] = {
                        "dates": dates,
                        "values": [float(x) for x in mfi_values],
                        "current": curr_mfi,
                        "signal": signal
                    }

                elif indicator.lower() == "keltner":
                    ema_period = params.get("keltner_ema_period", 20) if params else 20
                    atr_period = params.get("keltner_atr_period", 14) if params else 14
                    atr_mult = params.get("keltner_atr_mult", 2) if params else 2
                    kc_data = self._calculate_keltner_channels(df, ema_period, atr_period, atr_mult)
                    current_price = float(df['Close'].iloc[-1])
                    prev_price = float(df['Close'].iloc[-2])

                    # Keltner Channels Signal Logic:
                    # Price crosses above upper channel = Buy (breakout)
                    # Price crosses below lower channel = Sell (breakdown)
                    # Price returns to middle from upper = Sell signal
                    # Price returns to middle from lower = Buy signal
                    signal = "neutral"
                    upper = float(kc_data["upper"][-1])
                    lower = float(kc_data["lower"][-1])
                    prev_upper = float(kc_data["upper"][-2])
                    prev_lower = float(kc_data["lower"][-2])

                    if prev_price <= prev_upper and current_price > upper:
                        signal = "buy"
                    elif prev_price >= prev_lower and current_price < lower:
                        signal = "sell"

                    results["keltner"] = {
                        "dates": dates,
                        "upper": [float(x) for x in kc_data["upper"]],
                        "middle": [float(x) for x in kc_data["middle"]],
                        "lower": [float(x) for x in kc_data["lower"]],
                        "current": {
                            "upper": upper,
                            "middle": float(kc_data["middle"][-1]),
                            "lower": lower,
                            "price": current_price
                        },
                        "signal": signal
                    }

                elif indicator.lower() == "williams_r" or indicator.lower() == "williamsr":
                    period = params.get("williams_period", 14) if params else 14
                    wr_values = self._calculate_williams_r(df, period)
                    curr_wr = float(wr_values[-1])
                    prev_wr = float(wr_values[-2]) if len(wr_values) >= 2 else -50

                    # Williams %R Signal Logic:
                    # WR crosses above -80 (from oversold) = Buy
                    # WR crosses below -20 (from overbought) = Sell
                    # WR < -80 = Oversold
                    # WR > -20 = Overbought
                    signal = "neutral"
                    if prev_wr < -80 and curr_wr >= -80:
                        signal = "buy"
                    elif prev_wr > -20 and curr_wr <= -20:
                        signal = "sell"

                    results["williams_r"] = {
                        "dates": dates,
                        "values": [float(x) for x in wr_values],
                        "current": curr_wr,
                        "signal": signal
                    }

            except Exception as e:
                results[indicator] = {"error": str(e)}

        return results
    
    def screen_stocks(self, criteria: Dict[str, Any], tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        """Screen stocks based on technical criteria"""
        if not tickers:
            # Default to Nifty 50 stocks or implement your own list
            tickers = self._get_default_stock_list()
            
        results = {}
        for ticker in tickers:
            try:
                start_date, end_date = self._convert_period_to_dates("1mo")
                df = get_ohlc_data(ticker, start_date, end_date, "1d")  # Use shorter period for screening
                if not df.empty:
                    matches_criteria = self._evaluate_screening_criteria(df, criteria)
                    if matches_criteria:
                        results[ticker] = matches_criteria
            except Exception as e:
                continue
                
        return results
    
    def get_support_resistance(self, ticker: str) -> Dict[str, Any]:
        """Calculate support and resistance levels"""
        start_date, end_date = self._convert_period_to_dates("1y")
        df = get_ohlc_data(ticker, start_date, end_date, "1d")
        if df.empty:
            return {"error": "No data available"}
            
        # Calculate pivot points
        pivot = (df['High'].iloc[-1] + df['Low'].iloc[-1] + df['Close'].iloc[-1]) / 3
        r1 = 2 * pivot - df['Low'].iloc[-1]
        s1 = 2 * pivot - df['High'].iloc[-1]
        r2 = pivot + (df['High'].iloc[-1] - df['Low'].iloc[-1])
        s2 = pivot - (df['High'].iloc[-1] - df['Low'].iloc[-1])
        
        return {
            "pivot": float(pivot),
            "resistance": [float(r1), float(r2)],
            "support": [float(s1), float(s2)]
        }
    
    def identify_patterns(self, ticker: str) -> Dict[str, Any]:
        """Identify chart patterns"""
        start_date, end_date = self._convert_period_to_dates("6mo")
        df = get_ohlc_data(ticker, start_date, end_date, "1d")
        if df.empty:
            return {"error": "No data available"}
            
        patterns = {
            "trend": self._identify_trend_patterns(df),
            "momentum": self._identify_momentum_patterns(df),
            "volatility": self._identify_volatility_patterns(df)
        }
        
        return patterns
    
    def get_trading_signals(self, ticker: str) -> Dict[str, Any]:
        """Generate trading signals based on multiple indicators"""
        start_date, end_date = self._convert_period_to_dates("3mo")
        df = get_ohlc_data(ticker, start_date, end_date, "1d")
        if df.empty:
            return {"error": "No data available"}
            
        signals = {}
        current_price = float(df['Close'].iloc[-1])
        
        # RSI Signal
        rsi = self._calculate_rsi(df)
        signals["rsi"] = {
            "value": float(rsi[-1]),
            "signal": "buy" if rsi[-1] > 30 else "sell" if rsi[-1] < 70 else "neutral",
            "description": "RSI oversold" if rsi[-1] < 30 else "RSI overbought" if rsi[-1] > 70 else "RSI neutral"
        }
        
        # MACD Signal
        macd = self._calculate_macd(df)
        signals["macd"] = {
            "value": {
                "macd": float(macd["macd"][-1]),
                "signal": float(macd["signal"][-1]),
                "histogram": float(macd["histogram"][-1])
            },
            "signal": "buy" if macd["macd"][-1] > macd["signal"][-1] else "sell",
            "description": "MACD bullish crossover" if macd["macd"][-1] > macd["signal"][-1] else "MACD bearish crossover"
        }
        
        # EMA/SMA Signal
        ema = self._calculate_ema(df, 20)
        signals["ema"] = {
            "value": float(ema[-1]),
            "signal": "buy" if current_price > ema[-1] else "sell",
            "description": "Price above EMA" if current_price > ema[-1] else "Price below EMA"
        }
        
        # Stochastic Signal
        stoch = self._calculate_stochastic(df)
        signals["stochastic"] = {
            "value": {
                "k": float(stoch["k"][-1]),
                "d": float(stoch["d"][-1])
            },
            "signal": "buy" if stoch["k"][-1] > stoch["d"][-1] and stoch["k"][-1] < 20 else "sell" if stoch["k"][-1] < stoch["d"][-1] and stoch["k"][-1] > 80 else "neutral",
            "description": "Stochastic oversold crossover" if stoch["k"][-1] > stoch["d"][-1] and stoch["k"][-1] < 20 else "Stochastic overbought crossover" if stoch["k"][-1] < stoch["d"][-1] and stoch["k"][-1] > 80 else "Stochastic neutral"
        }
        
        # Bollinger Bands Signal
        bb = self._calculate_bollinger_bands(df)
        signals["bollinger"] = {
            "value": {
                "upper": float(bb["upper"][-1]),
                "middle": float(bb["middle"][-1]),
                "lower": float(bb["lower"][-1]),
                "price": current_price
            },
            "signal": "buy" if current_price <= bb["lower"][-1] else "sell" if current_price >= bb["upper"][-1] else "neutral",
            "description": "Price at lower band" if current_price <= bb["lower"][-1] else "Price at upper band" if current_price >= bb["upper"][-1] else "Price within bands"
        }
        
        # ATR Signal (for volatility context)
        atr = self._calculate_atr(df)
        signals["atr"] = {
            "value": float(atr[-1]),
            "signal": "neutral",
            "description": f"ATR: {atr[-1]:.2f} - Use for stop loss/take profit"
        }
        
        # OBV Signal
        obv, obv_signals = self.calculate_obv(df, {"signal_period": 20, "ma_type": 1})
        signals["obv"] = {
            "value": float(obv[-1]),
            "signal": "buy" if obv[-1] > obv[-2] else "sell",
            "description": "Volume rising with price" if obv[-1] > obv[-2] else "Volume falling with price"
        }
        
        # VWAP Signal
        vwap, vwap_signals = self.calculate_vwap(df, {"period": 14, "anchor": 1})
        signals["vwap"] = {
            "value": float(vwap[-1]),
            "signal": "buy" if current_price > vwap[-1] else "sell",
            "description": "Price above VWAP" if current_price > vwap[-1] else "Price below VWAP"
        }
        
        # Pivot Points Signal
        pivot_data = self._calculate_pivot_points(df)
        pivot_signal = "neutral"
        pivot_desc = "Price within pivot range"
        if current_price <= pivot_data["support1"]:
            pivot_signal = "buy"
            pivot_desc = "Price near support level"
        elif current_price >= pivot_data["resistance1"]:
            pivot_signal = "sell"
            pivot_desc = "Price near resistance level"
        
        signals["pivot"] = {
            "value": pivot_data,
            "signal": pivot_signal,
            "description": pivot_desc
        }
        
        # Fibonacci Signal
        fib_data = self._calculate_fibonacci_retracement(df)
        fib_signal = "neutral"
        fib_desc = "Price not near fibonacci levels"
        for level, value in fib_data["levels"].items():
            if abs(current_price - value) / value < 0.01:  # Within 1% of fib level
                fib_signal = "buy" if current_price > value else "sell"
                fib_desc = f"Price near {level}% fibonacci level"
                break
        
        signals["fibonacci"] = {
            "value": fib_data,
            "signal": fib_signal,
            "description": fib_desc
        }
        
        # Overall Signal
        signals["overall"] = self._calculate_overall_signal(signals)
        
        return signals
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        """Calculate RSI indicator with improved NaN handling and min_periods"""
        try:
            logger.info(f"Calculating RSI with period {period}")
            
            # Validate input data
            if df.empty or 'Close' not in df.columns:
                logger.error("Invalid input data for RSI calculation")
                return np.full(max(len(df), period), 50.0)
            
            # Calculate price changes
            delta = df['Close'].diff()
            
            # Get gains and losses, ensuring no NaN propagation
            gain = delta.where(delta > 0, 0).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            
            # Use rolling average with min_periods=1 to reduce NaN values
            avg_gain = gain.rolling(window=period, min_periods=1).mean()
            avg_loss = loss.rolling(window=period, min_periods=1).mean()
            
            # Ensure no division by zero
            avg_loss = avg_loss.replace(0, 1e-10)
            
            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            # Fill any remaining NaN with neutral value (50)
            rsi = rsi.fillna(50)
            
            # Ensure all values are within valid range [0, 100]
            rsi = np.clip(rsi.values, 0, 100)
            
            logger.info(f"RSI calculated successfully. Range: {rsi.min():.2f} - {rsi.max():.2f}")
            logger.info(f"RSI NaN count: {pd.isna(rsi).sum()}/{len(rsi)}")
            
            return rsi
        except Exception as e:
            logger.error(f"Error calculating RSI: {str(e)}")
            return np.full(max(len(df), period), 50.0)
    
    def _calculate_macd(self, df: pd.DataFrame, fastperiod: int = 12, slowperiod: int = 26, signalperiod: int = 9) -> Dict[str, np.ndarray]:
        """Calculate MACD indicator with improved NaN handling"""
        try:
            logger.info(f"Calculating MACD with fast={fastperiod}, slow={slowperiod}, signal={signalperiod}")
            
            # Validate input data
            if df.empty or 'Close' not in df.columns:
                logger.error("Invalid input data for MACD calculation")
                zeros = np.zeros(max(len(df), slowperiod))
                return {'macd': zeros, 'signal': zeros, 'histogram': zeros}
            
            # Calculate EMAs with min_periods=1 to reduce NaN values
            fast_ema = df['Close'].ewm(span=fastperiod, adjust=False, min_periods=1).mean()
            slow_ema = df['Close'].ewm(span=slowperiod, adjust=False, min_periods=1).mean()
            
            # Calculate MACD line
            macd_line = fast_ema - slow_ema
            
            # Calculate signal line with min_periods=1
            signal_line = macd_line.ewm(span=signalperiod, adjust=False, min_periods=1).mean()
            
            # Calculate histogram
            histogram = macd_line - signal_line
            
            # Fill any remaining NaN values with 0
            macd_line = macd_line.fillna(0).values
            signal_line = signal_line.fillna(0).values
            histogram = histogram.fillna(0).values
            
            logger.info(f"MACD calculated successfully. MACD range: {macd_line.min():.4f} - {macd_line.max():.4f}")
            logger.info(f"MACD NaN counts - MACD: {pd.isna(macd_line).sum()}, Signal: {pd.isna(signal_line).sum()}, Histogram: {pd.isna(histogram).sum()}")
            
            return {
                'macd': macd_line,
                'signal': signal_line, 
                'histogram': histogram
            }
        except Exception as e:
            logger.error(f"Error calculating MACD: {str(e)}")
            zeros = np.zeros(max(len(df), slowperiod))
            return {'macd': zeros, 'signal': zeros, 'histogram': zeros}
    
    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, num_std: int = 2) -> Dict[str, np.ndarray]:
        """Calculate Bollinger Bands with improved NaN handling"""
        try:
            logger.info(f"Calculating Bollinger Bands with period={period}, std={num_std}")
            
            # Validate input data
            if df.empty or 'Close' not in df.columns:
                logger.error("Invalid input data for Bollinger Bands calculation")
                zeros = np.zeros(max(len(df), period))
                return {"upper": zeros, "middle": zeros, "lower": zeros}
            
            # Calculate middle band (SMA) with min_periods=1
            middle = df['Close'].rolling(window=period, min_periods=1).mean()
            
            # Calculate standard deviation with min_periods=1
            std = df['Close'].rolling(window=period, min_periods=1).std()
            
            # Fill any NaN in std with 0 to prevent NaN propagation
            std = std.fillna(0)
            
            # Calculate upper and lower bands
            upper = middle + (std * num_std)
            lower = middle - (std * num_std)
            
            # Fill any remaining NaN values
            middle = middle.fillna(method='ffill').fillna(df['Close'].mean())
            upper = upper.fillna(method='ffill').fillna(df['Close'].mean())
            lower = lower.fillna(method='ffill').fillna(df['Close'].mean())
            
            logger.info(f"Bollinger Bands calculated successfully")
            
            return {
                "upper": upper.values,
                "middle": middle.values,
                "lower": lower.values
            }
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {str(e)}")
            close_mean = df['Close'].mean() if not df.empty and 'Close' in df.columns else 100
            size = max(len(df), period) if not df.empty else period
            return {
                "upper": np.full(size, close_mean),
                "middle": np.full(size, close_mean),
                "lower": np.full(size, close_mean)
            }
    
    def _calculate_sma(self, df: pd.DataFrame, period: int = 20) -> np.ndarray:
        """Calculate Simple Moving Average with improved NaN handling"""
        try:
            logger.info(f"Calculating SMA with period {period}")
            
            # Validate input data
            if df.empty or 'Close' not in df.columns:
                logger.error("Invalid input data for SMA calculation")
                return np.full(max(len(df), period), df['Close'].mean() if not df.empty else 100.0)
            
            # Calculate SMA with min_periods=1 to reduce NaN values
            sma = df['Close'].rolling(window=period, min_periods=1).mean()
            
            # Fill any remaining NaN values
            sma = sma.fillna(method='ffill').fillna(df['Close'].mean())
            
            logger.info(f"SMA calculated successfully. Range: {sma.min():.2f} - {sma.max():.2f}")
            return sma.values
        except Exception as e:
            logger.error(f"Error calculating SMA: {str(e)}")
            close_mean = df['Close'].mean() if not df.empty and 'Close' in df.columns else 100.0
            return np.full(max(len(df), period), close_mean)
    
    def _calculate_ema(self, df: pd.DataFrame, period: int = 20) -> np.ndarray:
        """Calculate Exponential Moving Average with improved NaN handling"""
        try:
            logger.info(f"Calculating EMA with period {period}")
            
            # Validate input data
            if df.empty or 'Close' not in df.columns:
                logger.error("Invalid input data for EMA calculation")
                return np.full(max(len(df), period), df['Close'].mean() if not df.empty else 100.0)
            
            # Calculate EMA with min_periods=1 to reduce NaN values
            ema = df['Close'].ewm(span=period, adjust=False, min_periods=1).mean()
            
            # Fill any remaining NaN values
            ema = ema.fillna(method='ffill').fillna(df['Close'].mean())
            
            logger.info(f"EMA calculated successfully. Range: {ema.min():.2f} - {ema.max():.2f}")
            return ema.values
        except Exception as e:
            logger.error(f"Error calculating EMA: {str(e)}")
            close_mean = df['Close'].mean() if not df.empty and 'Close' in df.columns else 100.0
            return np.full(max(len(df), period), close_mean)
    
    def _get_default_stock_list(self) -> List[str]:
        """Get default list of stocks (e.g., Nifty 50)"""
        # Implement your own logic to get default stock list
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]
    
    def _evaluate_screening_criteria(self, df: pd.DataFrame, criteria: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate if a stock matches the screening criteria"""
        results = {}
        
        for indicator, condition in criteria.items():
            if indicator == "rsi":
                rsi = self._calculate_rsi(df)
                if condition.get("below") and rsi[-1] < condition["below"]:
                    results["rsi"] = float(rsi[-1])
                elif condition.get("above") and rsi[-1] > condition["above"]:
                    results["rsi"] = float(rsi[-1])
            elif indicator == "volume":
                avg_volume = df['Volume'].mean()
                if condition.get("min") and avg_volume > condition["min"]:
                    results["volume"] = float(avg_volume)
                    
        return results if results else None
    
    def _identify_trend_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify trend patterns"""
        patterns = {}
        
        # ADX (Average Directional Index)
        adx = trend.ADXIndicator(df['High'], df['Low'], df['Close'])
        adx_value = float(adx.adx().iloc[-1])
        
        patterns["trend_strength"] = {
            "value": adx_value,
            "interpretation": "strong" if adx_value > 25 else "weak"
        }
        
        # Trend direction using moving averages
        sma_20 = self._calculate_sma(df, 20)
        sma_50 = self._calculate_sma(df, 50)
        
        patterns["trend_direction"] = "uptrend" if sma_20[-1] > sma_50[-1] else "downtrend"
        
        return patterns
    
    def _identify_momentum_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify momentum patterns"""
        patterns = {}
        
        # Stochastic Oscillator
        stoch = momentum.StochasticOscillator(df['High'], df['Low'], df['Close'])
        stoch_k = float(stoch.stoch().iloc[-1])
        stoch_d = float(stoch.stoch_signal().iloc[-1])
        
        patterns["stochastic"] = {
            "k_line": stoch_k,
            "d_line": stoch_d,
            "signal": "oversold" if stoch_k < 20 else "overbought" if stoch_k > 80 else "neutral"
        }
        
        return patterns
    
    def _identify_volatility_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify volatility patterns"""
        patterns = {}
        
        # Average True Range
        atr = volatility.AverageTrueRange(df['High'], df['Low'], df['Close'])
        atr_value = float(atr.average_true_range().iloc[-1])
        
        patterns["volatility"] = {
            "atr": atr_value,
            "interpretation": "high" if atr_value > df['Close'].mean() * 0.02 else "low"
        }
        
        return patterns
    
    def _calculate_overall_signal(self, signals: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall trading signal based on multiple indicators"""
        score = 0
        total_indicators = 0
        
        # RSI contribution
        if "rsi" in signals:
            total_indicators += 1
            if signals["rsi"]["signal"] == "buy":
                score += 1
            elif signals["rsi"]["signal"] == "sell":
                score -= 1
            
        # MACD contribution
        if "macd" in signals:
            total_indicators += 1
            if signals["macd"]["signal"] == "buy":
                score += 1
            elif signals["macd"]["signal"] == "sell":
                score -= 1
                
        # EMA/SMA contribution
        if "ema" in signals:
            total_indicators += 1
            if signals["ema"]["signal"] == "buy":
                score += 1
            elif signals["ema"]["signal"] == "sell":
                score -= 1
                
        # Stochastic contribution
        if "stochastic" in signals:
            total_indicators += 1
            if signals["stochastic"]["signal"] == "buy":
                score += 1
            elif signals["stochastic"]["signal"] == "sell":
                score -= 1
                
        # Bollinger Bands contribution
        if "bollinger" in signals:
            total_indicators += 1
            if signals["bollinger"]["signal"] == "buy":
                score += 1
            elif signals["bollinger"]["signal"] == "sell":
                score -= 1
                
        # OBV contribution
        if "obv" in signals:
            total_indicators += 1
            if signals["obv"]["signal"] == "buy":
                score += 1
            elif signals["obv"]["signal"] == "sell":
                score -= 1
                
        # VWAP contribution
        if "vwap" in signals:
            total_indicators += 1
            if signals["vwap"]["signal"] == "buy":
                score += 1
            elif signals["vwap"]["signal"] == "sell":
                score -= 1
                
        # Pivot Points contribution
        if "pivot" in signals:
            total_indicators += 1
            if signals["pivot"]["signal"] == "buy":
                score += 1
            elif signals["pivot"]["signal"] == "sell":
                score -= 1
                
        # Fibonacci contribution
        if "fibonacci" in signals:
            total_indicators += 1
            if signals["fibonacci"]["signal"] == "buy":
                score += 1
            elif signals["fibonacci"]["signal"] == "sell":
                score -= 1
            
        # Calculate signal strength based on consensus
        if total_indicators > 0:
            consensus_ratio = abs(score) / total_indicators
            if consensus_ratio >= 0.7:
                strength = "strong"
            elif consensus_ratio >= 0.4:
                strength = "moderate"
            else:
                strength = "weak"
        else:
            strength = "weak"
            
        return {
            "signal": "buy" if score > 0 else "sell" if score < 0 else "neutral",
            "strength": strength,
            "score": score,
            "total_indicators": total_indicators,
            "consensus_ratio": abs(score) / total_indicators if total_indicators > 0 else 0
        }
    
    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, np.ndarray]:
        """Calculate Stochastic Oscillator with improved NaN handling"""
        try:
            logger.info(f"Calculating Stochastic with k_period={k_period}, d_period={d_period}")
            
            # Validate input data
            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
                logger.error("Invalid input data for Stochastic calculation")
                zeros = np.zeros(max(len(df), k_period))
                return {"k": zeros, "d": zeros}
            
            # Calculate manually to have better control over NaN handling
            lowest_low = df['Low'].rolling(window=k_period, min_periods=1).min()
            highest_high = df['High'].rolling(window=k_period, min_periods=1).max()
            
            # Calculate %K
            k_percent = 100 * ((df['Close'] - lowest_low) / (highest_high - lowest_low))
            k_percent = k_percent.fillna(50)  # Fill NaN with neutral value
            
            # Calculate %D (smoothed %K)
            d_percent = k_percent.rolling(window=d_period, min_periods=1).mean()
            d_percent = d_percent.fillna(50)  # Fill NaN with neutral value
            
            # Ensure values are within valid range [0, 100]
            k_values = np.clip(k_percent.values, 0, 100)
            d_values = np.clip(d_percent.values, 0, 100)
            
            logger.info(f"Stochastic calculated successfully. K range: {k_values.min():.2f} - {k_values.max():.2f}")
            
            return {
                "k": k_values,
                "d": d_values
            }
        except Exception as e:
            logger.error(f"Error calculating Stochastic: {str(e)}")
            size = max(len(df), k_period) if not df.empty else k_period
            default_values = np.full(size, 50.0)  # Neutral stochastic values
            return {"k": default_values, "d": default_values}
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        """Calculate Average True Range with improved NaN handling"""
        try:
            logger.info(f"Calculating ATR with period {period}")
            
            # Validate input data
            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
                logger.error("Invalid input data for ATR calculation")
                return np.zeros(max(len(df), period))
            
            # Calculate True Range manually for better control
            high_low = df['High'] - df['Low']
            high_close_prev = abs(df['High'] - df['Close'].shift(1))
            low_close_prev = abs(df['Low'] - df['Close'].shift(1))
            
            # True Range is the maximum of the three
            true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            
            # Fill any NaN values (usually first row)
            true_range = true_range.fillna(high_low)
            
            # Calculate ATR as exponential moving average of True Range
            atr = true_range.ewm(span=period, adjust=False, min_periods=1).mean()
            
            # Fill any remaining NaN values
            atr = atr.fillna(true_range.mean())
            
            logger.info(f"ATR calculated successfully. Range: {atr.min():.4f} - {atr.max():.4f}")
            return atr.values
        except Exception as e:
            logger.error(f"Error calculating ATR: {str(e)}")
            # Return a reasonable default based on price range
            if not df.empty and all(col in df.columns for col in ['High', 'Low']):
                avg_range = (df['High'] - df['Low']).mean()
                return np.full(len(df), max(avg_range, 1.0))
            return np.ones(max(len(df), period))
    
    def calculate_obv(self, df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.Series, List[Dict[str, Any]]]:
        """
        Calculate On-Balance Volume with improved NaN handling
        params:
            signal_period: Period for signal line calculation
            ma_type: Moving average type (1 for SMA, 2 for EMA)
        """
        try:
            signal_period = params.get('signal_period', 20)
            ma_type = params.get('ma_type', 1)  # 1 for SMA, 2 for EMA
            
            logger.info(f"Calculating OBV with signal_period={signal_period}, ma_type={ma_type}")
            
            # Handle different column name formats
            close_col = 'Close' if 'Close' in df.columns else 'close'
            volume_col = 'Volume' if 'Volume' in df.columns else 'volume'
            
            # Validate required columns exist
            if close_col not in df.columns or volume_col not in df.columns:
                logger.error(f"Required columns not found for OBV: {close_col}, {volume_col}")
                empty_series = pd.Series(0, index=df.index)
                return empty_series, []
            
            # Calculate OBV manually for better control
            price_change = df[close_col].diff()
            obv = pd.Series(0.0, index=df.index)
            
            for i in range(1, len(df)):
                if pd.isna(price_change.iloc[i]) or pd.isna(df[volume_col].iloc[i]):
                    obv.iloc[i] = obv.iloc[i-1]  # Carry forward previous value
                elif price_change.iloc[i] > 0:
                    obv.iloc[i] = obv.iloc[i-1] + df[volume_col].iloc[i]
                elif price_change.iloc[i] < 0:
                    obv.iloc[i] = obv.iloc[i-1] - df[volume_col].iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i-1]  # No change
            
            # Calculate signal line based on ma_type with min_periods=1
            if ma_type == 2:  # EMA
                signal_line = obv.ewm(span=signal_period, adjust=False, min_periods=1).mean()
            else:  # Default to SMA
                signal_line = obv.rolling(window=signal_period, min_periods=1).mean()
            
            # Fill any NaN values
            signal_line = signal_line.fillna(method='ffill').fillna(0)
            
            # Generate signals with improved NaN handling
            signals = []
            for i in range(1, len(obv)):
                if pd.isna(obv.iloc[i]) or pd.isna(signal_line.iloc[i]) or pd.isna(obv.iloc[i-1]) or pd.isna(signal_line.iloc[i-1]):
                    continue
                
                curr_price = df[close_col].iloc[i] if not pd.isna(df[close_col].iloc[i]) else df[close_col].iloc[i-1]
                
                if obv.iloc[i] > signal_line.iloc[i] and obv.iloc[i-1] <= signal_line.iloc[i-1]:
                    signals.append({
                        'timestamp': df.index[i],
                        'type': 'buy',
                        'price': float(curr_price),
                        'strength': 1
                    })
                elif obv.iloc[i] < signal_line.iloc[i] and obv.iloc[i-1] >= signal_line.iloc[i-1]:
                    signals.append({
                        'timestamp': df.index[i],
                        'type': 'sell',
                        'price': float(curr_price),
                        'strength': 1
                    })
            
            logger.info(f"OBV calculated successfully. Generated {len(signals)} signals")
            return obv, signals
        except Exception as e:
            logger.error(f"Error calculating OBV: {str(e)}")
            empty_series = pd.Series(0, index=df.index)
            return empty_series, []
    
    def calculate_vwap(self, df: pd.DataFrame, params: Dict[str, Any]) -> Tuple[pd.Series, List[Dict[str, Any]]]:
        """
        Calculate Volume Weighted Average Price with improved NaN handling
        params:
            period: Rolling window period
            anchor: Reset frequency (1: daily, 2: weekly, 3: monthly)
        """
        try:
            period = params.get('period', 14)
            anchor = params.get('anchor', 1)
            
            logger.info(f"Calculating VWAP with period={period}, anchor={anchor}")
            
            # Handle different column name formats
            high_col = 'High' if 'High' in df.columns else 'high'
            low_col = 'Low' if 'Low' in df.columns else 'low'
            close_col = 'Close' if 'Close' in df.columns else 'close'
            volume_col = 'Volume' if 'Volume' in df.columns else 'volume'
            
            # Validate required columns exist
            required_cols = [high_col, low_col, close_col, volume_col]
            if not all(col in df.columns for col in required_cols):
                logger.error(f"Required columns not found for VWAP: {required_cols}")
                empty_series = pd.Series(df[close_col].mean() if close_col in df.columns else 100, index=df.index)
                return empty_series, []
            
            # Create a working copy to avoid modifying original dataframe
            df_work = df.copy()
            
            # Calculate typical price with NaN handling
            typical_price = (df_work[high_col] + df_work[low_col] + df_work[close_col]) / 3
            typical_price = typical_price.fillna(df_work[close_col])
            
            # Simplified VWAP calculation without complex grouping
            # Use rolling window approach instead
            pv = typical_price * df_work[volume_col].fillna(0)
            volume_filled = df_work[volume_col].fillna(0)
            
            # Calculate rolling VWAP
            rolling_pv = pv.rolling(window=period, min_periods=1).sum()
            rolling_volume = volume_filled.rolling(window=period, min_periods=1).sum()
            
            # Avoid division by zero
            rolling_volume = rolling_volume.replace(0, 1)
            vwap = rolling_pv / rolling_volume
            
            # Fill any remaining NaN values
            vwap = vwap.fillna(typical_price)
            
            # Generate signals with improved NaN handling
            signals = []
            for i in range(1, len(df_work)):
                if (pd.isna(vwap.iloc[i]) or pd.isna(vwap.iloc[i-1]) or 
                    pd.isna(df_work[close_col].iloc[i]) or pd.isna(df_work[close_col].iloc[i-1])):
                    continue
                
                curr_close = df_work[close_col].iloc[i]
                prev_close = df_work[close_col].iloc[i-1]
                curr_vwap = vwap.iloc[i]
                prev_vwap = vwap.iloc[i-1]
                
                if curr_close > curr_vwap and prev_close <= prev_vwap:
                    signals.append({
                        'timestamp': df_work.index[i],
                        'type': 'buy',
                        'price': float(curr_close),
                        'strength': 1
                    })
                elif curr_close < curr_vwap and prev_close >= prev_vwap:
                    signals.append({
                        'timestamp': df_work.index[i],
                        'type': 'sell',
                        'price': float(curr_close),
                        'strength': 1
                    })
            
            logger.info(f"VWAP calculated successfully. Generated {len(signals)} signals")
            return vwap, signals
        except Exception as e:
            logger.error(f"Error calculating VWAP: {str(e)}")
            # Return close price as fallback VWAP
            close_col = 'Close' if 'Close' in df.columns else 'close'
            if close_col in df.columns:
                fallback_vwap = df[close_col].fillna(method='ffill').fillna(df[close_col].mean())
            else:
                fallback_vwap = pd.Series(100, index=df.index)
            return fallback_vwap, []
    
    def _calculate_pivot_points(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate Pivot Points"""
        high = df['High'].iloc[-1]
        low = df['Low'].iloc[-1]
        close = df['Close'].iloc[-1]
        
        pivot = (high + low + close) / 3
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)
        
        return {
            "pivot": float(pivot),
            "resistance1": float(r1),
            "resistance2": float(r2),
            "resistance3": float(r3),
            "support1": float(s1),
            "support2": float(s2),
            "support3": float(s3)
        }
    
    def _calculate_fibonacci_retracement(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate Fibonacci Retracement levels"""
        # Get the highest high and lowest low over the last 50 periods
        period = min(50, len(df))
        high = df['High'].rolling(window=period).max().iloc[-1]
        low = df['Low'].rolling(window=period).min().iloc[-1]

        diff = high - low

        levels = {
            "0.0": float(high),
            "23.6": float(high - 0.236 * diff),
            "38.2": float(high - 0.382 * diff),
            "50.0": float(high - 0.5 * diff),
            "61.8": float(high - 0.618 * diff),
            "78.6": float(high - 0.786 * diff),
            "100.0": float(low)
        }

        return {
            "high": float(high),
            "low": float(low),
            "levels": levels
        }

    def _calculate_supertrend(self, df: pd.DataFrame, period: int = 10, multiplier: float = 3) -> Dict[str, np.ndarray]:
        """
        Calculate Supertrend Indicator
        Trend-following indicator with dynamic stop-loss bands
        """
        try:
            logger.info(f"Calculating Supertrend with period={period}, multiplier={multiplier}")

            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
                logger.error("Invalid input data for Supertrend calculation")
                zeros = np.zeros(len(df))
                return {'supertrend': zeros, 'direction': zeros, 'upper_band': zeros, 'lower_band': zeros}

            # Calculate ATR
            atr = self._calculate_atr(df, period)

            # Calculate basic bands
            hl2 = (df['High'] + df['Low']) / 2
            basic_ub = hl2 + (multiplier * atr)
            basic_lb = hl2 - (multiplier * atr)

            # Initialize final bands
            final_ub = pd.Series(index=df.index, dtype=float)
            final_lb = pd.Series(index=df.index, dtype=float)
            supertrend = pd.Series(index=df.index, dtype=float)
            direction = pd.Series(index=df.index, dtype=int)

            for i in range(len(df)):
                if i == 0:
                    final_ub.iloc[i] = basic_ub.iloc[i]
                    final_lb.iloc[i] = basic_lb.iloc[i]
                else:
                    # Upper band
                    if basic_ub.iloc[i] < final_ub.iloc[i-1] or df['Close'].iloc[i-1] > final_ub.iloc[i-1]:
                        final_ub.iloc[i] = basic_ub.iloc[i]
                    else:
                        final_ub.iloc[i] = final_ub.iloc[i-1]

                    # Lower band
                    if basic_lb.iloc[i] > final_lb.iloc[i-1] or df['Close'].iloc[i-1] < final_lb.iloc[i-1]:
                        final_lb.iloc[i] = basic_lb.iloc[i]
                    else:
                        final_lb.iloc[i] = final_lb.iloc[i-1]

                # Determine supertrend and direction
                if i == 0 or direction.iloc[i-1] == 1:
                    if df['Close'].iloc[i] <= final_ub.iloc[i]:
                        supertrend.iloc[i] = final_ub.iloc[i]
                        direction.iloc[i] = -1
                    else:
                        supertrend.iloc[i] = final_lb.iloc[i]
                        direction.iloc[i] = 1
                else:
                    if df['Close'].iloc[i] >= final_lb.iloc[i]:
                        supertrend.iloc[i] = final_lb.iloc[i]
                        direction.iloc[i] = 1
                    else:
                        supertrend.iloc[i] = final_ub.iloc[i]
                        direction.iloc[i] = -1

            logger.info(f"Supertrend calculated successfully")

            return {
                'supertrend': supertrend.values,
                'direction': direction.values,
                'upper_band': final_ub.values,
                'lower_band': final_lb.values
            }
        except Exception as e:
            logger.error(f"Error calculating Supertrend: {str(e)}")
            zeros = np.zeros(len(df))
            return {'supertrend': zeros, 'direction': zeros, 'upper_band': zeros, 'lower_band': zeros}

    def _calculate_ichimoku(self, df: pd.DataFrame, period1: int = 9, period2: int = 26, period3: int = 52) -> Dict[str, np.ndarray]:
        """
        Calculate Ichimoku Cloud
        Comprehensive indicator showing trend, support/resistance, and momentum
        """
        try:
            logger.info(f"Calculating Ichimoku Cloud with periods {period1}, {period2}, {period3}")

            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
                logger.error("Invalid input data for Ichimoku calculation")
                zeros = np.zeros(len(df))
                return {
                    'tenkan': zeros, 'kijun': zeros,
                    'senkou_a': zeros, 'senkou_b': zeros, 'chikou': zeros
                }

            # Tenkan-sen (Conversion Line) = (9-period high + 9-period low) / 2
            tenkan_high = df['High'].rolling(window=period1, min_periods=1).max()
            tenkan_low = df['Low'].rolling(window=period1, min_periods=1).min()
            tenkan = (tenkan_high + tenkan_low) / 2

            # Kijun-sen (Base Line) = (26-period high + 26-period low) / 2
            kijun_high = df['High'].rolling(window=period2, min_periods=1).max()
            kijun_low = df['Low'].rolling(window=period2, min_periods=1).min()
            kijun = (kijun_high + kijun_low) / 2

            # Senkou Span A = (Tenkan + Kijun) / 2, plotted 26 periods ahead
            senkou_a = ((tenkan + kijun) / 2).shift(period2)

            # Senkou Span B = (52-period high + 52-period low) / 2, plotted 26 periods ahead
            senkou_b_high = df['High'].rolling(window=period3, min_periods=1).max()
            senkou_b_low = df['Low'].rolling(window=period3, min_periods=1).min()
            senkou_b = ((senkou_b_high + senkou_b_low) / 2).shift(period2)

            # Chikou Span = Close plotted 26 periods in the past
            chikou = df['Close'].shift(-period2)

            # Fill NaN values
            tenkan = tenkan.fillna(method='bfill').fillna(df['Close'])
            kijun = kijun.fillna(method='bfill').fillna(df['Close'])
            senkou_a = senkou_a.fillna(method='bfill').fillna(df['Close'])
            senkou_b = senkou_b.fillna(method='bfill').fillna(df['Close'])
            chikou = chikou.fillna(method='ffill').fillna(df['Close'])

            logger.info(f"Ichimoku Cloud calculated successfully")

            return {
                'tenkan': tenkan.values,
                'kijun': kijun.values,
                'senkou_a': senkou_a.values,
                'senkou_b': senkou_b.values,
                'chikou': chikou.values
            }
        except Exception as e:
            logger.error(f"Error calculating Ichimoku: {str(e)}")
            close_values = df['Close'].values if not df.empty else np.zeros(1)
            return {
                'tenkan': close_values, 'kijun': close_values,
                'senkou_a': close_values, 'senkou_b': close_values, 'chikou': close_values
            }

    def _calculate_cci(self, df: pd.DataFrame, period: int = 20) -> np.ndarray:
        """
        Calculate Commodity Channel Index (CCI)
        Momentum indicator for identifying trend changes and breakouts
        """
        try:
            logger.info(f"Calculating CCI with period={period}")

            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
                logger.error("Invalid input data for CCI calculation")
                return np.zeros(len(df))

            # Calculate Typical Price
            typical_price = (df['High'] + df['Low'] + df['Close']) / 3

            # Calculate SMA of Typical Price
            sma_tp = typical_price.rolling(window=period, min_periods=1).mean()

            # Calculate Mean Deviation
            mean_dev = typical_price.rolling(window=period, min_periods=1).apply(
                lambda x: np.abs(x - x.mean()).mean(), raw=True
            )

            # Prevent division by zero
            mean_dev = mean_dev.replace(0, 1e-10)

            # Calculate CCI
            cci = (typical_price - sma_tp) / (0.015 * mean_dev)

            # Fill NaN values with 0
            cci = cci.fillna(0)

            logger.info(f"CCI calculated successfully. Range: {cci.min():.2f} - {cci.max():.2f}")

            return cci.values
        except Exception as e:
            logger.error(f"Error calculating CCI: {str(e)}")
            return np.zeros(len(df))

    def _calculate_mfi(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        """
        Calculate Money Flow Index (MFI)
        Volume-weighted RSI, identifies overbought/oversold with volume confirmation
        """
        try:
            logger.info(f"Calculating MFI with period={period}")

            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close', 'Volume']):
                logger.error("Invalid input data for MFI calculation")
                return np.full(len(df), 50.0)  # Neutral value

            # Calculate Typical Price
            typical_price = (df['High'] + df['Low'] + df['Close']) / 3

            # Calculate Raw Money Flow
            raw_money_flow = typical_price * df['Volume']

            # Identify positive and negative money flow
            positive_mf = pd.Series(0.0, index=df.index)
            negative_mf = pd.Series(0.0, index=df.index)

            for i in range(1, len(df)):
                if typical_price.iloc[i] > typical_price.iloc[i-1]:
                    positive_mf.iloc[i] = raw_money_flow.iloc[i]
                elif typical_price.iloc[i] < typical_price.iloc[i-1]:
                    negative_mf.iloc[i] = raw_money_flow.iloc[i]

            # Calculate positive and negative money flow sums
            positive_mf_sum = positive_mf.rolling(window=period, min_periods=1).sum()
            negative_mf_sum = negative_mf.rolling(window=period, min_periods=1).sum()

            # Prevent division by zero
            negative_mf_sum = negative_mf_sum.replace(0, 1e-10)

            # Calculate Money Flow Ratio
            mfr = positive_mf_sum / negative_mf_sum

            # Calculate MFI
            mfi = 100 - (100 / (1 + mfr))

            # Fill NaN values with neutral value (50)
            mfi = mfi.fillna(50)

            # Clip to valid range [0, 100]
            mfi = np.clip(mfi.values, 0, 100)

            logger.info(f"MFI calculated successfully. Range: {mfi.min():.2f} - {mfi.max():.2f}")

            return mfi
        except Exception as e:
            logger.error(f"Error calculating MFI: {str(e)}")
            return np.full(len(df), 50.0)

    def _calculate_keltner_channels(self, df: pd.DataFrame, ema_period: int = 20, atr_period: int = 14, atr_mult: float = 2) -> Dict[str, np.ndarray]:
        """
        Calculate Keltner Channels
        Volatility-based channels using EMA and ATR
        """
        try:
            logger.info(f"Calculating Keltner Channels with ema_period={ema_period}, atr_period={atr_period}, atr_mult={atr_mult}")

            if df.empty or 'Close' not in df.columns:
                logger.error("Invalid input data for Keltner Channels calculation")
                zeros = np.zeros(len(df))
                return {'upper': zeros, 'middle': zeros, 'lower': zeros}

            # Calculate middle line (EMA)
            ema = self._calculate_ema(df, ema_period)

            # Calculate ATR
            atr = self._calculate_atr(df, atr_period)

            # Calculate upper and lower channels
            upper = ema + (atr * atr_mult)
            lower = ema - (atr * atr_mult)

            logger.info(f"Keltner Channels calculated successfully")

            return {
                'upper': upper,
                'middle': ema,
                'lower': lower
            }
        except Exception as e:
            logger.error(f"Error calculating Keltner Channels: {str(e)}")
            close_mean = df['Close'].mean() if not df.empty else 100.0
            size = len(df) if not df.empty else 1
            return {
                'upper': np.full(size, close_mean),
                'middle': np.full(size, close_mean),
                'lower': np.full(size, close_mean)
            }

    def _calculate_williams_r(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        """
        Calculate Williams %R
        Momentum indicator showing overbought/oversold levels
        """
        try:
            logger.info(f"Calculating Williams %R with period={period}")

            if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
                logger.error("Invalid input data for Williams %R calculation")
                return np.full(len(df), -50.0)  # Neutral value

            # Calculate highest high and lowest low over period
            highest_high = df['High'].rolling(window=period, min_periods=1).max()
            lowest_low = df['Low'].rolling(window=period, min_periods=1).min()

            # Prevent division by zero
            range_hl = highest_high - lowest_low
            range_hl = range_hl.replace(0, 1e-10)

            # Calculate Williams %R
            williams_r = -100 * ((highest_high - df['Close']) / range_hl)

            # Fill NaN values with neutral value (-50)
            williams_r = williams_r.fillna(-50)

            # Clip to valid range [-100, 0]
            williams_r = np.clip(williams_r.values, -100, 0)

            logger.info(f"Williams %R calculated successfully. Range: {williams_r.min():.2f} - {williams_r.max():.2f}")

            return williams_r
        except Exception as e:
            logger.error(f"Error calculating Williams %R: {str(e)}")
            return np.full(len(df), -50.0)

    def _get_data_with_indicators(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        timeframe: str,
        indicators: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Get data with technical indicators"""
        try:
            logger.info(f"Getting data with indicators for {ticker}")
            logger.info(f"Timeframe: {timeframe}")
            logger.info(f"Indicators requested: {[ind['type'] for ind in indicators]}")
            
            # Get OHLC data
            df = get_ohlc_data(ticker, start_date, end_date, timeframe)
            if df.empty:
                logger.error(f"No data available for {ticker}")
                return df

            logger.info(f"Initial data shape: {df.shape}")
            logger.info(f"Initial columns: {df.columns.tolist()}")
            logger.info(f"Sample data:\n{df.head()}")

            # Calculate indicators
            for indicator in indicators:
                try:
                    indicator_type = indicator['type'].lower()
                    params = indicator.get('parameters', {})
                    logger.info(f"Calculating {indicator_type} with params: {params}")

                    if indicator_type == 'rsi':
                        period = params.get('period', 14)
                        rsi_values = self._calculate_rsi(df, period)
                        df[f'RSI_{period}'] = rsi_values
                        logger.info(f"RSI_{period} calculation completed. Sample values:\n{df[f'RSI_{period}'].head()}")

                    elif indicator_type == 'sma':
                        period = params.get('period', 20)
                        sma_values = self._calculate_sma(df, period)
                        df[f'SMA_{period}'] = sma_values
                        logger.info(f"SMA_{period} calculation completed. Sample values:\n{df[f'SMA_{period}'].head()}")

                    elif indicator_type == 'ema':
                        period = params.get('period', 20)
                        ema_values = self._calculate_ema(df, period)
                        df[f'EMA_{period}'] = ema_values
                        logger.info(f"EMA_{period} calculation completed. Sample values:\n{df[f'EMA_{period}'].head()}")

                    elif indicator_type == 'macd':
                        fast_period = params.get('fastperiod', 12)
                        slow_period = params.get('slowperiod', 26)
                        signal_period = params.get('signalperiod', 9)
                        macd_data = self._calculate_macd(df, fast_period, slow_period, signal_period)
                        df['MACD'] = macd_data['macd']
                        df['MACD_Signal'] = macd_data['signal']
                        df['MACD_Hist'] = macd_data['histogram']
                        logger.info("MACD calculation completed. Sample values:\n" + \
                                  f"MACD: {df['MACD'].head()}\n" + \
                                  f"Signal: {df['MACD_Signal'].head()}\n" + \
                                  f"Histogram: {df['MACD_Hist'].head()}")

                    elif indicator_type == 'bollinger':
                        period = params.get('period', 20)
                        bb_data = self._calculate_bollinger_bands(df, period)
                        df['BB_Upper'] = bb_data['upper']
                        df['BB_Middle'] = bb_data['middle']
                        df['BB_Lower'] = bb_data['lower']
                        logger.info("Bollinger Bands calculation completed. Sample values:\n" + \
                                  f"Upper: {df['BB_Upper'].head()}\n" + \
                                  f"Middle: {df['BB_Middle'].head()}\n" + \
                                  f"Lower: {df['BB_Lower'].head()}")

                    elif indicator_type == 'supertrend':
                        period = params.get('period', 10)
                        multiplier = params.get('multiplier', 3)
                        st_data = self._calculate_supertrend(df, period, multiplier)
                        df['Supertrend'] = st_data['supertrend']
                        df['ST_Direction'] = st_data['direction']
                        df['ST_Upper'] = st_data['upper_band']
                        df['ST_Lower'] = st_data['lower_band']
                        logger.info("Supertrend calculation completed. Sample values:\n" + \
                                  f"Supertrend: {df['Supertrend'].head()}\n" + \
                                  f"Direction: {df['ST_Direction'].head()}")

                    elif indicator_type == 'ichimoku':
                        period1 = params.get('period1', 9)
                        period2 = params.get('period2', 26)
                        period3 = params.get('period3', 52)
                        ich_data = self._calculate_ichimoku(df, period1, period2, period3)
                        df['Ichimoku_Tenkan'] = ich_data['tenkan']
                        df['Ichimoku_Kijun'] = ich_data['kijun']
                        df['Ichimoku_SenkouA'] = ich_data['senkou_a']
                        df['Ichimoku_SenkouB'] = ich_data['senkou_b']
                        df['Ichimoku_Chikou'] = ich_data['chikou']
                        logger.info("Ichimoku Cloud calculation completed. Sample values:\n" + \
                                  f"Tenkan: {df['Ichimoku_Tenkan'].head()}\n" + \
                                  f"Kijun: {df['Ichimoku_Kijun'].head()}")

                    elif indicator_type == 'cci':
                        period = params.get('period', 20)
                        cci_values = self._calculate_cci(df, period)
                        df[f'CCI_{period}'] = cci_values
                        logger.info(f"CCI_{period} calculation completed. Sample values:\n{df[f'CCI_{period}'].head()}")

                    elif indicator_type == 'mfi':
                        period = params.get('period', 14)
                        mfi_values = self._calculate_mfi(df, period)
                        df[f'MFI_{period}'] = mfi_values
                        logger.info(f"MFI_{period} calculation completed. Sample values:\n{df[f'MFI_{period}'].head()}")

                    elif indicator_type == 'keltner':
                        ema_period = params.get('ema_period', 20)
                        atr_period = params.get('atr_period', 14)
                        atr_mult = params.get('atr_mult', 2)
                        kc_data = self._calculate_keltner_channels(df, ema_period, atr_period, atr_mult)
                        df['KC_Upper'] = kc_data['upper']
                        df['KC_Middle'] = kc_data['middle']
                        df['KC_Lower'] = kc_data['lower']
                        logger.info("Keltner Channels calculation completed. Sample values:\n" + \
                                  f"Upper: {df['KC_Upper'].head()}\n" + \
                                  f"Middle: {df['KC_Middle'].head()}\n" + \
                                  f"Lower: {df['KC_Lower'].head()}")

                    elif indicator_type == 'williams_r' or indicator_type == 'williamsr':
                        period = params.get('period', 14)
                        wr_values = self._calculate_williams_r(df, period)
                        df[f'Williams_R_{period}'] = wr_values
                        logger.info(f"Williams_R_{period} calculation completed. Sample values:\n{df[f'Williams_R_{period}'].head()}")

                    elif indicator_type == 'atr':
                        period = params.get('period', 14)
                        atr_values = self._calculate_atr(df, period)
                        df[f'ATR_{period}'] = atr_values
                        logger.info(f"ATR_{period} calculation completed. Sample values:\n{df[f'ATR_{period}'].head()}")

                    elif indicator_type == 'stochastic':
                        k_period = params.get('k_period', 14)
                        d_period = params.get('d_period', 3)
                        stoch_data = self._calculate_stochastic(df, k_period, d_period)
                        df['Stoch_K'] = stoch_data['k']
                        df['Stoch_D'] = stoch_data['d']
                        logger.info("Stochastic calculation completed. Sample values:\n" + \
                                  f"K: {df['Stoch_K'].head()}\n" + \
                                  f"D: {df['Stoch_D'].head()}")

                except Exception as e:
                    logger.error(f"Error calculating {indicator_type}: {str(e)}")
                    logger.error(f"DataFrame info at error:\n{df.info()}")
                    continue

            logger.info(f"Final data shape: {df.shape}")
            logger.info(f"Final columns: {df.columns.tolist()}")
            logger.info("Sample of final data with indicators:\n" + \
                      f"{df.head().to_string()}")

            return df

        except Exception as e:
            logger.error(f"Error in _get_data_with_indicators: {str(e)}")
            logger.error(f"Full traceback:", exc_info=True)
            return pd.DataFrame() 