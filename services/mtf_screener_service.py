"""
Multi-Timeframe Stock Screener Service - OPTIMIZED VERSION

Performance Optimizations:
1. Batch yfinance download (50 stocks in 1 API call)
2. Single regime calculation (calculate once, reuse for all stocks)
3. Two-level caching (OHLCV data cache + results cache)
4. Background pre-computation (APScheduler)
5. Two-phase screening (quick filter + detailed analysis)

Target: 1-5 seconds for full screening (50% faster with NIFTY 50)
"""

import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Thread
import logging
import time
import hashlib

from screener_model.mtf_regime_detector import MTFRegimeDetector, get_regime_detector
from screener_model.mtf_indicator_calculator import MTFIndicatorCalculator
from screener_model.pattern_detector import PatternDetector
from screener_model.risk_reward_engine import RiskRewardEngine
from screener_model.scoring_engine import ScoringEngine, get_scoring_engine
from middleware.cache_manager import cache

# Import dynamic NIFTY 50 fetcher instead of hardcoded list
from services.nifty_fetcher import get_nifty_fetcher, get_nifty50_stocks, get_sector_mapping

# Import SHORT/Selling signal modules
try:
    from screener_model.selling_signal_aggregator import SellingSignalAggregator
    from screener_model.breakdown_detector import BreakdownDetector
    from screener_model.new_lows_detector import NewLowsDetector
    from screener_model.resistance_fader import ResistanceFader
    SHORT_MODULES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"SHORT modules not available: {e}")
    SHORT_MODULES_AVAILABLE = False
    SellingSignalAggregator = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Note: Stock universe is now dynamically fetched from NSE API
# See services/nifty_fetcher.py for implementation
# Fallback lists are maintained in nifty_fetcher.py


class OptimizedDataCache:
    """
    Three-level cache for OHLCV data and screening results
    Level 1: Redis (shared) - for regime and results
    Level 2: In-Memory (local) - for regime and results fallback
    Level 3: In-Memory (local) - for OHLCV DataFrames (not Redis-compatible)
    """

    def __init__(self):
        self.ohlcv_cache = {}  # {timeframe: {ticker: (data, timestamp)}}
        self.results_cache = {}  # {cache_key: (result, timestamp)} - Memory fallback
        self.regime_cache = {}  # {key: (data, timestamp)} - Memory fallback
        self.lock = Lock()

        # Cache TTLs in seconds
        self.ohlcv_ttl = 300  # 5 minutes for raw data
        self.results_ttl = 300  # 5 minutes for results (was 2 min, increased to reduce cold-cache hits)
        self.regime_ttl = 300  # 5 minutes for regime

    def get_ohlcv(self, timeframe: str, ticker: str) -> Optional[pd.DataFrame]:
        """Get cached OHLCV data if valid"""
        with self.lock:
            if timeframe not in self.ohlcv_cache:
                return None
            if ticker not in self.ohlcv_cache[timeframe]:
                return None

            data, timestamp = self.ohlcv_cache[timeframe][ticker]
            if (datetime.now() - timestamp).seconds < self.ohlcv_ttl:
                return data
            return None

    def set_ohlcv(self, timeframe: str, ticker: str, data: pd.DataFrame):
        """Cache OHLCV data"""
        with self.lock:
            if timeframe not in self.ohlcv_cache:
                self.ohlcv_cache[timeframe] = {}
            self.ohlcv_cache[timeframe][ticker] = (data, datetime.now())

    def set_ohlcv_batch(self, timeframe: str, batch_data: Dict[str, pd.DataFrame]):
        """Cache multiple tickers at once"""
        with self.lock:
            if timeframe not in self.ohlcv_cache:
                self.ohlcv_cache[timeframe] = {}
            timestamp = datetime.now()
            for ticker, data in batch_data.items():
                self.ohlcv_cache[timeframe][ticker] = (data, timestamp)

    def get_result(self, cache_key: str) -> Optional[Dict]:
        """Get cached result if valid (tries Redis first, then memory)"""
        # Try Redis cache first (shared across processes)
        redis_key = f"screener_result:{cache_key}"
        cached = cache.get(redis_key)
        if cached:
            logger.debug(f"Redis cache hit for: {cache_key}")
            return cached

        # Fallback to memory cache
        with self.lock:
            if cache_key not in self.results_cache:
                return None

            result, timestamp = self.results_cache[cache_key]
            if (datetime.now() - timestamp).seconds < self.results_ttl:
                logger.debug(f"Memory cache hit for: {cache_key}")
                return result
            return None

    def set_result(self, cache_key: str, result: Dict):
        """Cache screening result (to both Redis and memory)"""
        # Cache to Redis (shared)
        redis_key = f"screener_result:{cache_key}"
        cache.set(redis_key, result, ttl=self.results_ttl)

        # Also cache to memory (fallback)
        with self.lock:
            self.results_cache[cache_key] = (result, datetime.now())

    def get_regime(self, key: str = "nifty_regime") -> Optional[Dict]:
        """Get cached regime data (tries Redis first, then memory)"""
        # Try Redis cache first (shared across processes)
        redis_key = f"regime:{key}"
        cached = cache.get(redis_key)
        if cached:
            logger.debug(f"Redis cache hit for regime: {key}")
            return cached

        # Fallback to memory cache
        with self.lock:
            if key not in self.regime_cache:
                return None

            data, timestamp = self.regime_cache[key]
            if (datetime.now() - timestamp).seconds < self.regime_ttl:
                logger.debug(f"Memory cache hit for regime: {key}")
                return data
            return None

    def set_regime(self, data: Dict, key: str = "nifty_regime"):
        """Cache regime data (to both Redis and memory)"""
        # Cache to Redis (shared)
        redis_key = f"regime:{key}"
        cache.set(redis_key, data, ttl=self.regime_ttl)

        # Also cache to memory (fallback)
        with self.lock:
            self.regime_cache[key] = (data, datetime.now())

    def clear_expired(self):
        """Clear expired cache entries"""
        with self.lock:
            now = datetime.now()

            # Clear expired OHLCV
            for timeframe in list(self.ohlcv_cache.keys()):
                for ticker in list(self.ohlcv_cache[timeframe].keys()):
                    _, ts = self.ohlcv_cache[timeframe][ticker]
                    if (now - ts).seconds >= self.ohlcv_ttl:
                        del self.ohlcv_cache[timeframe][ticker]

            # Clear expired results
            for key in list(self.results_cache.keys()):
                _, ts = self.results_cache[key]
                if (now - ts).seconds >= self.results_ttl:
                    del self.results_cache[key]


class BatchDataFetcher:
    """
    Batch data fetcher using yfinance multi-ticker download
    Downloads all 50 stocks in 1 API call instead of 50 calls
    """

    # Timeframe to yfinance period/interval mapping
    TIMEFRAME_CONFIG = {
        '5m': {'period': '5d', 'interval': '5m'},
        '15m': {'period': '10d', 'interval': '15m'},
        '1h': {'period': '60d', 'interval': '1h'},
        '1d': {'period': '1y', 'interval': '1d'}
    }

    @staticmethod
    def fetch_batch(tickers: List[str], timeframe: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data for multiple tickers in one API call

        Args:
            tickers: List of ticker symbols
            timeframe: One of '5m', '15m', '1h', '1d'

        Returns:
            Dictionary mapping ticker to DataFrame
        """
        config = BatchDataFetcher.TIMEFRAME_CONFIG.get(timeframe, BatchDataFetcher.TIMEFRAME_CONFIG['1d'])

        try:
            start_time = time.time()

            # Download all tickers at once - this is the KEY optimization
            # yfinance handles batching internally and is much faster
            data = yf.download(
                tickers=tickers,
                period=config['period'],
                interval=config['interval'],
                group_by='ticker',
                auto_adjust=True,
                prepost=False,
                threads=True,  # Enable multi-threading
                progress=False  # Disable progress bar for speed
            )

            elapsed = time.time() - start_time
            logger.info(f"Batch download for {len(tickers)} tickers ({timeframe}) completed in {elapsed:.2f}s")

            # Parse the multi-ticker DataFrame into individual DataFrames
            result = {}

            if len(tickers) == 1:
                # Single ticker - different structure
                ticker = tickers[0]
                if not data.empty:
                    result[ticker] = data.copy()
            else:
                # Multiple tickers - grouped by ticker
                for ticker in tickers:
                    try:
                        if ticker in data.columns.get_level_values(0):
                            ticker_data = data[ticker].copy()
                            # Drop rows with all NaN values
                            ticker_data = ticker_data.dropna(how='all')
                            if not ticker_data.empty:
                                result[ticker] = ticker_data
                    except Exception as e:
                        logger.warning(f"Error extracting data for {ticker}: {e}")

            logger.info(f"Successfully parsed data for {len(result)} tickers")
            return result

        except Exception as e:
            logger.error(f"Batch download error: {e}")
            return {}

    @staticmethod
    def fetch_single(ticker: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Fallback: fetch single ticker data"""
        config = BatchDataFetcher.TIMEFRAME_CONFIG.get(timeframe, BatchDataFetcher.TIMEFRAME_CONFIG['1d'])

        try:
            data = yf.download(
                tickers=ticker,
                period=config['period'],
                interval=config['interval'],
                progress=False
            )
            return data if not data.empty else None
        except Exception as e:
            logger.error(f"Single download error for {ticker}: {e}")
            return None


class MTFScreenerService:
    """
    OPTIMIZED Multi-Timeframe Stock Screener Service

    Performance improvements:
    - Batch download: 50 stocks in 1 API call (NIFTY 50)
    - Single regime: Calculate once, reuse for all
    - Two-level caching: OHLCV + results
    - Two-phase screening: Quick filter then detailed
    - Parallel processing: ThreadPoolExecutor
    """

    SUPPORTED_TIMEFRAMES = ['5m', '15m', '1h', '1d']

    # Quick filter thresholds for two-phase screening (SHORT-OPTIMIZED)
    QUICK_FILTER_THRESHOLDS = {
        'min_price_change_5d': -50,  # Allow up to 50% drop (good for SHORTS!)
        'max_price_change_5d': 30,   # Max 30% gain in 5 days
        'min_volume_ratio': 0.2,     # Lowered to 20% (was too restrictive)
    }

    def __init__(self):
        """Initialize optimized screener service with dynamic stock fetching"""
        self.cache = OptimizedDataCache()
        self.data_fetcher = BatchDataFetcher()
        self.regime_detector = get_regime_detector()
        self.scoring_engine = get_scoring_engine()

        # DYNAMIC FETCHING: Get NIFTY 50 stocks from API instead of hardcoded
        logger.info("Initializing MTF Screener with dynamic NIFTY 50 fetching...")
        try:
            self.stock_universe = get_nifty50_stocks()  # Fetch from NSE API (cached 24h)
            self.sector_map = get_sector_mapping()  # Fetch sector mapping
            logger.info(f"Loaded {len(self.stock_universe)} NIFTY 50 stocks dynamically")
        except Exception as e:
            logger.error(f"Failed to fetch dynamic stock list: {e}, using fallback")
            # Fallback is handled inside nifty_fetcher
            self.stock_universe = get_nifty50_stocks()
            self.sector_map = get_sector_mapping()

        self.cache_ttl = 300  # For backward compatibility

        # Pre-computed results storage
        self._precomputed_results = {}
        self._precompute_lock = Lock()

        # Background job flag
        self._background_running = False

        # FIX #1: Request deduplication locks (one per timeframe)
        # Prevents multiple parallel requests from downloading the same data
        self._download_locks = {tf: Lock() for tf in self.SUPPORTED_TIMEFRAMES}
        self._pending_downloads = {}  # Track in-progress downloads

        # FIX #3: Screening deduplication locks (one per timeframe)
        # Prevents longs/shorts/heatmap from all running screen_all_stocks in parallel
        self._screening_locks = {tf: Lock() for tf in self.SUPPORTED_TIMEFRAMES}

        # FIX #2: Shared ThreadPoolExecutor (class-level, not context manager)
        # Prevents "cannot schedule new futures after interpreter shutdown" error
        self._executor = ThreadPoolExecutor(max_workers=20)

        # Store reference to nifty fetcher for refresh capability
        self._nifty_fetcher = get_nifty_fetcher()

        # Pre-train HMM model in background on startup
        # This prevents first request from being slow (9.32s saved!)
        if not self.regime_detector.is_trained:
            logger.info("🚀 Starting background HMM model pre-training...")
            self._pre_train_model_background()
        else:
            logger.info("✅ HMM model already loaded from disk - ready to use!")
            # Pre-warm regime cache in background so first request is fast
            self._pre_warm_cache_background()

    def _pre_train_model_background(self):
        """
        Pre-train HMM regime model in background thread on startup
        This makes first user request fast (2-3s instead of 12s!)
        After training, also pre-warms the regime cache.
        """
        def train_model():
            try:
                logger.info("⏳ Pre-training HMM model on NIFTY 50 (2y data)...")
                start_time = time.time()

                result = self.regime_detector.train("^NSEI", "2y")

                elapsed = time.time() - start_time

                if result.get("status") == "success":
                    logger.info(f"✅ HMM model pre-trained successfully in {elapsed:.2f}s")
                    logger.info(f"   Model score: {result.get('model_score', 0):.2f}")
                    # After training, pre-warm the regime cache
                    self._do_pre_warm_cache()
                else:
                    logger.warning(f"⚠️ HMM pre-training failed: {result.get('message')}")

            except Exception as e:
                logger.error(f"❌ Error in background HMM training: {str(e)}")

        # Start training in daemon thread (won't block server startup)
        training_thread = Thread(target=train_model, daemon=True, name="HMM-PreTraining")
        training_thread.start()
        logger.info("🔄 HMM training started in background (server ready to accept requests)")

    def _pre_warm_cache_background(self):
        """Pre-warm regime and screening caches in a background thread"""
        def warm_cache():
            self._do_pre_warm_cache()
        thread = Thread(target=warm_cache, daemon=True, name="Cache-PreWarm")
        thread.start()
        logger.info("🔄 Cache pre-warming started in background")

    def _do_pre_warm_cache(self):
        """Actually pre-warm caches (regime + screening for all timeframes)"""
        try:
            # Pre-warm regime cache
            logger.info("🔥 Pre-warming regime cache...")
            regime = self.get_nifty_regime_strip()
            if regime.get('status') == 'success':
                logger.info(f"✅ Regime cache warmed: {regime.get('current_regime', 'Unknown')}")

            # Pre-warm screening results for all timeframes
            logger.info("🔥 Pre-warming screening results for all timeframes...")
            for tf in self.SUPPORTED_TIMEFRAMES:
                try:
                    result = self.screen_all_stocks(tf)
                    if result.get('status') == 'success':
                        logger.info(f"✅ Pre-warmed {tf} screening cache ({result.get('processing_time_seconds', 0)}s)")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to pre-warm {tf}: {e}")

            logger.info("✅ All caches pre-warmed successfully!")
        except Exception as e:
            logger.error(f"❌ Error pre-warming caches: {str(e)}")

    def __del__(self):
        """Cleanup executor on service destruction"""
        try:
            self._executor.shutdown(wait=False)
        except:
            pass

    def _get_cache_key(self, prefix: str, *args) -> str:
        """Generate cache key"""
        return f"{prefix}_{'_'.join(str(a) for a in args)}"

    def get_nifty_regime_strip(self) -> Dict[str, Any]:
        """
        Get NIFTY 50 regime using HMM model for accurate buy/sell signals

        Returns actual regime detection with real market signals
        """
        # Check cache first
        cached = self.cache.get_regime()
        if cached:
            logger.debug("Using cached regime data")
            return cached

        try:
            # Use the actual HMM regime detector instead of hardcoded neutral
            regime_result = self.regime_detector.get_nifty_regime_strip()

            if regime_result.get("status") != "success":
                logger.warning("Regime detection failed, using fallback")
                # Fallback - still try to detect something instead of neutral
                result = {
                    "status": "success",
                    "current_regime": "Low Volatility",
                    "regime_name": "Low Volatility",
                    "confidence": 0.5,
                    "bias": "NEUTRAL",
                    "color": "#3b82f6",
                    "short_favorable": False,
                    "probabilities": {
                        "Bullish Trend": 0.25,
                        "Bearish Trend": 0.25,
                        "High Volatility": 0.25,
                        "Low Volatility": 0.25
                    },
                    "description": "Fallback regime - using default settings",
                    "timestamp": datetime.now().isoformat()
                }
            else:
                result = regime_result

            self.cache.set_regime(result)
            return result
        except Exception as e:
            logger.error(f"Error getting regime strip: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "current_regime": "Unknown"
            }

    def _batch_download_stocks(self, timeframe: str) -> Dict[str, pd.DataFrame]:
        """
        Download all stocks in batch (OPTIMIZED with request deduplication)

        FIX #1: Uses locks to prevent duplicate downloads when multiple
        parallel requests hit the same timeframe simultaneously.

        Returns:
            Dictionary mapping ticker to DataFrame
        """
        # FIX #1: Acquire lock for this timeframe to prevent duplicate downloads
        with self._download_locks[timeframe]:
            # Check cache INSIDE the lock (double-check pattern)
            # This ensures only ONE request proceeds to download
            cached_data = {}
            missing_tickers = []

            for ticker in self.stock_universe:
                cached = self.cache.get_ohlcv(timeframe, ticker)
                if cached is not None:
                    cached_data[ticker] = cached
                else:
                    missing_tickers.append(ticker)

            if not missing_tickers:
                logger.info(f"All {len(cached_data)} tickers served from cache ({timeframe})")
                return cached_data

            # Only one request per timeframe will reach here
            logger.info(f"Batch downloading {len(missing_tickers)} tickers for {timeframe} (cached: {len(cached_data)})")
            new_data = BatchDataFetcher.fetch_batch(missing_tickers, timeframe)

            # Cache new data
            if new_data:
                self.cache.set_ohlcv_batch(timeframe, new_data)

            # Merge cached and new data
            return {**cached_data, **new_data}

    def _quick_filter(self, all_data: Dict[str, pd.DataFrame]) -> List[str]:
        """
        Phase 1: Quick filter to eliminate obviously bad candidates

        Reduces 50 stocks to ~15-25 candidates for detailed analysis

        Args:
            all_data: Dictionary of ticker -> DataFrame

        Returns:
            List of tickers that pass the quick filter
        """
        passed = []

        for ticker, df in all_data.items():
            try:
                if df is None or df.empty or len(df) < 5:
                    continue

                # Basic data quality check
                if 'Close' not in df.columns or 'Volume' not in df.columns:
                    continue

                current_price = df['Close'].iloc[-1]
                if pd.isna(current_price) or current_price <= 0:
                    continue

                # Price change filter (last 5 periods)
                if len(df) >= 5:
                    price_5d_ago = df['Close'].iloc[-5]
                    if price_5d_ago > 0:
                        price_change = ((current_price - price_5d_ago) / price_5d_ago) * 100

                        if price_change < self.QUICK_FILTER_THRESHOLDS['min_price_change_5d']:
                            continue
                        if price_change > self.QUICK_FILTER_THRESHOLDS['max_price_change_5d']:
                            continue

                # Volume filter
                avg_volume = df['Volume'].rolling(20).mean().iloc[-1]
                current_volume = df['Volume'].iloc[-1]

                if avg_volume > 0:
                    vol_ratio = current_volume / avg_volume
                    if vol_ratio < self.QUICK_FILTER_THRESHOLDS['min_volume_ratio']:
                        continue

                passed.append(ticker)

            except Exception as e:
                logger.debug(f"Quick filter error for {ticker}: {e}")
                continue

        logger.info(f"Quick filter: {len(passed)}/{len(all_data)} stocks passed")
        return passed

    def _analyze_stock_fast(self, ticker: str, df: pd.DataFrame, timeframe: str,
                            regime_data: Dict) -> Optional[Dict]:
        """
        Phase 2: Detailed analysis for filtered candidates with DUAL scoring

        Uses pre-fetched data to avoid API calls
        Calculates both LONG and SHORT scores
        """
        try:
            start_time = time.time()

            # Use pre-fetched data - NO API CALL
            indicator_calc = MTFIndicatorCalculator(
                ticker, timeframe,
                pre_fetched_data=df  # Pass pre-fetched data
            )

            all_indicators = indicator_calc.get_all_indicators()

            if all_indicators.get('current_price', 0) == 0:
                return None

            # Detect patterns
            pattern_detector = PatternDetector(df)
            pattern_data = pattern_detector.get_all_patterns()

            # Determine signal bias (will be overridden by dual scoring)
            trend = all_indicators.get('trend', {})
            pattern_bias = pattern_data.get('dominant_bias', 'NEUTRAL')
            trend_bias = trend.get('overall_trend', 'neutral')

            if pattern_bias != 'NEUTRAL':
                initial_bias = pattern_bias
            elif trend_bias == 'bullish':
                initial_bias = 'LONG'
            elif trend_bias == 'bearish':
                initial_bias = 'SHORT'
            else:
                initial_bias = 'NEUTRAL'

            # Calculate risk-reward
            entry_price = all_indicators.get('current_price', 0)
            risk_reward_engine = RiskRewardEngine(df, timeframe)
            trade_setup = risk_reward_engine.get_trade_setup(
                entry_price, initial_bias,
                indicators=all_indicators,
                score=75
            )

            # Calculate LONG score (using shared regime data)
            scoring_data = {
                'regime_data': regime_data,
                'signal_bias': initial_bias,
                'trend_data': all_indicators.get('trend', {}),
                'pattern_data': pattern_data,
                'volume_data': all_indicators.get('volume', {}),
                'momentum_data': all_indicators.get('momentum', {}),
                'trade_setup': trade_setup,
                'df': df,  # Add DataFrame for SHORT scoring
                'timeframe': timeframe
            }

            # Calculate DUAL score (LONG + SHORT)
            dual_score_result = self.scoring_engine.calculate_dual_score(scoring_data)

            long_score = dual_score_result.get('long_score', 50)
            short_score = dual_score_result.get('short_score', 30)
            direction = dual_score_result.get('direction', 'HOLD')
            final_score = dual_score_result.get('total_score', 50)

            # Use direction from dual scoring
            signal_bias = direction if direction != 'HOLD' else initial_bias

            # Get SHORT-specific signals if SHORT modules available
            short_signals = None
            short_trade_setup = None
            if SHORT_MODULES_AVAILABLE and short_score >= 50:
                try:
                    selling_aggregator = SellingSignalAggregator(df, timeframe)
                    regime_name = regime_data.get('current_regime', 'Unknown')
                    short_analysis = selling_aggregator.get_all_short_signals(regime_name)
                    short_signals = short_analysis.get('best_signal')
                    short_trade_setup = short_analysis.get('trade_setup')
                except Exception as e:
                    logger.debug(f"Error getting SHORT signals for {ticker}: {e}")

            # Update trade setup based on direction
            if direction == 'SHORT' and short_trade_setup:
                trade_setup = {
                    'entry_price': short_trade_setup.get('entry', entry_price),
                    'stop_loss': short_trade_setup.get('stop_loss', entry_price * 1.03),
                    'target_1': short_trade_setup.get('target', entry_price * 0.97),
                    'target_2': short_trade_setup.get('target', entry_price * 0.95) * 0.98,
                    'rr_ratio': short_trade_setup.get('risk_reward', 2.0),
                    'rr_string': f"1:{short_trade_setup.get('risk_reward', 2.0):.1f}",
                    'risk_percentage': 3.0,
                    'direction': 'SHORT'
                }
            else:
                trade_setup = risk_reward_engine.get_trade_setup(
                    entry_price, signal_bias,
                    indicators=all_indicators,
                    score=final_score
                )
                trade_setup['direction'] = 'LONG'

            processing_time = time.time() - start_time

            return {
                'ticker': ticker,
                'total_score': final_score,
                'long_score': long_score,
                'short_score': short_score,
                'direction': direction,
                'eligible': dual_score_result.get('eligible', False),
                'signal_bias': signal_bias,
                'current_price': entry_price,
                'trade_setup': trade_setup,
                'short_trade_setup': short_trade_setup,
                'short_signals': short_signals,
                'regime': {
                    'name': regime_data.get('current_regime', 'Unknown'),
                    'confidence': regime_data.get('confidence', 0),
                    'bias': regime_data.get('bias', 'NEUTRAL'),
                    'color': regime_data.get('color', '#6b7280'),
                    'short_favorable': regime_data.get('short_favorable', False)
                },
                'patterns': pattern_data,
                'indicators': all_indicators,
                'sector': self.sector_map.get(ticker, 'Unknown'),
                'category': dual_score_result.get('category', 'D'),
                'score_breakdown': dual_score_result.get('long_breakdown', {}),
                'short_breakdown': dual_score_result.get('short_breakdown', {}),
                'processing_time_ms': round(processing_time * 1000, 2)
            }

        except Exception as e:
            logger.debug(f"Error analyzing {ticker}: {e}")
            return None

    def screen_single_stock(self, ticker: str, timeframe: str) -> Dict[str, Any]:
        """
        Screen a single stock (OPTIMIZED with caching)
        """
        cache_key = self._get_cache_key("stock", ticker, timeframe)

        # Check results cache
        cached = self.cache.get_result(cache_key)
        if cached:
            return cached

        try:
            start_time = time.time()

            # Get regime data (cached)
            regime_data = self.get_nifty_regime_strip()

            # Get stock data (check cache first)
            df = self.cache.get_ohlcv(timeframe, ticker)
            if df is None:
                df = BatchDataFetcher.fetch_single(ticker, timeframe)
                if df is not None:
                    self.cache.set_ohlcv(timeframe, ticker, df)

            if df is None or df.empty:
                return {
                    "status": "error",
                    "message": f"No data available for {ticker}",
                    "ticker": ticker,
                    "timeframe": timeframe
                }

            # Analyze
            analysis = self._analyze_stock_fast(ticker, df, timeframe, regime_data)

            if analysis is None:
                return {
                    "status": "error",
                    "message": f"Analysis failed for {ticker}",
                    "ticker": ticker,
                    "timeframe": timeframe
                }

            processing_time = time.time() - start_time

            result = {
                "status": "success",
                "ticker": ticker,
                "timeframe": timeframe,
                "current_price": analysis['current_price'],
                "signal_bias": analysis['signal_bias'],
                "score": analysis['total_score'],
                "eligible": analysis['eligible'],
                "category": analysis['category'],
                "score_breakdown": analysis['score_breakdown'],
                "regime": analysis['regime'],
                "trade_setup": {
                    "entry": analysis['trade_setup'].get('entry_price', analysis['current_price']),
                    "stop_loss": analysis['trade_setup'].get('stop_loss', 0),
                    "target_1": analysis['trade_setup'].get('target_1', 0),
                    "target_2": analysis['trade_setup'].get('target_2', 0),
                    "rr_ratio": analysis['trade_setup'].get('rr_ratio', 0),
                    "rr_string": analysis['trade_setup'].get('rr_string', '1:0'),
                    "risk_percentage": analysis['trade_setup'].get('risk_percentage', 0)
                },
                "indicators": {
                    "trend": analysis['indicators'].get('trend', {}),
                    "momentum": analysis['indicators'].get('momentum', {}),
                    "volatility": analysis['indicators'].get('volatility', {}),
                    "volume": analysis['indicators'].get('volume', {})
                },
                "patterns": {
                    "best_pattern": analysis['patterns'].get('best_pattern'),
                    "total_patterns": analysis['patterns'].get('total_patterns', 0),
                    "dominant_bias": analysis['patterns'].get('dominant_bias', 'NEUTRAL')
                },
                "sector": analysis['sector'],
                "processing_time_ms": round(processing_time * 1000, 2),
                "timestamp": datetime.now().isoformat()
            }

            # Cache result
            self.cache.set_result(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Error screening {ticker}: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "ticker": ticker,
                "timeframe": timeframe
            }

    def screen_all_stocks(self, timeframe: str, max_workers: int = 20) -> Dict[str, Any]:
        """
        Screen all NIFTY 50 stocks (OPTIMIZED)

        Two-phase approach:
        1. Batch download all data (1 API call)
        2. Quick filter to ~15-25 candidates
        3. Parallel detailed analysis

        Target: 1-5 seconds (50% faster with NIFTY 50)

        Uses screening lock to prevent duplicate work when longs/shorts/heatmap
        all call this method simultaneously for the same timeframe.
        """
        cache_key = self._get_cache_key("all_stocks", timeframe)

        # Check results cache BEFORE acquiring lock (fast path)
        cached = self.cache.get_result(cache_key)
        if cached:
            logger.info(f"Returning cached results for {timeframe}")
            return cached

        # Acquire screening lock - only one thread screens per timeframe
        with self._screening_locks[timeframe]:
            # Double-check cache INSIDE lock (another thread may have just finished)
            cached = self.cache.get_result(cache_key)
            if cached:
                logger.info(f"Returning cached results for {timeframe} (populated by another request)")
                return cached

            return self._do_screen_all_stocks(timeframe, cache_key, max_workers)

    def _do_screen_all_stocks(self, timeframe: str, cache_key: str, max_workers: int = 20) -> Dict[str, Any]:
        """Internal: actual screening logic, called under lock"""
        try:
            start_time = time.time()

            # Step 1: Get regime strip (cached - single calculation)
            regime_strip = self.get_nifty_regime_strip()
            regime_time = time.time() - start_time
            logger.info(f"Regime calculation: {regime_time:.2f}s")

            # Step 2: Batch download all stocks (1 API call)
            download_start = time.time()
            all_data = self._batch_download_stocks(timeframe)
            download_time = time.time() - download_start
            logger.info(f"Batch download: {download_time:.2f}s for {len(all_data)} stocks")

            # Step 3: Quick filter (Phase 1)
            filter_start = time.time()
            filtered_tickers = self._quick_filter(all_data)
            filter_time = time.time() - filter_start
            logger.info(f"Quick filter: {filter_time:.2f}s")

            # Step 4: Parallel detailed analysis (Phase 2)
            # FIX #2: Use class-level executor instead of context manager
            # This prevents "cannot schedule new futures after interpreter shutdown" error
            analysis_start = time.time()
            results = []

            # Use the shared executor (not context manager)
            future_to_ticker = {
                self._executor.submit(
                    self._analyze_stock_fast,
                    ticker,
                    all_data[ticker],
                    timeframe,
                    regime_strip
                ): ticker
                for ticker in filtered_tickers
                if ticker in all_data
            }

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    logger.debug(f"Analysis error for {ticker}: {e}")

            analysis_time = time.time() - analysis_start
            logger.info(f"Detailed analysis: {analysis_time:.2f}s for {len(results)} stocks")

            # Step 5: Rank and select top 5
            top_stocks = self.scoring_engine.rank_stocks(results, self.sector_map)

            # Format for frontend with DUAL scoring
            formatted_stocks = []
            for stock in top_stocks:
                trade = stock.get('trade_setup', {})
                regime = stock.get('regime', {})
                patterns = stock.get('patterns', {})
                indicators = stock.get('indicators', {})
                short_signals = stock.get('short_signals')

                # Determine direction display
                direction = stock.get('direction', 'HOLD')
                long_score = stock.get('long_score', stock.get('total_score', 0))
                short_score = stock.get('short_score', 30)

                formatted_stocks.append({
                    'symbol': stock.get('ticker', '').replace('.NS', ''),
                    'ticker': stock.get('ticker', ''),
                    'score': stock.get('total_score', 0),
                    'long_score': long_score,
                    'short_score': short_score,
                    'direction': direction,
                    'rank': stock.get('rank', 0),
                    'bias': stock.get('signal_bias', 'NEUTRAL'),
                    'entry': trade.get('entry_price', 0),
                    'stop_loss': trade.get('stop_loss', 0),
                    'target_1': trade.get('target_1', 0),
                    'target_2': trade.get('target_2', 0),
                    'rr_ratio': trade.get('rr_ratio', 0),
                    'rr_string': trade.get('rr_string', '1:0'),
                    'risk_percentage': trade.get('risk_percentage', 0),
                    'trade_direction': trade.get('direction', 'LONG'),
                    'regime': regime.get('name', 'Unknown'),
                    'regime_color': regime.get('color', '#6b7280'),
                    'short_favorable': regime.get('short_favorable', False),
                    'volume_bar': indicators.get('volume', {}).get('volume_score', 50),
                    'momentum_bar': indicators.get('momentum', {}).get('momentum_score', 50),
                    'pattern': patterns.get('best_pattern', {}).get('type', 'None') if patterns.get('best_pattern') else 'No Pattern',
                    'short_signal': short_signals.get('type', 'None') if short_signals else 'None',
                    'short_confidence': short_signals.get('confidence', 0) if short_signals else 0,
                    'sector': stock.get('sector', 'Unknown'),
                    'category': stock.get('category', 'D'),
                    'eligible': stock.get('eligible', False)
                })

            total_time = time.time() - start_time

            result = {
                "status": "success",
                "timeframe": timeframe,
                "regime_strip": regime_strip,
                "top_stocks": formatted_stocks,
                "total_screened": len(self.stock_universe),
                "filtered_count": len(filtered_tickers),
                "qualified_count": len([s for s in results if s.get('eligible', False)]),
                "processing_time_seconds": round(total_time, 2),
                "performance_breakdown": {
                    "regime_calculation_s": round(regime_time, 2),
                    "batch_download_s": round(download_time, 2),
                    "quick_filter_s": round(filter_time, 2),
                    "detailed_analysis_s": round(analysis_time, 2)
                },
                "timestamp": datetime.now().isoformat()
            }

            # Cache result
            self.cache.set_result(cache_key, result)

            logger.info(f"TOTAL screening time: {total_time:.2f}s for {timeframe}")

            return result

        except Exception as e:
            logger.error(f"Error screening all stocks: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": str(e),
                "timeframe": timeframe
            }

    def get_sector_heatmap(self, timeframe: str) -> Dict[str, Any]:
        """Get sector performance heatmap (uses cached screening results)"""
        try:
            # Get all stock results (uses cache)
            all_results = self.screen_all_stocks(timeframe)

            if all_results.get('status') != 'success':
                return {"status": "error", "message": "Failed to get stock data"}

            # Aggregate by sector
            sector_data = {}
            for stock in all_results.get('top_stocks', []):
                sector = stock.get('sector', 'Unknown')
                if sector not in sector_data:
                    sector_data[sector] = {
                        'scores': [],
                        'stocks': [],
                        'long_count': 0,
                        'short_count': 0
                    }

                sector_data[sector]['scores'].append(stock.get('score', 0))
                sector_data[sector]['stocks'].append(stock)

                if stock.get('bias') == 'LONG':
                    sector_data[sector]['long_count'] += 1
                elif stock.get('bias') == 'SHORT':
                    sector_data[sector]['short_count'] += 1

            # Calculate sector metrics
            heatmap = {}
            for sector, data in sector_data.items():
                avg_score = np.mean(data['scores']) if data['scores'] else 0
                top_stock = max(data['stocks'], key=lambda x: x.get('score', 0)) if data['stocks'] else None

                if data['long_count'] > data['short_count']:
                    sentiment = 'bullish'
                elif data['short_count'] > data['long_count']:
                    sentiment = 'bearish'
                else:
                    sentiment = 'neutral'

                heatmap[sector] = {
                    'score': round(float(avg_score), 1),
                    'top_stock': top_stock.get('symbol', '') if top_stock else '',
                    'sentiment': sentiment,
                    'stock_count': len(data['stocks']),
                    'long_count': data['long_count'],
                    'short_count': data['short_count']
                }

            return {
                "status": "success",
                "timeframe": timeframe,
                "sectors": heatmap,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating sector heatmap: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_all_timeframe_results(self) -> Dict[str, Any]:
        """Get screening results for all 4 timeframes"""
        try:
            start_time = time.time()

            # Get regime strip (shared across timeframes)
            regime_strip = self.get_nifty_regime_strip()

            # Screen each timeframe (results are cached)
            timeframe_results = {}
            for tf in self.SUPPORTED_TIMEFRAMES:
                result = self.screen_all_stocks(tf)
                timeframe_results[tf] = {
                    'top_stocks': result.get('top_stocks', []),
                    'qualified_count': result.get('qualified_count', 0),
                    'total_screened': result.get('total_screened', 0)
                }

            processing_time = time.time() - start_time

            return {
                "status": "success",
                "regime_strip": regime_strip,
                "timeframes": timeframe_results,
                "processing_time_seconds": round(processing_time, 2),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting all timeframe results: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_full_data(self, timeframe: str) -> Dict[str, Any]:
        """
        Get ALL data for a timeframe in a single call: longs, shorts, heatmap, and regime.

        This eliminates the need for 3 separate API calls (longs + shorts + heatmap)
        that all internally call screen_all_stocks(), preventing redundant work.

        Returns:
            Dictionary with top_longs, top_shorts, sector_heatmap, and regime_strip
        """
        try:
            start_time = time.time()

            # Single call to screen_all_stocks (cached + dedup-locked)
            result = self.screen_all_stocks(timeframe)

            if result.get('status') != 'success':
                return result

            all_stocks = result.get('top_stocks', [])
            regime_strip = result.get('regime_strip', {})

            # Sort and filter for LONGS
            longs_sorted = sorted(all_stocks, key=lambda x: x.get('long_score', 0), reverse=True)
            top_longs = [s for s in longs_sorted if s.get('long_score', 0) >= 65 and s.get('direction') in ['LONG', 'HOLD']][:5]
            for i, stock in enumerate(top_longs, 1):
                stock['long_rank'] = i

            # Sort and filter for SHORTS
            shorts_sorted = sorted(all_stocks, key=lambda x: x.get('short_score', 0), reverse=True)
            top_shorts = [s for s in shorts_sorted if s.get('short_score', 0) >= 50][:10]
            for i, stock in enumerate(top_shorts, 1):
                stock['short_rank'] = i

            # Build sector heatmap from same data
            sector_data = {}
            for stock in all_stocks:
                sector = stock.get('sector', 'Unknown')
                if sector not in sector_data:
                    sector_data[sector] = {'scores': [], 'stocks': [], 'long_count': 0, 'short_count': 0}
                sector_data[sector]['scores'].append(stock.get('score', 0))
                sector_data[sector]['stocks'].append(stock)
                if stock.get('bias') == 'LONG':
                    sector_data[sector]['long_count'] += 1
                elif stock.get('bias') == 'SHORT':
                    sector_data[sector]['short_count'] += 1

            heatmap = {}
            for sector, data in sector_data.items():
                avg_score = np.mean(data['scores']) if data['scores'] else 0
                top_stock = max(data['stocks'], key=lambda x: x.get('score', 0)) if data['stocks'] else None
                if data['long_count'] > data['short_count']:
                    sentiment = 'bullish'
                elif data['short_count'] > data['long_count']:
                    sentiment = 'bearish'
                else:
                    sentiment = 'neutral'
                heatmap[sector] = {
                    'score': round(float(avg_score), 1),
                    'top_stock': top_stock.get('symbol', '') if top_stock else '',
                    'sentiment': sentiment,
                    'stock_count': len(data['stocks']),
                    'long_count': data['long_count'],
                    'short_count': data['short_count']
                }

            # Get regime with SHORT interpretation
            regime_with_short = regime_strip.copy()
            try:
                regime_id = regime_strip.get('regime_id', 3)
                short_info = self.regime_detector.get_short_regime_info(regime_id)
                regime_with_short['short_interpretation'] = short_info['short_interpretation']
                regime_with_short['short_score_multiplier'] = short_info['short_score_multiplier']
                regime_with_short['short_strategy'] = short_info['short_strategy']
                regime_with_short['short_favorable'] = short_info['short_favorable']
                regime_with_short['target_extension'] = short_info.get('target_extension', 1.0)
            except Exception as e:
                logger.debug(f"Error adding SHORT info to regime: {e}")

            total_time = time.time() - start_time

            return {
                "status": "success",
                "timeframe": timeframe,
                "regime_strip": regime_with_short,
                "top_longs": top_longs,
                "longs_found": len(top_longs),
                "top_shorts": top_shorts,
                "shorts_found": len(top_shorts),
                "sectors": heatmap,
                "total_screened": result.get('total_screened', 0),
                "qualified_count": result.get('qualified_count', 0),
                "processing_time_seconds": round(total_time, 2),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error in get_full_data for {timeframe}: {str(e)}")
            return {"status": "error", "message": str(e), "timeframe": timeframe}

    def precompute_results(self):
        """
        Background pre-computation of screening results

        Call this periodically (e.g., every 5 minutes) to keep results fresh
        """
        logger.info("Starting background pre-computation...")

        try:
            for timeframe in self.SUPPORTED_TIMEFRAMES:
                self.screen_all_stocks(timeframe)
                logger.info(f"Pre-computed results for {timeframe}")

            logger.info("Background pre-computation complete")

        except Exception as e:
            logger.error(f"Pre-computation error: {e}")

    def refresh_stock_universe(self) -> Dict[str, Any]:
        """
        Refresh NIFTY 50 stock universe from API

        Returns:
            Status and updated stock info
        """
        try:
            logger.info("Refreshing NIFTY 50 stock universe...")

            # Force refresh from API
            self.stock_universe = self._nifty_fetcher.get_nifty50_stocks(force_refresh=True)
            self.sector_map = self._nifty_fetcher.get_sector_mapping()

            # Clear screening cache since stock list changed
            self.cache.clear_expired()

            info = self._nifty_fetcher.get_stock_info()

            logger.info(f"Stock universe refreshed: {len(self.stock_universe)} stocks")

            return {
                'status': 'success',
                'message': f'Stock universe refreshed: {len(self.stock_universe)} stocks',
                'data': info
            }
        except Exception as e:
            logger.error(f"Error refreshing stock universe: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    def get_stock_universe_info(self) -> Dict[str, Any]:
        """
        Get current stock universe information

        Returns:
            Stock list, count, sectors, and metadata
        """
        return self._nifty_fetcher.get_stock_info()


# Singleton instance
_mtf_screener_service = None


def get_mtf_screener_service() -> MTFScreenerService:
    """Get singleton MTF screener service instance"""
    global _mtf_screener_service
    if _mtf_screener_service is None:
        _mtf_screener_service = MTFScreenerService()
    return _mtf_screener_service


# Optional: Background scheduler setup
def start_background_precomputation(interval_minutes: int = 5):
    """
    Start background pre-computation thread

    Usage:
        from services.mtf_screener_service import start_background_precomputation
        start_background_precomputation(5)  # Every 5 minutes
    """
    import threading
    import time as time_module

    def background_worker():
        service = get_mtf_screener_service()
        while True:
            try:
                service.precompute_results()
            except Exception as e:
                logger.error(f"Background worker error: {e}")

            time_module.sleep(interval_minutes * 60)

    thread = threading.Thread(target=background_worker, daemon=True)
    thread.start()
    logger.info(f"Background pre-computation started (interval: {interval_minutes} min)")
    return thread
