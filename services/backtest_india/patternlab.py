"""
Pattern Lab — pattern outcome study mode (spec §29).

Physically separate from signal generation, by design. Nothing here is ever
readable by the strategy graph; this module exists purely to answer "does this
pattern's forward distribution differ from the unconditional one?"

The central discipline: a 60% hit rate is meaningless if the unconditional
base rate is 58%. Every pattern result is therefore reported against matched
non-pattern observations from the same instrument and window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.backtest_india import candles as candle_lib
from services.backtest_india import features as feat_lib
from services.backtest_india import patterns as pattern_lib
from services.backtest_india.datafeed import load_instrument
from services.backtest_india.structure import find_pivots

HORIZONS = (1, 3, 5, 10, 20)


def _forward_stats(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   idxs: np.ndarray, horizon: int) -> dict:
    """R_H = P_{t+H}/P_t - 1, plus the excursions along the way."""
    idxs = idxs[idxs + horizon < len(close)]
    if len(idxs) == 0:
        return {"samples": 0}

    entry = close[idxs]
    exit_ = close[idxs + horizon]
    rets = exit_ / entry - 1.0

    mfe, mae = [], []
    for i, e in zip(idxs, entry):
        window_h = high[i + 1: i + horizon + 1]
        window_l = low[i + 1: i + horizon + 1]
        if len(window_h) == 0:
            continue
        mfe.append(float(window_h.max() / e - 1.0))
        mae.append(float(window_l.min() / e - 1.0))

    return {
        "samples": int(len(rets)),
        "hit_rate": round(float((rets > 0).mean()), 4),
        "mean_return": round(float(rets.mean()), 6),
        "median_return": round(float(np.median(rets)), 6),
        "p25": round(float(np.percentile(rets, 25)), 6),
        "p75": round(float(np.percentile(rets, 75)), 6),
        "std": round(float(rets.std(ddof=1)), 6) if len(rets) > 1 else 0.0,
        "avg_mfe": round(float(np.mean(mfe)), 6) if mfe else None,
        "avg_mae": round(float(np.mean(mae)), 6) if mae else None,
    }


def _welch_t(a: np.ndarray, b: np.ndarray) -> float:
    """Welch's t statistic — reported as a descriptive contrast, not a p-value."""
    if len(a) < 5 or len(b) < 5:
        return 0.0
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    denom = np.sqrt(va + vb)
    return float((a.mean() - b.mean()) / denom) if denom > 0 else 0.0


def study(symbol: str, start: str, end: str, timeframe: str = "1d",
          exchange: str = "NSE", pattern_types: list = None,
          include_chart_patterns: bool = True) -> dict:
    """Run the forward-outcome study for one instrument."""
    series = load_instrument(symbol, start, end, timeframe, exchange)
    df = series.analysis
    close = df["Close"].to_numpy(float)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    n = len(close)

    parts = candle_lib.decompose(df)
    wanted = pattern_types or list(candle_lib.CANDLES.keys())

    results = []
    for key in wanted:
        spec = candle_lib.CANDLES.get(key)
        if not spec:
            continue
        try:
            mask = spec.fn(parts, **spec.params)
        except Exception:
            continue
        idxs = np.where(mask)[0]
        if len(idxs) < 5:
            results.append({
                "pattern": key, "label": spec.label, "direction": spec.direction,
                "occurrences": int(len(idxs)),
                "verdict": "too few occurrences to say anything",
                "horizons": [],
            })
            continue

        # matched control: every bar that is NOT the pattern, same instrument,
        # same window — the unconditional base rate
        control = np.setdiff1d(np.arange(n), idxs)

        horizons = []
        for h in HORIZONS:
            pat = _forward_stats(close, high, low, idxs, h)
            ctl = _forward_stats(close, high, low, control, h)
            if pat.get("samples", 0) == 0 or ctl.get("samples", 0) == 0:
                continue

            valid_p = idxs[idxs + h < n]
            valid_c = control[control + h < n]
            rp = close[valid_p + h] / close[valid_p] - 1.0
            rc = close[valid_c + h] / close[valid_c] - 1.0

            horizons.append({
                "horizon": h,
                "pattern": pat,
                "unconditional": ctl,
                "edge_hit_rate": round(pat["hit_rate"] - ctl["hit_rate"], 4),
                "edge_mean_return": round(pat["mean_return"] - ctl["mean_return"], 6),
                "t_statistic": round(_welch_t(rp, rc), 3),
            })

        edges = [h["edge_mean_return"] for h in horizons]
        ts = [abs(h["t_statistic"]) for h in horizons]
        if not edges:
            verdict = "no horizon had enough matched samples"
        elif max(ts) < 1.5:
            verdict = ("indistinguishable from the unconditional base rate at every "
                       "horizon tested")
        elif np.mean(edges) > 0:
            verdict = (f"forward returns run {np.mean(edges):+.2%} above the base rate "
                       f"on average (peak |t| = {max(ts):.1f})")
        else:
            verdict = (f"forward returns run {np.mean(edges):+.2%} BELOW the base rate "
                       f"on average (peak |t| = {max(ts):.1f})")

        results.append({
            "pattern": key, "label": spec.label, "direction": spec.direction,
            "occurrences": int(len(idxs)),
            "frequency": round(len(idxs) / n, 4),
            "verdict": verdict,
            "horizons": horizons,
        })

    chart_results = []
    if include_chart_patterns:
        atr14 = feat_lib.atr(high, low, close, 14)
        reqs = [{"id": k.lower(), "type": k} for k in
                ("DOUBLE_TOP", "DOUBLE_BOTTOM", "HEAD_SHOULDERS",
                 "INVERSE_HEAD_SHOULDERS", "TRIANGLE", "FLAG")]
        _, events, _ = pattern_lib.detect_all(df, reqs, atr_series=atr14,
                                              instrument=series.symbol)
        by_type: dict = {}
        for ev in events:
            by_type.setdefault(ev.pattern_id, []).append(ev)
        for pid, evs in by_type.items():
            confirmed = [e for e in evs if e.confirmation_index is not None]
            idxs = np.array([e.confirmation_index for e in confirmed], dtype=int)
            row = {
                "pattern": pid,
                "detected": len(evs),
                "confirmed": len(confirmed),
                "confirmation_rate": round(len(confirmed) / len(evs), 3) if evs else 0.0,
                "horizons": [],
            }
            if len(idxs) >= 5:
                control = np.setdiff1d(np.arange(n), idxs)
                for h in HORIZONS:
                    pat = _forward_stats(close, high, low, idxs, h)
                    ctl = _forward_stats(close, high, low, control, h)
                    if pat.get("samples", 0) and ctl.get("samples", 0):
                        row["horizons"].append({
                            "horizon": h, "pattern": pat, "unconditional": ctl,
                            "edge_mean_return": round(
                                pat["mean_return"] - ctl["mean_return"], 6),
                        })
            else:
                row["note"] = "fewer than 5 confirmed instances — no outcome study run"
            chart_results.append(row)

    return {
        "symbol": series.symbol,
        "timeframe": timeframe,
        "start": series.bars[0].event_time.isoformat(),
        "end": series.bars[-1].event_time.isoformat(),
        "bars": n,
        "horizons_tested": list(HORIZONS),
        "candlestick_patterns": sorted(results, key=lambda r: -r["occurrences"]),
        "chart_patterns": chart_results,
        "methodology": (
            "Forward returns are measured from the pattern's executable detection "
            "bar. Each pattern is compared against every non-pattern bar in the same "
            "instrument and window — the unconditional base rate. A pattern with a "
            "60% hit rate is worthless if the base rate is 58%, so only the DIFFERENCE "
            "is reported as an edge. The t-statistic is descriptive; it is not "
            "corrected for the number of patterns tested, and no p-value is claimed."
        ),
        "warning": (
            "This is an outcome study, not a prediction. Nothing here is used by the "
            "signal engine, and a pattern showing an edge on past data has not been "
            "shown to have one in future."
        ),
    }
