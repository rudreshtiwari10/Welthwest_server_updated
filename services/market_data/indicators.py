"""
Technical indicators library — pure numpy/pandas, no new dependencies.

Implements 12 common indicators. Each function takes a pandas DataFrame with
OHLCV columns (Open, High, Low, Close, Volume) and returns either a Series
or DataFrame depending on the indicator.

Also exposes compute_indicator(candles, name, **params) which accepts a list
of services.market_data.base.Candle objects and returns an IndicatorResult
with a neutral, non-directional output schema (per Phase 3 compliance: no
"Overbought"/"Bullish"/"BUY" labels — just descriptive facts).

Implemented:
    sma, ema, wma, rsi, macd, bollinger_bands, atr, stochastic,
    williams_r, obv, vwap, cci

These replace/augment the 4 indicators currently in services/indicators_service.py.
The legacy service is NOT touched; call sites continue to use it until migration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Union

import numpy as np
import pandas as pd

from services.market_data.base import Candle

logger = logging.getLogger(__name__)


# ---- Neutral output schema -------------------------------------------------


@dataclass
class IndicatorResult:
    """
    Neutral indicator output — facts only, no directional interpretation.

    Phase 3 compliance: no fields named `signal`, `recommendation`, `trend`,
    `interpretation`. Just the numeric value, percentile context, and a
    short factual description.
    """
    name: str
    symbol: Optional[str] = None
    value: Any = None                      # latest value (float or dict)
    series: list[float] = field(default_factory=list)   # full history, for charting
    params: dict = field(default_factory=dict)
    context: Optional[str] = None          # e.g. "RSI at 74, upper quartile of 52w range"
    percentile_52w: Optional[float] = None # 0-100, where latest sits in its own 52w range


# ---- Helpers ---------------------------------------------------------------


def _to_dataframe(candles: Iterable[Candle]) -> pd.DataFrame:
    """Convert a list of Candle objects into a standard OHLCV DataFrame."""
    rows = []
    for c in candles:
        rows.append(
            {
                "timestamp": c.timestamp,
                "Open": c.open,
                "High": c.high,
                "Low": c.low,
                "Close": c.close,
                "Volume": c.volume,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["Open", "High", "Low", "Close", "Volume"]
        )
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    return df


def _percentile_rank(series: pd.Series, window: int = 252) -> Optional[float]:
    """Where the latest value sits in its own trailing window (0-100)."""
    if series is None or len(series) == 0:
        return None
    s = series.dropna().tail(window)
    if len(s) < 2:
        return None
    latest = s.iloc[-1]
    rank = (s <= latest).sum() / len(s) * 100.0
    return float(rank)


def _to_list(series: pd.Series) -> list[float]:
    """Serialize a Series to a list, replacing NaN with None-safe floats."""
    return [None if pd.isna(v) else float(v) for v in series.tolist()]


# ---- Indicator implementations ---------------------------------------------


def sma(df: pd.DataFrame, period: int = 20, column: str = "Close") -> pd.Series:
    """Simple Moving Average."""
    return df[column].rolling(window=period, min_periods=period).mean()


def ema(df: pd.DataFrame, period: int = 20, column: str = "Close") -> pd.Series:
    """Exponential Moving Average."""
    return df[column].ewm(span=period, adjust=False).mean()


def wma(df: pd.DataFrame, period: int = 20, column: str = "Close") -> pd.Series:
    """Weighted Moving Average — linearly weighted, most recent = heaviest."""
    weights = np.arange(1, period + 1)
    return (
        df[column]
        .rolling(window=period)
        .apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    )


def rsi(df: pd.DataFrame, period: int = 14, column: str = "Close") -> pd.Series:
    """Relative Strength Index — Wilder's smoothing."""
    delta = df[column].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "Close",
) -> pd.DataFrame:
    """MACD line, signal line, and histogram."""
    ema_fast = df[column].ewm(span=fast, adjust=False).mean()
    ema_slow = df[column].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram}
    )


def bollinger_bands(
    df: pd.DataFrame, period: int = 20, std: float = 2.0, column: str = "Close"
) -> pd.DataFrame:
    """Bollinger Bands: middle (SMA), upper, lower, bandwidth."""
    middle = df[column].rolling(window=period).mean()
    stdev = df[column].rolling(window=period).std()
    upper = middle + std * stdev
    lower = middle - std * stdev
    bandwidth = (upper - lower) / middle
    return pd.DataFrame(
        {"middle": middle, "upper": upper, "lower": lower, "bandwidth": bandwidth}
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — Wilder's smoothing."""
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def stochastic(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3
) -> pd.DataFrame:
    """Stochastic Oscillator — %K and %D."""
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    k = 100 * (df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(window=d_period).mean()
    return pd.DataFrame({"k": k, "d": d})


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R — oscillator between -100 and 0."""
    high_max = df["High"].rolling(window=period).max()
    low_min = df["Low"].rolling(window=period).min()
    return -100 * (high_max - df["Close"]) / (high_max - low_min).replace(0, np.nan)


def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(df["Close"].diff().fillna(0))
    return (direction * df["Volume"]).cumsum()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-Weighted Average Price (cumulative)."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_vp = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum().replace(0, np.nan)
    return cum_vp / cum_vol


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Commodity Channel Index."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    sma_tp = typical_price.rolling(window=period).mean()
    mean_dev = typical_price.rolling(window=period).apply(
        lambda x: np.fabs(x - x.mean()).mean(), raw=False
    )
    return (typical_price - sma_tp) / (0.015 * mean_dev.replace(0, np.nan))


# ---- Unified entry point ---------------------------------------------------


_INDICATOR_REGISTRY = {
    "sma": sma,
    "ema": ema,
    "wma": wma,
    "rsi": rsi,
    "macd": macd,
    "bollinger": bollinger_bands,
    "bollinger_bands": bollinger_bands,
    "atr": atr,
    "stochastic": stochastic,
    "williams_r": williams_r,
    "obv": obv,
    "vwap": vwap,
    "cci": cci,
}


def list_indicators() -> list[str]:
    """Return all supported indicator names."""
    return sorted(set(_INDICATOR_REGISTRY.keys()))


def compute_indicator(
    candles: Union[Iterable[Candle], pd.DataFrame],
    name: str,
    *,
    symbol: Optional[str] = None,
    **params,
) -> IndicatorResult:
    """
    Compute a named indicator and return a neutral IndicatorResult.

        >>> result = compute_indicator(candles, "rsi", period=14)
        >>> result.value      # latest RSI
        >>> result.context    # "RSI 74 — upper quartile of 52-week range"
    """
    name = name.lower().strip()
    if name not in _INDICATOR_REGISTRY:
        raise ValueError(
            f"Unknown indicator {name!r}. Available: {list_indicators()}"
        )

    df = candles if isinstance(candles, pd.DataFrame) else _to_dataframe(candles)
    if df is None or df.empty:
        return IndicatorResult(
            name=name, symbol=symbol, params=params, context="No data"
        )

    fn = _INDICATOR_REGISTRY[name]
    try:
        output = fn(df, **params)
    except Exception as e:
        logger.warning("indicator %s failed: %s", name, e)
        return IndicatorResult(
            name=name,
            symbol=symbol,
            params=params,
            context=f"Indicator computation failed",
        )

    # Handle multi-line outputs (MACD, Bollinger, Stochastic) vs single Series.
    if isinstance(output, pd.DataFrame):
        latest = {col: _safe_last(output[col]) for col in output.columns}
        series = _to_list(output.iloc[:, 0])
        primary_series = output.iloc[:, 0]
    else:
        latest = _safe_last(output)
        series = _to_list(output)
        primary_series = output

    pct = _percentile_rank(primary_series)
    ctx = _describe(name, latest, pct)

    return IndicatorResult(
        name=name,
        symbol=symbol,
        value=latest,
        series=series,
        params=params,
        percentile_52w=pct,
        context=ctx,
    )


def _safe_last(series: pd.Series) -> Optional[float]:
    if series is None or len(series) == 0:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _describe(name: str, latest: Any, pct: Optional[float]) -> str:
    """
    Purely descriptive context string — no directional verbs.
    Phase 3 compliance: never "Overbought", never "Bullish", never "BUY".
    """
    if latest is None:
        return f"{name.upper()}: no value"

    if isinstance(latest, dict):
        parts = []
        for k, v in latest.items():
            if v is None:
                continue
            parts.append(f"{k}={v:.2f}")
        body = ", ".join(parts) if parts else "no value"
        return f"{name.upper()}: {body}"

    if pct is not None:
        return (
            f"{name.upper()} at {latest:.2f} "
            f"(position in 52-week range: {pct:.0f}th percentile)"
        )
    return f"{name.upper()} at {latest:.2f}"
