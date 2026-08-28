"""
Point-in-time data layer (spec §3, §4, §5, §33).

Responsibilities
----------------
1. Resolve a user symbol to an exchange-qualified ticker.
2. Fetch raw (unadjusted) OHLCV plus the corporate-action stream.
3. Audit data quality and quarantine impossible bars, recording provenance.
4. Produce TWO aligned series:
     - raw prices   -> what an order could actually execute against
     - analysis prices -> split/bonus adjusted, used for feature computation
   These are never silently mixed (spec §5).
5. Stamp every bar with event_time and availability_time.

The feed is deliberately dumb about strategies. It knows nothing about
indicators; it only guarantees the information-time contract.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from services.backtest_india.contracts import Bar

logger = logging.getLogger(__name__)


# ── Symbol resolution ───────────────────────────────────────────────────────

_INDEX_ALIASES = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY 50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTYNEXT50": "^NSMIDCP",
    "NIFTYIT": "^CNXIT",
    "INDIAVIX": "^INDIAVIX",
}

# Bars per year, by timeframe — used by every annualisation in metrics.py.
PERIODS_PER_YEAR = {
    "1m": 252 * 375,
    "5m": 252 * 75,
    "15m": 252 * 25,
    "30m": 252 * 12,
    "60m": 252 * 6,
    "1h": 252 * 6,
    "1d": 252,
    "1wk": 52,
    "1mo": 12,
}

# yfinance caps intraday history; enforce it up front rather than failing later.
MAX_INTRADAY_DAYS = {
    "1m": 7,
    "5m": 59,
    "15m": 59,
    "30m": 59,
    "60m": 720,
    "1h": 720,
}


def resolve_symbol(symbol: str, exchange: str = "NSE") -> str:
    """Map a user-typed symbol to a yfinance ticker. Fresh, self-contained."""
    s = (symbol or "").strip().upper()
    if not s:
        raise DataFeedError("Empty symbol")
    if s in _INDEX_ALIASES:
        return _INDEX_ALIASES[s]
    if s.startswith("^") or "." in s:
        return s
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{s}{suffix}"


def display_symbol(resolved: str) -> str:
    """Inverse of resolve_symbol for report labels."""
    for alias, tick in _INDEX_ALIASES.items():
        if tick == resolved:
            return alias
    return resolved.replace(".NS", "").replace(".BO", "")


class DataFeedError(Exception):
    pass


# ── Quality audit ───────────────────────────────────────────────────────────

@dataclass
class QualityReport:
    """Spec §33 — everything the auditor found, with provenance."""
    rows_in: int = 0
    rows_out: int = 0
    duplicate_timestamps: int = 0
    out_of_order: int = 0
    impossible_ohlc: int = 0
    non_positive_price: int = 0
    zero_volume_bars: int = 0
    missing_bars_estimated: int = 0
    stale_bars: int = 0
    quarantined_indices: list = field(default_factory=list)
    corporate_actions: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicate_timestamps": self.duplicate_timestamps,
            "out_of_order": self.out_of_order,
            "impossible_ohlc": self.impossible_ohlc,
            "non_positive_price": self.non_positive_price,
            "zero_volume_bars": self.zero_volume_bars,
            "missing_bars_estimated": self.missing_bars_estimated,
            "stale_bars": self.stale_bars,
            "quarantined": len(self.quarantined_indices),
            "corporate_actions": self.corporate_actions,
            "notes": self.notes,
        }


@dataclass
class InstrumentSeries:
    """
    One instrument's fully prepared, point-in-time-safe history.

    `bars` holds raw executable prices. `analysis` is the adjusted DataFrame
    features are computed from. Both share the same index, so a feature value
    at position i is always paired with the raw bar at position i.
    """
    symbol: str            # display symbol
    ticker: str            # resolved yfinance ticker
    timeframe: str
    bars: list             # list[Bar], raw prices
    analysis: pd.DataFrame  # adjusted OHLCV, index = event_time
    quality: QualityReport
    adv: np.ndarray        # rolling average daily traded value
    first_valid_index: int = 0

    def __len__(self) -> int:
        return len(self.bars)

    @property
    def timestamps(self) -> list:
        return [b.event_time for b in self.bars]


# ── Fetch + prepare ─────────────────────────────────────────────────────────

_fetch_lock = threading.Lock()
_memo: dict = {}
_MEMO_TTL = 900  # seconds — keeps sweeps and walk-forward from re-downloading


def _fetch_raw(ticker: str, start: str, end: str, interval: str) -> pd.DataFrame:
    """Download from yfinance with a short-lived in-process memo."""
    key = (ticker, start, end, interval)
    now = time.time()
    with _fetch_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < _MEMO_TTL:
            return hit[1].copy()

    import yfinance as yf

    # end is inclusive for the user, exclusive for yfinance
    end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    last_err = None
    for attempt in range(3):
        try:
            df = yf.Ticker(ticker).history(
                start=start,
                end=end_exclusive,
                interval=interval,
                auto_adjust=False,   # we do our own adjustment, explicitly
                actions=True,
                timeout=30,
            )
            if df is not None and not df.empty:
                with _fetch_lock:
                    _memo[key] = (now, df.copy())
                return df
            last_err = DataFeedError(f"No rows returned for {ticker}")
        except Exception as exc:                     # network / rate limit
            last_err = exc
            logger.warning("backtest_india: fetch attempt %s failed for %s: %s",
                           attempt + 1, ticker, exc)
        time.sleep(1.2 * (attempt + 1))
    raise DataFeedError(f"Could not fetch data for {ticker}: {last_err}")


def _audit(df: pd.DataFrame, timeframe: str) -> tuple[pd.DataFrame, QualityReport]:
    """Spec §33 — detect, count and quarantine bad data before anything reads it."""
    q = QualityReport(rows_in=len(df))

    # 1. duplicate timestamps: keep the last observation, count the drop
    dupes = df.index.duplicated(keep="last")
    q.duplicate_timestamps = int(dupes.sum())
    if q.duplicate_timestamps:
        df = df[~dupes]

    # 2. out-of-order rows
    if not df.index.is_monotonic_increasing:
        order = np.argsort(df.index.values, kind="stable")
        q.out_of_order = int((order != np.arange(len(order))).sum())
        df = df.iloc[order]

    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]

    # 3. impossible OHLC geometry
    bad_geo = (h < np.maximum(o, c) - 1e-9) | (l > np.minimum(o, c) + 1e-9) | (h < l)
    q.impossible_ohlc = int(bad_geo.sum())

    # 4. non-positive prices
    bad_price = (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0)
    bad_price = bad_price | o.isna() | h.isna() | l.isna() | c.isna()
    q.non_positive_price = int(bad_price.sum())

    quarantine = bad_geo | bad_price
    q.quarantined_indices = [str(t) for t in df.index[quarantine]]
    df = df[~quarantine]

    # 5. informational flags — counted, never silently repaired
    vol = df.get("Volume", pd.Series(0, index=df.index)).fillna(0)
    q.zero_volume_bars = int((vol <= 0).sum())
    if len(df) > 2:
        unchanged = (df["High"] == df["Low"]) & (df["Open"] == df["Close"])
        q.stale_bars = int(unchanged.sum())

    # 6. calendar gaps (daily only — intraday session gaps are expected)
    if timeframe == "1d" and len(df) > 5:
        span_days = (df.index[-1] - df.index[0]).days
        expected = max(1, int(span_days * 252 / 365.25))
        q.missing_bars_estimated = max(0, expected - len(df))
        if q.missing_bars_estimated > expected * 0.15:
            q.notes.append(
                f"{q.missing_bars_estimated} sessions appear absent vs a "
                f"{expected}-session expectation — holidays, halts or a data gap."
            )

    if q.impossible_ohlc or q.non_positive_price:
        q.notes.append(
            f"{len(q.quarantined_indices)} bar(s) quarantined for impossible "
            "OHLC geometry or non-positive prices; they are excluded from every "
            "feature and fill."
        )

    q.rows_out = len(df)
    return df, q


def _build_analysis_frame(df: pd.DataFrame, quality: QualityReport) -> pd.DataFrame:
    """
    Spec §5 — build the split/bonus-adjusted analysis series.

    Splits are applied backwards (older prices divided by the cumulative
    forward split factor) so a 1:2 split creates no artificial -50% return.
    Dividends are NOT folded into prices; they are paid as cash by the
    portfolio ledger, keeping executable prices honest.
    """
    splits = df.get("Stock Splits", pd.Series(0.0, index=df.index)).fillna(0.0)
    divs = df.get("Dividends", pd.Series(0.0, index=df.index)).fillna(0.0)

    ratio = splits.replace(0.0, 1.0).astype(float)
    # cumulative factor of all splits occurring at or after each bar
    cum_forward = ratio[::-1].cumprod()[::-1]
    # a split on bar i affects bars strictly before i
    factor = cum_forward / ratio

    adj = pd.DataFrame(index=df.index)
    for col in ("Open", "High", "Low", "Close"):
        adj[col] = df[col].astype(float) / factor
    adj["Volume"] = df.get("Volume", pd.Series(0.0, index=df.index)).astype(float) * factor

    for ts, r in ratio.items():
        if abs(r - 1.0) > 1e-9:
            quality.corporate_actions.append(
                {"type": "SPLIT", "date": str(ts.date() if hasattr(ts, "date") else ts),
                 "ratio": float(r)}
            )
    for ts, d in divs.items():
        if d and d > 0:
            quality.corporate_actions.append(
                {"type": "DIVIDEND", "date": str(ts.date() if hasattr(ts, "date") else ts),
                 "amount": float(d)}
            )
    return adj


def _availability_time(event_time: pd.Timestamp, timeframe: str) -> datetime:
    """
    Spec §3 — when the bar legally becomes readable.

    A completed bar is available the instant it closes; what it may NOT do is
    be executed against at its own close. That constraint lives in the latency
    queue (execution.py), which is where it belongs.
    """
    return event_time.to_pydatetime() if hasattr(event_time, "to_pydatetime") else event_time


def load_instrument(
    symbol: str,
    start: str,
    end: str,
    timeframe: str = "1d",
    exchange: str = "NSE",
    adv_window: int = 20,
) -> InstrumentSeries:
    """Fetch, audit, adjust and stamp one instrument's history."""
    ticker = resolve_symbol(symbol, exchange)

    # guard intraday range limits before the network call
    cap = MAX_INTRADAY_DAYS.get(timeframe)
    if cap:
        span = (pd.Timestamp(end) - pd.Timestamp(start)).days
        if span > cap:
            start = (pd.Timestamp(end) - pd.Timedelta(days=cap)).strftime("%Y-%m-%d")
            logger.info("backtest_india: %s window clipped to %s days for %s",
                        timeframe, cap, ticker)

    raw = _fetch_raw(ticker, start, end, timeframe)
    raw, quality = _audit(raw, timeframe)
    if len(raw) < 30:
        raise DataFeedError(
            f"{display_symbol(ticker)}: only {len(raw)} usable bars in the "
            f"requested window — need at least 30 to run a meaningful test."
        )
    if cap:
        quality.notes.append(
            f"Provider limits {timeframe} history to ~{cap} days; the window was "
            "clipped accordingly."
        )

    analysis = _build_analysis_frame(raw, quality)

    bars: list[Bar] = []
    splits = raw.get("Stock Splits", pd.Series(0.0, index=raw.index)).fillna(0.0)
    divs = raw.get("Dividends", pd.Series(0.0, index=raw.index)).fillna(0.0)
    disp = display_symbol(ticker)

    for ts, row in raw.iterrows():
        flags = []
        vol = float(row.get("Volume", 0) or 0)
        if vol <= 0:
            flags.append("ZERO_VOLUME")
        if row["High"] == row["Low"]:
            flags.append("NO_RANGE")
        bars.append(Bar(
            instrument=disp,
            event_time=ts.to_pydatetime(),
            availability_time=_availability_time(ts, timeframe),
            open=float(row["Open"]), high=float(row["High"]),
            low=float(row["Low"]), close=float(row["Close"]),
            volume=vol,
            dividend=float(divs.get(ts, 0.0) or 0.0),
            split_ratio=float(splits.get(ts, 0.0) or 0.0) or 1.0,
            flags=tuple(flags),
        ))

    tv = analysis["Close"].values * analysis["Volume"].values
    adv = pd.Series(tv).rolling(adv_window, min_periods=1).mean().values

    return InstrumentSeries(
        symbol=disp, ticker=ticker, timeframe=timeframe,
        bars=bars, analysis=analysis, quality=quality, adv=adv,
    )


def load_universe(
    symbols: list,
    start: str,
    end: str,
    timeframe: str = "1d",
    exchange: str = "NSE",
) -> tuple[dict, list]:
    """
    Load every requested instrument. Failures are collected, not raised, so a
    single dead ticker cannot kill a portfolio run.

    Returns (series_by_symbol, warnings).
    """
    out, warnings = {}, []
    for sym in symbols:
        try:
            series = load_instrument(sym, start, end, timeframe, exchange)
            out[series.symbol] = series
        except Exception as exc:
            warnings.append(f"{sym}: {exc}")
            logger.warning("backtest_india: skipping %s — %s", sym, exc)
    if not out:
        raise DataFeedError(
            "No instrument could be loaded. " + ("; ".join(warnings) if warnings else "")
        )
    return out, warnings


def build_master_calendar(series_map: dict) -> list:
    """
    Spec §12 — the union of every instrument's session times, sorted. The
    engine walks this calendar so multi-symbol runs stay aligned without any
    instrument ever seeing another's future.
    """
    stamps: set = set()
    for s in series_map.values():
        stamps.update(b.event_time for b in s.bars)
    return sorted(stamps)


def liquidity_filter(
    series: InstrumentSeries,
    min_price: float = 0.0,
    min_median_traded_value: float = 0.0,
    min_bars: int = 0,
) -> tuple[bool, str]:
    """Spec §4 — point-in-time-safe universe screen using the whole window's
    median (documented as a universe-construction choice, not a signal)."""
    if len(series) < min_bars:
        return False, f"only {len(series)} bars (< {min_bars})"
    close = series.analysis["Close"]
    if float(close.median()) < min_price:
        return False, f"median price {close.median():.2f} < {min_price}"
    mtv = float((close * series.analysis["Volume"]).median())
    if mtv < min_median_traded_value:
        return False, f"median traded value {mtv:,.0f} < {min_median_traded_value:,.0f}"
    return True, "ok"
