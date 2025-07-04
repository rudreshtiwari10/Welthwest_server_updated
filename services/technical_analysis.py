import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from ta import momentum, trend, volatility, volume
from services.stock_service import get_ohlc_data, format_indian_ticker
from services.cache_service import get_cached_data, set_cached_data
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TechnicalAnalysis:
    def __init__(self):
        self.default_period = "1y"
        self.default_interval = "1d"
        
    def calculate_indicators(self, ticker: str, indicators: List[str], params: Dict = None) -> Dict[str, Any]:
        """Calculate technical indicators for a given stock"""
        # Get historical data
        df = get_ohlc_data(ticker, self.default_period, self.default_interval)
        if df.empty:
            return {"error": "No data available for the ticker"}
            
        results = {}
        
        # Handle both params and parameters
        params = params.get("parameters", params) if params else {}
        
        for indicator in indicators:
            try:
                if indicator.lower() == "rsi":
                    period = params.get("rsi_period", 14) if params else 14
                    rsi_values = self._calculate_rsi(df, period)
                    results["rsi"] = {
                        "values": [float(x) for x in rsi_values[-10:]],  # Last 10 values
                        "current": float(rsi_values[-1]),
                        "signal": "buy" if rsi_values[-1] > 30 else "sell" if rsi_values[-1] < 70 else "neutral"
                    }
                elif indicator.lower() == "macd":
                    fastperiod = params.get("macd_fastperiod", 12) if params else 12
                    slowperiod = params.get("macd_slowperiod", 26) if params else 26
                    signalperiod = params.get("macd_signalperiod", 9) if params else 9
                    macd_data = self._calculate_macd(df, fastperiod, slowperiod, signalperiod)
                    results["macd"] = {
                        "macd": [float(x) for x in macd_data["macd"][-10:]],
                        "signal": [float(x) for x in macd_data["signal"][-10:]],
                        "histogram": [float(x) for x in macd_data["histogram"][-10:]],
                        "current": {
                            "macd": float(macd_data["macd"][-1]),
                            "signal": float(macd_data["signal"][-1]),
                            "histogram": float(macd_data["histogram"][-1])
                        },
                        "signal": "buy" if macd_data["macd"][-1] > macd_data["signal"][-1] else "sell"
                    }
                elif indicator.lower() == "bollinger":
                    period = params.get("bb_period", 20) if params else 20
                    bb_data = self._calculate_bollinger_bands(df, period)
                    current_price = float(df['Close'].iloc[-1])
                    results["bollinger"] = {
                        "upper": [float(x) for x in bb_data["upper"][-10:]],
                        "middle": [float(x) for x in bb_data["middle"][-10:]],
                        "lower": [float(x) for x in bb_data["lower"][-10:]],
                        "current": {
                            "upper": float(bb_data["upper"][-1]),
                            "middle": float(bb_data["middle"][-1]),
                            "lower": float(bb_data["lower"][-1]),
                            "price": current_price
                        },
                        "signal": "buy" if current_price <= bb_data["lower"][-1] else "sell" if current_price >= bb_data["upper"][-1] else "neutral"
                    }
                elif indicator.lower() == "sma":
                    period = params.get("sma_period", 20) if params else 20
                    sma_values = self._calculate_sma(df, period)
                    current_price = float(df['Close'].iloc[-1])
                    results["sma"] = {
                        "values": [float(x) for x in sma_values[-10:]],
                        "current": float(sma_values[-1]),
                        "signal": "buy" if current_price > sma_values[-1] else "sell"
                    }
                elif indicator.lower() == "ema":
                    period = params.get("ema_period", 20) if params else 20
                    ema_values = self._calculate_ema(df, period)
                    current_price = float(df['Close'].iloc[-1])
                    results["ema"] = {
                        "values": [float(x) for x in ema_values[-10:]],
                        "current": float(ema_values[-1]),
                        "signal": "buy" if current_price > ema_values[-1] else "sell"
                    }
                elif indicator.lower() == "stochastic":
                    k_period = params.get("stoch_k_period", 14) if params else 14
                    d_period = params.get("stoch_d_period", 3) if params else 3
                    stoch_data = self._calculate_stochastic(df, k_period, d_period)
                    results["stochastic"] = {
                        "k": [float(x) for x in stoch_data["k"][-10:]],
                        "d": [float(x) for x in stoch_data["d"][-10:]],
                        "current": {
                            "k": float(stoch_data["k"][-1]),
                            "d": float(stoch_data["d"][-1])
                        },
                        "signal": "buy" if stoch_data["k"][-1] > stoch_data["d"][-1] and stoch_data["k"][-1] < 20 else "sell" if stoch_data["k"][-1] < stoch_data["d"][-1] and stoch_data["k"][-1] > 80 else "neutral"
                    }
                elif indicator.lower() == "atr":
                    period = params.get("atr_period", 14) if params else 14
                    atr_values = self._calculate_atr(df, period)
                    results["atr"] = {
                        "values": [float(x) for x in atr_values[-10:]],
                        "current": float(atr_values[-1]),
                        "signal": "neutral"  # ATR is not directional
                    }
                elif indicator.lower() == "obv":
                    obv_values = self._calculate_obv(df)
                    results["obv"] = {
                        "values": [float(x) for x in obv_values[-10:]],
                        "current": float(obv_values[-1]),
                        "signal": "buy" if obv_values[-1] > obv_values[-2] else "sell"
                    }
                elif indicator.lower() == "vwap":
                    vwap_values = self._calculate_vwap(df)
                    current_price = float(df['Close'].iloc[-1])
                    results["vwap"] = {
                        "values": [float(x) for x in vwap_values[-10:]],
                        "current": float(vwap_values[-1]),
                        "signal": "buy" if current_price > vwap_values[-1] else "sell"
                    }
                elif indicator.lower() == "pivot":
                    pivot_data = self._calculate_pivot_points(df)
                    current_price = float(df['Close'].iloc[-1])
                    # Check if price is bouncing from support or rejecting from resistance
                    signal = "neutral"
                    if current_price <= pivot_data["support1"] or current_price <= pivot_data["support2"]:
                        signal = "buy"
                    elif current_price >= pivot_data["resistance1"] or current_price >= pivot_data["resistance2"]:
                        signal = "sell"
                    results["pivot"] = {
                        **pivot_data,
                        "current_price": current_price,
                        "signal": signal
                    }
                elif indicator.lower() == "fibonacci":
                    fib_data = self._calculate_fibonacci_retracement(df)
                    current_price = float(df['Close'].iloc[-1])
                    # Check if price is bouncing from retracement levels
                    signal = "neutral"
                    for level, value in fib_data["levels"].items():
                        if abs(current_price - value) / value < 0.01:  # Within 1% of fib level
                            signal = "buy" if current_price > value else "sell"
                            break
                    results["fibonacci"] = {
                        **fib_data,
                        "current_price": current_price,
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
                df = get_ohlc_data(ticker, "1mo", "1d")  # Use shorter period for screening
                if not df.empty:
                    matches_criteria = self._evaluate_screening_criteria(df, criteria)
                    if matches_criteria:
                        results[ticker] = matches_criteria
            except Exception as e:
                continue
                
        return results
    
    def get_support_resistance(self, ticker: str) -> Dict[str, Any]:
        """Calculate support and resistance levels"""
        df = get_ohlc_data(ticker, "1y", "1d")
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
        df = get_ohlc_data(ticker, "6mo", "1d")
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
        df = get_ohlc_data(ticker, "3mo", "1d")
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
        obv = self._calculate_obv(df)
        signals["obv"] = {
            "value": float(obv[-1]),
            "signal": "buy" if obv[-1] > obv[-2] else "sell",
            "description": "Volume rising with price" if obv[-1] > obv[-2] else "Volume falling with price"
        }
        
        # VWAP Signal
        vwap = self._calculate_vwap(df)
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
        """Calculate RSI indicator"""
        rsi = momentum.RSIIndicator(df['Close'], window=period)
        return rsi.rsi().fillna(0).values
    
    def _calculate_macd(self, df: pd.DataFrame, fastperiod: int = 12, slowperiod: int = 26, signalperiod: int = 9) -> Dict[str, np.ndarray]:
        """Calculate MACD indicator"""
        macd = trend.MACD(
            df['Close'], 
            window_slow=slowperiod,
            window_fast=fastperiod,
            window_sign=signalperiod
        )
        return {
            "macd": macd.macd().fillna(0).values,
            "signal": macd.macd_signal().fillna(0).values,
            "histogram": macd.macd_diff().fillna(0).values
        }
    
    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20) -> Dict[str, np.ndarray]:
        """Calculate Bollinger Bands"""
        bb = volatility.BollingerBands(df['Close'], window=period)
        return {
            "upper": bb.bollinger_hband().fillna(0).values,
            "middle": bb.bollinger_mavg().fillna(0).values,
            "lower": bb.bollinger_lband().fillna(0).values
        }
    
    def _calculate_sma(self, df: pd.DataFrame, period: int = 20) -> np.ndarray:
        """Calculate Simple Moving Average"""
        return trend.SMAIndicator(df['Close'], window=period).sma_indicator().fillna(0).values
    
    def _calculate_ema(self, df: pd.DataFrame, period: int = 20) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        return trend.EMAIndicator(df['Close'], window=period).ema_indicator().fillna(0).values
    
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
        """Calculate Stochastic Oscillator"""
        stoch = momentum.StochasticOscillator(df['High'], df['Low'], df['Close'], window=k_period, smooth_window=d_period)
        return {
            "k": stoch.stoch().fillna(0).values,
            "d": stoch.stoch_signal().fillna(0).values
        }
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        """Calculate Average True Range"""
        atr = volatility.AverageTrueRange(df['High'], df['Low'], df['Close'], window=period)
        return atr.average_true_range().fillna(0).values
    
    def _calculate_obv(self, df: pd.DataFrame) -> np.ndarray:
        """Calculate On-Balance Volume"""
        obv = volume.OnBalanceVolumeIndicator(df['Close'], df['Volume'])
        return obv.on_balance_volume().fillna(0).values
    
    def _calculate_vwap(self, df: pd.DataFrame) -> np.ndarray:
        """Calculate Volume Weighted Average Price"""
        # Calculate typical price
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        
        # Calculate volume weighted price
        vwap_values = []
        cumulative_volume = 0
        cumulative_price_volume = 0
        
        for i in range(len(df)):
            cumulative_volume += df['Volume'].iloc[i]
            cumulative_price_volume += typical_price.iloc[i] * df['Volume'].iloc[i]
            
            if cumulative_volume > 0:
                vwap_values.append(cumulative_price_volume / cumulative_volume)
            else:
                vwap_values.append(0)
                
        return np.array(vwap_values)
    
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
    
    def _get_data_with_indicators(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        timeframe: str,
        indicators: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Get historical data and calculate indicators"""
        # Try to get cached data
        cache_key = f"data_{ticker}_{start_date}_{end_date}_{timeframe}"
        cached_data = get_cached_data(cache_key)
        if cached_data is not None:
            return pd.DataFrame(cached_data)

        # Get fresh data using get_ohlc_data instead of get_historical_data
        df = get_ohlc_data(ticker, start_date=start_date, end_date=end_date, interval=timeframe)
        if df.empty:
            return df

        # Calculate indicators
        for indicator in indicators:
            try:
                ind_type = indicator["type"].lower()
                # Handle both params and parameters
                params = indicator.get("parameters", indicator.get("params", {}))
                
                if ind_type == "rsi":
                    df[f"RSI_{params.get('period', 14)}"] = self._calculate_rsi(df, params.get("period", 14))
                elif ind_type == "macd":
                    macd_data = self._calculate_macd(
                        df,
                        params.get("fastperiod", 12),
                        params.get("slowperiod", 26),
                        params.get("signalperiod", 9)
                    )
                    df["MACD"] = macd_data["macd"]
                    df["MACD_Signal"] = macd_data["signal"]
                    df["MACD_Hist"] = macd_data["histogram"]
                elif ind_type == "bollinger":
                    bb_data = self._calculate_bollinger_bands(df, params.get("period", 20))
                    df["BB_Upper"] = bb_data["upper"]
                    df["BB_Middle"] = bb_data["middle"]
                    df["BB_Lower"] = bb_data["lower"]
                elif ind_type == "sma":
                    df[f"SMA_{params.get('period', 20)}"] = self._calculate_sma(df, params.get("period", 20))
                elif ind_type == "ema":
                    df[f"EMA_{params.get('period', 20)}"] = self._calculate_ema(df, params.get("period", 20))
                elif ind_type == "stochastic":
                    stoch_data = self._calculate_stochastic(
                        df,
                        params.get("k_period", 14),
                        params.get("d_period", 3)
                    )
                    df["STOCH_K"] = stoch_data["k"]
                    df["STOCH_D"] = stoch_data["d"]
            except Exception as e:
                logger.error(f"Error calculating indicator {ind_type}: {str(e)}")
                continue

        # Cache the data
        set_cached_data(cache_key, df.to_dict(), self.cache_ttl)
        return df 