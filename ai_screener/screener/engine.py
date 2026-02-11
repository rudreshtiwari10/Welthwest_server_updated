"""Core screening engine -- the heart of WelthWest AI Screener.
Orchestrates: data fetch -> feature computation -> scoring -> ranking -> explanation.

This engine uses heuristic scoring (rule-based) by default, which works
without any trained ML models. When models are available, it uses them instead.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import Optional
import logging

from ai_screener.config.settings import get_settings, TIMEFRAME_CONFIG
from ai_screener.data.providers.yfinance_provider import YFinanceIndiaProvider
from ai_screener.features.pipeline import FeaturePipeline
from ai_screener.screener.scorer import CompositeScorer, REGIME_ADJUSTMENTS
from ai_screener.screener.explainer import SignalExplainer

logger = logging.getLogger(__name__)

# In-memory cache for screening results
_screening_cache: dict = {"results": [], "timestamp": None, "regime": None}


def detect_regime_heuristic(index_df: pd.DataFrame) -> dict:
    """Detect market regime using heuristic rules on NIFTY 50 data.
    Works without a trained HMM model.
    """
    if index_df.empty or len(index_df) < 60:
        return {
            "regime": "sideways",
            "confidence": 0.5,
            "state_probabilities": {},
            "adjustments": REGIME_ADJUSTMENTS["sideways"],
            "volatility_percentile": 0.5,
            "description": REGIME_ADJUSTMENTS["sideways"]["description"],
        }

    close = index_df["close"].values
    returns = pd.Series(close).pct_change().dropna()

    # 20-day and 60-day returns
    ret_20d = (close[-1] / close[-20] - 1) * 100 if len(close) >= 20 else 0
    ret_60d = (close[-1] / close[-60] - 1) * 100 if len(close) >= 60 else 0

    # Volatility: 21-day rolling std annualized
    vol_21d = float(returns.iloc[-21:].std() * np.sqrt(252)) if len(returns) >= 21 else 0.15
    vol_median = float(returns.rolling(21).std().median() * np.sqrt(252)) if len(returns) >= 42 else 0.15

    is_bull = ret_20d > 1 and ret_60d > 0
    is_bear = ret_20d < -1 and ret_60d < 0
    is_high_vol = vol_21d > vol_median * 1.2

    if is_bull and not is_high_vol:
        regime = "bull_low_vol"
        confidence = min(0.9, 0.6 + abs(ret_20d) / 20)
    elif is_bull and is_high_vol:
        regime = "bull_high_vol"
        confidence = min(0.85, 0.55 + abs(ret_20d) / 25)
    elif is_bear and not is_high_vol:
        regime = "bear_low_vol"
        confidence = min(0.85, 0.55 + abs(ret_20d) / 20)
    elif is_bear and is_high_vol:
        regime = "bear_high_vol"
        confidence = min(0.9, 0.6 + abs(ret_20d) / 15)
    else:
        regime = "sideways"
        confidence = 0.6

    vol_pct = float(pd.Series(returns.rolling(21).std()).rank(pct=True).iloc[-1]) if len(returns) >= 42 else 0.5

    adjustments = REGIME_ADJUSTMENTS.get(regime, REGIME_ADJUSTMENTS["sideways"])

    return {
        "regime": regime,
        "confidence": round(confidence, 3),
        "state_probabilities": {regime: confidence},
        "adjustments": adjustments,
        "volatility_percentile": round(vol_pct, 3),
        "description": adjustments["description"],
        "nifty_20d_return": round(ret_20d, 2),
        "nifty_60d_return": round(ret_60d, 2),
        "annualized_volatility": round(vol_21d * 100, 2),
    }


class ScreeningEngine:
    """Main screening engine that produces the final screened stock list."""

    def __init__(self):
        self.provider = YFinanceIndiaProvider()
        self.pipeline = FeaturePipeline()
        self.scorer = CompositeScorer()
        self.explainer = SignalExplainer()
        settings = get_settings()
        self.symbols = settings.nifty50_symbols

    def run_screen(
        self,
        symbols: Optional[list[str]] = None,
        top_n: int = 50,
        min_score: float = 0,
        sectors: Optional[list[str]] = None,
        timeframe: str = "1d",
    ) -> dict:
        """Run the complete screening pipeline.

        Returns dict with: timestamp, regime, regime_confidence, total_screened, results
        """
        global _screening_cache

        symbols = symbols or self.symbols
        tf_config = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1d"])
        logger.info(f"Starting screening for {len(symbols)} symbols (timeframe={timeframe})")

        # 1. Fetch NIFTY 50 index for regime detection
        logger.info("Step 1: Fetching NIFTY 50 index data for regime detection")
        index_df = self.provider.fetch_index_data("NIFTY50")
        regime_info = detect_regime_heuristic(index_df)
        logger.info(f"Regime detected: {regime_info['regime']} (confidence: {regime_info['confidence']})")

        # 2. Bulk fetch price data
        logger.info(f"Step 2: Fetching price data for {len(symbols)} stocks ({timeframe})")
        end_date = date.today()
        start_date = end_date - timedelta(days=tf_config["max_history_days"])
        price_data = self.provider.fetch_bulk_prices(symbols, start_date, end_date, interval=timeframe)
        logger.info(f"Got price data for {len(price_data)} stocks")

        # 3. Bulk-fetch fundamentals in parallel (8 threads)
        min_bars = tf_config["min_bars"]
        valid_symbols = [s for s in symbols if s in price_data and len(price_data[s]) >= min_bars]
        logger.info(f"Step 3: Fetching fundamentals for {len(valid_symbols)} stocks in parallel")
        all_fundamentals = self.provider.fetch_bulk_fundamentals(valid_symbols, max_workers=8)

        # 4. Compute features and score each stock
        logger.info("Step 4: Computing features and scoring")
        results = []

        for symbol in valid_symbols:
            try:
                df = price_data[symbol]
                current_price = float(df["close"].iloc[-1])

                fundamentals = all_fundamentals.get(symbol, {})

                # Compute features + anomaly records
                features, anomaly_records = self.pipeline.compute_features(
                    price_df=df,
                    current_price=current_price,
                    market_cap=fundamentals.get("market_cap", 0),
                    timeframe=timeframe,
                )

                # Score using heuristic (pass anomaly records for risk adjustment)
                momentum_prob = self.scorer.heuristic_momentum_probability(features)
                crash_prob = self.scorer.heuristic_crash_probability(features)

                composite = self.scorer.compute_score(
                    momentum_probability=momentum_prob,
                    crash_probability=crash_prob,
                    features=features,
                    regime_adjustments=regime_info["adjustments"],
                    anomaly_records=anomaly_records,
                )

                # Extract signals and explanation
                top_signals = self.explainer.extract_top_signals(features)
                explanation = self.explainer.generate_explanation(
                    symbol=symbol,
                    top_signals=top_signals,
                    regime=regime_info["regime"],
                    composite_score=composite,
                    timeframe=timeframe,
                    anomaly_records=anomaly_records,
                )

                result = {
                    "symbol": symbol,
                    "name": fundamentals.get("name", symbol),
                    "market": "NSE",
                    "sector": fundamentals.get("sector", ""),
                    "industry": fundamentals.get("industry", ""),
                    "overall_score": composite["overall_score"],
                    "momentum_score": composite["momentum_score"],
                    "risk_score": composite["risk_score"],
                    "momentum_probability": round(momentum_prob, 4),
                    "crash_probability": round(crash_prob, 4),
                    "regime": regime_info["regime"],
                    "regime_confidence": regime_info["confidence"],
                    "top_signals": top_signals,
                    "explanation": explanation,
                    "current_price": round(current_price, 2),
                    "price_change_5d": round(features.get("tech_roc_5", 0), 2),
                    "price_change_20d": round(features.get("tech_roc_21", 0), 2),
                    "rsi_14": round(features.get("tech_rsi_14", 50), 2),
                    "volume_ratio": round(features.get("vol_volume_ratio_10", 1), 2),
                    "market_cap": fundamentals.get("market_cap", 0),
                    "pe_ratio": fundamentals.get("pe_ratio"),
                    "52w_high": fundamentals.get("52w_high"),
                    "52w_low": fundamentals.get("52w_low"),
                    "timeframe": timeframe,
                    "anomalies": anomaly_records,
                    "has_anomaly": len(anomaly_records) > 0,
                }
                results.append(result)
                logger.info(f"  {symbol}: score={composite['overall_score']:.1f} anomalies={len(anomaly_records)}")

            except Exception as e:
                logger.warning(f"Failed to process {symbol}: {e}")

        # 4. Sort and filter
        results.sort(key=lambda x: x["overall_score"], reverse=True)

        if sectors:
            sectors_lower = [s.lower() for s in sectors]
            results = [r for r in results if r["sector"].lower() in sectors_lower]

        if min_score > 0:
            results = [r for r in results if r["overall_score"] >= min_score]

        results = results[:top_n]

        # Cache results
        output = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "timeframe": timeframe,
            "regime": regime_info["regime"],
            "regime_confidence": regime_info["confidence"],
            "regime_description": regime_info["description"],
            "total_screened": len(price_data),
            "results_count": len(results),
            "results": results,
        }

        _screening_cache = {
            "results": output,
            "timestamp": datetime.utcnow(),
            "regime": regime_info,
        }

        logger.info(f"Screening complete. {len(results)} stocks returned.")
        return output

    def get_stock_detail(self, symbol: str, timeframe: str = "1d") -> Optional[dict]:
        """Get detailed screening analysis for a specific stock."""
        logger.info(f"Fetching detail for {symbol} (parallel, timeframe={timeframe})")

        # Fetch all data in parallel (6 threads: price, fundamentals, earnings, insiders, holders, index)
        detail = self.provider.fetch_stock_detail_parallel(symbol, interval=timeframe)

        tf_config = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG["1d"])
        min_bars = tf_config["min_bars"]

        df = detail.get("price_df", pd.DataFrame())
        if df.empty or len(df) < min_bars:
            return None

        fundamentals = detail.get("fundamentals", {})
        earnings = detail.get("earnings", {})
        insider_txns = detail.get("insiders", [])
        holders = detail.get("holders", [])
        index_df = detail.get("index_df", pd.DataFrame())

        current_price = float(df["close"].iloc[-1])

        features, anomaly_records = self.pipeline.compute_features(
            price_df=df,
            earnings_data=earnings,
            insider_transactions=insider_txns,
            current_price=current_price,
            market_cap=fundamentals.get("market_cap", 0),
            timeframe=timeframe,
        )

        # Regime
        regime_info = detect_regime_heuristic(index_df)

        momentum_prob = self.scorer.heuristic_momentum_probability(features)
        crash_prob = self.scorer.heuristic_crash_probability(features)

        composite = self.scorer.compute_score(
            momentum_probability=momentum_prob,
            crash_probability=crash_prob,
            features=features,
            regime_adjustments=regime_info["adjustments"],
            anomaly_records=anomaly_records,
        )

        top_signals = self.explainer.extract_top_signals(features)
        explanation = self.explainer.generate_explanation(
            symbol=symbol,
            top_signals=top_signals,
            regime=regime_info["regime"],
            composite_score=composite,
            timeframe=timeframe,
            anomaly_records=anomaly_records,
        )

        return {
            "symbol": symbol,
            "name": fundamentals.get("name", symbol),
            "market": "NSE",
            "sector": fundamentals.get("sector", ""),
            "industry": fundamentals.get("industry", ""),
            "overall_score": composite["overall_score"],
            "momentum_score": composite["momentum_score"],
            "risk_score": composite["risk_score"],
            "momentum_probability": round(momentum_prob, 4),
            "crash_probability": round(crash_prob, 4),
            "regime": regime_info["regime"],
            "regime_confidence": regime_info["confidence"],
            "top_signals": top_signals,
            "explanation": explanation,
            "current_price": round(current_price, 2),
            "price_change_5d": round(features.get("tech_roc_5", 0), 2),
            "price_change_20d": round(features.get("tech_roc_21", 0), 2),
            "rsi_14": round(features.get("tech_rsi_14", 50), 2),
            "volume_ratio": round(features.get("vol_volume_ratio_10", 1), 2),
            "market_cap": fundamentals.get("market_cap", 0),
            "pe_ratio": fundamentals.get("pe_ratio"),
            "52w_high": fundamentals.get("52w_high"),
            "52w_low": fundamentals.get("52w_low"),
            "timeframe": timeframe,
            "anomalies": anomaly_records,
            "has_anomaly": len(anomaly_records) > 0,
            "fundamentals": fundamentals,
            "earnings": earnings,
            "insider_transactions": insider_txns[:10] if insider_txns else [],
            "institutional_holders": holders[:10] if holders else [],
            "features": {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items()},
        }


def get_cached_results() -> Optional[dict]:
    """Return cached screening results if fresh (< 1 hour old)."""
    if _screening_cache["timestamp"]:
        age = (datetime.utcnow() - _screening_cache["timestamp"]).total_seconds()
        if age < 3600:
            return _screening_cache["results"]
    return None


def get_cached_regime() -> Optional[dict]:
    """Return cached regime info."""
    return _screening_cache.get("regime")
