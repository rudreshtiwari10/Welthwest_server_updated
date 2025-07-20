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
        initial_capital: float,
        position_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timeframe: str = "1d",
        # Risk Management Parameters
        max_drawdown: Optional[float] = None,
        max_positions: Optional[int] = None,
        sector_exposure_limit: Optional[float] = None,
        consecutive_loss_limit: Optional[int] = None,
        daily_loss_limit: Optional[float] = None,
        weekly_loss_limit: Optional[float] = None,
        # Portfolio Constraints
        max_allocation: Optional[float] = None,
        margin_requirement: Optional[float] = None,
        margin_interest: Optional[float] = None,
        min_cash_reserve: Optional[float] = None,
        # Position Sizing Method
        position_sizing_method: str = "fixed",  # "fixed", "kelly"
        kelly_fraction: Optional[float] = None,
        # Correlation Settings
        correlation_threshold: Optional[float] = None,
        benchmark_symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run a backtest with the specified parameters
        
        Args:
            ticker: Stock/index symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            indicators: List of indicators with parameters and conditions
            initial_capital: Starting portfolio value
            position_size: Position size per trade (percentage of capital)
            stop_loss: Optional stop loss percentage
            take_profit: Optional take profit percentage
            timeframe: Data timeframe (1d, 1h, etc.)
            max_drawdown: Maximum allowed drawdown percentage
            max_positions: Maximum number of concurrent positions
            sector_exposure_limit: Maximum exposure to a single sector
            consecutive_loss_limit: Stop trading after X consecutive losses
            daily_loss_limit: Maximum daily loss percentage
            weekly_loss_limit: Maximum weekly loss percentage
            max_allocation: Maximum allocation per trade
            margin_requirement: Required margin percentage
            margin_interest: Annual margin interest rate
            min_cash_reserve: Minimum cash reserve percentage
            position_sizing_method: Method for position sizing (fixed or kelly)
            kelly_fraction: Fraction of Kelly criterion to use
            correlation_threshold: Maximum correlation between positions
            benchmark_symbol: Symbol for benchmark comparison
            
        Returns:
            Dict containing backtest results and performance metrics
        """
        try:
            # Input validation
            self._validate_inputs(
                ticker, start_date, end_date, indicators,
                initial_capital, position_size, stop_loss, take_profit, timeframe,
                max_drawdown, max_positions, sector_exposure_limit,
                consecutive_loss_limit, daily_loss_limit, weekly_loss_limit,
                max_allocation, margin_requirement, margin_interest,
                min_cash_reserve, position_sizing_method, kelly_fraction,
                correlation_threshold, benchmark_symbol
            )
            
            # Try to get cached results
            cache_key = f"backtest_{ticker}_{start_date}_{end_date}_{hash(str(indicators))}_{timeframe}"
            cached_result = get_cached_data(cache_key)
            if cached_result:
                logger.info(f"Using cached backtest results for {ticker}")
                return cached_result

            # Get historical data with indicators
            df = self._get_data_with_indicators(ticker, start_date, end_date, timeframe, indicators)
            if df.empty:
                raise ValueError(f"No data available for {ticker} in the specified date range")

            # Get benchmark data if specified
            benchmark_data = None
            if benchmark_symbol:
                try:
                    benchmark_data = self._get_data_with_indicators(
                        benchmark_symbol, start_date, end_date, timeframe, []
                    )
                except Exception as e:
                    logger.warning(f"Error fetching benchmark data: {str(e)}. Proceeding without benchmark comparison.")

            # Generate signals
            try:
                signals = self._generate_signals(df, indicators)
            except Exception as e:
                logger.error(f"Error generating signals: {str(e)}")
                signals = pd.Series(index=df.index, data=0)
            
            # Execute trades
            try:
                trades, metrics = self._execute_trades(
                    df,
                    signals,
                    initial_capital,
                    position_size,
                    stop_loss,
                    take_profit,
                    max_drawdown=max_drawdown,
                    max_positions=max_positions,
                    sector_exposure_limit=sector_exposure_limit,
                    consecutive_loss_limit=consecutive_loss_limit,
                    daily_loss_limit=daily_loss_limit,
                    weekly_loss_limit=weekly_loss_limit,
                    max_allocation=max_allocation,
                    margin_requirement=margin_requirement,
                    margin_interest=margin_interest,
                    min_cash_reserve=min_cash_reserve,
                    position_sizing_method=position_sizing_method,
                    kelly_fraction=kelly_fraction,
                    correlation_threshold=correlation_threshold,
                    benchmark_data=benchmark_data
                )
            except Exception as e:
                logger.error(f"Error executing trades: {str(e)}")
                return {
                    "trades": [],
                    "metrics": {
                        "total_trades": 0,
                        "winning_trades": 0,
                        "losing_trades": 0,
                        "total_pnl": 0.0,
                        "max_drawdown": 0.0
                    },
                    "performance": {
                        "total_return": 0,
                        "annualized_return": 0,
                        "sharpe_ratio": 0,
                        "max_drawdown": 0,
                        "win_rate": 0
                    },
                    "summary": "Backtest failed to execute trades. Please check your parameters and try again.",
                    "indicator_data": {}
                }
            
            # Calculate performance metrics
            try:
                performance = self._calculate_performance_metrics(
                    df, trades, metrics, benchmark_data
                )
            except Exception as e:
                logger.error(f"Error calculating performance metrics: {str(e)}")
                performance = {
                    "total_return": 0,
                    "annualized_return": 0,
                    "sharpe_ratio": 0,
                    "max_drawdown": 0,
                    "win_rate": 0
                }
            
            # Format dates consistently
            try:
                # Try to convert index to datetime if it's not already
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                dates = df.index.strftime('%Y-%m-%d').tolist()
            except Exception as e:
                logger.warning(f"Error formatting dates: {str(e)}. Using string conversion.")
                # Fallback to string conversion
                dates = [str(d) for d in df.index.tolist()]
            
            # Prepare indicator data with proper date alignment
            indicator_data = {}
            for indicator in indicators:
                try:
                    ind_type = indicator["type"].lower()
                    if ind_type == "rsi":
                        period = indicator.get("parameters", {}).get("period", 14)
                        column = f"RSI_{period}"
                        if column in df.columns:
                            indicator_data[column] = [
                                float(x) if not pd.isna(x) else None for x in df[column].tolist()
                            ]
                    elif ind_type == "macd":
                        if all(col in df.columns for col in ["MACD", "MACD_Signal", "MACD_Hist"]):
                            indicator_data["macd"] = [
                                float(x) if not pd.isna(x) else None for x in df["MACD"].tolist()
                            ]
                            indicator_data["macd_signal"] = [
                                float(x) if not pd.isna(x) else None for x in df["MACD_Signal"].tolist()
                            ]
                            indicator_data["macd_histogram"] = [
                                float(x) if not pd.isna(x) else None for x in df["MACD_Hist"].tolist()
                            ]
                    elif ind_type == "bollinger":
                        if all(col in df.columns for col in ["BB_Upper", "BB_Middle", "BB_Lower"]):
                            indicator_data["bollinger_upper"] = [
                                float(x) if not pd.isna(x) else None for x in df["BB_Upper"].tolist()
                            ]
                            indicator_data["bollinger_middle"] = [
                                float(x) if not pd.isna(x) else None for x in df["BB_Middle"].tolist()
                            ]
                            indicator_data["bollinger_lower"] = [
                                float(x) if not pd.isna(x) else None for x in df["BB_Lower"].tolist()
                            ]
                    elif ind_type == "sma":
                        period = indicator.get("parameters", {}).get("period", 20)
                        column = f"SMA_{period}"
                        if column in df.columns:
                            indicator_data[column] = [
                                float(x) if not pd.isna(x) else None for x in df[column].tolist()
                            ]
                    elif ind_type == "ema":
                        period = indicator.get("parameters", {}).get("period", 20)
                        column = f"EMA_{period}"
                        if column in df.columns:
                            indicator_data[column] = [
                                float(x) if not pd.isna(x) else None for x in df[column].tolist()
                            ]
                    elif ind_type == "stochastic":
                        if all(col in df.columns for col in ["Stoch_k", "Stoch_d"]):
                            indicator_data["stochastic_k"] = [
                                float(x) if not pd.isna(x) else None for x in df["Stoch_k"].tolist()
                            ]
                            indicator_data["stochastic_d"] = [
                                float(x) if not pd.isna(x) else None for x in df["Stoch_d"].tolist()
                            ]
                except Exception as e:
                    logger.error(f"Error formatting indicator data for {ind_type}: {str(e)}")
                    continue

            # Prepare results with consistent date formatting
            results = {
                "trades": trades,
                "metrics": metrics,
                "performance": performance,
                "summary": self._generate_summary(performance),
                "indicator_data": indicator_data,
                "dates": dates,
                "price_data": [{
                    "Date": date,
                    "Open": float(row.Open) if hasattr(row, 'Open') and not pd.isna(row.Open) else None,
                    "High": float(row.High) if hasattr(row, 'High') and not pd.isna(row.High) else None,
                    "Low": float(row.Low) if hasattr(row, 'Low') and not pd.isna(row.Low) else None,
                    "Close": float(row.Close) if hasattr(row, 'Close') and not pd.isna(row.Close) else None,
                    "Volume": float(row.Volume) if hasattr(row, 'Volume') and not pd.isna(row.Volume) else None
                } for date, row in zip(dates, df.itertuples())]
            }
            
            # Cache results
            try:
                set_cached_data(cache_key, results, self.cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to cache results: {str(e)}")
                
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
        initial_capital: float,
        position_size: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        timeframe: str,
        max_drawdown: Optional[float],
        max_positions: Optional[int],
        sector_exposure_limit: Optional[float],
        consecutive_loss_limit: Optional[int],
        daily_loss_limit: Optional[float],
        weekly_loss_limit: Optional[float],
        max_allocation: Optional[float],
        margin_requirement: Optional[float],
        margin_interest: Optional[float],
        min_cash_reserve: Optional[float],
        position_sizing_method: str,
        kelly_fraction: Optional[float],
        correlation_threshold: Optional[float],
        benchmark_symbol: Optional[str]
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

        # Validate initial capital
        if initial_capital <= 0:
            raise ValueError("Initial capital must be positive")

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

        # Validate risk management parameters
        if max_drawdown is not None and not 0 < max_drawdown < 100:
            raise ValueError("Maximum drawdown must be between 0 and 100")
        if max_positions is not None and max_positions <= 0:
            raise ValueError("Maximum positions must be positive")
        if sector_exposure_limit is not None and not 0 < sector_exposure_limit <= 100:
            raise ValueError("Sector exposure limit must be between 0 and 100")
        if consecutive_loss_limit is not None and consecutive_loss_limit <= 0:
            raise ValueError("Consecutive loss limit must be positive")
        if daily_loss_limit is not None and not 0 < daily_loss_limit < 100:
            raise ValueError("Daily loss limit must be between 0 and 100")
        if weekly_loss_limit is not None and not 0 < weekly_loss_limit < 100:
            raise ValueError("Weekly loss limit must be between 0 and 100")

        # Validate portfolio constraints
        if max_allocation is not None and not 0 < max_allocation <= 100:
            raise ValueError("Maximum allocation must be between 0 and 100")
        if margin_requirement is not None and not 0 < margin_requirement <= 100:
            raise ValueError("Margin requirement must be between 0 and 100")
        if margin_interest is not None and margin_interest < 0:
            raise ValueError("Margin interest must be non-negative")
        if min_cash_reserve is not None and not 0 <= min_cash_reserve < 100:
            raise ValueError("Minimum cash reserve must be between 0 and 100")

        # Validate position sizing method
        valid_sizing_methods = ["fixed", "kelly"]
        if position_sizing_method not in valid_sizing_methods:
            raise ValueError(f"Invalid position sizing method. Must be one of {valid_sizing_methods}")
        if position_sizing_method == "kelly" and (kelly_fraction is None or not 0 < kelly_fraction <= 1):
            raise ValueError("Kelly fraction must be between 0 and 1 when using Kelly criterion")

        # Validate correlation settings
        if correlation_threshold is not None and not -1 <= correlation_threshold <= 1:
            raise ValueError("Correlation threshold must be between -1 and 1")

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
                period = params.get("period", 20)
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
        """Get historical data with technical indicators"""
        try:
            # Get historical data
            df = get_ohlc_data(ticker, start_date, end_date, timeframe)
            if df.empty:
                raise ValueError(f"No data available for {ticker}")

            # Calculate indicators
            for indicator in indicators:
                try:
                    ind_type = indicator["type"].lower()
                    params = indicator.get("parameters", indicator.get("params", {}))

                    if ind_type == "rsi":
                        period = params.get("period", 14)
                        df[f'RSI_{period}'] = self.ta._calculate_rsi(df, period)

                    elif ind_type == "macd":
                        fastperiod = params.get("fastperiod", 12)
                        slowperiod = params.get("slowperiod", 26)
                        signalperiod = params.get("signalperiod", 9)
                        macd_data = self.ta._calculate_macd(df, fastperiod, slowperiod, signalperiod)
                        df['MACD'] = macd_data['macd']
                        df['MACD_Signal'] = macd_data['signal']
                        df['MACD_Hist'] = macd_data['histogram']

                    elif ind_type == "bollinger":
                        period = params.get("period", 20)
                        num_std = params.get("num_std", 2)
                        bb_data = self.ta._calculate_bollinger_bands(df, period, num_std)
                        df['BB_upper'] = bb_data['upper']
                        df['BB_middle'] = bb_data['middle']
                        df['BB_lower'] = bb_data['lower']

                    elif ind_type == "sma":
                        period = params.get("period", 20)
                        df[f'SMA_{period}'] = self.ta._calculate_sma(df, period)

                    elif ind_type == "ema":
                        period = params.get("period", 20)
                        df[f'EMA_{period}'] = self.ta._calculate_ema(df, period)

                    elif ind_type == "stochastic":
                        k_period = params.get("k_period", 14)
                        d_period = params.get("d_period", 3)
                        stoch_data = self.ta._calculate_stochastic(df, k_period, d_period)
                        df['STOCH_k'] = stoch_data['k']
                        df['STOCH_d'] = stoch_data['d']

                    elif ind_type == "atr":
                        period = params.get("period", 14)
                        df['ATR'] = self.ta._calculate_atr(df, period)

                    elif ind_type == "obv":
                        df['OBV'] = self.ta._calculate_obv(df)

                    elif ind_type == "vwap":
                        df['VWAP'] = self.ta._calculate_vwap(df)

                except Exception as e:
                    logger.error(f"Error calculating {ind_type}: {str(e)}")
                    continue

            return df

        except Exception as e:
            logger.error(f"Error in _get_data_with_indicators: {str(e)}")
            return pd.DataFrame()

    def _generate_signals(
        self,
        df: pd.DataFrame,
        indicators: List[Dict[str, Any]]
    ) -> pd.Series:
        """Generate trading signals based on indicators"""
        try:
            # Create a DataFrame to store signals from each indicator
            all_signals = pd.DataFrame(index=df.index)
            
            for indicator in indicators:
                try:
                    ind_type = indicator["type"].lower()
                    params = indicator.get("parameters", indicator.get("params", {}))
                    
                    if ind_type == "rsi":
                        period = params.get("period", 14)
                        column_name = f"RSI_{period}"
                        if column_name not in df.columns:
                            continue
                            
                        rsi = df[column_name]
                        oversold = 30
                        overbought = 70
                        
                        signals = pd.Series(0, index=df.index)
                        signals[rsi <= oversold] = 1
                        signals[rsi >= overbought] = -1
                        all_signals[f'signal_{ind_type}'] = signals
                        
                    elif ind_type == "macd":
                        if "MACD" not in df.columns or "MACD_Signal" not in df.columns:
                            continue
                            
                        macd = df["MACD"]
                        signal_line = df["MACD_Signal"]
                        
                        signals = pd.Series(0, index=df.index)
                        # Crossover signals
                        signals[(macd > signal_line) & (macd.shift(1) <= signal_line.shift(1))] = 1
                        signals[(macd < signal_line) & (macd.shift(1) >= signal_line.shift(1))] = -1
                        all_signals[f'signal_{ind_type}'] = signals
                        
                    elif ind_type == "bollinger":
                        if not all(col in df.columns for col in ["BB_upper", "BB_middle", "BB_lower"]):
                            continue
                            
                        signals = pd.Series(0, index=df.index)
                        # Price crossing below lower band = buy
                        signals[(df['Close'] <= df['BB_lower']) & (df['Close'].shift(1) > df['BB_lower'].shift(1))] = 1
                        # Price crossing above upper band = sell
                        signals[(df['Close'] >= df['BB_upper']) & (df['Close'].shift(1) < df['BB_upper'].shift(1))] = -1
                        all_signals[f'signal_{ind_type}'] = signals
                        
                    elif ind_type == "sma":
                        period = params.get("period", 20)
                        column_name = f"SMA_{period}"
                        if column_name not in df.columns:
                            continue
                            
                        signals = pd.Series(0, index=df.index)
                        # Price crossing above SMA = buy
                        signals[(df['Close'] > df[column_name]) & (df['Close'].shift(1) <= df[column_name].shift(1))] = 1
                        # Price crossing below SMA = sell
                        signals[(df['Close'] < df[column_name]) & (df['Close'].shift(1) >= df[column_name].shift(1))] = -1
                        all_signals[f'signal_{ind_type}'] = signals
                        
                    elif ind_type == "ema":
                        period = params.get("period", 20)
                        column_name = f"EMA_{period}"
                        if column_name not in df.columns:
                            continue
                            
                        signals = pd.Series(0, index=df.index)
                        # Price crossing above EMA = buy
                        signals[(df['Close'] > df[column_name]) & (df['Close'].shift(1) <= df[column_name].shift(1))] = 1
                        # Price crossing below EMA = sell
                        signals[(df['Close'] < df[column_name]) & (df['Close'].shift(1) >= df[column_name].shift(1))] = -1
                        all_signals[f'signal_{ind_type}'] = signals
                        
                    elif ind_type == "stochastic":
                        if "STOCH_k" not in df.columns or "STOCH_d" not in df.columns:
                            continue
                            
                        k_line = df["STOCH_k"]
                        d_line = df["STOCH_d"]
                        
                        signals = pd.Series(0, index=df.index)
                        # Bullish: K crosses above D in oversold territory
                        signals[(k_line > d_line) & (k_line.shift(1) <= d_line.shift(1)) & (k_line < 20)] = 1
                        # Bearish: K crosses below D in overbought territory
                        signals[(k_line < d_line) & (k_line.shift(1) >= d_line.shift(1)) & (k_line > 80)] = -1
                        all_signals[f'signal_{ind_type}'] = signals
                        
                except Exception as e:
                    logger.error(f"Error generating signals for {ind_type}: {str(e)}")
                    continue
            
            # If we have signals from multiple indicators
            if len(all_signals.columns) > 1:
                # Calculate the percentage of indicators agreeing on each signal
                total_indicators = len(indicators)
                buy_agreement = (all_signals == 1).sum(axis=1) / total_indicators
                sell_agreement = (all_signals == -1).sum(axis=1) / total_indicators
                
                # Generate final signals based on 40% agreement
                final_signals = pd.Series(0, index=df.index)
                final_signals[buy_agreement >= 0.4] = 1
                final_signals[sell_agreement >= 0.4] = -1
                
                # Log signal statistics
                buy_signals = (final_signals == 1).sum()
                sell_signals = (final_signals == -1).sum()
                logger.info(f"Total signals with 40% agreement: Buy={buy_signals}, Sell={sell_signals}")
                
                return final_signals
            elif len(all_signals.columns) == 1:
                # If only one indicator, use its signals directly
                return all_signals.iloc[:, 0]
            else:
                # No valid signals generated
                return pd.Series(0, index=df.index)
                
        except Exception as e:
            logger.error(f"Error in signal generation: {str(e)}")
            return pd.Series(index=df.index, data=0)

    def _calculate_kelly_fraction(
        self,
        trades: List[Dict[str, Any]]
    ) -> float:
        """Calculate the optimal Kelly fraction based on historical trades"""
        if not trades:
            return 0.5  # Default to 50% if no historical trades
            
        wins = [t for t in trades if t["pnl_pct"] > 0]
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        
        if not losses:  # Avoid division by zero
            return 1.0
            
        win_prob = len(wins) / len(trades)
        avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t["pnl_pct"] for t in losses])) if losses else 1
        
        # Kelly Criterion formula: f = (p(b+1) - 1)/b
        # where p is probability of win, b is win/loss ratio
        if avg_loss == 0:  # Avoid division by zero
            return 1.0
            
        b = avg_win / avg_loss
        kelly = win_prob * (b + 1) - 1
        kelly = kelly / b if b != 0 else 0
        
        # Limit kelly fraction to reasonable bounds
        return max(0.0, min(1.0, kelly))

    def _execute_trades(
        self,
        df: pd.DataFrame,
        signals: pd.Series,
        initial_capital: float,
        position_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        max_positions: Optional[int] = None,
        sector_exposure_limit: Optional[float] = None,
        consecutive_loss_limit: Optional[int] = None,
        daily_loss_limit: Optional[float] = None,
        weekly_loss_limit: Optional[float] = None,
        max_allocation: Optional[float] = None,
        margin_requirement: Optional[float] = None,
        margin_interest: Optional[float] = None,
        min_cash_reserve: Optional[float] = None,
        position_sizing_method: str = "fixed",
        kelly_fraction: Optional[float] = None,
        correlation_threshold: Optional[float] = None,
        benchmark_data: Optional[pd.DataFrame] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Execute trades based on signals"""
        try:
            trades = []
            metrics = {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0,
                'max_drawdown': 0.0,
                'max_consecutive_losses': 0,
                'current_consecutive_losses': 0,
                'daily_pnl': {},
                'weekly_pnl': {},
                'positions': [],
                'margin_used': 0.0,
                'margin_interest_paid': 0.0,
                'initial_capital': initial_capital,
                'equity_curve': {}
            }
            
            # Initialize metrics with proper date handling
            for date in df.index:
                date_str = pd.Timestamp(date).strftime('%Y-%m-%d')
                metrics['daily_pnl'][date_str] = 0.0
                metrics['equity_curve'][date_str] = initial_capital
                week_num = pd.Timestamp(date).isocalendar()[1]
                if week_num not in metrics['weekly_pnl']:
                    metrics['weekly_pnl'][week_num] = 0.0
            
            # Track positions and performance
            current_capital = initial_capital
            current_positions = []
            
            logger.info(f"Starting trade execution with {len(signals[signals != 0])} signals")
            
            for i in range(len(df)):
                date = df.index[i]
                date_str = pd.Timestamp(date).strftime('%Y-%m-%d')
                row = df.iloc[i]
                signal = signals.iloc[i]
                
                # Calculate daily P&L for existing positions using OHLC data
                daily_pnl = 0.0
                for pos in current_positions:
                    entry_price = pos['entry_price']
                    # Use actual price movement for P&L calculation
                    current_price = row['Close']  # End of day price
                    size = pos['size']
                    prev_price = df['Close'].iloc[i-1] if i > 0 else entry_price
                    daily_pos_pnl = (current_price - prev_price) * size
                    daily_pnl += daily_pos_pnl
                
                # Update daily and weekly P&L
                metrics['daily_pnl'][date_str] = daily_pnl
                current_capital += daily_pnl
                metrics['equity_curve'][date_str] = current_capital
                week_num = pd.Timestamp(date).isocalendar()[1]
                metrics['weekly_pnl'][week_num] += daily_pnl
                
                # Update existing positions
                positions_to_remove = []
                for pos in current_positions:
                    # Calculate P&L using OHLC data
                    entry_price = pos['entry_price']
                    # Check for stop loss/take profit using High/Low prices
                    high_price = row['High']
                    low_price = row['Low']
                    size = pos['size']
                    
                    # Calculate worst and best case P&L for the day
                    worst_pnl_pct = (low_price - entry_price) / entry_price * 100
                    best_pnl_pct = (high_price - entry_price) / entry_price * 100
                    
                    # Determine if stop loss or take profit was hit
                    hit_stop_loss = stop_loss and worst_pnl_pct <= -stop_loss
                    hit_take_profit = take_profit and best_pnl_pct >= take_profit
                    
                    if hit_stop_loss or hit_take_profit:
                        exit_price = (
                            entry_price * (1 - stop_loss/100) if hit_stop_loss
                            else entry_price * (1 + take_profit/100)
                        )
                        pnl = (exit_price - entry_price) * size
                        pnl_pct = (exit_price - entry_price) / entry_price * 100
                        
                        trades.append({
                            'entry_date': pos['entry_date'],
                            'exit_date': date_str,  # Use consistent date format
                            'entry_price': float(entry_price),  # Ensure float type
                            'exit_price': float(exit_price),  # Ensure float type
                            'size': float(size),  # Ensure float type
                            'pnl': float(pnl),  # Ensure float type
                            'pnl_pct': float(pnl_pct)  # Ensure float type
                        })
                        positions_to_remove.append(pos)
                        
                        # Update metrics
                        metrics['total_trades'] += 1
                        if pnl > 0:
                            metrics['winning_trades'] += 1
                            metrics['current_consecutive_losses'] = 0
                        else:
                            metrics['losing_trades'] += 1
                            metrics['current_consecutive_losses'] += 1
                            metrics['max_consecutive_losses'] = max(
                                metrics['max_consecutive_losses'],
                                metrics['current_consecutive_losses']
                            )
                        
                        metrics['total_pnl'] += pnl
                
                # Remove closed positions
                for pos in positions_to_remove:
                    current_positions.remove(pos)
                
                # Check for new entry signals
                if signal == 1 and (max_positions is None or len(current_positions) < max_positions):
                    # Calculate position size
                    if position_sizing_method == "kelly" and kelly_fraction:
                        size = current_capital * kelly_fraction
                    else:
                        # Convert percentage to decimal (e.g., 10% -> 0.1)
                        size = current_capital * (position_size / 100)
                    
                    # Check margin requirements
                    if margin_requirement:
                        required_margin = size * (margin_requirement / 100)
                        if required_margin > current_capital:
                            continue
                    
                    # Use next bar's open price for entry
                    if i + 1 < len(df):
                        entry_price = df['Open'].iloc[i + 1]
                    else:
                        entry_price = row['Close']  # Use close if last bar
                    
                    # Add new position with proper price
                    new_position = {
                        'entry_date': date_str,  # Use consistent date format
                        'entry_price': float(entry_price),  # Ensure float type
                        'size': float(size / entry_price)  # Ensure float type
                    }
                    current_positions.append(new_position)
                    metrics['positions'].append(new_position)
                    logger.info(f"Opened new position at {date_str}: price={entry_price:.2f}, size={size/entry_price:.2f}")
                
                # Check for exit signals
                elif signal == -1 and current_positions:
                    for pos in current_positions:
                        entry_price = pos['entry_price']
                        exit_price = row['Close']  # Use close price for exits
                        size = pos['size']
                        pnl = (exit_price - entry_price) * size
                        pnl_pct = (exit_price - entry_price) / entry_price * 100
                        
                        trades.append({
                            'entry_date': pos['entry_date'],
                            'exit_date': date_str,  # Use consistent date format
                            'entry_price': float(entry_price),  # Ensure float type
                            'exit_price': float(exit_price),  # Ensure float type
                            'size': float(size),  # Ensure float type
                            'pnl': float(pnl),  # Ensure float type
                            'pnl_pct': float(pnl_pct)  # Ensure float type
                        })
                        
                        # Update metrics
                        metrics['total_trades'] += 1
                        if pnl > 0:
                            metrics['winning_trades'] += 1
                            metrics['current_consecutive_losses'] = 0
                        else:
                            metrics['losing_trades'] += 1
                            metrics['current_consecutive_losses'] += 1
                            metrics['max_consecutive_losses'] = max(
                                metrics['max_consecutive_losses'],
                                metrics['current_consecutive_losses']
                            )
                        metrics['total_pnl'] += pnl
                    
                    # Clear all positions on exit signal
                    current_positions = []
            
            return trades, metrics
            
        except Exception as e:
            logger.error(f"Error in trade execution: {str(e)}")
            raise

    def _calculate_performance_metrics(
        self,
        df: pd.DataFrame,
        trades: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        benchmark_data: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """Calculate performance metrics"""
        try:
            if not trades:
                logger.warning("No trades found, returning default metrics")
                return {
                    'total_return': 0.0,
                    'annualized_return': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'win_rate': 0.0,
                    'daily_returns': [],
                    'daily_equity': []
                }
            
            # Get initial capital from metrics
            initial_capital = metrics.get('initial_capital', 100000.0)
            logger.info(f"Using initial capital: {initial_capital}")
            
            # Convert equity curve to series
            equity_curve = pd.Series(metrics['equity_curve'])
            logger.info(f"Equity curve shape: {equity_curve.shape}")
            logger.info(f"Equity curve range: {equity_curve.min():.2f} to {equity_curve.max():.2f}")
            
            # Calculate daily returns
            daily_returns = equity_curve.pct_change().fillna(0.0)
            logger.info(f"Daily returns shape: {daily_returns.shape}")
            logger.info(f"Daily returns range: {daily_returns.min():.4f} to {daily_returns.max():.4f}")
            
            # Calculate total return
            final_capital = equity_curve.iloc[-1]
            total_return = ((final_capital - initial_capital) / initial_capital) * 100
            logger.info(f"Total return: {total_return:.2f}%")
            
            # Calculate annualized return
            trading_days = len(daily_returns[daily_returns != 0])
            if trading_days > 0 and total_return > -100:
                annualized_return = ((1 + total_return/100) ** (252/trading_days) - 1) * 100
            else:
                annualized_return = 0.0
                logger.warning("No trading days or total loss, setting annualized return to 0")
            logger.info(f"Annualized return: {annualized_return:.2f}%")
            
            # Calculate Sharpe ratio
            daily_returns_nonzero = daily_returns[daily_returns != 0]
            if len(daily_returns_nonzero) > 0:
                returns_std = daily_returns_nonzero.std()
                if returns_std > 0:
                    sharpe_ratio = np.sqrt(252) * daily_returns_nonzero.mean() / returns_std
                else:
                    sharpe_ratio = 0.0
                    logger.warning("Zero standard deviation in returns, setting Sharpe ratio to 0")
            else:
                sharpe_ratio = 0.0
                logger.warning("No non-zero returns, setting Sharpe ratio to 0")
            logger.info(f"Sharpe ratio: {sharpe_ratio:.2f}")
            
            # Calculate maximum drawdown
            rolling_max = equity_curve.expanding().max()
            drawdowns = equity_curve - rolling_max
            relative_drawdowns = drawdowns / rolling_max
            max_drawdown = abs(relative_drawdowns.min()) * 100 if not relative_drawdowns.empty else 0.0
            logger.info(f"Maximum drawdown: {max_drawdown:.2f}%")
            
            # Calculate win rate
            total_trades = metrics.get('total_trades', 0)
            winning_trades = metrics.get('winning_trades', 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
            logger.info(f"Win rate: {win_rate:.2f}%")
            
            # Ensure all metrics are finite
            metrics_dict = {
                'total_return': float(np.nan_to_num(total_return, 0.0)),
                'annualized_return': float(np.nan_to_num(annualized_return, 0.0)),
                'sharpe_ratio': float(np.nan_to_num(sharpe_ratio, 0.0)),
                'max_drawdown': float(np.nan_to_num(max_drawdown, 0.0)),
                'win_rate': float(np.nan_to_num(win_rate, 0.0)),
                'daily_returns': daily_returns.tolist(),
                'daily_equity': equity_curve.tolist()
            }
            
            logger.info("Performance metrics calculated successfully:")
            logger.info(f"Total Return: {metrics_dict['total_return']:.2f}%")
            logger.info(f"Annualized Return: {metrics_dict['annualized_return']:.2f}%")
            logger.info(f"Sharpe Ratio: {metrics_dict['sharpe_ratio']:.2f}")
            logger.info(f"Max Drawdown: {metrics_dict['max_drawdown']:.2f}%")
            logger.info(f"Win Rate: {metrics_dict['win_rate']:.2f}%")
            
            return metrics_dict
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {str(e)}", exc_info=True)
            return {
                'total_return': 0.0,
                'annualized_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'win_rate': 0.0,
                'daily_returns': [],
                'daily_equity': []
            }

    def _run_monte_carlo_simulation(
        self,
        trades: List[Dict[str, Any]],
        initial_capital: float,
        num_simulations: int = 1000
    ) -> Dict[str, Any]:
        """Run Monte Carlo simulation to analyze strategy robustness"""
        if not trades:
            return {
                "percentiles": {},
                "metrics": {},
                "confidence_intervals": {}
            }

        # Extract returns from trades
        returns = [trade["pnl_pct"] / 100 for trade in trades]
        
        # Initialize arrays to store simulation results
        final_capitals = np.zeros(num_simulations)
        max_drawdowns = np.zeros(num_simulations)
        sharpe_ratios = np.zeros(num_simulations)
        
        # Run simulations
        for i in range(num_simulations):
            # Shuffle returns to create a new sequence
            shuffled_returns = np.random.choice(returns, size=len(returns), replace=False)
            
            # Calculate equity curve
            equity_curve = initial_capital * np.cumprod(1 + shuffled_returns)
            
            # Calculate metrics for this simulation
            final_capitals[i] = equity_curve[-1]
            
            # Calculate drawdown
            rolling_max = np.maximum.accumulate(equity_curve)
            drawdowns = (equity_curve - rolling_max) / rolling_max
            max_drawdowns[i] = abs(min(drawdowns))
            
            # Calculate Sharpe ratio
            returns_std = np.std(shuffled_returns)
            if returns_std != 0:
                sharpe_ratios[i] = np.sqrt(252) * (np.mean(shuffled_returns) / returns_std)

        # Calculate percentiles
        percentiles = {
            "final_capital": {
                "5th": np.percentile(final_capitals, 5),
                "25th": np.percentile(final_capitals, 25),
                "50th": np.percentile(final_capitals, 50),
                "75th": np.percentile(final_capitals, 75),
                "95th": np.percentile(final_capitals, 95)
            },
            "max_drawdown": {
                "5th": np.percentile(max_drawdowns, 5),
                "25th": np.percentile(max_drawdowns, 25),
                "50th": np.percentile(max_drawdowns, 50),
                "75th": np.percentile(max_drawdowns, 75),
                "95th": np.percentile(max_drawdowns, 95)
            },
            "sharpe_ratio": {
                "5th": np.percentile(sharpe_ratios, 5),
                "25th": np.percentile(sharpe_ratios, 25),
                "50th": np.percentile(sharpe_ratios, 50),
                "75th": np.percentile(sharpe_ratios, 75),
                "95th": np.percentile(sharpe_ratios, 95)
            }
        }

        # Calculate confidence intervals (95%)
        confidence_intervals = {
            "final_capital": {
                "lower": np.percentile(final_capitals, 2.5),
                "upper": np.percentile(final_capitals, 97.5)
            },
            "max_drawdown": {
                "lower": np.percentile(max_drawdowns, 2.5),
                "upper": np.percentile(max_drawdowns, 97.5)
            },
            "sharpe_ratio": {
                "lower": np.percentile(sharpe_ratios, 2.5),
                "upper": np.percentile(sharpe_ratios, 97.5)
            }
        }

        # Calculate summary metrics
        metrics = {
            "final_capital": {
                "mean": np.mean(final_capitals),
                "std": np.std(final_capitals),
                "min": np.min(final_capitals),
                "max": np.max(final_capitals)
            },
            "max_drawdown": {
                "mean": np.mean(max_drawdowns),
                "std": np.std(max_drawdowns),
                "min": np.min(max_drawdowns),
                "max": np.max(max_drawdowns)
            },
            "sharpe_ratio": {
                "mean": np.mean(sharpe_ratios),
                "std": np.std(sharpe_ratios),
                "min": np.min(sharpe_ratios),
                "max": np.max(sharpe_ratios)
            }
        }

        return {
            "percentiles": percentiles,
            "metrics": metrics,
            "confidence_intervals": confidence_intervals
        }

    def _generate_summary(self, performance: Dict[str, Any]) -> str:
        """Generate a comprehensive summary of backtest results"""
        summary = []
        
        # Overall Performance
        summary.append("Overall Performance:")
        summary.append(f"- Total Return: {performance.get('total_return', 0):.2f}%")
        summary.append(f"- Annualized Return: {performance.get('annualized_return', 0):.2f}%")
        summary.append(f"- Time in Market: {performance.get('time_in_market', 0):.2f}%")
        
        # Risk Metrics
        summary.append("\nRisk Metrics:")
        summary.append(f"- Sharpe Ratio: {performance.get('sharpe_ratio', 0):.2f}")
        summary.append(f"- Sortino Ratio: {performance.get('sortino_ratio', 0):.2f}")
        summary.append(f"- Calmar Ratio: {performance.get('calmar_ratio', 0):.2f}")
        summary.append(f"- Omega Ratio: {performance.get('omega_ratio', 0):.2f}")
        summary.append(f"- Maximum Drawdown: {performance.get('max_drawdown', 0):.2f}%")
        summary.append(f"- Ulcer Index: {performance.get('ulcer_index', 0):.2f}")
        
        # Trade Statistics
        summary.append("\nTrade Statistics:")
        summary.append(f"- Win Rate: {performance.get('win_rate', 0):.2f}%")
        summary.append(f"- Profit Factor: {performance.get('profit_factor', 0):.2f}")
        summary.append(f"- Average Trade Duration: {performance.get('avg_trade_duration', 0):.1f} days")
        summary.append(f"- Average MAE: {performance.get('avg_mae', 0):.2f}%")
        summary.append(f"- Average MFE: {performance.get('avg_mfe', 0):.2f}%")
        summary.append(f"- Longest Win Streak: {performance.get('longest_win_streak', 0)}")
        summary.append(f"- Longest Lose Streak: {performance.get('longest_lose_streak', 0)}")
        
        # Daily/Weekly Analysis
        if 'daily_pnl_stats' in performance and performance['daily_pnl_stats']:
            summary.append("\nDaily P&L Statistics:")
            daily_stats = performance['daily_pnl_stats']
            summary.append(f"- Mean: {daily_stats.get('mean', 0):.2f}%")
            summary.append(f"- Standard Deviation: {daily_stats.get('std', 0):.2f}%")
            summary.append(f"- Best Day: {daily_stats.get('best', 0):.2f}%")
            summary.append(f"- Worst Day: {daily_stats.get('worst', 0):.2f}%")
        
        if 'weekly_pnl_stats' in performance and performance['weekly_pnl_stats']:
            summary.append("\nWeekly P&L Statistics:")
            weekly_stats = performance['weekly_pnl_stats']
            summary.append(f"- Mean: {weekly_stats.get('mean', 0):.2f}%")
            summary.append(f"- Standard Deviation: {weekly_stats.get('std', 0):.2f}%")
            summary.append(f"- Best Week: {weekly_stats.get('best', 0):.2f}%")
            summary.append(f"- Worst Week: {weekly_stats.get('worst', 0):.2f}%")
        
        # Benchmark Comparison (if available)
        if performance.get('benchmark_correlation', 0) != 0:
            summary.append("\nBenchmark Comparison:")
            summary.append(f"- Correlation: {performance.get('benchmark_correlation', 0):.2f}")
            summary.append(f"- Beta: {performance.get('benchmark_beta', 0):.2f}")
            summary.append(f"- Alpha: {performance.get('benchmark_alpha', 0):.2f}%")
        
        return "\n".join(summary) 