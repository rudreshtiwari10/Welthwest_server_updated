import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
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