"""
Chart-pattern engine (spec §10, §11).

Detectors operate on CONFIRMED pivots only (from structure.find_pivots), so a
pattern's geometry can never be assembled from bars the strategy had not yet
seen. Each detector emits a PatternEvent carrying:

    anchor_indices     — where the geometry actually sits
    detection_index    — first bar at which the geometry was knowable
                         (max of the constituent pivots' detection bars)
    confirmation_index — first bar closing beyond the neckline / boundary
    trigger_level, invalidation_level
    quality            — component scores (fit, touches, duration, breakout
                         distance, volume confirmation). Never a probability.

Signal generation may only use `confirmation_index`. Forward-outcome analysis
lives in patternlab.py and is physically separate, per spec §11.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from services.backtest_india.contracts import PatternEvent
from services.backtest_india.structure import Pivot, find_pivots


def _series(df):
    return (df["High"].to_numpy(float), df["Low"].to_numpy(float),
            df["Close"].to_numpy(float), df["Volume"].to_numpy(float))


def _confirm_break(close: np.ndarray, start: int, level: float,
                   direction: str, horizon: int, buffer: float = 0.0) -> Optional[int]:
    """First bar in (start, start+horizon] closing beyond `level`."""
    end = min(len(close), start + horizon + 1)
    for j in range(start + 1, end):
        if direction == "down" and close[j] < level - buffer:
            return j
        if direction == "up" and close[j] > level + buffer:
            return j
    return None


def _volume_confirmation(vol: np.ndarray, idx: int, lookback: int = 20) -> float:
    """Breakout volume relative to its trailing mean, clipped to [0, 2]."""
    lo = max(0, idx - lookback)
    base = np.nanmean(vol[lo:idx]) if idx > lo else np.nan
    if not base or np.isnan(base) or base <= 0:
        return 0.0
    return float(np.clip(vol[idx] / base, 0.0, 2.0))


def _geo_score(values: list, tolerance: float) -> float:
    """How tightly a set of prices agrees, scaled 0-1 against the tolerance."""
    if len(values) < 2:
        return 0.0
    spread = (max(values) - min(values)) / max(1e-9, np.mean(values))
    return float(np.clip(1.0 - spread / max(1e-9, tolerance), 0.0, 1.0))


# ── Double / triple tops and bottoms ────────────────────────────────────────

def detect_double_top(df, pivots, tol: float = 0.03, min_sep: int = 5,
                      max_sep: int = 120, confirm_horizon: int = 40,
                      instrument: str = "") -> list:
    h, l, c, v = _series(df)
    highs = [p for p in pivots if p.kind == "HIGH"]
    lows = [p for p in pivots if p.kind == "LOW"]
    events: list = []
    for a, b in zip(highs, highs[1:]):
        sep = b.index - a.index
        if sep < min_sep or sep > max_sep:
            continue
        if abs(a.price - b.price) / max(a.price, b.price) > tol:
            continue
        valley = [p for p in lows if a.index < p.index < b.index]
        if not valley:
            continue
        neck = min(valley, key=lambda p: p.price)
        if neck.price >= min(a.price, b.price):
            continue
        detection = max(a.detected, b.detected, neck.detected)
        if detection >= len(c):
            continue
        conf = _confirm_break(c, detection, neck.price, "down", confirm_horizon)
        depth = (min(a.price, b.price) - neck.price) / neck.price
        events.append(PatternEvent(
            pattern_id="DOUBLE_TOP", instrument=instrument, direction="BEARISH",
            anchor_indices=[a.index, neck.index, b.index],
            detection_index=detection, confirmation_index=conf,
            trigger_level=float(neck.price),
            invalidation_level=float(max(a.price, b.price)),
            quality={
                "geometric_fit": _geo_score([a.price, b.price], tol),
                "touches": 2, "duration_bars": int(sep),
                "structure_depth": round(float(depth), 4),
                "breakout_distance": round(float((neck.price - c[conf]) / neck.price), 4) if conf else None,
                "volume_confirmation": round(_volume_confirmation(v, conf), 3) if conf else None,
            },
            params={"min_separation": min_sep, "max_separation": max_sep},
            tolerance={"price_tolerance": tol},
        ))
    return events


def detect_double_bottom(df, pivots, tol: float = 0.03, min_sep: int = 5,
                         max_sep: int = 120, confirm_horizon: int = 40,
                         instrument: str = "") -> list:
    h, l, c, v = _series(df)
    lows = [p for p in pivots if p.kind == "LOW"]
    highs = [p for p in pivots if p.kind == "HIGH"]
    events: list = []
    for a, b in zip(lows, lows[1:]):
        sep = b.index - a.index
        if sep < min_sep or sep > max_sep:
            continue
        if abs(a.price - b.price) / max(a.price, b.price) > tol:
            continue
        peak_candidates = [p for p in highs if a.index < p.index < b.index]
        if not peak_candidates:
            continue
        neck = max(peak_candidates, key=lambda p: p.price)
        if neck.price <= max(a.price, b.price):
            continue
        detection = max(a.detected, b.detected, neck.detected)
        if detection >= len(c):
            continue
        conf = _confirm_break(c, detection, neck.price, "up", confirm_horizon)
        depth = (neck.price - max(a.price, b.price)) / neck.price
        events.append(PatternEvent(
            pattern_id="DOUBLE_BOTTOM", instrument=instrument, direction="BULLISH",
            anchor_indices=[a.index, neck.index, b.index],
            detection_index=detection, confirmation_index=conf,
            trigger_level=float(neck.price),
            invalidation_level=float(min(a.price, b.price)),
            quality={
                "geometric_fit": _geo_score([a.price, b.price], tol),
                "touches": 2, "duration_bars": int(sep),
                "structure_depth": round(float(depth), 4),
                "breakout_distance": round(float((c[conf] - neck.price) / neck.price), 4) if conf else None,
                "volume_confirmation": round(_volume_confirmation(v, conf), 3) if conf else None,
            },
            params={"min_separation": min_sep, "max_separation": max_sep},
            tolerance={"price_tolerance": tol},
        ))
    return events


def detect_triple(df, pivots, kind: str = "TOP", tol: float = 0.035,
                  max_span: int = 200, confirm_horizon: int = 40,
                  instrument: str = "") -> list:
    """Three extrema agreeing within tolerance, confirmed by a neckline break."""
    h, l, c, v = _series(df)
    want = "HIGH" if kind == "TOP" else "LOW"
    other = "LOW" if kind == "TOP" else "HIGH"
    ext = [p for p in pivots if p.kind == want]
    mids = [p for p in pivots if p.kind == other]
    events: list = []
    for a, b, d in zip(ext, ext[1:], ext[2:]):
        span = d.index - a.index
        if span > max_span or span < 10:
            continue
        prices = [a.price, b.price, d.price]
        if (max(prices) - min(prices)) / max(prices) > tol:
            continue
        between = [p for p in mids if a.index < p.index < d.index]
        if len(between) < 2:
            continue
        neck = (min(between, key=lambda p: p.price) if kind == "TOP"
                else max(between, key=lambda p: p.price))
        detection = max(a.detected, b.detected, d.detected, neck.detected)
        if detection >= len(c):
            continue
        direction = "down" if kind == "TOP" else "up"
        conf = _confirm_break(c, detection, neck.price, direction, confirm_horizon)
        events.append(PatternEvent(
            pattern_id=f"TRIPLE_{kind}", instrument=instrument,
            direction="BEARISH" if kind == "TOP" else "BULLISH",
            anchor_indices=[a.index, b.index, d.index, neck.index],
            detection_index=detection, confirmation_index=conf,
            trigger_level=float(neck.price),
            invalidation_level=float(max(prices) if kind == "TOP" else min(prices)),
            quality={
                "geometric_fit": _geo_score(prices, tol), "touches": 3,
                "duration_bars": int(span),
                "volume_confirmation": round(_volume_confirmation(v, conf), 3) if conf else None,
            },
            params={"max_span": max_span}, tolerance={"price_tolerance": tol},
        ))
    return events


# ── Head and shoulders ──────────────────────────────────────────────────────

def detect_head_shoulders(df, pivots, inverse: bool = False,
                          shoulder_tol: float = 0.05, head_ratio: float = 1.02,
                          max_span: int = 250, confirm_horizon: int = 50,
                          instrument: str = "") -> list:
    """
    Left shoulder, head, right shoulder with a neckline through the two
    intervening extremes. The neckline may slope; confirmation is a close
    beyond the neckline *extrapolated to the breakout bar*.
    """
    h, l, c, v = _series(df)
    want = "LOW" if inverse else "HIGH"
    other = "HIGH" if inverse else "LOW"
    ext = [p for p in pivots if p.kind == want]
    mids = [p for p in pivots if p.kind == other]
    events: list = []

    for ls, head, rs in zip(ext, ext[1:], ext[2:]):
        span = rs.index - ls.index
        if span > max_span or span < 15:
            continue
        if inverse:
            if not (head.price < ls.price / head_ratio and head.price < rs.price / head_ratio):
                continue
        else:
            if not (head.price > ls.price * head_ratio and head.price > rs.price * head_ratio):
                continue
        if abs(ls.price - rs.price) / max(ls.price, rs.price) > shoulder_tol:
            continue

        n1 = [p for p in mids if ls.index < p.index < head.index]
        n2 = [p for p in mids if head.index < p.index < rs.index]
        if not n1 or not n2:
            continue
        p1 = (max(n1, key=lambda p: p.price) if inverse else min(n1, key=lambda p: p.price))
        p2 = (max(n2, key=lambda p: p.price) if inverse else min(n2, key=lambda p: p.price))

        slope = (p2.price - p1.price) / max(1, (p2.index - p1.index))
        detection = max(ls.detected, head.detected, rs.detected, p1.detected, p2.detected)
        if detection >= len(c):
            continue

        direction = "up" if inverse else "down"
        conf = None
        end = min(len(c), detection + confirm_horizon + 1)
        for j in range(detection + 1, end):
            neck_j = p1.price + slope * (j - p1.index)
            if (direction == "up" and c[j] > neck_j) or (direction == "down" and c[j] < neck_j):
                conf = j
                break

        neck_at_detect = float(p1.price + slope * (detection - p1.index))
        events.append(PatternEvent(
            pattern_id="INVERSE_HEAD_SHOULDERS" if inverse else "HEAD_SHOULDERS",
            instrument=instrument, direction="BULLISH" if inverse else "BEARISH",
            anchor_indices=[ls.index, p1.index, head.index, p2.index, rs.index],
            detection_index=detection, confirmation_index=conf,
            trigger_level=neck_at_detect,
            invalidation_level=float(head.price),
            quality={
                "geometric_fit": _geo_score([ls.price, rs.price], shoulder_tol),
                "head_prominence": round(float(abs(head.price - (ls.price + rs.price) / 2) /
                                               ((ls.price + rs.price) / 2)), 4),
                "touches": 5, "duration_bars": int(span),
                "neckline_slope": round(float(slope), 6),
                "volume_confirmation": round(_volume_confirmation(v, conf), 3) if conf else None,
            },
            params={"head_ratio": head_ratio, "max_span": max_span},
            tolerance={"shoulder_tolerance": shoulder_tol},
        ))
    return events


# ── Triangles, rectangles, wedges, channels ─────────────────────────────────

def _fit_line(xs: list, ys: list) -> tuple[float, float, float]:
    """OLS fit; returns (slope, intercept, r2)."""
    x = np.asarray(xs, float); y = np.asarray(ys, float)
    if len(x) < 2:
        return 0.0, float(y.mean() if len(y) else 0.0), 0.0
    xm, ym = x.mean(), y.mean()
    denom = float(((x - xm) ** 2).sum())
    if denom == 0:
        return 0.0, float(ym), 0.0
    slope = float(((x - xm) * (y - ym)).sum() / denom)
    intercept = float(ym - slope * xm)
    pred = slope * x + intercept
    sse = float(((y - pred) ** 2).sum())
    sst = float(((y - ym) ** 2).sum())
    return slope, intercept, (1.0 - sse / sst if sst > 0 else 0.0)


def detect_triangle_family(df, pivots, window_pivots: int = 6,
                           flat_tol: float = 0.02, min_r2: float = 0.60,
                           confirm_horizon: int = 30, instrument: str = "") -> list:
    """
    Ascending / descending / symmetrical triangles and rectangles, classified
    from the fitted slopes of the recent upper and lower pivot boundaries.
    """
    h, l, c, v = _series(df)
    highs = [p for p in pivots if p.kind == "HIGH"]
    lows = [p for p in pivots if p.kind == "LOW"]
    events: list = []
    if len(highs) < 3 or len(lows) < 3:
        return events

    half = max(3, window_pivots // 2)
    for hi_end in range(half, len(highs) + 1):
        hs = highs[hi_end - half:hi_end]
        last_h = hs[-1]
        ls = [p for p in lows if p.index <= last_h.index][-half:]
        if len(ls) < half:
            continue
        detection = max(max(p.detected for p in hs), max(p.detected for p in ls))
        if detection >= len(c) - 1:
            continue

        hs_slope, hs_int, hs_r2 = _fit_line([p.index for p in hs], [p.price for p in hs])
        ls_slope, ls_int, ls_r2 = _fit_line([p.index for p in ls], [p.price for p in ls])
        if hs_r2 < min_r2 and ls_r2 < min_r2:
            continue

        mean_price = float(np.mean([p.price for p in hs + ls]))
        # normalise slopes to "fraction of price per bar" so the flatness test
        # means the same thing on a Rs.50 stock and a Rs.5000 stock
        hs_norm = hs_slope / mean_price
        ls_norm = ls_slope / mean_price
        flat_h = abs(hs_norm) < flat_tol / 100.0
        flat_l = abs(ls_norm) < flat_tol / 100.0

        if flat_h and ls_norm > flat_tol / 100.0:
            pid, direction, brk = "ASCENDING_TRIANGLE", "BULLISH", "up"
        elif flat_l and hs_norm < -flat_tol / 100.0:
            pid, direction, brk = "DESCENDING_TRIANGLE", "BEARISH", "down"
        elif hs_norm < -flat_tol / 100.0 and ls_norm > flat_tol / 100.0:
            pid, direction, brk = "SYMMETRICAL_TRIANGLE", "NEUTRAL", "either"
        elif flat_h and flat_l:
            pid, direction, brk = "RECTANGLE", "NEUTRAL", "either"
        elif hs_norm > flat_tol / 100.0 and ls_norm > flat_tol / 100.0 and hs_norm < ls_norm:
            pid, direction, brk = "RISING_WEDGE", "NEUTRAL", "either"
        elif hs_norm < -flat_tol / 100.0 and ls_norm < -flat_tol / 100.0 and hs_norm > ls_norm:
            pid, direction, brk = "FALLING_WEDGE", "NEUTRAL", "either"
        else:
            continue

        conf, conf_dir = None, None
        end = min(len(c), detection + confirm_horizon + 1)
        for j in range(detection + 1, end):
            up_b = hs_slope * j + hs_int
            lo_b = ls_slope * j + ls_int
            if brk in ("up", "either") and c[j] > up_b:
                conf, conf_dir = j, "BULLISH"
                break
            if brk in ("down", "either") and c[j] < lo_b:
                conf, conf_dir = j, "BEARISH"
                break

        events.append(PatternEvent(
            pattern_id=pid, instrument=instrument,
            direction=conf_dir or direction,
            anchor_indices=[p.index for p in ls] + [p.index for p in hs],
            detection_index=detection, confirmation_index=conf,
            trigger_level=float(hs_slope * detection + hs_int),
            invalidation_level=float(ls_slope * detection + ls_int),
            quality={
                "geometric_fit": round(float(max(hs_r2, ls_r2)), 3),
                "upper_fit_r2": round(float(hs_r2), 3),
                "lower_fit_r2": round(float(ls_r2), 3),
                "touches": len(hs) + len(ls),
                "duration_bars": int(last_h.index - min(p.index for p in ls)),
                "convergence": round(float(abs(hs_norm - ls_norm)), 6),
                "volume_confirmation": round(_volume_confirmation(v, conf), 3) if conf else None,
            },
            params={"window_pivots": window_pivots, "min_r2": min_r2},
            tolerance={"flat_tolerance_pct": flat_tol},
        ))
        if len(events) >= 200:      # overlapping windows can otherwise flood
            break
    return events


def detect_flag(df, pivots, impulse_atr: float = 3.0, impulse_bars: int = 10,
                consolidation_bars: int = 15, max_retrace: float = 0.50,
                atr_series: Optional[np.ndarray] = None,
                confirm_horizon: int = 20, instrument: str = "") -> list:
    """
    Impulse measured in ATR units followed by a shallow countertrend drift,
    confirmed by a close beyond the consolidation high (bull) or low (bear).
    """
    h, l, c, v = _series(df)
    n = len(c)
    if atr_series is None or n < impulse_bars + consolidation_bars + 5:
        return []
    events: list = []
    i = impulse_bars
    while i < n - consolidation_bars - 1:
        a = atr_series[i]
        if np.isnan(a) or a <= 0:
            i += 1
            continue
        move = c[i] - c[i - impulse_bars]
        if abs(move) < impulse_atr * a:
            i += 1
            continue
        bull = move > 0
        end = min(n - 1, i + consolidation_bars)
        seg_h = float(np.max(h[i:end + 1]))
        seg_l = float(np.min(l[i:end + 1]))
        retrace = (c[i] - seg_l) / abs(move) if bull else (seg_h - c[i]) / abs(move)
        if retrace > max_retrace:
            i += 1
            continue
        level = seg_h if bull else seg_l
        conf = _confirm_break(c, end, level, "up" if bull else "down", confirm_horizon)
        events.append(PatternEvent(
            pattern_id="BULL_FLAG" if bull else "BEAR_FLAG", instrument=instrument,
            direction="BULLISH" if bull else "BEARISH",
            anchor_indices=[i - impulse_bars, i, end],
            detection_index=end, confirmation_index=conf,
            trigger_level=float(level),
            invalidation_level=float(seg_l if bull else seg_h),
            quality={
                "impulse_atr": round(float(abs(move) / a), 2),
                "retracement": round(float(retrace), 3),
                "duration_bars": int(end - (i - impulse_bars)),
                "touches": 2,
                "volume_confirmation": round(_volume_confirmation(v, conf), 3) if conf else None,
            },
            params={"impulse_atr": impulse_atr, "impulse_bars": impulse_bars},
            tolerance={"max_retrace": max_retrace},
        ))
        i = end + 1
    return events


# ── Driver ──────────────────────────────────────────────────────────────────

CHART_PATTERNS = {
    "DOUBLE_TOP": ("Double Top", "BEARISH",
                   {"tol": 0.03, "min_sep": 5, "max_sep": 120, "confirm_horizon": 40}),
    "DOUBLE_BOTTOM": ("Double Bottom", "BULLISH",
                      {"tol": 0.03, "min_sep": 5, "max_sep": 120, "confirm_horizon": 40}),
    "TRIPLE_TOP": ("Triple Top", "BEARISH", {"tol": 0.035, "max_span": 200}),
    "TRIPLE_BOTTOM": ("Triple Bottom", "BULLISH", {"tol": 0.035, "max_span": 200}),
    "HEAD_SHOULDERS": ("Head & Shoulders", "BEARISH",
                       {"shoulder_tol": 0.05, "head_ratio": 1.02, "max_span": 250}),
    "INVERSE_HEAD_SHOULDERS": ("Inverse Head & Shoulders", "BULLISH",
                               {"shoulder_tol": 0.05, "head_ratio": 1.02, "max_span": 250}),
    "TRIANGLE": ("Triangle / Rectangle / Wedge family", "CONTEXT",
                 {"window_pivots": 6, "flat_tol": 0.02, "min_r2": 0.60}),
    "FLAG": ("Flag / Pennant", "CONTEXT",
             {"impulse_atr": 3.0, "impulse_bars": 10, "consolidation_bars": 15}),
}


def detect_all(df: pd.DataFrame, requests: list, pivot_k: int = 3,
               atr_series: Optional[np.ndarray] = None,
               instrument: str = "") -> tuple[dict, list, list]:
    """
    Run requested chart-pattern detectors.

    Returns (confirmed_masks_by_id, all_events, errors). The mask is True only
    on the CONFIRMATION bar — the earliest bar a strategy may act on.
    """
    n = len(df)
    h = df["High"].to_numpy(float); l = df["Low"].to_numpy(float)
    pivots = find_pivots(h, l, pivot_k)
    masks, events, errors = {}, [], []

    for req in requests or []:
        rid = req.get("id")
        rtype = str(req.get("type", "")).upper()
        if rtype not in CHART_PATTERNS:
            errors.append(f"Unknown chart pattern '{rtype}' (id={rid})")
            continue
        p = {k: v for k, v in req.items() if k not in ("id", "type")}
        try:
            if rtype == "DOUBLE_TOP":
                found = detect_double_top(df, pivots, instrument=instrument, **p)
            elif rtype == "DOUBLE_BOTTOM":
                found = detect_double_bottom(df, pivots, instrument=instrument, **p)
            elif rtype == "TRIPLE_TOP":
                found = detect_triple(df, pivots, "TOP", instrument=instrument, **p)
            elif rtype == "TRIPLE_BOTTOM":
                found = detect_triple(df, pivots, "BOTTOM", instrument=instrument, **p)
            elif rtype == "HEAD_SHOULDERS":
                found = detect_head_shoulders(df, pivots, False, instrument=instrument, **p)
            elif rtype == "INVERSE_HEAD_SHOULDERS":
                found = detect_head_shoulders(df, pivots, True, instrument=instrument, **p)
            elif rtype == "TRIANGLE":
                found = detect_triangle_family(df, pivots, instrument=instrument, **p)
            else:
                found = detect_flag(df, pivots, atr_series=atr_series,
                                    instrument=instrument, **p)
        except Exception as exc:
            errors.append(f"Chart pattern '{rid}' ({rtype}) failed: {exc}")
            continue

        mask = np.zeros(n, dtype=bool)
        want_dir = str(req.get("direction", "")).upper()
        for ev in found:
            if ev.confirmation_index is None:
                continue
            if want_dir and ev.direction != want_dir:
                continue
            mask[ev.confirmation_index] = True
        masks[rid] = mask
        events.extend(found)

    return masks, events, errors


def catalogue() -> list:
    return [
        {"key": k, "label": lbl, "direction": d, "params": p}
        for k, (lbl, d, p) in CHART_PATTERNS.items()
    ]
