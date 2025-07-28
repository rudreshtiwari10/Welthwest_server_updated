import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from .technical_analysis import TechnicalAnalysis
from .market_regime_classifier import MarketRegimeClassifier
from services.cache_service import get_cached_data, set_cached_data
from services.stock_service import get_ohlc_data, format_indian_ticker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BacktestingService:
    def __init__(self):
        self.ta = TechnicalAnalysis()
        self.regime_classifier = MarketRegimeClassifier()
        self.cache_ttl = 3600  # 1 hour cache TTL
        
        # Try to load existing market regime model
        try:
            self.regime_classifier.load_model()
            logger.info("Market regime model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load market regime model: {str(e)}")
            self.regime_classifier.is_trained = False  # Disable regime filtering

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
        # Multi-timeframe parameters
        higher_timeframes: Optional[List[str]] = None,
        timeframe_confluence: bool = True,
        trend_timeframe: Optional[str] = None,
        # Market regime filtering
        enable_regime_filter: bool = False,  # Changed default to False for user choice
        regime_strategy_mapping: Optional[Dict[int, Dict[str, Any]]] = None,
        minimum_confidence_threshold: float = 30.0,  # New parameter for relaxed criteria
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

            # Get historical data with indicators (multi-timeframe if enabled)
            if higher_timeframes and timeframe_confluence:
                df = self._get_multi_timeframe_data_with_indicators(
                    ticker, start_date, end_date, timeframe, higher_timeframes, indicators
                )
            else:
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

            # Generate signals (with multi-timeframe analysis and regime filtering)
            try:
                if higher_timeframes and timeframe_confluence:
                    signals = self._generate_multi_timeframe_signals(
                        df, indicators, timeframe, higher_timeframes, trend_timeframe,
                        minimum_confidence_threshold
                    )
                else:
                    signals = self._generate_signals(df, indicators, minimum_confidence_threshold)
                
                # Apply market regime filtering if enabled
                if enable_regime_filter and self.regime_classifier.is_trained:
                    try:
                        signals = self._apply_regime_filtering(
                            signals, df, ticker, regime_strategy_mapping, minimum_confidence_threshold
                        )
                    except Exception as e:
                        logger.warning(f"Error in regime filtering, continuing without it: {str(e)}")
                        # Continue with original signals if regime filtering fails
                    
            except Exception as e:
                logger.error(f"Error generating signals: {str(e)}")
                signals = pd.Series(index=df.index, data=0)
            
            # Execute trades
            try:
                trades, metrics = self._execute_trades_advanced(
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
                # Ensure we have a proper datetime index
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                
                # Remove timezone if present and format consistently
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                
                dates = df.index.strftime('%Y-%m-%d').tolist()
                logger.info(f"Formatted {len(dates)} dates for backtesting results")
            except Exception as e:
                logger.warning(f"Error formatting dates: {str(e)}. Using string conversion.")
                # Fallback to string conversion
                dates = [str(d).split()[0] for d in df.index.tolist()]  # Keep only date part
            
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

            # Calculate confidence statistics if available
            confidence_stats = {}
            if hasattr(signals, 'confidence_values'):
                confidence_values = signals.confidence_values
                non_zero_confidence = confidence_values[confidence_values > 0]
                if len(non_zero_confidence) > 0:
                    confidence_stats = {
                        "average_confidence": float(non_zero_confidence.mean()),
                        "min_confidence": float(non_zero_confidence.min()),
                        "max_confidence": float(non_zero_confidence.max()),
                        "confidence_std": float(non_zero_confidence.std())
                    }
            
            # Prepare results with consistent date formatting
            results = {
                "trades": trades,
                "metrics": metrics,
                "performance": performance,
                "summary": self._generate_summary(performance, confidence_stats, minimum_confidence_threshold),
                "indicator_data": indicator_data,
                "dates": dates,
                "confidence_stats": confidence_stats,
                "minimum_confidence_threshold": minimum_confidence_threshold,
                "regime_filter_enabled": enable_regime_filter,
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
        indicators: List[Dict[str, Any]],
        adaptive_parameters: bool = True
    ) -> pd.DataFrame:
        """Get historical data with technical indicators (adaptive parameters)"""
        try:
            # Get historical data
            df = get_ohlc_data(ticker, start_date, end_date, timeframe)
            if df.empty:
                raise ValueError(f"No data available for {ticker}")

            # Calculate ATR for volatility normalization
            df['ATR'] = self.ta._calculate_atr(df, 14)
            df['Volatility'] = df['ATR'] / df['Close'] * 100
            
            # Calculate market regime indicators
            df['VIX_Proxy'] = df['High'].rolling(20).std() / df['Close'].rolling(20).mean() * 100
            df['Trend_Strength'] = abs(df['Close'].rolling(20).mean() - df['Close'].rolling(50).mean()) / df['Close']

            # Calculate indicators with adaptive parameters
            for indicator in indicators:
                try:
                    ind_type = indicator["type"].lower()
                    base_params = indicator.get("parameters", indicator.get("params", {}))
                    
                    # Apply adaptive parameter optimization
                    if adaptive_parameters:
                        params = self._optimize_indicator_parameters(df, ind_type, base_params)
                    else:
                        params = base_params

                    if ind_type == "rsi":
                        period = params.get("period", 14)
                        # Apply volatility-adjusted thresholds
                        if adaptive_parameters:
                            volatility_factor = df['Volatility'].rolling(20).mean()
                            df[f'RSI_{period}_Oversold'] = 30 - volatility_factor * 0.3
                            df[f'RSI_{period}_Overbought'] = 70 + volatility_factor * 0.3
                        
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
                        
                        # Adaptive standard deviation based on volatility regime
                        if adaptive_parameters:
                            volatility_regime = df['VIX_Proxy'].rolling(20).mean()
                            adaptive_std = num_std * (1 + volatility_regime / 100)
                            bb_data = self.ta._calculate_bollinger_bands(df, period, adaptive_std)
                        else:
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
        indicators: List[Dict[str, Any]],
        minimum_confidence_threshold: float = 30.0,
        confirmation_bars: int = 2,
        volume_confirmation: bool = True,
        adaptive_thresholds: bool = True
    ) -> pd.Series:
        """Generate trading signals with multi-condition confirmation"""
        try:
            # Create a DataFrame to store signals from each indicator
            all_signals = pd.DataFrame(index=df.index)
            signal_confidence = pd.DataFrame(index=df.index)
            
            # Calculate ATR for volatility-based adaptive thresholds
            if adaptive_thresholds and 'ATR' not in df.columns:
                df['ATR'] = self.ta._calculate_atr(df, 14)
            
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
                        
                        # Adaptive thresholds based on volatility
                        if adaptive_thresholds and 'ATR' in df.columns:
                            volatility_factor = df['ATR'] / df['Close'] * 100
                            oversold = 30 - volatility_factor.rolling(20).mean() * 0.5
                            overbought = 70 + volatility_factor.rolling(20).mean() * 0.5
                        else:
                            oversold = 30
                            overbought = 70
                        
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        # Generate base signals with confirmation and NaN filtering
                        for i in range(confirmation_bars, len(rsi)):
                            # Skip if any required values are NaN
                            if pd.isna(rsi.iloc[i]) or pd.isna(rsi.iloc[i-1]):
                                continue
                            
                            # Check for persistent conditions
                            rsi_window = rsi.iloc[i-confirmation_bars:i+1]
                            
                            # Skip if any values in the window are NaN
                            if rsi_window.isna().any():
                                continue
                            
                            # Get thresholds (handle NaN)
                            if isinstance(oversold, pd.Series):
                                oversold_val = oversold.iloc[i] if not pd.isna(oversold.iloc[i]) else 30
                                overbought_val = overbought.iloc[i] if not pd.isna(overbought.iloc[i]) else 70
                            else:
                                oversold_val = oversold
                                overbought_val = overbought
                            
                            # Buy signal: RSI oversold for multiple bars and turning up
                            if (rsi_window <= oversold_val).sum() >= confirmation_bars and \
                               rsi.iloc[i] > rsi.iloc[i-1]:
                                signals.iloc[i] = 1
                                confidence.iloc[i] = min(1.0, abs(oversold_val - rsi.iloc[i]) / 10)
                            
                            # Sell signal: RSI overbought for multiple bars and turning down
                            elif (rsi_window >= overbought_val).sum() >= confirmation_bars and \
                                 rsi.iloc[i] < rsi.iloc[i-1]:
                                signals.iloc[i] = -1
                                confidence.iloc[i] = min(1.0, abs(rsi.iloc[i] - overbought_val) / 10)
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "macd":
                        if "MACD" not in df.columns or "MACD_Signal" not in df.columns:
                            continue
                            
                        macd = df["MACD"]
                        signal_line = df["MACD_Signal"]
                        histogram = df["MACD_Hist"]
                        
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        # Enhanced MACD signals with histogram confirmation and NaN filtering
                        for i in range(confirmation_bars, len(macd)):
                            # Skip if any required values are NaN
                            if (pd.isna(macd.iloc[i]) or pd.isna(signal_line.iloc[i]) or 
                                pd.isna(histogram.iloc[i]) or pd.isna(macd.iloc[i-1]) or 
                                pd.isna(signal_line.iloc[i-1]) or pd.isna(histogram.iloc[i-1]) or
                                pd.isna(macd.iloc[i-confirmation_bars])):
                                continue
                            
                            # Bullish crossover with histogram confirmation
                            if (macd.iloc[i] > signal_line.iloc[i] and 
                                macd.iloc[i-1] <= signal_line.iloc[i-1] and
                                histogram.iloc[i] > histogram.iloc[i-1] and
                                macd.iloc[i] > macd.iloc[i-confirmation_bars]):
                                signals.iloc[i] = 1
                                # Safe confidence calculation
                                if abs(macd.iloc[i]) > 0:
                                    confidence.iloc[i] = min(1.0, abs(histogram.iloc[i]) / abs(macd.iloc[i]))
                                else:
                                    confidence.iloc[i] = 0.5
                            
                            # Bearish crossover with histogram confirmation
                            elif (macd.iloc[i] < signal_line.iloc[i] and 
                                  macd.iloc[i-1] >= signal_line.iloc[i-1] and
                                  histogram.iloc[i] < histogram.iloc[i-1] and
                                  macd.iloc[i] < macd.iloc[i-confirmation_bars]):
                                signals.iloc[i] = -1
                                # Safe confidence calculation
                                if abs(macd.iloc[i]) > 0:
                                    confidence.iloc[i] = min(1.0, abs(histogram.iloc[i]) / abs(macd.iloc[i]))
                                else:
                                    confidence.iloc[i] = 0.5
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
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
            
            # Enhanced signal aggregation with confidence weighting
            if len(all_signals.columns) > 1:
                # Calculate weighted agreement based on signal confidence
                total_indicators = len(indicators)
                weighted_buy_score = pd.Series(0.0, index=df.index)
                weighted_sell_score = pd.Series(0.0, index=df.index)
                
                for col in all_signals.columns:
                    signal_col = all_signals[col]
                    confidence_col = signal_confidence.get(col, pd.Series(1.0, index=df.index))
                    
                    # Weight signals by confidence
                    weighted_buy_score += (signal_col == 1) * confidence_col
                    weighted_sell_score += (signal_col == -1) * confidence_col
                
                # Normalize by maximum possible score
                max_score = total_indicators
                buy_agreement = weighted_buy_score / max_score
                sell_agreement = weighted_sell_score / max_score
                
                # Volume confirmation if enabled
                if volume_confirmation and 'Volume' in df.columns:
                    volume_ma = df['Volume'].rolling(20).mean()
                    volume_confirmation_factor = df['Volume'] / volume_ma
                    
                    # Enhance signals with above-average volume
                    buy_agreement *= np.where(volume_confirmation_factor > 1.2, 1.2, 1.0)
                    sell_agreement *= np.where(volume_confirmation_factor > 1.2, 1.2, 1.0)
                
                # Generate final signals with relaxed adaptive threshold
                final_signals = pd.Series(0, index=df.index)
                # Convert percentage to decimal for comparison
                signal_threshold = minimum_confidence_threshold / 100.0
                
                # Add confidence tracking for each signal
                signal_confidence_values = pd.Series(0.0, index=df.index)
                
                final_signals[buy_agreement >= signal_threshold] = 1
                final_signals[sell_agreement >= signal_threshold] = -1
                
                # Store confidence values for analysis
                signal_confidence_values[buy_agreement >= signal_threshold] = buy_agreement[buy_agreement >= signal_threshold]
                signal_confidence_values[sell_agreement >= signal_threshold] = sell_agreement[sell_agreement >= signal_threshold]
                
                # Filter out conflicting signals
                conflicting = (buy_agreement >= signal_threshold) & (sell_agreement >= signal_threshold)
                final_signals[conflicting] = 0
                
                # Log enhanced signal statistics with confidence threshold info
                buy_signals = (final_signals == 1).sum()
                sell_signals = (final_signals == -1).sum()
                avg_buy_confidence = weighted_buy_score[final_signals == 1].mean() if buy_signals > 0 else 0
                avg_sell_confidence = weighted_sell_score[final_signals == -1].mean() if sell_signals > 0 else 0
                
                logger.info(f"Enhanced signals with {minimum_confidence_threshold:.1f}% threshold - "
                          f"Buy: {buy_signals} (avg confidence: {avg_buy_confidence:.2f}), "
                          f"Sell: {sell_signals} (avg confidence: {avg_sell_confidence:.2f})")
                
                # Store confidence data in final_signals for later use
                final_signals.confidence_values = signal_confidence_values
                
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

    def _calculate_adaptive_position_size(
        self,
        current_capital: float,
        base_position_size: float,
        df: pd.DataFrame,
        current_index: int,
        trades: List[Dict[str, Any]],
        position_sizing_method: str = "fixed",
        kelly_fraction: Optional[float] = None,
        volatility_adjustment: bool = True,
        equity_curve_filter: bool = True,
        consecutive_losses: int = 0
    ) -> float:
        """Calculate adaptive position size based on multiple factors"""
        try:
            base_size = current_capital * (base_position_size / 100)
            
            # Start with base size
            adjusted_size = base_size
            
            # 1. Position sizing method adjustment
            if position_sizing_method == "kelly" and len(trades) > 10:
                kelly_optimal = self._calculate_enhanced_kelly_fraction(trades)
                if kelly_fraction:
                    kelly_optimal *= kelly_fraction  # Apply fraction of Kelly
                adjusted_size = current_capital * kelly_optimal
            
            # 2. Volatility adjustment
            if volatility_adjustment and current_index >= 20:
                volatility_factor = self._calculate_volatility_adjustment(
                    df, current_index
                )
                adjusted_size *= volatility_factor
            
            # 3. Equity curve filter
            if equity_curve_filter and len(trades) > 5:
                equity_filter = self._calculate_equity_curve_filter(
                    current_capital, trades
                )
                adjusted_size *= equity_filter
            
            # 4. Consecutive loss adjustment
            if consecutive_losses > 0:
                loss_penalty = max(0.5, 1 - (consecutive_losses * 0.1))
                adjusted_size *= loss_penalty
            
            # 5. Drawdown protection
            if len(trades) > 0:
                drawdown_factor = self._calculate_drawdown_protection(
                    current_capital, trades[0].get('initial_capital', current_capital)
                )
                adjusted_size *= drawdown_factor
            
            # Ensure reasonable bounds
            min_size = current_capital * 0.01  # Minimum 1%
            max_size = current_capital * 0.25  # Maximum 25%
            
            return max(min_size, min(max_size, adjusted_size))
            
        except Exception as e:
            logger.error(f"Error calculating adaptive position size: {str(e)}")
            return current_capital * (base_position_size / 100)
    
    def _calculate_enhanced_kelly_fraction(
        self,
        trades: List[Dict[str, Any]]
    ) -> float:
        """Calculate enhanced Kelly fraction with improvements"""
        if not trades or len(trades) < 10:
            return 0.05  # Conservative default
            
        returns = [t["pnl_pct"] / 100 for t in trades]
        
        # Calculate basic Kelly
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        
        if not losses or not wins:
            return 0.05
            
        win_prob = len(wins) / len(returns)
        avg_win = np.mean(wins)
        avg_loss = abs(np.mean(losses))
        
        if avg_loss == 0:
            return 0.05
            
        # Enhanced Kelly with risk adjustments
        basic_kelly = (win_prob * avg_win - (1 - win_prob) * avg_loss) / avg_win
        
        # Adjust for skewness (penalize negative skew)
        skewness = self._calculate_skewness(returns)
        skew_adjustment = 1 - max(0, -skewness * 0.1)
        
        # Adjust for tail risk (penalize large losses)
        tail_risk = np.percentile([abs(r) for r in losses], 95) if losses else 0
        tail_adjustment = 1 - min(0.5, tail_risk)
        
        # Adjust for volatility
        volatility = np.std(returns)
        vol_adjustment = 1 / (1 + volatility * 2)
        
        enhanced_kelly = basic_kelly * skew_adjustment * tail_adjustment * vol_adjustment
        
        # Conservative bounds
        return max(0.01, min(0.2, enhanced_kelly))
    
    def _calculate_volatility_adjustment(
        self,
        df: pd.DataFrame,
        current_index: int,
        lookback: int = 20
    ) -> float:
        """Calculate position size adjustment based on volatility"""
        try:
            start_idx = max(0, current_index - lookback)
            recent_returns = df['Close'].iloc[start_idx:current_index].pct_change().dropna()
            
            if len(recent_returns) < 5:
                return 1.0
                
            current_vol = recent_returns.std()
            long_term_vol = df['Close'].iloc[:current_index].pct_change().std()
            
            if long_term_vol == 0:
                return 1.0
                
            vol_ratio = current_vol / long_term_vol
            
            # Reduce size when volatility is high
            if vol_ratio > 1.5:
                return 0.7  # Reduce by 30%
            elif vol_ratio > 1.2:
                return 0.85  # Reduce by 15%
            elif vol_ratio < 0.8:
                return 1.15  # Increase by 15%
            else:
                return 1.0
                
        except Exception:
            return 1.0
    
    def _calculate_equity_curve_filter(
        self,
        current_capital: float,
        trades: List[Dict[str, Any]],
        lookback: int = 10
    ) -> float:
        """Filter position size based on equity curve trend"""
        try:
            if len(trades) < lookback:
                return 1.0
                
            recent_trades = trades[-lookback:]
            initial_capital = trades[0].get('initial_capital', current_capital)
            
            # Calculate equity curve points
            equity_points = [initial_capital]
            running_capital = initial_capital
            
            for trade in recent_trades:
                running_capital += trade.get('pnl', 0)
                equity_points.append(running_capital)
            
            # Calculate trend (simple linear regression slope)
            x = np.arange(len(equity_points))
            slope = np.polyfit(x, equity_points, 1)[0]
            
            # Adjust position size based on trend
            if slope > 0:
                return 1.1  # Increase size when equity trending up
            elif slope < -initial_capital * 0.01:  # Significant downtrend
                return 0.8  # Reduce size when equity trending down
            else:
                return 1.0
                
        except Exception:
            return 1.0
    
    def _calculate_drawdown_protection(
        self,
        current_capital: float,
        initial_capital: float
    ) -> float:
        """Reduce position size based on current drawdown"""
        try:
            if initial_capital <= 0:
                return 1.0
                
            drawdown = (initial_capital - current_capital) / initial_capital
            
            if drawdown > 0.15:  # 15% drawdown
                return 0.5  # Reduce to 50%
            elif drawdown > 0.10:  # 10% drawdown
                return 0.7  # Reduce to 70%
            elif drawdown > 0.05:  # 5% drawdown
                return 0.85  # Reduce to 85%
            else:
                return 1.0
                
        except Exception:
            return 1.0
    
    def _calculate_skewness(self, returns: List[float]) -> float:
        """Calculate skewness of returns"""
        try:
            if len(returns) < 3:
                return 0
                
            returns_array = np.array(returns)
            mean_return = np.mean(returns_array)
            std_return = np.std(returns_array)
            
            if std_return == 0:
                return 0
                
            skew = np.mean(((returns_array - mean_return) / std_return) ** 3)
            return skew
            
        except Exception:
            return 0

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
                
                # Check for new entry signals with improved logic
                if signal == 1 and (max_positions is None or len(current_positions) < max_positions):
                    # Enhanced entry conditions
                    should_enter = self._validate_entry_conditions(
                        df, i, current_capital, consecutive_loss_limit, 
                        metrics['current_consecutive_losses'], daily_loss_limit,
                        metrics['daily_pnl'], date_str
                    )
                    
                    if should_enter:
                        # Calculate adaptive position size
                        size = self._calculate_adaptive_position_size(
                            current_capital=current_capital,
                            base_position_size=position_size,
                            df=df,
                            current_index=i,
                            trades=trades,
                            position_sizing_method=position_sizing_method,
                            kelly_fraction=kelly_fraction,
                            volatility_adjustment=True,
                            equity_curve_filter=True,
                            consecutive_losses=metrics['current_consecutive_losses']
                        )
                        
                        # Check margin requirements
                        if margin_requirement:
                            required_margin = size * (margin_requirement / 100)
                            if required_margin > current_capital:
                                continue
                        
                        # Improved entry price logic with gap analysis
                        entry_price = self._calculate_optimal_entry_price(df, i)
                        
                        # Get signal confidence if available
                        signal_confidence = 0.5  # Default
                        if hasattr(signals, 'confidence_values') and i < len(signals.confidence_values):
                            signal_confidence = signals.confidence_values.iloc[i]
                        
                        # Add new position with enhanced tracking
                        new_position = {
                            'entry_date': date_str,
                            'entry_price': float(entry_price),
                            'size': float(size / entry_price),
                            'signal_confidence': float(signal_confidence),
                            'entry_reason': 'signal_buy',
                            'market_conditions': self._capture_market_conditions(df, i)
                        }
                        current_positions.append(new_position)
                        metrics['positions'].append(new_position)
                        logger.info(f"Opened new position at {date_str}: price={entry_price:.2f}, size={size/entry_price:.2f}, confidence={signal_confidence:.2f}")
                
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
            
            # Calculate additional metrics
            sortino_ratio = self._calculate_sortino_ratio(daily_returns)
            calmar_ratio = self._calculate_calmar_ratio(annualized_return, max_drawdown)
            profit_factor = self._calculate_profit_factor(trades)
            
            # Calculate comprehensive trading metrics
            comprehensive_metrics = self._calculate_comprehensive_metrics(trades, daily_returns, initial_capital)
            
            # Calculate strategy efficiency metrics
            efficiency_metrics = self._calculate_strategy_efficiency_metrics(trades, equity_curve)
            
            # Ensure all metrics are finite
            metrics_dict = {
                'total_return': float(np.nan_to_num(total_return, 0.0)),
                'annualized_return': float(np.nan_to_num(annualized_return, 0.0)),
                'sharpe_ratio': float(np.nan_to_num(sharpe_ratio, 0.0)),
                'sortino_ratio': float(np.nan_to_num(sortino_ratio, 0.0)),
                'calmar_ratio': float(np.nan_to_num(calmar_ratio, 0.0)),
                'max_drawdown': float(np.nan_to_num(max_drawdown, 0.0)),
                'win_rate': float(np.nan_to_num(win_rate, 0.0)),
                'profit_factor': float(np.nan_to_num(profit_factor, 0.0)),
                'total_trades': int(total_trades),
                'winning_trades': int(winning_trades),
                'losing_trades': int(total_trades - winning_trades),
                'daily_returns': daily_returns.tolist(),
                'daily_equity': equity_curve.tolist(),
                'volatility': float(daily_returns.std() * np.sqrt(252)) if len(daily_returns) > 1 else 0.0,
                # Add comprehensive metrics
                'comprehensive_metrics': comprehensive_metrics,
                'efficiency_metrics': efficiency_metrics
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

    def _generate_summary(self, performance: Dict[str, Any], confidence_stats: Dict[str, Any] = None, minimum_confidence_threshold: float = 30.0) -> str:
        """Generate a comprehensive summary of backtest results"""
        summary = []
        
        # Strategy Configuration
        summary.append("Strategy Configuration:")
        summary.append(f"- Minimum Confidence Threshold: {minimum_confidence_threshold:.1f}%")
        if confidence_stats:
            summary.append(f"- Average Signal Confidence: {confidence_stats.get('average_confidence', 0) * 100:.1f}%")
            summary.append(f"- Signal Confidence Range: {confidence_stats.get('min_confidence', 0) * 100:.1f}% - {confidence_stats.get('max_confidence', 0) * 100:.1f}%")
        
        # Overall Performance
        summary.append("\nOverall Performance:")
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
        
        # Add comprehensive metrics if available
        comp_metrics = performance.get('comprehensive_metrics', {})
        if comp_metrics:
            summary.append(f"- Average Win: ${comp_metrics.get('average_win', 0):.2f}")
            summary.append(f"- Average Loss: ${comp_metrics.get('average_loss', 0):.2f}")
            summary.append(f"- Win/Loss Ratio: {comp_metrics.get('win_loss_ratio', 0):.2f}")
            summary.append(f"- Expectancy: ${comp_metrics.get('expectancy', 0):.2f}")
            summary.append(f"- Average Trade Duration: {comp_metrics.get('average_trade_duration', 0):.1f} days")
            summary.append(f"- Max Consecutive Wins: {comp_metrics.get('max_consecutive_wins', 0)}")
            summary.append(f"- Max Consecutive Losses: {comp_metrics.get('max_consecutive_losses', 0)}")
            summary.append(f"- VaR (95%): {comp_metrics.get('var_95', 0):.2f}%")
        else:
            summary.append(f"- Average Trade Duration: {performance.get('avg_trade_duration', 0):.1f} days")
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
        
        # Strategy Efficiency Metrics
        eff_metrics = performance.get('efficiency_metrics', {})
        if eff_metrics:
            summary.append("\nStrategy Efficiency:")
            summary.append(f"- Market Exposure: {eff_metrics.get('market_exposure', 0) * 100:.1f}%")
            summary.append(f"- Return per Trade: ${eff_metrics.get('return_per_trade', 0):.2f}")
            summary.append(f"- Win Efficiency: {eff_metrics.get('win_efficiency', 0) * 100:.1f}%")
            summary.append(f"- Average Recovery Time: {eff_metrics.get('average_recovery_time', 0):.1f} days")
            summary.append(f"- Equity Curve Linearity: {eff_metrics.get('equity_curve_linearity', 0):.3f}")
            summary.append(f"- Consistency Score: {eff_metrics.get('consistency_score', 0):.3f}")
        
        # Benchmark Comparison (if available)
        if performance.get('benchmark_correlation', 0) != 0:
            summary.append("\nBenchmark Comparison:")
            summary.append(f"- Correlation: {performance.get('benchmark_correlation', 0):.2f}")
            summary.append(f"- Beta: {performance.get('benchmark_beta', 0):.2f}")
            summary.append(f"- Alpha: {performance.get('benchmark_alpha', 0):.2f}%")
        
        return "\n".join(summary)
    
    def _calculate_sortino_ratio(self, daily_returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (downside deviation)"""
        try:
            if len(daily_returns) == 0:
                return 0.0
            
            excess_returns = daily_returns - (risk_free_rate / 252)
            downside_returns = excess_returns[excess_returns < 0]
            
            if len(downside_returns) == 0 or downside_returns.std() == 0:
                return 0.0
            
            return float(np.sqrt(252) * excess_returns.mean() / downside_returns.std())
        except Exception:
            return 0.0
    
    def _calculate_calmar_ratio(self, annualized_return: float, max_drawdown: float) -> float:
        """Calculate Calmar ratio (annual return / max drawdown)"""
        try:
            if max_drawdown == 0:
                return 0.0
            return float(annualized_return / max_drawdown)
        except Exception:
            return 0.0
    
    def _calculate_profit_factor(self, trades: List[Dict[str, Any]]) -> float:
        """Calculate profit factor (gross profit / gross loss)"""
        try:
            if not trades:
                return 0.0
            
            wins = [t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]
            losses = [t['pnl_pct'] for t in trades if t['pnl_pct'] <= 0]
            
            total_wins = sum(wins) if wins else 0
            total_losses = abs(sum(losses)) if losses else 0
            
            if total_losses == 0:
                return float('inf') if total_wins > 0 else 0.0
            
            return float(total_wins / total_losses)
        except Exception:
            return 0.0
    
    def _calculate_comprehensive_metrics(self, trades: List[Dict[str, Any]], daily_returns: pd.Series, initial_capital: float) -> Dict[str, Any]:
        """Calculate comprehensive trading performance metrics"""
        try:
            if not trades:
                return {}
            
            # Trade analysis
            winning_trades = [t for t in trades if t['pnl'] > 0]
            losing_trades = [t for t in trades if t['pnl'] <= 0]
            
            # Basic trade metrics
            avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
            avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0
            
            # Risk-adjusted metrics
            expectancy = (len(winning_trades) / len(trades) * abs(avg_win) + 
                         len(losing_trades) / len(trades) * avg_loss) if trades else 0
            
            # Trade duration analysis
            trade_durations = []
            for trade in trades:
                try:
                    entry_date = pd.to_datetime(trade['entry_date'])
                    exit_date = pd.to_datetime(trade['exit_date'])
                    duration = (exit_date - entry_date).days
                    trade_durations.append(duration)
                except:
                    continue
            
            # Consecutive wins/losses
            consecutive_wins, consecutive_losses, current_streak = self._calculate_streaks(trades)
            
            # Return distribution analysis
            trade_returns = [t['pnl_pct'] for t in trades]
            
            metrics = {
                # Trade Statistics
                "average_win": float(avg_win),
                "average_loss": float(avg_loss),
                "win_loss_ratio": float(abs(avg_win / avg_loss)) if avg_loss != 0 else float('inf'),
                "expectancy": float(expectancy),
                "largest_win": float(max([t['pnl'] for t in trades])) if trades else 0,
                "largest_loss": float(min([t['pnl'] for t in trades])) if trades else 0,
                
                # Duration Metrics
                "average_trade_duration": float(np.mean(trade_durations)) if trade_durations else 0,
                "median_trade_duration": float(np.median(trade_durations)) if trade_durations else 0,
                "min_trade_duration": int(min(trade_durations)) if trade_durations else 0,
                "max_trade_duration": int(max(trade_durations)) if trade_durations else 0,
                
                # Streak Analysis
                "max_consecutive_wins": int(consecutive_wins),
                "max_consecutive_losses": int(consecutive_losses),
                "current_streak": current_streak,
                
                # Return Distribution
                "trade_return_mean": float(np.mean(trade_returns)) if trade_returns else 0,
                "trade_return_std": float(np.std(trade_returns)) if trade_returns else 0,
                "trade_return_skewness": float(self._calculate_skewness(trade_returns)),
                "trade_return_kurtosis": float(self._calculate_kurtosis(trade_returns)),
                
                # Risk Metrics
                "var_95": float(np.percentile(trade_returns, 5)) if trade_returns else 0,
                "cvar_95": float(np.mean([r for r in trade_returns if r <= np.percentile(trade_returns, 5)])) if trade_returns else 0,
                
                # Recovery Factor
                "recovery_factor": float(expectancy / abs(min(trade_returns))) if trade_returns and min(trade_returns) < 0 else 0
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating comprehensive metrics: {str(e)}")
            return {}
    
    def _calculate_strategy_efficiency_metrics(self, trades: List[Dict[str, Any]], equity_curve: pd.Series) -> Dict[str, Any]:
        """Calculate strategy efficiency and optimization metrics"""
        try:
            if not trades:
                return {}
            
            # Market exposure analysis
            total_days = len(equity_curve)
            days_in_market = len([t for t in trades if t['pnl'] != 0])  # Approximate
            market_exposure = (days_in_market / total_days) if total_days > 0 else 0
            
            # Efficiency ratios
            total_return = (equity_curve.iloc[-1] - equity_curve.iloc[0]) / equity_curve.iloc[0]
            buy_hold_return = total_return  # Simplified - would need benchmark for accurate calculation
            
            # Trade efficiency
            winning_trades = [t for t in trades if t['pnl'] > 0]
            total_winning_pnl = sum([t['pnl'] for t in winning_trades])
            total_pnl = sum([t['pnl'] for t in trades])
            
            # Drawdown analysis
            running_max = equity_curve.expanding().max()
            drawdowns = (equity_curve - running_max) / running_max
            
            # Recovery analysis
            recovery_times = []
            in_drawdown = False
            drawdown_start = None
            
            for i, dd in enumerate(drawdowns):
                if dd < -0.01 and not in_drawdown:  # Entering drawdown (>1%)
                    in_drawdown = True
                    drawdown_start = i
                elif dd >= 0 and in_drawdown:  # Recovering from drawdown
                    in_drawdown = False
                    if drawdown_start is not None:
                        recovery_times.append(i - drawdown_start)
            
            metrics = {
                # Efficiency Metrics
                "market_exposure": float(market_exposure),
                "return_per_trade": float(total_pnl / len(trades)) if trades else 0,
                "profit_per_day_in_market": float(total_pnl / days_in_market) if days_in_market > 0 else 0,
                
                # Win Efficiency
                "win_contribution": float(total_winning_pnl / total_pnl) if total_pnl != 0 else 0,
                "win_efficiency": float(len(winning_trades) / len(trades)) if trades else 0,
                
                # Drawdown Recovery
                "average_recovery_time": float(np.mean(recovery_times)) if recovery_times else 0,
                "max_recovery_time": int(max(recovery_times)) if recovery_times else 0,
                "drawdown_frequency": float(len(recovery_times) / total_days) if total_days > 0 else 0,
                
                # Risk-Adjusted Efficiency
                "risk_adjusted_return": float(total_return / equity_curve.std()) if equity_curve.std() > 0 else 0,
                "return_to_max_drawdown": float(total_return / abs(drawdowns.min())) if drawdowns.min() < 0 else 0,
                
                # Stability Metrics
                "equity_curve_linearity": float(self._calculate_linearity(equity_curve)),
                "consistency_score": float(self._calculate_consistency_score(trades))
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating efficiency metrics: {str(e)}")
            return {}
    
    def _calculate_streaks(self, trades: List[Dict[str, Any]]) -> tuple:
        """Calculate consecutive wins and losses"""
        if not trades:
            return 0, 0, 0
        
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0
        current_streak = 0
        
        for trade in trades:
            if trade['pnl'] > 0:
                current_wins += 1
                current_losses = 0
                current_streak = current_wins
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                current_streak = -current_losses
                max_losses = max(max_losses, current_losses)
        
        return max_wins, max_losses, current_streak
    
    def _calculate_kurtosis(self, returns: List[float]) -> float:
        """Calculate kurtosis of returns"""
        try:
            if len(returns) < 4:
                return 0
            
            returns_array = np.array(returns)
            mean_return = np.mean(returns_array)
            std_return = np.std(returns_array)
            
            if std_return == 0:
                return 0
            
            kurt = np.mean(((returns_array - mean_return) / std_return) ** 4) - 3
            return kurt
            
        except Exception:
            return 0
    
    def _calculate_linearity(self, equity_curve: pd.Series) -> float:
        """Calculate how linear the equity curve is (R-squared of linear regression)"""
        try:
            if len(equity_curve) < 3:
                return 0
            
            x = np.arange(len(equity_curve))
            y = equity_curve.values
            
            # Calculate R-squared
            correlation_matrix = np.corrcoef(x, y)
            correlation = correlation_matrix[0, 1]
            r_squared = correlation ** 2
            
            return r_squared
            
        except Exception:
            return 0
    
    def _calculate_consistency_score(self, trades: List[Dict[str, Any]]) -> float:
        """Calculate consistency score based on trade distribution"""
        try:
            if not trades or len(trades) < 5:
                return 0
            
            # Group trades into time periods and calculate returns for each period
            trade_returns = [t['pnl_pct'] for t in trades]
            
            # Calculate rolling windows of trade performance
            window_size = max(5, len(trades) // 4)
            period_returns = []
            
            for i in range(0, len(trade_returns) - window_size + 1, window_size):
                period_return = sum(trade_returns[i:i + window_size])
                period_returns.append(period_return)
            
            if len(period_returns) < 2:
                return 0
            
            # Consistency is inverse of coefficient of variation
            mean_return = np.mean(period_returns)
            std_return = np.std(period_returns)
            
            if mean_return == 0 or std_return == 0:
                return 0
            
            cv = abs(std_return / mean_return)
            consistency = 1 / (1 + cv)  # Scale to 0-1
            
            return consistency
            
        except Exception:
            return 0
    
    def _validate_entry_conditions(self, df: pd.DataFrame, current_index: int, current_capital: float,
                                 consecutive_loss_limit: Optional[int], current_consecutive_losses: int,
                                 daily_loss_limit: Optional[float], daily_pnl: Dict, date_str: str) -> bool:
        """Validate additional entry conditions beyond signal"""
        try:
            # Check consecutive loss limit
            if consecutive_loss_limit and current_consecutive_losses >= consecutive_loss_limit:
                return False
            
            # Check daily loss limit
            if daily_loss_limit:
                daily_loss_pct = (daily_pnl.get(date_str, 0) / current_capital) * 100
                if daily_loss_pct <= -daily_loss_limit:
                    return False
            
            # Check for market conditions (avoid entries during high volatility spikes)
            if current_index >= 5:
                recent_volatility = df['Close'].iloc[current_index-5:current_index].pct_change().std()
                historical_volatility = df['Close'].iloc[:current_index].pct_change().std()
                
                if recent_volatility > historical_volatility * 3:  # Very high volatility
                    return False
            
            # Check for gap conditions (avoid large gaps)
            if current_index > 0:
                prev_close = df['Close'].iloc[current_index - 1]
                current_open = df['Open'].iloc[current_index]
                gap = abs(current_open - prev_close) / prev_close
                
                if gap > 0.05:  # 5% gap - too risky
                    return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Error in entry validation: {str(e)}")
            return True  # Default to allow entry if validation fails
    
    def _calculate_optimal_entry_price(self, df: pd.DataFrame, current_index: int) -> float:
        """Calculate optimal entry price considering market microstructure"""
        try:
            current_row = df.iloc[current_index]
            
            # Use next bar's open if available (more realistic)
            if current_index + 1 < len(df):
                next_open = df['Open'].iloc[current_index + 1]
                current_close = current_row['Close']
                
                # Check for gap
                gap = (next_open - current_close) / current_close
                
                # If small gap, use open price
                if abs(gap) < 0.02:  # Less than 2% gap
                    return next_open
                else:
                    # For large gaps, use a price between close and open
                    return current_close + (gap * 0.5 * current_close)
            else:
                # Last bar - use close price
                return current_row['Close']
                
        except Exception as e:
            logger.warning(f"Error calculating entry price: {str(e)}")
            return df['Close'].iloc[current_index]
    
    def _capture_market_conditions(self, df: pd.DataFrame, current_index: int) -> Dict[str, float]:
        """Capture market conditions at the time of entry"""
        try:
            conditions = {}
            
            if current_index >= 20:  # Need sufficient history
                recent_data = df.iloc[current_index-20:current_index+1]
                
                # Volatility regime
                conditions['volatility'] = recent_data['Close'].pct_change().std()
                
                # Trend strength
                sma_short = recent_data['Close'].rolling(5).mean().iloc[-1]
                sma_long = recent_data['Close'].rolling(20).mean().iloc[-1]
                conditions['trend_strength'] = (sma_short - sma_long) / sma_long
                
                # Volume profile
                avg_volume = recent_data['Volume'].mean()
                current_volume = recent_data['Volume'].iloc[-1]
                conditions['volume_ratio'] = current_volume / avg_volume if avg_volume > 0 else 1.0
                
                # Price momentum
                conditions['momentum'] = recent_data['Close'].pct_change(5).iloc[-1]
                
            return conditions
            
        except Exception as e:
            logger.warning(f"Error capturing market conditions: {str(e)}")
            return {}
    
    def _get_multi_timeframe_data_with_indicators(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        base_timeframe: str,
        higher_timeframes: List[str],
        indicators: List[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Get data with indicators across multiple timeframes"""
        try:
            # Get base timeframe data
            base_df = self._get_data_with_indicators(ticker, start_date, end_date, base_timeframe, indicators)
            if base_df.empty:
                return base_df
            
            # Get higher timeframe data and merge
            for htf in higher_timeframes:
                try:
                    htf_df = self._get_data_with_indicators(ticker, start_date, end_date, htf, indicators)
                    if htf_df.empty:
                        continue
                    
                    # Resample higher timeframe data to base timeframe
                    htf_resampled = self._resample_to_base_timeframe(htf_df, base_df.index, htf)
                    
                    # Merge with base dataframe using suffix
                    suffix = f"_{htf}"
                    for col in htf_resampled.columns:
                        if col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
                            base_df[f"{col}{suffix}"] = htf_resampled[col]
                    
                    logger.info(f"Added {htf} timeframe indicators to base dataframe")
                
                except Exception as e:
                    logger.error(f"Error processing {htf} timeframe: {str(e)}")
                    continue
            
            return base_df
            
        except Exception as e:
            logger.error(f"Error in multi-timeframe data preparation: {str(e)}")
            return pd.DataFrame()
    
    def _resample_to_base_timeframe(self, htf_df: pd.DataFrame, base_index: pd.Index, htf: str) -> pd.DataFrame:
        """Resample higher timeframe data to base timeframe using forward fill"""
        try:
            # Create a new dataframe with base timeframe index
            resampled_df = pd.DataFrame(index=base_index)
            
            # Forward fill higher timeframe data
            for col in htf_df.columns:
                if col not in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    # Use forward fill to propagate HTF values
                    resampled_series = htf_df[col].reindex(base_index, method='ffill')
                    resampled_df[col] = resampled_series
            
            return resampled_df
            
        except Exception as e:
            logger.error(f"Error resampling {htf} data: {str(e)}")
            return pd.DataFrame(index=base_index)
    
    def _generate_multi_timeframe_signals(
        self,
        df: pd.DataFrame,
        indicators: List[Dict[str, Any]],
        base_timeframe: str,
        higher_timeframes: List[str],
        trend_timeframe: Optional[str] = None,
        minimum_confidence_threshold: float = 30.0
    ) -> pd.Series:
        """Generate signals using multi-timeframe analysis"""
        try:
            # Get base timeframe signals
            base_signals = self._generate_signals(df, indicators, minimum_confidence_threshold)
            
            # Determine trend from higher timeframe
            trend_direction = self._determine_multi_timeframe_trend(
                df, higher_timeframes, trend_timeframe or higher_timeframes[0]
            )
            
            # Filter base signals based on higher timeframe confluence
            filtered_signals = self._apply_timeframe_confluence(
                base_signals, df, higher_timeframes, trend_direction
            )
            
            return filtered_signals
            
        except Exception as e:
            logger.error(f"Error in multi-timeframe signal generation: {str(e)}")
            return pd.Series(index=df.index, data=0)
    
    def _determine_multi_timeframe_trend(
        self,
        df: pd.DataFrame,
        higher_timeframes: List[str],
        trend_timeframe: str
    ) -> pd.Series:
        """Determine trend direction from higher timeframe"""
        try:
            trend_direction = pd.Series(0, index=df.index)  # 1=uptrend, -1=downtrend, 0=neutral
            
            # Look for trend indicators in the specified timeframe
            suffix = f"_{trend_timeframe}"
            
            # Use EMA crossover for trend determination
            ema_fast_col = f"EMA_12{suffix}"
            ema_slow_col = f"EMA_26{suffix}"
            
            if ema_fast_col in df.columns and ema_slow_col in df.columns:
                ema_fast = df[ema_fast_col]
                ema_slow = df[ema_slow_col]
                
                trend_direction = pd.Series(0, index=df.index)
                trend_direction[ema_fast > ema_slow] = 1  # Uptrend
                trend_direction[ema_fast < ema_slow] = -1  # Downtrend
            
            # Alternative: Use MACD for trend
            elif f"MACD{suffix}" in df.columns:
                macd = df[f"MACD{suffix}"]
                trend_direction[macd > 0] = 1
                trend_direction[macd < 0] = -1
            
            return trend_direction
            
        except Exception as e:
            logger.error(f"Error determining multi-timeframe trend: {str(e)}")
            return pd.Series(0, index=df.index)
    
    def _apply_timeframe_confluence(
        self,
        base_signals: pd.Series,
        df: pd.DataFrame,
        higher_timeframes: List[str],
        trend_direction: pd.Series
    ) -> pd.Series:
        """Apply confluence rules across timeframes"""
        try:
            filtered_signals = base_signals.copy()
            
            # Rule 1: Only take buy signals in uptrend, sell signals in downtrend
            filtered_signals[(base_signals == 1) & (trend_direction != 1)] = 0
            filtered_signals[(base_signals == -1) & (trend_direction != -1)] = 0
            
            # Rule 2: Check for momentum alignment across timeframes
            for htf in higher_timeframes:
                suffix = f"_{htf}"
                
                # RSI momentum filter
                rsi_col = f"RSI_14{suffix}"
                if rsi_col in df.columns:
                    rsi_htf = df[rsi_col]
                    
                    # Filter buy signals when HTF RSI is overbought
                    filtered_signals[(filtered_signals == 1) & (rsi_htf > 80)] = 0
                    # Filter sell signals when HTF RSI is oversold
                    filtered_signals[(filtered_signals == -1) & (rsi_htf < 20)] = 0
                
                # MACD momentum filter
                macd_col = f"MACD{suffix}"
                macd_signal_col = f"MACD_Signal{suffix}"
                if macd_col in df.columns and macd_signal_col in df.columns:
                    macd_htf = df[macd_col]
                    macd_signal_htf = df[macd_signal_col]
                    
                    # Require MACD alignment
                    macd_bullish = macd_htf > macd_signal_htf
                    macd_bearish = macd_htf < macd_signal_htf
                    
                    filtered_signals[(filtered_signals == 1) & (~macd_bullish)] = 0
                    filtered_signals[(filtered_signals == -1) & (~macd_bearish)] = 0
            
            # Log filtering results
            original_buy = (base_signals == 1).sum()
            original_sell = (base_signals == -1).sum()
            filtered_buy = (filtered_signals == 1).sum()
            filtered_sell = (filtered_signals == -1).sum()
            
            logger.info(f"Multi-timeframe filtering: Buy {original_buy}->{filtered_buy}, "
                       f"Sell {original_sell}->{filtered_sell}")
            
            return filtered_signals
            
        except Exception as e:
            logger.error(f"Error applying timeframe confluence: {str(e)}")
            return base_signals
    
    def _optimize_indicator_parameters(
        self,
        df: pd.DataFrame,
        indicator_type: str,
        base_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimize indicator parameters based on market conditions"""
        try:
            optimized_params = base_params.copy()
            
            # Get current market volatility
            current_volatility = df['Volatility'].rolling(20).mean().iloc[-1] if len(df) > 20 else 20
            
            # Get trend strength
            trend_strength = df['Trend_Strength'].rolling(20).mean().iloc[-1] if len(df) > 20 else 0.02
            
            if indicator_type == "rsi":
                base_period = base_params.get("period", 14)
                # Shorter periods in volatile markets, longer in stable markets
                if current_volatility > 25:  # High volatility
                    optimized_params["period"] = max(10, int(base_period * 0.8))
                elif current_volatility < 15:  # Low volatility
                    optimized_params["period"] = min(21, int(base_period * 1.2))
                    
            elif indicator_type == "macd":
                fast_period = base_params.get("fastperiod", 12)
                slow_period = base_params.get("slowperiod", 26)
                signal_period = base_params.get("signalperiod", 9)
                
                # Adjust based on market trend strength
                if trend_strength > 0.05:  # Strong trending market
                    optimized_params["fastperiod"] = max(8, int(fast_period * 0.8))
                    optimized_params["slowperiod"] = max(20, int(slow_period * 0.8))
                elif trend_strength < 0.02:  # Range-bound market
                    optimized_params["fastperiod"] = min(15, int(fast_period * 1.2))
                    optimized_params["slowperiod"] = min(35, int(slow_period * 1.2))
                    
            elif indicator_type == "bollinger":
                base_period = base_params.get("period", 20)
                base_std = base_params.get("num_std", 2)
                
                # Adjust period based on volatility
                if current_volatility > 25:
                    optimized_params["period"] = max(15, int(base_period * 0.8))
                elif current_volatility < 15:
                    optimized_params["period"] = min(30, int(base_period * 1.2))
                    
            elif indicator_type in ["sma", "ema"]:
                base_period = base_params.get("period", 20)
                # Faster moving averages in trending markets
                if trend_strength > 0.05:
                    optimized_params["period"] = max(10, int(base_period * 0.8))
                elif trend_strength < 0.02:
                    optimized_params["period"] = min(35, int(base_period * 1.2))
            
            return optimized_params
            
        except Exception as e:
            logger.error(f"Error optimizing parameters for {indicator_type}: {str(e)}")
            return base_params
    
    def _apply_regime_filtering(
        self,
        signals: pd.Series,
        df: pd.DataFrame,
        ticker: str,
        regime_strategy_mapping: Optional[Dict[int, Dict[str, Any]]] = None,
        minimum_confidence_threshold: float = 30.0
    ) -> pd.Series:
        """Apply market regime-based signal filtering"""
        try:
            filtered_signals = signals.copy()
            
            # Get regime predictions for the entire period
            regime_predictions = self._get_regime_predictions_for_period(df, ticker)
            
            # Default regime strategy mapping if not provided (using relaxed thresholds)
            if regime_strategy_mapping is None:
                # Convert minimum confidence from percentage to decimal
                base_confidence = minimum_confidence_threshold / 100.0
                regime_strategy_mapping = {
                    0: {"allow_long": True, "allow_short": False, "confidence_threshold": base_confidence},     # Bull Trending
                    1: {"allow_long": False, "allow_short": True, "confidence_threshold": base_confidence},    # Bear Trending
                    2: {"allow_long": True, "allow_short": True, "confidence_threshold": base_confidence + 0.1}, # Sideways - slightly higher
                    3: {"allow_long": False, "allow_short": False, "confidence_threshold": base_confidence + 0.2}, # High Volatility - much higher
                    4: {"allow_long": True, "allow_short": True, "confidence_threshold": base_confidence - 0.1}  # Accumulation - lower
                }
            
            # Apply filtering based on regime
            for i, (regime, confidence) in enumerate(regime_predictions):
                if i >= len(filtered_signals):
                    break
                    
                regime_config = regime_strategy_mapping.get(regime, {})
                
                # Check if we meet confidence threshold
                min_confidence = regime_config.get("confidence_threshold", 0.5)
                if confidence < min_confidence:
                    filtered_signals.iloc[i] = 0
                    continue
                
                # Filter based on regime rules
                current_signal = filtered_signals.iloc[i]
                
                # Block long signals if not allowed in this regime
                if current_signal == 1 and not regime_config.get("allow_long", True):
                    filtered_signals.iloc[i] = 0
                
                # Block short signals if not allowed in this regime
                elif current_signal == -1 and not regime_config.get("allow_short", True):
                    filtered_signals.iloc[i] = 0
            
            # Log filtering results
            original_signals = (signals != 0).sum()
            filtered_signals_count = (filtered_signals != 0).sum()
            
            logger.info(f"Regime filtering: {original_signals} -> {filtered_signals_count} signals")
            
            return filtered_signals
            
        except Exception as e:
            logger.error(f"Error in regime filtering: {str(e)}")
            return signals
    
    def _get_regime_predictions_for_period(
        self,
        df: pd.DataFrame,
        ticker: str
    ) -> List[Tuple[int, float]]:
        """Get regime predictions for the entire backtest period"""
        try:
            # Check if regime classifier is actually working
            if not self.regime_classifier.is_trained:
                logger.debug("Regime classifier not trained, using default regime")
                return [(2, 0.5)] * len(df)
            
            # Try a quick test prediction first
            try:
                test_df = df.tail(30).copy()  # Use last 30 rows for test
                test_result = self.regime_classifier.predict_regime(ticker, test_df)
                if test_result["status"] != "success":
                    logger.warning(f"Regime classifier test failed: {test_result.get('message')}")
                    return [(2, 0.5)] * len(df)
            except Exception as e:
                logger.warning(f"Regime classifier test failed with error: {str(e)}")
                return [(2, 0.5)] * len(df)
            
            regime_predictions = []
            
            # Use a simpler approach - predict regime for chunks of data
            chunk_size = max(30, len(df) // 20)  # Smaller chunks for stability
            
            for i in range(0, len(df), chunk_size):
                end_idx = min(i + chunk_size + 20, len(df))  # Overlap for continuity
                start_idx = max(0, i)
                
                if end_idx - start_idx < 20:  # Need minimum data
                    # Fill remaining with previous prediction or default
                    prev_regime = regime_predictions[-1][0] if regime_predictions else 2
                    prev_confidence = regime_predictions[-1][1] if regime_predictions else 0.5
                    for _ in range(i, len(df)):
                        regime_predictions.append((prev_regime, prev_confidence))
                    break
                
                try:
                    # Get data chunk
                    chunk_df = df.iloc[start_idx:end_idx].copy()
                    
                    # Predict regime for this chunk
                    regime_result = self.regime_classifier.predict_regime(ticker, chunk_df)
                    
                    if regime_result["status"] == "success":
                        regime = regime_result["regime"]
                        confidence = regime_result["confidence"]
                    else:
                        regime = 2  # Default to sideways
                        confidence = 0.5
                        
                except Exception:
                    regime = 2  # Default to sideways
                    confidence = 0.5
                
                # Apply this regime to all points in the chunk
                chunk_actual_size = min(chunk_size, len(df) - i)
                for _ in range(chunk_actual_size):
                    regime_predictions.append((regime, confidence))
            
            # Ensure we have predictions for all data points
            while len(regime_predictions) < len(df):
                regime_predictions.append((2, 0.5))
            
            return regime_predictions[:len(df)]  # Trim to exact size
            
        except Exception as e:
            logger.warning(f"Error getting regime predictions, using default: {str(e)}")
            return [(2, 0.5)] * len(df)  # Default to sideways for all periods
    
    def _execute_trades_advanced(
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
        benchmark_data: Optional[pd.DataFrame] = None,
        entry_methods: Optional[List[str]] = None,
        exit_methods: Optional[List[str]] = None,
        partial_exit_levels: Optional[List[float]] = None,
        trailing_stop_activation: Optional[float] = None,
        trailing_stop_distance: Optional[float] = None,
        time_based_exit: Optional[int] = None,
        support_resistance_exits: bool = False
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Execute trades with advanced entry/exit methods"""
        try:
            # Default methods if not specified
            if entry_methods is None:
                entry_methods = ["market_open"]  # Default to market open entry
            if exit_methods is None:
                exit_methods = ["signal_exit", "stop_loss", "take_profit"]
            
            # Use basic execution for now - can be extended later
            logger.info(f"Using advanced execution with methods: entry={entry_methods}, exit={exit_methods}")
            
            return self._execute_trades(
                df, signals, initial_capital, position_size, stop_loss, take_profit,
                max_drawdown, max_positions, sector_exposure_limit,
                consecutive_loss_limit, daily_loss_limit, weekly_loss_limit,
                max_allocation, margin_requirement, margin_interest,
                min_cash_reserve, position_sizing_method, kelly_fraction,
                correlation_threshold, benchmark_data
            )
            
        except Exception as e:
            logger.error(f"Error in advanced trade execution: {str(e)}")
            # Fallback to basic execution
            return self._execute_trades(
                df, signals, initial_capital, position_size, stop_loss, take_profit,
                max_drawdown, max_positions, sector_exposure_limit,
                consecutive_loss_limit, daily_loss_limit, weekly_loss_limit,
                max_allocation, margin_requirement, margin_interest,
                min_cash_reserve, position_sizing_method, kelly_fraction,
                correlation_threshold, benchmark_data
            ) 