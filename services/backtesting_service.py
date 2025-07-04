import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from .technical_analysis import TechnicalAnalysis
from services.cache_service import get_cached_data, set_cached_data
from services.stock_service import get_ohlc_data, format_indian_ticker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BacktestingService:
    def __init__(self):
        self.ta = TechnicalAnalysis()
        self.cache_ttl = 3600  # 1 hour cache TTL

    def run_backtest(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        indicators: List[Dict[str, Any]],
        position_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timeframe: str = "1d"
    ) -> Dict[str, Any]:
        """
        Run a backtest with the specified parameters
        
        Args:
            ticker: Stock/index symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            indicators: List of indicators with parameters and conditions
            position_size: Position size per trade (percentage of capital)
            stop_loss: Optional stop loss percentage
            take_profit: Optional take profit percentage
            timeframe: Data timeframe (1d, 1h, etc.)
            
        Returns:
            Dict containing backtest results and performance metrics
        """
        try:
            # Input validation
            self._validate_inputs(
                ticker, start_date, end_date, indicators,
                position_size, stop_loss, take_profit, timeframe
            )
            
            # Try to get cached results
            cache_key = f"backtest_{ticker}_{start_date}_{end_date}_{hash(str(indicators))}_{timeframe}"
            cached_result = get_cached_data(cache_key)
            if cached_result:
                logger.info(f"Using cached backtest results for {ticker}")
                return cached_result

            # Get historical data
            df = self._get_data_with_indicators(ticker, start_date, end_date, timeframe, indicators)
            if df.empty:
                raise ValueError(f"No data available for {ticker} in the specified date range")

            # Generate signals
            signals = self._generate_signals(df, indicators)
            
            # Execute trades
            trades, metrics = self._execute_trades(
                df, signals, position_size, stop_loss, take_profit
            )
            
            # Calculate performance metrics
            performance = self._calculate_performance_metrics(df, trades, metrics)
            
            # Prepare and cache results
            results = {
                "trades": trades,
                "metrics": metrics,
                "performance": performance,
                "summary": self._generate_summary(performance)
            }
            
            set_cached_data(cache_key, results, self.cache_ttl)
            return results

        except ValueError as e:
            logger.error(f"Validation error in backtest: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error in backtest execution: {str(e)}")
            raise

    def _validate_inputs(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        indicators: List[Dict[str, Any]],
        position_size: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        timeframe: str
    ) -> None:
        """Validate all input parameters"""
        # Validate dates
        try:
            start = pd.Timestamp(start_date)
            end = pd.Timestamp(end_date)
            if start >= end:
                raise ValueError("Start date must be before end date")
            if end > pd.Timestamp.now():
                raise ValueError("End date cannot be in the future")
        except ValueError as e:
            raise ValueError(f"Invalid date format: {str(e)}")

        # Validate position size
        if not 0 < position_size <= 100:
            raise ValueError("Position size must be between 0 and 100")

        # Validate stop loss and take profit
        if stop_loss is not None and not 0 < stop_loss < 100:
            raise ValueError("Stop loss must be between 0 and 100")
        if take_profit is not None and not 0 < take_profit < 100:
            raise ValueError("Take profit must be between 0 and 100")

        # Validate timeframe
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]
        if timeframe not in valid_timeframes:
            raise ValueError(f"Invalid timeframe. Must be one of {valid_timeframes}")

        # Validate indicators
        if not indicators:
            raise ValueError("At least one indicator must be specified")
        for indicator in indicators:
            if "type" not in indicator:
                raise ValueError("Each indicator must have a type")
            if "parameters" not in indicator and "params" not in indicator:
                raise ValueError(f"Parameters must be specified for indicator {indicator['type']}")
            
            # Get parameters
            params = indicator.get("parameters", indicator.get("params", {}))
            
            # Validate parameters based on indicator type
            if indicator["type"].lower() == "rsi":
                period = params.get("period")
                if period is not None and not (1 < period < 100):
                    raise ValueError(f"RSI period must be between 1 and 100")
            elif indicator["type"].lower() == "macd":
                fastperiod = params.get("fastperiod")
                slowperiod = params.get("slowperiod")
                signalperiod = params.get("signalperiod")
                if fastperiod is not None and not (1 < fastperiod < 100):
                    raise ValueError(f"MACD fast period must be between 1 and 100")
                if slowperiod is not None and not (1 < slowperiod < 100):
                    raise ValueError(f"MACD slow period must be between 1 and 100")
                if signalperiod is not None and not (1 < signalperiod < 100):
                    raise ValueError(f"MACD signal period must be between 1 and 100")
            elif indicator["type"].lower() == "bollinger":
                period = params.get("period")
                if period is not None and not (1 < period < 100):
                    raise ValueError(f"Bollinger period must be between 1 and 100")

    def _get_data_with_indicators(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        timeframe: str,
        indicators: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Get historical data and calculate indicators"""
        try:
            # Try to get cached data
            cache_key = f"data_{ticker}_{start_date}_{end_date}_{timeframe}"
            cached_data = get_cached_data(cache_key)
            if cached_data is not None:
                return pd.DataFrame(cached_data)

            # Format ticker for Indian market
            formatted_ticker = format_indian_ticker(ticker)
            logger.info(f"Fetching data for {formatted_ticker} from {start_date} to {end_date}")

            # Get fresh data using get_ohlc_data
            df = get_ohlc_data(formatted_ticker, start_date=start_date, end_date=end_date, interval=timeframe)
            if df.empty:
                if ticker.upper() in ["NIFTY", "BANKNIFTY", "SENSEX"]:
                    logger.error(f"No data available for index {ticker}. Make sure the date range is valid and not too far in the past.")
                    raise ValueError(f"No data available for index {ticker}. For indices, historical data is typically limited to recent years.")
                else:
                    logger.warning(f"No data available for {ticker} from {start_date} to {end_date}")
                return df

            # Calculate indicators
            for indicator in indicators:
                try:
                    ind_type = indicator["type"].lower()
                    # Handle both params and parameters
                    params = indicator.get("parameters", indicator.get("params", {}))
                    
                    if ind_type == "rsi":
                        df[f"RSI_{params.get('period', 14)}"] = self.ta._calculate_rsi(df, params.get("period", 14))
                    elif ind_type == "macd":
                        macd_data = self.ta._calculate_macd(
                            df,
                            params.get("fastperiod", 12),
                            params.get("slowperiod", 26),
                            params.get("signalperiod", 9)
                        )
                        df["MACD"] = macd_data["macd"]
                        df["MACD_Signal"] = macd_data["signal"]
                        df["MACD_Hist"] = macd_data["histogram"]
                    elif ind_type == "bollinger":
                        bb_data = self.ta._calculate_bollinger_bands(
                            df,
                            params.get("period", 20)
                        )
                        df["BB_Upper"] = bb_data["upper"]
                        df["BB_Middle"] = bb_data["middle"]
                        df["BB_Lower"] = bb_data["lower"]
                    elif ind_type == "sma":
                        df[f"SMA_{params.get('period', 20)}"] = self.ta._calculate_sma(df, params.get("period", 20))
                    elif ind_type == "ema":
                        df[f"EMA_{params.get('period', 20)}"] = self.ta._calculate_ema(df, params.get("period", 20))
                except Exception as e:
                    logger.error(f"Error calculating indicator {ind_type}: {str(e)}")
                    raise ValueError(f"Failed to calculate {ind_type} indicator: {str(e)}")

            # Cache the data
            set_cached_data(cache_key, df.to_dict(), self.cache_ttl)
            return df

        except Exception as e:
            logger.error(f"Error getting data with indicators: {str(e)}")
            raise

    def _generate_signals(
        self,
        df: pd.DataFrame,
        indicators: List[Dict[str, Any]]
    ) -> pd.Series:
        """Generate trading signals based on indicators"""
        signals = pd.Series(index=df.index, data=0)  # 0: no signal, 1: buy, -1: sell
        
        for indicator in indicators:
            try:
                ind_type = indicator["type"].lower()
                params = indicator.get("parameters", indicator.get("params", {}))
                conditions = indicator.get("conditions", {})
                
                if ind_type == "rsi":
                    period = params.get("period", 14)
                    rsi = df[f"RSI_{period}"]
                    
                    # RSI conditions - use boolean indexing correctly
                    oversold = conditions.get("oversold", 30)
                    overbought = conditions.get("overbought", 70)
                    
                    # Create buy and sell masks
                    buy_mask = (rsi <= oversold)
                    sell_mask = (rsi >= overbought)
                    
                    # Apply signals where conditions are met
                    signals[buy_mask] = 1
                    signals[sell_mask] = -1
                        
                elif ind_type == "macd":
                    # MACD crossover signals
                    macd = df["MACD"]
                    signal_line = df["MACD_Signal"]
                    
                    # Get threshold from conditions or use default (0)
                    threshold = conditions.get("threshold", 0)
                    
                    # Crossover conditions with threshold
                    buy_mask = (macd > signal_line) & (macd.shift(1) <= signal_line.shift(1)) & (abs(macd - signal_line) > threshold)
                    sell_mask = (macd < signal_line) & (macd.shift(1) >= signal_line.shift(1)) & (abs(macd - signal_line) > threshold)
                    
                    signals[buy_mask] = 1
                    signals[sell_mask] = -1
                    
                elif ind_type == "bollinger":
                    # Get Bollinger Bands parameters
                    period = params.get("period", 20)
                    
                    # Get price and bands
                    price = df["Close"]
                    upper = df["BB_Upper"]
                    lower = df["BB_Lower"]
                    
                    # Get percentage threshold from conditions or use default (0)
                    threshold = conditions.get("threshold", 0)
                    
                    # Calculate percentage distance from bands
                    upper_dist = (upper - price) / price * 100
                    lower_dist = (price - lower) / price * 100
                    
                    # Generate signals when price crosses bands beyond threshold
                    buy_mask = (lower_dist <= threshold) & (lower_dist.shift(1) > threshold)
                    sell_mask = (upper_dist <= threshold) & (upper_dist.shift(1) > threshold)
                    
                    signals[buy_mask] = 1
                    signals[sell_mask] = -1
                    
                elif ind_type == "sma":
                    period = params.get("period", 20)
                    sma = df[f"SMA_{period}"]
                    price = df["Close"]
                    
                    # Get threshold from conditions or use default (0)
                    threshold = conditions.get("threshold", 0)
                    
                    # Calculate percentage difference
                    diff_pct = (price - sma) / sma * 100
                    
                    # Generate signals when price crosses SMA beyond threshold
                    buy_mask = (diff_pct > threshold) & (diff_pct.shift(1) <= threshold)
                    sell_mask = (diff_pct < -threshold) & (diff_pct.shift(1) >= -threshold)
                    
                    signals[buy_mask] = 1
                    signals[sell_mask] = -1
                    
                elif ind_type == "ema":
                    period = params.get("period", 20)
                    ema = df[f"EMA_{period}"]
                    price = df["Close"]
                    
                    # Get threshold from conditions or use default (0)
                    threshold = conditions.get("threshold", 0)
                    
                    # Calculate percentage difference
                    diff_pct = (price - ema) / ema * 100
                    
                    # Generate signals when price crosses EMA beyond threshold
                    buy_mask = (diff_pct > threshold) & (diff_pct.shift(1) <= threshold)
                    sell_mask = (diff_pct < -threshold) & (diff_pct.shift(1) >= -threshold)
                    
                    signals[buy_mask] = 1
                    signals[sell_mask] = -1
                    
            except Exception as e:
                logger.error(f"Error generating signals for {ind_type}: {str(e)}")
                continue
                
        return signals

    def _execute_trades(
        self,
        df: pd.DataFrame,
        signals: pd.Series,
        position_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Execute trades based on signals"""
        trades = []
        metrics = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_profit_loss": 0,
            "max_drawdown": 0,
            "win_rate": 0,
        }
        
        position = 0  # 0: no position, 1: long, -1: short
        entry_price = 0
        entry_date = None
        
        for date, row in df.iterrows():
            price = row["Close"]
            signal = signals[date]
            
            # Check for exit conditions
            if position != 0:
                pl_pct = ((price - entry_price) / entry_price * 100) * position
                
                # Check stop loss
                if stop_loss and pl_pct <= -stop_loss:
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": price,
                        "position": "long" if position == 1 else "short",
                        "pl_pct": -stop_loss,
                        "exit_reason": "stop_loss"
                    })
                    position = 0
                    metrics["total_trades"] += 1
                    metrics["losing_trades"] += 1
                    metrics["total_profit_loss"] -= stop_loss
                    continue

                # Check take profit
                if take_profit and pl_pct >= take_profit:
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": price,
                        "position": "long" if position == 1 else "short",
                        "pl_pct": take_profit,
                        "exit_reason": "take_profit"
                    })
                    position = 0
                    metrics["total_trades"] += 1
                    metrics["winning_trades"] += 1
                    metrics["total_profit_loss"] += take_profit
                    continue

            # Enter new position
            if position == 0 and signal != 0:
                position = signal
                entry_price = price
                entry_date = date

        # Calculate final metrics
        if metrics["total_trades"] > 0:
            metrics["win_rate"] = (metrics["winning_trades"] / metrics["total_trades"]) * 100
            
        return trades, metrics

    def _calculate_performance_metrics(
        self,
        df: pd.DataFrame,
        trades: List[Dict[str, Any]],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        if not trades:
            return {
                "total_return": 0,
                "annualized_return": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "win_rate": 0,
                "profit_factor": 0
            }

        # Calculate returns
        returns = pd.Series(index=df.index, data=0.0)
        gross_profits = 0
        gross_losses = 0
        
        for trade in trades:
            entry_date = trade["entry_date"]
            exit_date = trade["exit_date"]
            pl_pct = trade["pl_pct"]
            returns[exit_date] = pl_pct
            
            # Calculate gross profits and losses for profit factor
            if pl_pct > 0:
                gross_profits += pl_pct
            else:
                gross_losses -= pl_pct  # Make losses positive for division

        # Calculate metrics
        total_return = returns.sum()
        annual_factor = 252 / len(df)  # Assuming daily data
        annualized_return = (1 + total_return/100) ** annual_factor - 1
        
        # Calculate Sharpe ratio
        risk_free_rate = 0.02  # Assuming 2% risk-free rate
        excess_returns = returns - (risk_free_rate / 252)
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() != 0 else 0

        # Calculate drawdown
        cumulative = (1 + returns/100).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = (cumulative - rolling_max) / rolling_max
        max_drawdown = abs(drawdowns.min()) * 100 if not drawdowns.empty else 0

        # Calculate profit factor
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else 0 if gross_profits == 0 else float('inf')

        return {
            "total_return": total_return,
            "annualized_return": annualized_return * 100,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": metrics["win_rate"],
            "profit_factor": profit_factor
        }

    def _generate_summary(self, performance: Dict[str, Any]) -> str:
        """Generate a human-readable summary of backtest performance"""
        return f"""Backtest Performance Summary:
Total Return: {performance['total_return']:.2f}%
Annualized Return: {performance['annualized_return']:.2f}%
Sharpe Ratio: {performance['sharpe_ratio']:.2f}
Maximum Drawdown: {performance['max_drawdown']:.2f}%
Win Rate: {performance['win_rate']:.2f}%
Profit Factor: {performance['profit_factor']:.2f}""" 