"""Flask blueprint wrapping the AI Screener engine.

All AI Screener endpoints are mounted under /api/ai-screener/...
This is a thin Flask adapter -- the actual logic lives in ai_screener/.
"""
from flask import Blueprint, jsonify, request
import logging

from ai_screener.config.settings import VALID_TIMEFRAMES, TIMEFRAME_CONFIG
from ai_screener.screener.engine import ScreeningEngine, get_cached_results, get_cached_regime, detect_regime_heuristic
from ai_screener.data.providers.yfinance_provider import YFinanceIndiaProvider
from ai_screener.features.pipeline import FeaturePipeline

ai_screener_bp = Blueprint("ai_screener", __name__, url_prefix="/api/ai-screener")
logger = logging.getLogger(__name__)

# Lazy-init singleton engine
_engine = None


def _get_engine() -> ScreeningEngine:
    global _engine
    if _engine is None:
        _engine = ScreeningEngine()
    return _engine


# ─── Health ────────────────────────────────────────────────────────────

@ai_screener_bp.route("/health", methods=["GET"])
def screener_health():
    """Check AI Screener data sources."""
    yf_ok = False
    try:
        provider = YFinanceIndiaProvider()
        yf_ok = provider.health_check()
    except Exception:
        pass

    return jsonify({
        "status": "healthy" if yf_ok else "degraded",
        "service": "welthwest-ai-screener",
        "version": "1.0.0",
        "market": "NSE/BSE",
        "data_source": "yfinance",
        "yfinance_status": "ok" if yf_ok else "error",
    })


# ─── Screening ─────────────────────────────────────────────────────────

@ai_screener_bp.route("/screen", methods=["POST"])
def screen_stocks():
    """Run the AI screener on NIFTY 50 stocks.

    JSON body (all optional):
        symbols: list[str]   – specific symbols (default NIFTY 50)
        top_n: int           – max results (default 20)
        min_score: float     – minimum overall score (default 0)
        sectors: list[str]   – filter by sector names
        timeframe: str       – "1d" (default), "1h", or "15m"
    """
    data = request.get_json(silent=True) or {}
    timeframe = data.get("timeframe", "1d")
    if timeframe not in VALID_TIMEFRAMES:
        return jsonify({"error": f"Invalid timeframe '{timeframe}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"}), 400

    engine = _get_engine()
    try:
        result = engine.run_screen(
            symbols=data.get("symbols"),
            top_n=data.get("top_n", 20),
            min_score=data.get("min_score", 0),
            sectors=data.get("sectors"),
            timeframe=timeframe,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Screening failed: {e}")
        return jsonify({"error": f"Screening failed: {str(e)}"}), 500


@ai_screener_bp.route("/screen/quick", methods=["POST"])
def quick_screen():
    """Quick screen for specific symbols (max 10)."""
    data = request.get_json(silent=True) or {}
    symbols = data.get("symbols", [])
    if not symbols:
        return jsonify({"error": "symbols list required"}), 400
    if len(symbols) > 10:
        return jsonify({"error": "Quick screen supports max 10 symbols"}), 400

    timeframe = data.get("timeframe", "1d")
    if timeframe not in VALID_TIMEFRAMES:
        return jsonify({"error": f"Invalid timeframe '{timeframe}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"}), 400

    engine = _get_engine()
    try:
        result = engine.run_screen(
            symbols=symbols,
            top_n=data.get("top_n", 10),
            timeframe=timeframe,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Quick screening failed: {e}")
        return jsonify({"error": f"Screening failed: {str(e)}"}), 500


@ai_screener_bp.route("/screen/cached", methods=["GET"])
def get_cached_screen():
    """Get the most recent cached screening results (< 1 hour old)."""
    cached = get_cached_results()
    if cached:
        return jsonify(cached)
    return jsonify({"error": "No cached results available. Run /screen first."}), 404


@ai_screener_bp.route("/screen/<symbol>", methods=["GET"])
def get_stock_details(symbol: str):
    """Get detailed screening analysis for a specific stock.

    Query params:
        timeframe: "1d" (default), "1h", or "15m"
    """
    timeframe = request.args.get("timeframe", "1d").lower()
    if timeframe not in VALID_TIMEFRAMES:
        return jsonify({"error": f"Invalid timeframe '{timeframe}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"}), 400

    engine = _get_engine()
    try:
        result = engine.get_stock_detail(symbol.upper(), timeframe=timeframe)
        if result is None:
            return jsonify({"error": f"No data found for {symbol}"}), 404
        return jsonify(result)
    except Exception as e:
        logger.error(f"Stock detail failed for {symbol}: {e}")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


# ─── Regime ────────────────────────────────────────────────────────────

@ai_screener_bp.route("/regime", methods=["GET"])
def get_current_regime():
    """Get current NIFTY market regime detection."""
    cached = get_cached_regime()
    if cached:
        return jsonify(cached)

    try:
        provider = YFinanceIndiaProvider()
        index_df = provider.fetch_index_data("NIFTY50")
        if index_df.empty:
            return jsonify({"error": "Could not fetch NIFTY 50 data"}), 503

        regime_info = detect_regime_heuristic(index_df)
        regime_info["nifty_current"] = round(float(index_df["close"].iloc[-1]), 2)
        if len(index_df) > 1:
            regime_info["nifty_previous_close"] = round(float(index_df["close"].iloc[-2]), 2)
        return jsonify(regime_info)
    except Exception as e:
        logger.error(f"Regime detection failed: {e}")
        return jsonify({"error": f"Regime detection failed: {str(e)}"}), 500


@ai_screener_bp.route("/regime/vix", methods=["GET"])
def get_india_vix():
    """Get current India VIX data."""
    try:
        provider = YFinanceIndiaProvider()
        vix_df = provider.fetch_index_data("INDIAVIX")
        if vix_df.empty:
            return jsonify({"error": "Could not fetch India VIX data"}), 503

        current_vix = float(vix_df["close"].iloc[-1])
        prev_vix = float(vix_df["close"].iloc[-2]) if len(vix_df) > 1 else current_vix

        return jsonify({
            "symbol": "INDIAVIX",
            "current": round(current_vix, 2),
            "previous_close": round(prev_vix, 2),
            "change_pct": round((current_vix / prev_vix - 1) * 100, 2),
            "interpretation": (
                "Low fear (bullish)" if current_vix < 13 else
                "Normal" if current_vix < 20 else
                "Elevated fear" if current_vix < 30 else
                "High fear (caution)"
            ),
        })
    except Exception as e:
        logger.error(f"VIX fetch failed: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Signals & Price ───────────────────────────────────────────────────

@ai_screener_bp.route("/signals/<symbol>", methods=["GET"])
def get_stock_signals(symbol: str):
    """Get detailed signal breakdown for a stock.

    Query params:
        timeframe: "1d" (default), "1h", or "15m"
    """
    from datetime import date, timedelta

    symbol = symbol.upper()
    timeframe = request.args.get("timeframe", "1d").lower()

    if timeframe not in VALID_TIMEFRAMES:
        return jsonify({"error": f"Invalid timeframe '{timeframe}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"}), 400

    tf_config = TIMEFRAME_CONFIG[timeframe]
    provider = YFinanceIndiaProvider()
    pipeline = FeaturePipeline()

    end_date = date.today()
    start_date = end_date - timedelta(days=tf_config["max_history_days"])

    df = provider.fetch_price_data(symbol, start_date, end_date, interval=timeframe)
    if df.empty or len(df) < tf_config["min_bars"]:
        return jsonify({
            "error": f"Insufficient data for {symbol} on {timeframe} timeframe ({len(df) if not df.empty else 0} bars, need {tf_config['min_bars']})"
        }), 404

    current_price = float(df["close"].iloc[-1])
    fundamentals = provider.fetch_fundamentals(symbol)

    features, anomaly_records = pipeline.compute_features(
        price_df=df,
        current_price=current_price,
        market_cap=fundamentals.get("market_cap", 0),
        timeframe=timeframe,
    )

    technical = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("tech_")}
    volume = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("vol_")}
    fundamental = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("fund_")}
    insider = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("insider_")}
    india = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("india_")}
    meta = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("meta_")}
    anomaly_features = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items() if k.startswith("anomaly_")}

    return jsonify({
        "symbol": symbol,
        "name": fundamentals.get("name", symbol),
        "current_price": current_price,
        "timeframe": timeframe,
        "data_points": len(df),
        "signals": {
            "technical": technical,
            "volume": volume,
            "fundamental": fundamental,
            "insider": insider,
            "india_specific": india,
            "meta": meta,
            "anomaly": anomaly_features,
        },
        "anomalies": anomaly_records,
        "has_anomaly": len(anomaly_records) > 0,
        "summary": {
            "rsi_14": features.get("tech_rsi_14", 50),
            "macd_crossover": features.get("tech_macd_crossover", 0),
            "volume_ratio_10d": features.get("vol_volume_ratio_10", 1),
            "bullish_signal_count": features.get("meta_bullish_signal_count", 0),
            "momentum_acceleration": features.get("tech_momentum_acceleration", 0),
            "anomaly_count": len(anomaly_records),
        },
    })


@ai_screener_bp.route("/price/<symbol>", methods=["GET"])
def get_price_history(symbol: str):
    """Get price history for a stock.

    Query params:
        days: number of calendar days (default 90)
        timeframe: "1d" (default), "1h", or "15m"
    """
    from datetime import date, timedelta

    symbol = symbol.upper()
    timeframe = request.args.get("timeframe", "1d").lower()
    days = request.args.get("days", 90, type=int)

    if timeframe not in VALID_TIMEFRAMES:
        return jsonify({"error": f"Invalid timeframe '{timeframe}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"}), 400

    tf_config = TIMEFRAME_CONFIG[timeframe]
    provider = YFinanceIndiaProvider()

    effective_days = min(days, tf_config["max_history_days"])
    end_date = date.today()
    start_date = end_date - timedelta(days=effective_days)

    df = provider.fetch_price_data(symbol, start_date, end_date, interval=timeframe)
    if df.empty:
        return jsonify({"error": f"No price data for {symbol}"}), 404

    is_intraday = timeframe != "1d"
    ts_format = "%Y-%m-%d %H:%M" if is_intraday else "%Y-%m-%d"

    records = []
    for _, row in df.iterrows():
        records.append({
            "date": row["timestamp"].strftime(ts_format),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })

    return jsonify({
        "symbol": symbol,
        "timeframe": timeframe,
        "days": effective_days,
        "data_points": len(records),
        "prices": records,
    })
