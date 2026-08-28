"""
Candlestick predicate catalogue (spec §8).

Every pattern is a deterministic boolean predicate with explicit, stored
tolerances — no fuzzy visual labelling. For each candle the engine defines:

    body       = |C - O|
    range      = H - L
    upper_wick = H - max(O, C)
    lower_wick = min(O, C) - L
    body_pct   = body / range

Detectors return a boolean array aligned to the frame. A pattern that needs
k prior bars is False for the first k bars — never NaN-propagated into a
comparison, and never true on a bar whose inputs do not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class CandleParts:
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    body: np.ndarray
    rng: np.ndarray
    upper: np.ndarray
    lower: np.ndarray
    body_pct: np.ndarray
    bullish: np.ndarray
    bearish: np.ndarray


def decompose(df: pd.DataFrame) -> CandleParts:
    o = df["Open"].to_numpy(float)
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    body = np.abs(c - o)
    rng = h - l
    safe = np.where(rng == 0, np.nan, rng)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    return CandleParts(
        o=o, h=h, l=l, c=c, body=body, rng=rng,
        upper=upper, lower=lower,
        body_pct=body / safe,
        bullish=c > o, bearish=c < o,
    )


def _prev(a: np.ndarray, k: int = 1) -> np.ndarray:
    """Shift forward by k bars (value from k bars ago), NaN/False padded."""
    out = np.empty_like(a)
    if a.dtype == bool:
        out = np.zeros_like(a, dtype=bool)
        if k < len(a):
            out[k:] = a[:-k]
        return out
    out = np.full(len(a), np.nan)
    if k < len(a):
        out[k:] = a[:-k]
    return out


def _clean(mask: np.ndarray) -> np.ndarray:
    return np.nan_to_num(mask.astype(float), nan=0.0).astype(bool)


# ── Single-bar patterns ─────────────────────────────────────────────────────

def doji(p: CandleParts, eps: float = 0.10) -> np.ndarray:
    return _clean(p.body_pct <= eps)


def dragonfly_doji(p: CandleParts, eps: float = 0.10, eps_w: float = 0.10,
                   min_lower: float = 0.60) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    return _clean((p.body_pct <= eps) & (p.upper / r <= eps_w) & (p.lower / r >= min_lower))


def gravestone_doji(p: CandleParts, eps: float = 0.10, eps_w: float = 0.10,
                    min_upper: float = 0.60) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    return _clean((p.body_pct <= eps) & (p.lower / r <= eps_w) & (p.upper / r >= min_upper))


def spinning_top(p: CandleParts, max_body: float = 0.30, min_wick: float = 0.25) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    return _clean((p.body_pct <= max_body) & (p.upper / r >= min_wick) & (p.lower / r >= min_wick))


def marubozu(p: CandleParts, min_body: float = 0.90, max_wick: float = 0.05) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    return _clean((p.body_pct >= min_body) & (p.upper / r <= max_wick) & (p.lower / r <= max_wick))


def hammer(p: CandleParts, wick_ratio: float = 2.0, max_upper: float = 0.25,
           body_position: float = 0.60) -> np.ndarray:
    """Lower wick >= 2*body, tiny upper wick, body sitting in the upper part."""
    r = np.where(p.rng == 0, np.nan, p.rng)
    b = np.where(p.body == 0, 1e-9, p.body)
    body_mid = (p.o + p.c) / 2.0
    position = (body_mid - p.l) / r
    return _clean((p.lower >= wick_ratio * b) & (p.upper <= max_upper * b) &
                  (position >= body_position))


def inverted_hammer(p: CandleParts, wick_ratio: float = 2.0, max_lower: float = 0.25,
                    body_position: float = 0.40) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    b = np.where(p.body == 0, 1e-9, p.body)
    body_mid = (p.o + p.c) / 2.0
    position = (body_mid - p.l) / r
    return _clean((p.upper >= wick_ratio * b) & (p.lower <= max_lower * b) &
                  (position <= body_position))


def shooting_star(p: CandleParts, wick_ratio: float = 2.0, max_lower: float = 0.25,
                  body_position: float = 0.40, require_uptrend: int = 1,
                  trend_lookback: int = 5) -> np.ndarray:
    """Inverted-hammer geometry, but context-gated on a prior advance.

    The uptrend context uses only bars strictly before the signal bar.
    """
    base = inverted_hammer(p, wick_ratio, max_lower, body_position)
    if not int(require_uptrend):
        return base
    prior_close = _prev(p.c, 1)
    older_close = _prev(p.c, trend_lookback + 1)
    uptrend = _clean(prior_close > older_close)
    return base & uptrend


# ── Two-bar patterns ────────────────────────────────────────────────────────

def engulfing_bull(p: CandleParts, min_body_ratio: float = 1.0) -> np.ndarray:
    po, pc, pb = _prev(p.o), _prev(p.c), _prev(p.body)
    return _clean(_prev(p.bearish) & p.bullish & (p.o <= pc) & (p.c >= po) &
                  (p.body >= min_body_ratio * pb))


def engulfing_bear(p: CandleParts, min_body_ratio: float = 1.0) -> np.ndarray:
    po, pc, pb = _prev(p.o), _prev(p.c), _prev(p.body)
    return _clean(_prev(p.bullish) & p.bearish & (p.o >= pc) & (p.c <= po) &
                  (p.body >= min_body_ratio * pb))


def inside_bar(p: CandleParts) -> np.ndarray:
    return _clean((p.h < _prev(p.h)) & (p.l > _prev(p.l)))


def outside_bar(p: CandleParts) -> np.ndarray:
    return _clean((p.h > _prev(p.h)) & (p.l < _prev(p.l)))


def harami_bull(p: CandleParts, max_body_ratio: float = 0.60) -> np.ndarray:
    po, pc, pb = _prev(p.o), _prev(p.c), _prev(p.body)
    top, bot = np.maximum(po, pc), np.minimum(po, pc)
    inside = (np.maximum(p.o, p.c) <= top) & (np.minimum(p.o, p.c) >= bot)
    return _clean(_prev(p.bearish) & p.bullish & inside &
                  (p.body <= max_body_ratio * np.where(pb == 0, np.nan, pb)))


def harami_bear(p: CandleParts, max_body_ratio: float = 0.60) -> np.ndarray:
    po, pc, pb = _prev(p.o), _prev(p.c), _prev(p.body)
    top, bot = np.maximum(po, pc), np.minimum(po, pc)
    inside = (np.maximum(p.o, p.c) <= top) & (np.minimum(p.o, p.c) >= bot)
    return _clean(_prev(p.bullish) & p.bearish & inside &
                  (p.body <= max_body_ratio * np.where(pb == 0, np.nan, pb)))


def piercing_line(p: CandleParts) -> np.ndarray:
    po, pc = _prev(p.o), _prev(p.c)
    mid = (po + pc) / 2.0
    return _clean(_prev(p.bearish) & p.bullish & (p.o < pc) & (p.c > mid) & (p.c < po))


def dark_cloud_cover(p: CandleParts) -> np.ndarray:
    po, pc = _prev(p.o), _prev(p.c)
    mid = (po + pc) / 2.0
    return _clean(_prev(p.bullish) & p.bearish & (p.o > pc) & (p.c < mid) & (p.c > po))


def gap_up(p: CandleParts) -> np.ndarray:
    return _clean(p.o > _prev(p.h))


def gap_down(p: CandleParts) -> np.ndarray:
    return _clean(p.o < _prev(p.l))


# ── Three-bar patterns ──────────────────────────────────────────────────────

def morning_star(p: CandleParts, small_body: float = 0.50, penetration: float = 0.50) -> np.ndarray:
    """Large bearish, small-bodied middle, strong bullish close into bar-1 body."""
    o1, c1, b1 = _prev(p.o, 2), _prev(p.c, 2), _prev(p.body, 2)
    b2 = _prev(p.body, 1)
    bear1 = _prev(p.bearish, 2)
    mid1 = (o1 + c1) / 2.0
    small_mid = b2 <= small_body * np.where(b1 == 0, np.nan, b1)
    return _clean(bear1 & small_mid & p.bullish &
                  (p.c > mid1) & (p.c >= c1 + penetration * (o1 - c1)))


def evening_star(p: CandleParts, small_body: float = 0.50, penetration: float = 0.50) -> np.ndarray:
    o1, c1, b1 = _prev(p.o, 2), _prev(p.c, 2), _prev(p.body, 2)
    b2 = _prev(p.body, 1)
    bull1 = _prev(p.bullish, 2)
    mid1 = (o1 + c1) / 2.0
    small_mid = b2 <= small_body * np.where(b1 == 0, np.nan, b1)
    return _clean(bull1 & small_mid & p.bearish &
                  (p.c < mid1) & (p.c <= c1 - penetration * (c1 - o1)))


def three_white_soldiers(p: CandleParts, max_upper_wick: float = 0.40) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    ok_wick = (p.upper / r <= max_upper_wick)
    return _clean(_prev(p.bullish, 2) & _prev(p.bullish, 1) & p.bullish &
                  (_prev(p.c, 1) > _prev(p.c, 2)) & (p.c > _prev(p.c, 1)) &
                  ok_wick & _prev(ok_wick, 1))


def three_black_crows(p: CandleParts, max_lower_wick: float = 0.40) -> np.ndarray:
    r = np.where(p.rng == 0, np.nan, p.rng)
    ok_wick = (p.lower / r <= max_lower_wick)
    return _clean(_prev(p.bearish, 2) & _prev(p.bearish, 1) & p.bearish &
                  (_prev(p.c, 1) < _prev(p.c, 2)) & (p.c < _prev(p.c, 1)) &
                  ok_wick & _prev(ok_wick, 1))


def three_inside_up(p: CandleParts) -> np.ndarray:
    """Bullish harami on bars t-1/t-2, confirmed by a close above bar t-2's open."""
    hb = harami_bull(p)
    return _clean(_prev(hb, 1) & p.bullish & (p.c > _prev(p.o, 2)))


def three_inside_down(p: CandleParts) -> np.ndarray:
    hb = harami_bear(p)
    return _clean(_prev(hb, 1) & p.bearish & (p.c < _prev(p.o, 2)))


def three_outside_up(p: CandleParts) -> np.ndarray:
    eb = engulfing_bull(p)
    return _clean(_prev(eb, 1) & p.bullish & (p.c > _prev(p.c, 1)))


def three_outside_down(p: CandleParts) -> np.ndarray:
    eb = engulfing_bear(p)
    return _clean(_prev(eb, 1) & p.bearish & (p.c < _prev(p.c, 1)))


# ── Registry ────────────────────────────────────────────────────────────────

@dataclass
class CandleSpec:
    key: str
    label: str
    direction: str
    bars: int
    params: dict
    description: str
    fn: Callable


CANDLES: dict[str, CandleSpec] = {}


def _reg(spec: CandleSpec):
    CANDLES[spec.key] = spec
    return spec


_reg(CandleSpec("DOJI", "Doji", "NEUTRAL", 1, {"eps": 0.10},
                "Body no larger than eps of the bar range.", doji))
_reg(CandleSpec("DRAGONFLY_DOJI", "Dragonfly Doji", "BULLISH", 1,
                {"eps": 0.10, "eps_w": 0.10, "min_lower": 0.60},
                "Doji body with a dominant lower wick and negligible upper wick.",
                dragonfly_doji))
_reg(CandleSpec("GRAVESTONE_DOJI", "Gravestone Doji", "BEARISH", 1,
                {"eps": 0.10, "eps_w": 0.10, "min_upper": 0.60},
                "Doji body with a dominant upper wick and negligible lower wick.",
                gravestone_doji))
_reg(CandleSpec("SPINNING_TOP", "Spinning Top", "NEUTRAL", 1,
                {"max_body": 0.30, "min_wick": 0.25},
                "Small body with meaningful wicks on both sides.", spinning_top))
_reg(CandleSpec("MARUBOZU", "Marubozu", "DIRECTIONAL", 1,
                {"min_body": 0.90, "max_wick": 0.05},
                "Body fills the range; wicks are negligible.", marubozu))
_reg(CandleSpec("HAMMER", "Hammer", "BULLISH", 1,
                {"wick_ratio": 2.0, "max_upper": 0.25, "body_position": 0.60},
                "Long lower wick, small upper wick, body in the upper range.", hammer))
_reg(CandleSpec("INVERTED_HAMMER", "Inverted Hammer", "BULLISH", 1,
                {"wick_ratio": 2.0, "max_lower": 0.25, "body_position": 0.40},
                "Long upper wick, small lower wick, body in the lower range.",
                inverted_hammer))
_reg(CandleSpec("SHOOTING_STAR", "Shooting Star", "BEARISH", 1,
                {"wick_ratio": 2.0, "max_lower": 0.25, "body_position": 0.40,
                 "require_uptrend": 1, "trend_lookback": 5},
                "Inverted-hammer geometry gated on a prior advance (past bars only).",
                shooting_star))
_reg(CandleSpec("ENGULFING_BULL", "Bullish Engulfing", "BULLISH", 2,
                {"min_body_ratio": 1.0},
                "Bullish body fully covering the prior bearish body.", engulfing_bull))
_reg(CandleSpec("ENGULFING_BEAR", "Bearish Engulfing", "BEARISH", 2,
                {"min_body_ratio": 1.0},
                "Bearish body fully covering the prior bullish body.", engulfing_bear))
_reg(CandleSpec("INSIDE_BAR", "Inside Bar", "NEUTRAL", 2, {},
                "Range entirely inside the prior bar's range.", inside_bar))
_reg(CandleSpec("OUTSIDE_BAR", "Outside Bar", "NEUTRAL", 2, {},
                "Range entirely covering the prior bar's range.", outside_bar))
_reg(CandleSpec("HARAMI_BULL", "Bullish Harami", "BULLISH", 2, {"max_body_ratio": 0.60},
                "Small bullish body inside a larger prior bearish body.", harami_bull))
_reg(CandleSpec("HARAMI_BEAR", "Bearish Harami", "BEARISH", 2, {"max_body_ratio": 0.60},
                "Small bearish body inside a larger prior bullish body.", harami_bear))
_reg(CandleSpec("PIERCING_LINE", "Piercing Line", "BULLISH", 2, {},
                "Opens below the prior close, closes above the prior body midpoint.",
                piercing_line))
_reg(CandleSpec("DARK_CLOUD", "Dark Cloud Cover", "BEARISH", 2, {},
                "Opens above the prior close, closes below the prior body midpoint.",
                dark_cloud_cover))
_reg(CandleSpec("GAP_UP", "Gap Up", "BULLISH", 2, {},
                "Open above the prior bar's high (session-gap definition).", gap_up))
_reg(CandleSpec("GAP_DOWN", "Gap Down", "BEARISH", 2, {},
                "Open below the prior bar's low (session-gap definition).", gap_down))
_reg(CandleSpec("MORNING_STAR", "Morning Star", "BULLISH", 3,
                {"small_body": 0.50, "penetration": 0.50},
                "Bearish bar, small-bodied pause, strong bullish close into bar one.",
                morning_star))
_reg(CandleSpec("EVENING_STAR", "Evening Star", "BEARISH", 3,
                {"small_body": 0.50, "penetration": 0.50},
                "Bullish bar, small-bodied pause, strong bearish close into bar one.",
                evening_star))
_reg(CandleSpec("THREE_WHITE_SOLDIERS", "Three White Soldiers", "BULLISH", 3,
                {"max_upper_wick": 0.40},
                "Three rising bullish closes with controlled upper wicks.",
                three_white_soldiers))
_reg(CandleSpec("THREE_BLACK_CROWS", "Three Black Crows", "BEARISH", 3,
                {"max_lower_wick": 0.40},
                "Three falling bearish closes with controlled lower wicks.",
                three_black_crows))
_reg(CandleSpec("THREE_INSIDE_UP", "Three Inside Up", "BULLISH", 3, {},
                "Bullish harami confirmed by a close beyond the first body.",
                three_inside_up))
_reg(CandleSpec("THREE_INSIDE_DOWN", "Three Inside Down", "BEARISH", 3, {},
                "Bearish harami confirmed by a close beyond the first body.",
                three_inside_down))
_reg(CandleSpec("THREE_OUTSIDE_UP", "Three Outside Up", "BULLISH", 3, {},
                "Bullish engulfing followed by a continuation close.", three_outside_up))
_reg(CandleSpec("THREE_OUTSIDE_DOWN", "Three Outside Down", "BEARISH", 3, {},
                "Bearish engulfing followed by a continuation close.", three_outside_down))


def compute_candles(df: pd.DataFrame, requests: list) -> tuple[dict, list]:
    """
    Evaluate requested candle predicates.

    `requests` is a list of {"id", "type", **tolerances}. Returns
    (values_by_id, errors). Values are boolean arrays; the graph layer treats
    them as truthy conditions directly.
    """
    parts = decompose(df)
    values, errors = {}, []
    for req in requests or []:
        rid = req.get("id")
        rtype = str(req.get("type", "")).upper()
        spec = CANDLES.get(rtype)
        if not spec:
            errors.append(f"Unknown candle pattern '{rtype}' (id={rid})")
            continue
        params = {**spec.params, **{k: v for k, v in req.items() if k in spec.params}}
        try:
            values[rid] = spec.fn(parts, **params)
        except Exception as exc:
            errors.append(f"Candle '{rid}' ({rtype}) failed: {exc}")
    return values, errors


def catalogue() -> list:
    return [
        {"key": s.key, "label": s.label, "direction": s.direction,
         "bars": s.bars, "params": s.params, "description": s.description}
        for s in sorted(CANDLES.values(), key=lambda x: (x.bars, x.key))
    ]
