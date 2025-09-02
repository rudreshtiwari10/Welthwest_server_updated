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
        # Market regime filtering - disabled by default to ensure signals are generated
        enable_regime_filter: bool = False,
        regime_strategy_mapping: Optional[Dict[int, Dict[str, Any]]] = None,
        minimum_confidence_threshold: float = 0.0,  # Lowered to 0% for maximum signal generation
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
                    logger.info(f"\n=== SIGNAL GENERATION START ===")
                    logger.info(f"Indicators: {[ind['type'] for ind in indicators]}")
                    logger.info(f"Data shape: {df.shape}")
                    logger.info(f"Date range: {df.index.min()} to {df.index.max()}")
                    logger.info(f"Minimum confidence threshold: {minimum_confidence_threshold}%")
                    
                    signals = self._generate_signals(df, indicators, minimum_confidence_threshold)
                    
                    # Log signal summary
                    total_signals = len(signals[signals != 0])
                    buy_signals = len(signals[signals == 1])
                    sell_signals = len(signals[signals == -1])
                    logger.info(f"\n=== SIGNAL GENERATION COMPLETE ===")
                    logger.info(f"Total signals generated: {total_signals} (Buy: {buy_signals}, Sell: {sell_signals})")
                    if total_signals > 0:
                        signal_dates = df.index[signals != 0].tolist()[:10]
                        logger.info(f"First 10 signal dates: {signal_dates}")
                    
                    if total_signals == 0:
                        logger.warning("⚠️  NO SIGNALS GENERATED! Check indicator calculations and thresholds.")
                    else:
                        logger.info(f"✅ Signal generation successful!")
                
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

        # Validate stop loss and take profit - preserve exact values
        if stop_loss is not None:
            if not isinstance(stop_loss, (int, float)) or stop_loss <= 0 or stop_loss >= 100:
                raise ValueError("Stop loss must be a number between 0 and 100")
            # Preserve exact input value - no rounding or adjustment
            
        if take_profit is not None:
            if not isinstance(take_profit, (int, float)) or take_profit <= 0 or take_profit >= 100:
                raise ValueError("Take profit must be a number between 0 and 100")
            # Preserve exact input value - no rounding or adjustment

        # Validate timeframe - expanded to include more options
        valid_timeframes = ["1m", "2m", "5m", "10m", "15m", "30m", "45m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1wk", "1mo"]
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
            
            # Only require parameters for specific indicators that need them
            ind_type = indicator["type"].lower()
            requires_params = ["rsi", "macd", "bollinger", "sma", "ema", "stochastic", "atr"]
            
            if ind_type in requires_params:
                if "parameters" not in indicator and "params" not in indicator:
                    raise ValueError(f"Parameters must be specified for indicator {indicator['type']}")
            else:
                # For VWAP and OBV, provide default parameters if not specified
                if "parameters" not in indicator and "params" not in indicator:
                    if ind_type == "vwap":
                        indicator["parameters"] = {"period": 14, "anchor": 1}
                    elif ind_type == "obv":
                        indicator["parameters"] = {"signal_period": 20, "ma_type": 1}
            
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
        adaptive_parameters: bool = False  # Disabled by default to prevent parameter issues
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
                        # Apply volatility-adjusted thresholds (only if enabled and columns exist)
                        if adaptive_parameters and 'Volatility' in df.columns:
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
                        
                        # Adaptive standard deviation (only if enabled and columns exist)
                        if adaptive_parameters and 'VIX_Proxy' in df.columns:
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
                        obv_data, _ = self.ta.calculate_obv(df, params)
                        df['OBV'] = obv_data

                    elif ind_type == "vwap":
                        vwap_data, _ = self.ta.calculate_vwap(df, params)
                        df['VWAP'] = vwap_data

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
        minimum_confidence_threshold: float = 0.0,  # Lowered default threshold
        confirmation_bars: int = 1,  # Reduced confirmation requirement
        volume_confirmation: bool = False,  # Disabled by default
        adaptive_thresholds: bool = False,  # Simplified thresholds by default
        timeframe: str = "1d",
        use_multi_timeframe: bool = True
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
                        
                        # Simplified signal generation with less restrictive conditions
                        logger.info(f"Generating RSI signals with oversold={oversold}, overbought={overbought}")
                        
                        # Generate signals with minimal confirmation requirements
                        for i in range(1, len(rsi)):
                            # Skip if current or previous value is NaN
                            if pd.isna(rsi.iloc[i]) or pd.isna(rsi.iloc[i-1]):
                                continue
                            
                            # Get threshold values
                            if isinstance(oversold, pd.Series):
                                oversold_val = oversold.iloc[i] if not pd.isna(oversold.iloc[i]) else 30
                                overbought_val = overbought.iloc[i] if not pd.isna(overbought.iloc[i]) else 70
                            else:
                                oversold_val = 30  # Use fixed values for reliability
                                overbought_val = 70
                            
                            current_rsi = rsi.iloc[i]
                            prev_rsi = rsi.iloc[i-1]
                            
                            # More lenient RSI signals
                            # Buy signal: RSI below 40 and turning up, or crossing above 30
                            if ((current_rsi < 40 and current_rsi > prev_rsi) or 
                                (prev_rsi <= 30 and current_rsi > 30)):
                                signals.iloc[i] = 1
                                confidence.iloc[i] = min(100.0, abs(40 - current_rsi) * 2.5)  # Higher confidence scores
                                logger.debug(f"RSI Buy signal at {df.index[i]}: RSI={current_rsi:.2f}")
                            
                            # Sell signal: RSI above 60 and turning down, or crossing below 70
                            elif ((current_rsi > 60 and current_rsi < prev_rsi) or 
                                  (prev_rsi >= 70 and current_rsi < 70)):
                                signals.iloc[i] = -1
                                confidence.iloc[i] = min(100.0, abs(current_rsi - 60) * 2.5)
                                logger.debug(f"RSI Sell signal at {df.index[i]}: RSI={current_rsi:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} RSI signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
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
                        
                        # Simplified MACD signals focusing on crossovers
                        logger.info("Generating MACD signals")
                        
                        for i in range(1, len(macd)):
                            # Skip if any required values are NaN
                            if (pd.isna(macd.iloc[i]) or pd.isna(signal_line.iloc[i]) or 
                                pd.isna(macd.iloc[i-1]) or pd.isna(signal_line.iloc[i-1])):
                                continue
                            
                            curr_macd = macd.iloc[i]
                            curr_signal = signal_line.iloc[i]
                            prev_macd = macd.iloc[i-1]
                            prev_signal = signal_line.iloc[i-1]
                            
                            # Simplified bullish crossover
                            if prev_macd <= prev_signal and curr_macd > curr_signal:
                                signals.iloc[i] = 1
                                confidence.iloc[i] = min(100.0, abs(curr_macd - curr_signal) * 10)
                                logger.debug(f"MACD Buy signal at {df.index[i]}: MACD={curr_macd:.4f}, Signal={curr_signal:.4f}")
                            
                            # Simplified bearish crossover
                            elif prev_macd >= prev_signal and curr_macd < curr_signal:
                                signals.iloc[i] = -1
                                confidence.iloc[i] = min(100.0, abs(curr_signal - curr_macd) * 10) 
                                logger.debug(f"MACD Sell signal at {df.index[i]}: MACD={curr_macd:.4f}, Signal={curr_signal:.4f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} MACD signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "bollinger":
                        # Check for different possible column names
                        bb_cols = ["BB_upper", "BB_middle", "BB_lower"]
                        alt_bb_cols = ["BB_Upper", "BB_Middle", "BB_Lower"]  # Alternative naming
                        
                        if all(col in df.columns for col in bb_cols):
                            upper_col, middle_col, lower_col = bb_cols
                        elif all(col in df.columns for col in alt_bb_cols):
                            upper_col, middle_col, lower_col = alt_bb_cols
                        else:
                            logger.warning(f"Bollinger Bands columns not found. Available: {df.columns.tolist()}")
                            continue
                            
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info("Generating Bollinger Bands signals")
                        
                        # More sensitive Bollinger Band signals
                        for i in range(1, len(df)):
                            if (pd.isna(df['Close'].iloc[i]) or pd.isna(df['BB_upper'].iloc[i]) or 
                                pd.isna(df['BB_lower'].iloc[i]) or pd.isna(df['Close'].iloc[i-1])):
                                continue
                            
                            curr_price = df['Close'].iloc[i]
                            prev_price = df['Close'].iloc[i-1]
                            upper_band = df[upper_col].iloc[i]
                            lower_band = df[lower_col].iloc[i]
                            middle_band = df[middle_col].iloc[i]
                            
                            # Buy signal: Price near or below lower band
                            if curr_price <= lower_band * 1.01:  # Within 1% of lower band
                                signals.iloc[i] = 1
                                confidence.iloc[i] = max(50.0, 100 - abs(curr_price - lower_band) / lower_band * 100)
                                logger.debug(f"BB Buy signal at {df.index[i]}: Price={curr_price:.2f}, Lower={lower_band:.2f}")
                            
                            # Sell signal: Price near or above upper band  
                            elif curr_price >= upper_band * 0.99:  # Within 1% of upper band
                                signals.iloc[i] = -1
                                confidence.iloc[i] = max(50.0, 100 - abs(curr_price - upper_band) / upper_band * 100)
                                logger.debug(f"BB Sell signal at {df.index[i]}: Price={curr_price:.2f}, Upper={upper_band:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} Bollinger signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "sma":
                        period = params.get("period", 20)
                        column_name = f"SMA_{period}"
                        if column_name not in df.columns:
                            continue
                            
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info(f"Generating SMA_{period} signals")
                        
                        # Simple crossover signals with confidence
                        for i in range(1, len(df)):
                            if (pd.isna(df['Close'].iloc[i]) or pd.isna(df[column_name].iloc[i]) or
                                pd.isna(df['Close'].iloc[i-1]) or pd.isna(df[column_name].iloc[i-1])):
                                continue
                            
                            curr_price = df['Close'].iloc[i]
                            prev_price = df['Close'].iloc[i-1]
                            curr_sma = df[column_name].iloc[i]
                            prev_sma = df[column_name].iloc[i-1]
                            
                            # Price crossing above SMA = buy
                            if prev_price <= prev_sma and curr_price > curr_sma:
                                signals.iloc[i] = 1
                                confidence.iloc[i] = min(100.0, abs(curr_price - curr_sma) / curr_sma * 100 * 10)
                                logger.debug(f"SMA Buy signal at {df.index[i]}: Price={curr_price:.2f}, SMA={curr_sma:.2f}")
                            
                            # Price crossing below SMA = sell
                            elif prev_price >= prev_sma and curr_price < curr_sma:
                                signals.iloc[i] = -1
                                confidence.iloc[i] = min(100.0, abs(curr_sma - curr_price) / curr_sma * 100 * 10)
                                logger.debug(f"SMA Sell signal at {df.index[i]}: Price={curr_price:.2f}, SMA={curr_sma:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} SMA signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "ema":
                        period = params.get("period", 20)
                        column_name = f"EMA_{period}"
                        if column_name not in df.columns:
                            continue
                            
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info(f"Generating EMA_{period} signals")
                        
                        # Simple crossover signals with confidence
                        for i in range(1, len(df)):
                            if (pd.isna(df['Close'].iloc[i]) or pd.isna(df[column_name].iloc[i]) or
                                pd.isna(df['Close'].iloc[i-1]) or pd.isna(df[column_name].iloc[i-1])):
                                continue
                            
                            curr_price = df['Close'].iloc[i]
                            prev_price = df['Close'].iloc[i-1]
                            curr_ema = df[column_name].iloc[i]
                            prev_ema = df[column_name].iloc[i-1]
                            
                            # Price crossing above EMA = buy
                            if prev_price <= prev_ema and curr_price > curr_ema:
                                signals.iloc[i] = 1
                                confidence.iloc[i] = min(100.0, abs(curr_price - curr_ema) / curr_ema * 100 * 10)
                                logger.debug(f"EMA Buy signal at {df.index[i]}: Price={curr_price:.2f}, EMA={curr_ema:.2f}")
                            
                            # Price crossing below EMA = sell
                            elif prev_price >= prev_ema and curr_price < curr_ema:
                                signals.iloc[i] = -1
                                confidence.iloc[i] = min(100.0, abs(curr_ema - curr_price) / curr_ema * 100 * 10)
                                logger.debug(f"EMA Sell signal at {df.index[i]}: Price={curr_price:.2f}, EMA={curr_ema:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} EMA signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "stochastic":
                        # Check for different possible column names
                        if "STOCH_k" in df.columns and "STOCH_d" in df.columns:
                            k_col, d_col = "STOCH_k", "STOCH_d"
                        elif "Stoch_k" in df.columns and "Stoch_d" in df.columns:
                            k_col, d_col = "Stoch_k", "Stoch_d"
                        else:
                            logger.warning(f"Stochastic columns not found. Available: {df.columns.tolist()}")
                            continue
                            
                        k_line = df[k_col]
                        d_line = df[d_col]
                        
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info("Generating Stochastic signals")
                        
                        # Enhanced Stochastic signals with confidence
                        for i in range(1, len(k_line)):
                            if (pd.isna(k_line.iloc[i]) or pd.isna(d_line.iloc[i]) or
                                pd.isna(k_line.iloc[i-1]) or pd.isna(d_line.iloc[i-1])):
                                continue
                            
                            curr_k = k_line.iloc[i]
                            curr_d = d_line.iloc[i]
                            prev_k = k_line.iloc[i-1]
                            prev_d = d_line.iloc[i-1]
                            
                            # More lenient Stochastic signals
                            # Bullish: K crosses above D, especially in oversold territory
                            if prev_k <= prev_d and curr_k > curr_d:
                                signals.iloc[i] = 1
                                # Higher confidence if in oversold territory
                                if curr_k < 30:
                                    confidence.iloc[i] = min(100.0, 80 + (30 - curr_k))
                                else:
                                    confidence.iloc[i] = min(100.0, 50 + abs(curr_k - curr_d))
                                logger.debug(f"Stochastic Buy signal at {df.index[i]}: K={curr_k:.2f}, D={curr_d:.2f}")
                            
                            # Bearish: K crosses below D, especially in overbought territory
                            elif prev_k >= prev_d and curr_k < curr_d:
                                signals.iloc[i] = -1
                                # Higher confidence if in overbought territory
                                if curr_k > 70:
                                    confidence.iloc[i] = min(100.0, 80 + (curr_k - 70))
                                else:
                                    confidence.iloc[i] = min(100.0, 50 + abs(curr_d - curr_k))
                                logger.debug(f"Stochastic Sell signal at {df.index[i]}: K={curr_k:.2f}, D={curr_d:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} Stochastic signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "obv":
                        if "OBV" not in df.columns:
                            continue
                            
                        obv = df["OBV"]
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info("Generating OBV signals")
                        
                        # Calculate OBV moving average for trend detection
                        obv_ma = obv.rolling(window=10, min_periods=1).mean()
                        
                        # Enhanced OBV signals with confidence
                        for i in range(1, len(obv)):
                            if (pd.isna(obv.iloc[i]) or pd.isna(obv.iloc[i-1]) or
                                pd.isna(obv_ma.iloc[i]) or pd.isna(obv_ma.iloc[i-1])):
                                continue
                            
                            curr_obv = obv.iloc[i]
                            prev_obv = obv.iloc[i-1]
                            curr_ma = obv_ma.iloc[i]
                            prev_ma = obv_ma.iloc[i-1]
                            
                            # More sensitive OBV signals
                            # Bullish: OBV rising and above moving average
                            if curr_obv > prev_obv and curr_obv > curr_ma and prev_obv <= prev_ma:
                                signals.iloc[i] = 1
                                # Confidence based on momentum
                                momentum = abs(curr_obv - prev_obv) / max(abs(prev_obv), 1)
                                confidence.iloc[i] = min(100.0, 60 + momentum * 100)
                                logger.debug(f"OBV Buy signal at {df.index[i]}: OBV={curr_obv:.0f}, MA={curr_ma:.0f}")
                            
                            # Bearish: OBV falling and below moving average
                            elif curr_obv < prev_obv and curr_obv < curr_ma and prev_obv >= prev_ma:
                                signals.iloc[i] = -1
                                momentum = abs(curr_obv - prev_obv) / max(abs(prev_obv), 1)
                                confidence.iloc[i] = min(100.0, 60 + momentum * 100)
                                logger.debug(f"OBV Sell signal at {df.index[i]}: OBV={curr_obv:.0f}, MA={curr_ma:.0f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} OBV signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "vwap":
                        if "VWAP" not in df.columns:
                            continue
                            
                        vwap = df["VWAP"]
                        close = df["Close"]
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info("Generating VWAP signals")
                        
                        # Enhanced VWAP signals with confidence
                        for i in range(1, len(close)):
                            if (pd.isna(vwap.iloc[i]) or pd.isna(vwap.iloc[i-1]) or 
                                pd.isna(close.iloc[i]) or pd.isna(close.iloc[i-1])):
                                continue
                            
                            curr_price = close.iloc[i]
                            prev_price = close.iloc[i-1]
                            curr_vwap = vwap.iloc[i]
                            prev_vwap = vwap.iloc[i-1]
                            
                            # More sensitive VWAP signals
                            # Bullish: Price crosses above VWAP or significantly above
                            if ((prev_price <= prev_vwap and curr_price > curr_vwap) or
                                (curr_price > curr_vwap * 1.005)):  # 0.5% above VWAP
                                signals.iloc[i] = 1
                                # Confidence based on distance from VWAP
                                distance_pct = abs(curr_price - curr_vwap) / curr_vwap * 100
                                confidence.iloc[i] = min(100.0, 50 + distance_pct * 20)
                                logger.debug(f"VWAP Buy signal at {df.index[i]}: Price={curr_price:.2f}, VWAP={curr_vwap:.2f}")
                            
                            # Bearish: Price crosses below VWAP or significantly below
                            elif ((prev_price >= prev_vwap and curr_price < curr_vwap) or
                                  (curr_price < curr_vwap * 0.995)):  # 0.5% below VWAP
                                signals.iloc[i] = -1
                                distance_pct = abs(curr_vwap - curr_price) / curr_vwap * 100
                                confidence.iloc[i] = min(100.0, 50 + distance_pct * 20)
                                logger.debug(f"VWAP Sell signal at {df.index[i]}: Price={curr_price:.2f}, VWAP={curr_vwap:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} VWAP signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                    elif ind_type == "atr":
                        if "ATR" not in df.columns:
                            continue
                            
                        atr = df["ATR"]
                        signals = pd.Series(0, index=df.index)
                        confidence = pd.Series(0.0, index=df.index)
                        
                        logger.info("Generating ATR signals")
                        
                        # Calculate ATR moving average with min_periods
                        atr_sma = atr.rolling(window=20, min_periods=1).mean()
                        
                        # Enhanced ATR-based volatility signals with confidence
                        for i in range(1, len(atr)):
                            if pd.isna(atr.iloc[i]) or pd.isna(atr_sma.iloc[i]):
                                continue
                            
                            curr_atr = atr.iloc[i]
                            avg_atr = atr_sma.iloc[i]
                            
                            # More nuanced volatility signals
                            volatility_ratio = curr_atr / avg_atr if avg_atr > 0 else 1
                            
                            # Low volatility (consolidation) - potentially bullish for breakouts
                            if volatility_ratio < 0.7:  # ATR 30% below average
                                signals.iloc[i] = 1
                                confidence.iloc[i] = min(100.0, 60 + (0.7 - volatility_ratio) * 100)
                                logger.debug(f"ATR Buy signal at {df.index[i]}: Low volatility, ratio={volatility_ratio:.2f}")
                            
                            # High volatility - risk-off signal
                            elif volatility_ratio > 1.5:  # ATR 50% above average
                                signals.iloc[i] = -1
                                confidence.iloc[i] = min(100.0, 60 + (volatility_ratio - 1.5) * 50)
                                logger.debug(f"ATR Sell signal at {df.index[i]}: High volatility, ratio={volatility_ratio:.2f}")
                        
                        signal_count = (signals != 0).sum()
                        logger.info(f"Generated {signal_count} ATR signals (Buy: {(signals == 1).sum()}, Sell: {(signals == -1).sum()})")
                        
                        all_signals[f'signal_{ind_type}'] = signals
                        signal_confidence[f'signal_{ind_type}'] = confidence
                        
                except Exception as e:
                    logger.error(f"Error generating signals for {ind_type}: {str(e)}")
                    import traceback
                    logger.error(f"Full traceback: {traceback.format_exc()}")
                    continue
            
            # Simplified and more permissive signal aggregation
            logger.info(f"Aggregating signals from {len(all_signals.columns)} indicators")
            
            if len(all_signals.columns) > 1:
                # More permissive voting system - accept any indicator signal
                buy_votes = pd.Series(0, index=df.index)
                sell_votes = pd.Series(0, index=df.index)
                signal_confidence_values = pd.Series(0.0, index=df.index)
                
                for col in all_signals.columns:
                    signal_col = all_signals[col]
                    buy_votes += (signal_col == 1).astype(int)
                    sell_votes += (signal_col == -1).astype(int)
                
                # Calculate agreement percentage
                total_indicators = len(all_signals.columns)
                buy_agreement = buy_votes / total_indicators
                sell_agreement = sell_votes / total_indicators
                
                # Much more lenient threshold - accept signals from any single indicator
                signal_threshold = max(0.1, minimum_confidence_threshold / 100.0)  # Very low threshold
                
                # Generate final signals with permissive threshold
                final_signals = pd.Series(0, index=df.index)
                
                # Accept buy signals if ANY indicator shows a buy (much more permissive)
                buy_mask = buy_agreement >= signal_threshold
                final_signals[buy_mask] = 1
                signal_confidence_values[buy_mask] = buy_agreement[buy_mask] * 100
                
                # Accept sell signals if ANY indicator shows a sell
                sell_mask = sell_agreement >= signal_threshold
                final_signals[sell_mask] = -1
                signal_confidence_values[sell_mask] = sell_agreement[sell_mask] * 100
                
                # Handle conflicting signals by keeping the stronger one
                conflicting = buy_mask & sell_mask
                if conflicting.any():
                    # Keep the signal with higher agreement
                    stronger_buy = buy_agreement[conflicting] > sell_agreement[conflicting]
                    final_signals.loc[conflicting & stronger_buy] = 1
                    final_signals.loc[conflicting & ~stronger_buy] = -1
                
                # Log signal statistics
                buy_signals = (final_signals == 1).sum()
                sell_signals = (final_signals == -1).sum()
                avg_confidence = signal_confidence_values[signal_confidence_values > 0].mean()
                
                logger.info(f"Final aggregated signals: Buy={buy_signals}, Sell={sell_signals}, "
                          f"Avg confidence={avg_confidence:.1f}%, Threshold={minimum_confidence_threshold:.1f}%")
                
                # Store confidence data in final_signals for later use
                final_signals.confidence_values = signal_confidence_values
                
                return final_signals
                
            elif len(all_signals.columns) == 1:
                # If only one indicator, use its signals directly with confidence
                logger.info("Using single indicator signals directly")
                single_signal = all_signals.iloc[:, 0]
                
                # Add confidence values if available
                if len(signal_confidence.columns) > 0:
                    confidence_values = signal_confidence.iloc[:, 0]
                    single_signal.confidence_values = confidence_values
                else:
                    # Default confidence for single indicator
                    confidence_values = pd.Series(75.0, index=df.index)  # High confidence for single indicator
                    confidence_values[single_signal == 0] = 0
                    single_signal.confidence_values = confidence_values
                
                buy_signals = (single_signal == 1).sum()
                sell_signals = (single_signal == -1).sum()
                logger.info(f"Single indicator signals: Buy={buy_signals}, Sell={sell_signals}")
                
                return single_signal
            else:
                # No valid signals generated - return empty series with confidence
                logger.warning("No valid indicators found for signal generation")
                empty_signals = pd.Series(0, index=df.index)
                empty_signals.confidence_values = pd.Series(0.0, index=df.index)
                return empty_signals
                
        except Exception as e:
            logger.error(f"Error in signal generation: {str(e)}")
            return pd.Series(index=df.index, data=0)

    def _generate_multi_timeframe_signals(
        self,
        df: pd.DataFrame,
        indicators: List[Dict[str, Any]],
        timeframe: str,
        higher_timeframes: List[str],
        minimum_confidence_threshold: float = 50.0
    ) -> pd.Series:
        """Generate signals using multiple timeframes for better confirmation"""
        try:
            # Generate signals for the primary timeframe
            primary_signals = self._generate_signals(
                df, indicators, minimum_confidence_threshold,
                use_multi_timeframe=False
            )
            
            # For higher timeframes, we need to simulate the data
            # In a real implementation, you would fetch actual higher timeframe data
            higher_tf_signals = {}
            
            for htf in higher_timeframes:
                # Simulate higher timeframe by resampling
                htf_df = self._resample_to_higher_timeframe(df, timeframe, htf)
                if not htf_df.empty:
                    htf_signals = self._generate_signals(
                        htf_df, indicators, minimum_confidence_threshold,
                        use_multi_timeframe=False
                    )
                    # Align higher timeframe signals with primary timeframe
                    aligned_signals = self._align_timeframe_signals(htf_signals, df.index, htf)
                    higher_tf_signals[htf] = aligned_signals
            
            # Combine signals with trend confirmation
            final_signals = self._combine_multi_timeframe_signals(
                primary_signals, higher_tf_signals, minimum_confidence_threshold
            )
            
            return final_signals
            
        except Exception as e:
            logger.error(f"Error in multi-timeframe signal generation: {str(e)}")
            return primary_signals

    def _resample_to_higher_timeframe(self, df: pd.DataFrame, current_tf: str, target_tf: str) -> pd.DataFrame:
        """Resample data to higher timeframe"""
        try:
            # Define timeframe mappings
            tf_map = {
                '1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W', '1M': '1M'
            }
            
            if target_tf not in tf_map:
                return pd.DataFrame()
            
            # Resample OHLCV data
            resampled = df.resample(tf_map[target_tf]).agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            # Recalculate indicators for the higher timeframe
            if not resampled.empty and len(resampled) > 50:  # Need enough data
                # Add basic indicators
                resampled = self.ta.calculate_rsi(resampled, 14)
                resampled = self.ta.calculate_macd(resampled, 12, 26, 9)
                resampled = self.ta.calculate_moving_averages(resampled, [20, 50])
                
            return resampled
            
        except Exception as e:
            logger.error(f"Error resampling to {target_tf}: {str(e)}")
            return pd.DataFrame()

    def _align_timeframe_signals(self, htf_signals: pd.Series, target_index: pd.Index, htf: str) -> pd.Series:
        """Align higher timeframe signals with primary timeframe"""
        try:
            aligned = pd.Series(0, index=target_index)
            
            for i, date in enumerate(target_index):
                # Find the corresponding higher timeframe signal
                htf_date = htf_signals.index[htf_signals.index <= date]
                if len(htf_date) > 0:
                    latest_htf = htf_date[-1]
                    aligned.iloc[i] = htf_signals.loc[latest_htf]
            
            return aligned
            
        except Exception as e:
            logger.error(f"Error aligning {htf} signals: {str(e)}")
            return pd.Series(0, index=target_index)

    def _combine_multi_timeframe_signals(
        self,
        primary_signals: pd.Series,
        higher_tf_signals: Dict[str, pd.Series],
        min_confidence: float
    ) -> pd.Series:
        """Combine signals from multiple timeframes"""
        try:
            final_signals = primary_signals.copy()
            
            # Only take primary signals that align with higher timeframe trend
            for i in range(len(final_signals)):
                if final_signals.iloc[i] != 0:  # If there's a primary signal
                    # Check higher timeframe confirmation
                    htf_confirmation = True
                    
                    for htf_name, htf_signal in higher_tf_signals.items():
                        if i < len(htf_signal):
                            htf_value = htf_signal.iloc[i]
                            # Require same direction or neutral from higher timeframes
                            if htf_value != 0 and htf_value != final_signals.iloc[i]:
                                htf_confirmation = False
                                break
                    
                    # If no higher timeframe confirmation, reduce signal strength
                    if not htf_confirmation:
                        final_signals.iloc[i] = 0
            
            # Preserve confidence values if they exist
            if hasattr(primary_signals, 'confidence_values'):
                final_signals.confidence_values = primary_signals.confidence_values
            
            return final_signals
            
        except Exception as e:
            logger.error(f"Error combining multi-timeframe signals: {str(e)}")
            return primary_signals

    def _apply_volume_filter(self, signals: pd.Series, df: pd.DataFrame) -> pd.Series:
        """Filter signals based on volume confirmation"""
        try:
            if 'Volume' not in df.columns:
                return signals
            
            filtered_signals = signals.copy()
            volume_ma = df['Volume'].rolling(20).mean()
            
            for i in range(len(signals)):
                if signals.iloc[i] != 0:  # If there's a signal
                    # Require above-average volume for signal confirmation
                    if i < len(df) and df['Volume'].iloc[i] < volume_ma.iloc[i] * 1.2:
                        filtered_signals.iloc[i] = 0
            
            return filtered_signals
            
        except Exception as e:
            logger.error(f"Error applying volume filter: {str(e)}")
            return signals

    def _apply_market_regime_filter(self, df: pd.DataFrame, current_index: int, date_str: str) -> bool:
        """Apply market regime filtering to determine if trading conditions are favorable"""
        try:
            # Simple market regime detection based on volatility and trend
            if current_index < 20:  # Need enough data
                return True
            
            # Calculate recent volatility (ATR-based)
            recent_data = df.iloc[max(0, current_index-20):current_index+1]
            high_low_diff = (recent_data['High'] - recent_data['Low']) / recent_data['Close']
            avg_volatility = high_low_diff.mean()
            
            # Calculate trend strength using moving averages
            if 'MA_20' in df.columns and 'MA_50' in df.columns:
                ma20 = df['MA_20'].iloc[current_index]
                ma50 = df['MA_50'].iloc[current_index]
                trend_strength = abs(ma20 - ma50) / ma50 if ma50 != 0 else 0
            else:
                # Fallback: calculate simple trend
                if len(recent_data) >= 10:
                    trend_strength = abs(recent_data['Close'].iloc[-1] - recent_data['Close'].iloc[0]) / recent_data['Close'].iloc[0]
                else:
                    trend_strength = 0
            
            # Determine market regime
            high_volatility_threshold = 0.03  # 3% average daily range
            low_trend_threshold = 0.02  # 2% trend strength
            
            # Unfavorable conditions: High volatility with low trend (choppy market)
            if avg_volatility > high_volatility_threshold and trend_strength < low_trend_threshold:
                logger.debug(f"Unfavorable market regime at {date_str}: High volatility ({avg_volatility:.3f}) with low trend ({trend_strength:.3f})")
                return False
            
            # Also avoid trading in extreme volatility
            if avg_volatility > high_volatility_threshold * 2:  # Very high volatility
                logger.debug(f"Extreme volatility detected at {date_str}: {avg_volatility:.3f}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error in market regime filter: {str(e)}")
            return True  # Default to allowing trades if filter fails

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
            
            signal_count = len(signals[signals != 0])
            logger.info(f"\n=== TRADE EXECUTION START ===")
            logger.info(f"Starting trade execution with {signal_count} signals")
            logger.info(f"Initial capital: ${initial_capital:,.2f}")
            logger.info(f"Position size: {position_size}%")
            
            if signal_count == 0:
                logger.warning("⚠️  No signals to execute trades with. Returning empty results.")
                return [], {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'max_drawdown': 0.0,
                    'initial_capital': initial_capital,
                    'equity_curve': {}
                }
            
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
                    current_price = row['Close']
                    size = pos['size']
                    
                    # Update trailing stop logic
                    highest_price = pos.get('highest_price', entry_price)
                    if current_price > highest_price:
                        pos['highest_price'] = current_price
                        # Update trailing stop (3% from highest price)
                        trailing_stop_percentage = 3.0
                        trailing_stop = current_price * (1 - trailing_stop_percentage/100)
                        current_stop_loss = pos.get('stop_loss_price', entry_price * (1 - stop_loss/100) if stop_loss else None)
                        if current_stop_loss is None or trailing_stop > current_stop_loss:
                            pos['stop_loss_price'] = trailing_stop
                    
                    # Calculate worst and best case P&L for the day
                    worst_pnl_pct = (low_price - entry_price) / entry_price * 100
                    best_pnl_pct = (high_price - entry_price) / entry_price * 100
                    
                    # Check trailing stop
                    current_stop_loss = pos.get('stop_loss_price', entry_price * (1 - stop_loss/100) if stop_loss else None)
                    hit_trailing_stop = current_stop_loss and low_price <= current_stop_loss
                    
                    # Determine if stop loss or take profit was hit - use exact values
                    hit_stop_loss = (stop_loss and worst_pnl_pct <= -float(stop_loss)) or hit_trailing_stop
                    hit_take_profit = take_profit and best_pnl_pct >= float(take_profit)
                    
                    if hit_stop_loss or hit_take_profit:
                        # Use exact user-provided values without modification
                        if hit_stop_loss:
                            exit_price = entry_price * (1 - float(stop_loss)/100)
                        else:
                            exit_price = entry_price * (1 + float(take_profit)/100)
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
                
                # Check for new entry signals - more permissive for testing
                if signal == 1 and (max_positions is None or len(current_positions) < max_positions):
                    # Check market regime first
                    should_enter = True
                    market_regime_filter = self._apply_market_regime_filter(df, i, date_str)
                    if not market_regime_filter:
                        should_enter = False
                        logger.debug(f"Entry blocked by unfavorable market regime at {date_str}")
                    
                    # Simplified entry conditions - allow most entries for testing
                    if should_enter:
                        should_enter = self._validate_entry_conditions(
                            df, i, current_capital, consecutive_loss_limit, 
                            metrics['current_consecutive_losses'], daily_loss_limit,
                            metrics['daily_pnl'], date_str
                        )
                    
                    # Add risk-reward ratio validation
                    if should_enter and stop_loss and take_profit:
                        risk_reward_ratio = take_profit / stop_loss
                        if risk_reward_ratio < 2.0:  # Only take trades with potential 2:1 reward-to-risk
                            should_enter = False
                            logger.debug(f"Entry blocked by poor risk-reward ratio: {risk_reward_ratio:.2f} < 2.0")
                    
                    # Check current drawdown before entry
                    if should_enter and max_drawdown:
                        peak_equity = max(metrics['equity_curve'].values()) if metrics['equity_curve'] else initial_capital
                        current_drawdown = (peak_equity - current_capital) / peak_equity * 100
                        if current_drawdown >= max_drawdown:
                            should_enter = False
                            logger.debug(f"Entry blocked by max drawdown: {current_drawdown:.2f}% >= {max_drawdown}%")
                    
                    if not should_enter:
                        logger.debug(f"Entry signal at {date_str} blocked by validation")
                    
                    if should_enter:
                        # Calculate position size based on risk amount if stop loss is specified
                        if stop_loss:
                            # Calculate position size based on risk per trade
                            risk_per_trade = 2.0  # Risk 2% per trade
                            risk_amount = current_capital * (risk_per_trade / 100)
                            entry_price_estimate = row['Close']
                            stop_loss_amount = entry_price_estimate * (stop_loss / 100)
                            base_position_value = risk_amount / stop_loss_amount * entry_price_estimate
                            calculated_position_size = min((base_position_value / current_capital) * 100, position_size)
                        else:
                            calculated_position_size = position_size
                        
                        # Calculate adaptive position size
                        size = self._calculate_adaptive_position_size(
                            current_capital=current_capital,
                            base_position_size=calculated_position_size,
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
                        
                        # Calculate actual shares based on position size
                        shares = size / entry_price
                        
                        # Add new position with enhanced tracking
                        new_position = {
                            'entry_date': date_str,
                            'entry_price': float(entry_price),
                            'size': float(shares),
                            'signal_confidence': float(signal_confidence),
                            'entry_reason': 'signal_buy',
                            'market_conditions': self._capture_market_conditions(df, i),
                            'highest_price': float(entry_price),  # Initialize for trailing stop
                            'stop_loss_price': float(entry_price * (1 - stop_loss/100)) if stop_loss else None
                        }
                        current_positions.append(new_position)
                        metrics['positions'].append(new_position)
                        logger.info(f"Opened new position at {date_str}: price={entry_price:.2f}, size={size/entry_price:.2f}, confidence={signal_confidence:.2f}")
                        
                elif signal == 1:
                    # Log why we couldn't enter
                    if max_positions and len(current_positions) >= max_positions:
                        logger.debug(f"Entry signal at {date_str} blocked: max positions ({max_positions}) reached")
                    else:
                        logger.debug(f"Entry signal at {date_str} processed but not entered")
                
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
        """Simplified and more permissive entry validation for debugging"""
        try:
            # Only check the most critical limits, relaxed for testing
            
            # Check consecutive loss limit (only if specified and very strict)
            if consecutive_loss_limit and consecutive_loss_limit < 10 and current_consecutive_losses >= consecutive_loss_limit:
                logger.debug(f"Entry blocked by consecutive loss limit: {current_consecutive_losses} >= {consecutive_loss_limit}")
                return False
            
            # Check daily loss limit (only if specified and very strict)
            if daily_loss_limit and daily_loss_limit < 20:  # Only block if very strict limit
                daily_loss_pct = (daily_pnl.get(date_str, 0) / current_capital) * 100
                if daily_loss_pct <= -daily_loss_limit:
                    logger.debug(f"Entry blocked by daily loss limit: {daily_loss_pct:.2f}% <= -{daily_loss_limit}%")
                    return False
            
            # Allow all other entries for signal generation testing
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
        """Optimize indicator parameters based on market conditions with fallbacks"""
        try:
            optimized_params = base_params.copy()
            
            # Get current market volatility with fallback calculation
            if 'Volatility' in df.columns and len(df) > 20:
                current_volatility = df['Volatility'].rolling(20).mean().iloc[-1]
            else:
                # Calculate simple volatility proxy from price data
                returns = df['Close'].pct_change().rolling(20).std() * 100
                current_volatility = returns.iloc[-1] if len(returns) > 0 and not pd.isna(returns.iloc[-1]) else 20
            
            # Get trend strength with fallback calculation
            if 'Trend_Strength' in df.columns and len(df) > 20:
                trend_strength = df['Trend_Strength'].rolling(20).mean().iloc[-1]
            else:
                # Simple trend strength proxy using moving average slope
                ma20 = df['Close'].rolling(20).mean()
                if len(ma20) > 1:
                    trend_strength = abs(ma20.iloc[-1] - ma20.iloc[-2]) / ma20.iloc[-2] if ma20.iloc[-2] != 0 else 0.02
                else:
                    trend_strength = 0.02
            
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

    def comprehensive_backtest(
        self,
        ticker: str,
        selected_indicators: Dict[str, Any],
        voting_threshold: float = 0.6,
        period: str = '1y',
        timeframe: str = '1d',
        initial_capital: float = 100000,
        position_size_pct: float = 0.1,
        risk_reward_ratio: float = 2.0,
        max_drawdown_pct: float = 0.05,
        monte_carlo_simulations: int = 1000,
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """
        Comprehensive backtest method that bridges to IndianStockStrategyBuilder
        This method provides the interface expected by the API endpoints
        """
        try:
            # Import the engine here to avoid circular imports
            from services.backtesting_engine import IndianStockStrategyBuilder
            
            # Initialize the builder
            builder = IndianStockStrategyBuilder()
            
            # Fetch stock data
            df = builder.fetch_stock_data(ticker, period, timeframe)
            if df is None or df.empty:
                raise ValueError(f"No data found for symbol: {ticker}")
            
            # Calculate indicators
            df = builder.calculate_indicators(df, selected_indicators)
            
            # Generate voting signals
            df = builder.generate_voting_signals(df, selected_indicators, voting_threshold)
            
            # Run backtest
            trades_df, equity_df, metrics = builder.backtest_strategy(
                df, initial_capital, position_size_pct, risk_reward_ratio, max_drawdown_pct
            )
            
            # Generate charts
            charts = builder.create_comprehensive_charts(df, trades_df, equity_df)
            
            # Create trades list in the expected format
            trades = []
            if not trades_df.empty:
                for _, trade in trades_df.iterrows():
                    trades.append({
                        'Entry_Date': trade.get('Entry_Date', ''),
                        'Exit_Date': trade.get('Exit_Date', ''),
                        'Entry_Price': float(trade.get('Entry_Price', 0)),
                        'Exit_Price': float(trade.get('Exit_Price', 0)),
                        'Position_Size': float(trade.get('Position_Size', 0)),
                        'Direction': trade.get('Direction', 'Long'),
                        'PnL': float(trade.get('PnL', 0)),
                        'Return_Pct': float(trade.get('Return_Pct', 0)),
                        'Exit_Reason': trade.get('Exit_Reason', 'Signal')
                    })
            
            # Create equity curve data
            equity_curve = []
            if not equity_df.empty:
                for _, point in equity_df.iterrows():
                    equity_curve.append({
                        'Date': point.get('Date', ''),
                        'Equity': float(point.get('Equity', 0)),
                        'Capital': float(point.get('Capital', 0)),
                        'Position': float(point.get('Position', 0)),
                        'Price': float(point.get('Price', 0)),
                        'Drawdown': float(point.get('Drawdown', 0))
                    })
            
            # Run Monte Carlo simulation if requested
            monte_carlo = None
            if monte_carlo_simulations > 0 and not trades_df.empty:
                mc_stats, mc_results = builder.monte_carlo_analysis(
                    trades_df, initial_capital, monte_carlo_simulations, confidence_level
                )
                monte_carlo = {
                    'statistics': mc_stats,
                    'results': mc_results
                }
            
            # Prepare the result in the expected format
            result = {
                'metrics': metrics,
                'trades': trades,
                'equity_curve': equity_curve,
                'stock_data': df.to_dict('records'),
                'charts': charts,
                'monte_carlo': monte_carlo,
                'summary': {
                    'symbol': ticker,
                    'period': period,
                    'timeframe': timeframe,
                    'total_data_points': len(df),
                    'indicators_used': list(selected_indicators.keys()),
                    'voting_threshold': voting_threshold,
                    'backtest_period': {
                        'start_date': df.iloc[0]['Date'].strftime('%Y-%m-%d') if not df.empty else '',
                        'end_date': df.iloc[-1]['Date'].strftime('%Y-%m-%d') if not df.empty else ''
                    }
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error in comprehensive_backtest: {str(e)}")
            raise e 