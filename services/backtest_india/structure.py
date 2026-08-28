"""
Price-action structure engine (spec §9).

The single most important rule in this module: a swing pivot is NOT knowable
at the bar where it occurs. Confirming that bar t is a swing high requires k
bars *after* t. Every function here therefore separates:

    pivot_index      — where the extreme actually sits
    detection_index  — pivot_index + k, the first bar at which it is knowable

Anything the strategy graph can read is indexed by detection time. The pivot's
own bar index is retained only for charting and audit. This is what stops
"break of a confirmed resistance" from quietly becoming a look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Pivot:
    index: int          # bar where the extreme occurred
    detected: int       # bar at which it became knowable (index + k)
    price: float
    kind: str           # HIGH | LOW


@dataclass
class StructureState:
    """Everything the structure layer exposes, all detection-time indexed."""
    pivots: list = field(default_factory=list)
    swing_high_level: np.ndarray = None    # last confirmed swing high, as known at i
    swing_low_level: np.ndarray = None
    swing_high_age: np.ndarray = None
    swing_low_age: np.ndarray = None
    bos_up: np.ndarray = None
    bos_down: np.ndarray = None
    choch_up: np.ndarray = None
    choch_down: np.ndarray = None
    resistance: np.ndarray = None          # nearest clustered level above
    support: np.ndarray = None             # nearest clustered level below
    trend: np.ndarray = None               # +1 / 0 / -1 from HH-HL sequencing
    compression: np.ndarray = None         # bandwidth percentile, 0-100
    levels: list = field(default_factory=list)   # clustered S/R for charting


def find_pivots(h: np.ndarray, l: np.ndarray, k: int = 3) -> list:
    """
    Fractal pivots: H_t is a swing high if it dominates the k bars either side.

    The comparison to the right side is strict-or-equal per the spec
    (H_t >= H_{t+1:t+k}) while the left is strict, which prevents a flat run of
    equal highs from registering k separate pivots.
    """
    n = len(h)
    out: list = []
    for t in range(k, n - k):
        left_h, right_h = h[t - k:t], h[t + 1:t + k + 1]
        if h[t] > left_h.max() and h[t] >= right_h.max():
            out.append(Pivot(index=t, detected=t + k, price=float(h[t]), kind="HIGH"))
        left_l, right_l = l[t - k:t], l[t + 1:t + k + 1]
        if l[t] < left_l.min() and l[t] <= right_l.min():
            out.append(Pivot(index=t, detected=t + k, price=float(l[t]), kind="LOW"))
    out.sort(key=lambda p: (p.detected, p.index))
    return out


def _running_levels(pivots: list, n: int, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """For every bar, the most recent CONFIRMED pivot level of `kind` and its age."""
    level = np.full(n, np.nan)
    age = np.full(n, np.nan)
    cur_price, cur_index = np.nan, None
    ptr = 0
    ordered = [p for p in pivots if p.kind == kind]
    for i in range(n):
        while ptr < len(ordered) and ordered[ptr].detected <= i:
            cur_price = ordered[ptr].price
            cur_index = ordered[ptr].index
            ptr += 1
        level[i] = cur_price
        age[i] = (i - cur_index) if cur_index is not None else np.nan
    return level, age


def cluster_levels(pivots: list, atr_series: np.ndarray, prices: np.ndarray,
                   pct_tol: float = 0.005, atr_mult: float = 0.5,
                   min_touches: int = 2) -> list:
    """
    Spec §9 — support/resistance by clustering confirmed pivots within
    tolerance delta = max(pct_tol * price, atr_mult * ATR).

    Clusters are built incrementally in detection order so a level's "touch
    count as of bar i" only ever counts pivots already confirmed by bar i.
    """
    clusters: list = []
    for p in pivots:
        atr_here = atr_series[p.index] if p.index < len(atr_series) else np.nan
        atr_here = 0.0 if np.isnan(atr_here) else float(atr_here)
        tol = max(pct_tol * p.price, atr_mult * atr_here)
        placed = False
        for cl in clusters:
            if abs(cl["price"] - p.price) <= tol:
                total = cl["touches"] + 1
                cl["price"] = (cl["price"] * cl["touches"] + p.price) / total
                cl["touches"] = total
                cl["last_detected"] = p.detected
                cl["kinds"].add(p.kind)
                placed = True
                break
        if not placed:
            clusters.append({
                "price": p.price, "touches": 1,
                "first_detected": p.detected, "last_detected": p.detected,
                "kinds": {p.kind}, "tolerance": tol,
            })
    return [
        {"price": round(c["price"], 4), "touches": c["touches"],
         "first_detected": c["first_detected"], "last_detected": c["last_detected"],
         "kind": "RESISTANCE" if "HIGH" in c["kinds"] else "SUPPORT",
         "tolerance": round(c["tolerance"], 4)}
        for c in clusters if c["touches"] >= min_touches
    ]


def _nearest_levels(levels: list, close: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Nearest clustered level above / below the close, using only levels whose
    first confirmation already happened."""
    n = len(close)
    res = np.full(n, np.nan)
    sup = np.full(n, np.nan)
    ordered = sorted(levels, key=lambda x: x["first_detected"])
    active: list = []
    ptr = 0
    for i in range(n):
        while ptr < len(ordered) and ordered[ptr]["first_detected"] <= i:
            active.append(ordered[ptr]["price"])
            ptr += 1
        if not active:
            continue
        above = [p for p in active if p > close[i]]
        below = [p for p in active if p < close[i]]
        if above:
            res[i] = min(above)
        if below:
            sup[i] = max(below)
    return res, sup


def build_structure(df: pd.DataFrame, atr_series: np.ndarray,
                    k: int = 3, bos_buffer_atr: float = 0.10,
                    pct_tol: float = 0.005, atr_tol: float = 0.5,
                    min_touches: int = 2,
                    bandwidth: Optional[np.ndarray] = None,
                    compression_window: int = 100) -> StructureState:
    """Compute the full structure state for one instrument."""
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    n = len(c)

    pivots = find_pivots(h, l, k)
    sh_level, sh_age = _running_levels(pivots, n, "HIGH")
    sl_level, sl_age = _running_levels(pivots, n, "LOW")

    atr_safe = np.nan_to_num(atr_series, nan=0.0)
    buf = bos_buffer_atr * atr_safe

    # ── Break of structure: close beyond the last CONFIRMED swing + buffer ──
    bos_up = np.zeros(n, dtype=bool)
    bos_down = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if not np.isnan(sh_level[i]) and c[i] > sh_level[i] + buf[i] and c[i - 1] <= sh_level[i] + buf[i]:
            bos_up[i] = True
        if not np.isnan(sl_level[i]) and c[i] < sl_level[i] - buf[i] and c[i - 1] >= sl_level[i] - buf[i]:
            bos_down[i] = True

    # ── Change of character: the first break against the prevailing bias ──
    choch_up = np.zeros(n, dtype=bool)
    choch_down = np.zeros(n, dtype=bool)
    bias = 0
    for i in range(n):
        if bos_up[i]:
            if bias <= 0 and bias != 0:
                choch_up[i] = True
            bias = 1
        elif bos_down[i]:
            if bias >= 0 and bias != 0:
                choch_down[i] = True
            bias = -1

    # ── Trend from higher-high / higher-low sequencing of confirmed pivots ──
    trend = np.zeros(n)
    highs = [p for p in pivots if p.kind == "HIGH"]
    lows = [p for p in pivots if p.kind == "LOW"]
    hp = lp = 0
    last_h: list = []
    last_l: list = []
    state = 0
    for i in range(n):
        while hp < len(highs) and highs[hp].detected <= i:
            last_h.append(highs[hp].price); hp += 1
        while lp < len(lows) and lows[lp].detected <= i:
            last_l.append(lows[lp].price); lp += 1
        if len(last_h) >= 2 and len(last_l) >= 2:
            hh = last_h[-1] > last_h[-2]
            hl = last_l[-1] > last_l[-2]
            lh = last_h[-1] < last_h[-2]
            ll = last_l[-1] < last_l[-2]
            if hh and hl:
                state = 1
            elif lh and ll:
                state = -1
            else:
                state = 0
        trend[i] = state

    levels = cluster_levels(pivots, atr_series, c, pct_tol, atr_tol, min_touches)
    resistance, support = _nearest_levels(levels, c)

    if bandwidth is not None:
        comp = pd.Series(bandwidth).rolling(compression_window, min_periods=20).apply(
            lambda w: 100.0 * float((w[:-1] <= w[-1]).sum()) / max(1, len(w) - 1), raw=True
        ).to_numpy()
    else:
        comp = np.full(n, np.nan)

    return StructureState(
        pivots=pivots,
        swing_high_level=sh_level, swing_low_level=sl_level,
        swing_high_age=sh_age, swing_low_age=sl_age,
        bos_up=bos_up, bos_down=bos_down,
        choch_up=choch_up, choch_down=choch_down,
        resistance=resistance, support=support,
        trend=trend, compression=comp, levels=levels,
    )


def breakout_signal(df: pd.DataFrame, level: np.ndarray, direction: str = "up",
                    buffer_pct: float = 0.0) -> np.ndarray:
    """Close crosses a level (the level array must already be detection-safe)."""
    c = df["Close"].to_numpy(float)
    prev = np.roll(c, 1); prev[0] = c[0]
    thresh = level * (1 + buffer_pct) if direction == "up" else level * (1 - buffer_pct)
    if direction == "up":
        out = (c > thresh) & (prev <= thresh)
    else:
        out = (c < thresh) & (prev >= thresh)
    return np.nan_to_num(out.astype(float), nan=0.0).astype(bool)


def retest_signal(df: pd.DataFrame, level: np.ndarray, direction: str = "up",
                  tolerance_pct: float = 0.01, window: int = 10) -> np.ndarray:
    """
    Spec §9 — after a breakout, price returns within tolerance of the broken
    level and then closes back in the breakout direction.
    """
    c = df["Close"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    hgh = df["High"].to_numpy(float)
    n = len(c)
    brk = breakout_signal(df, level, direction)
    out = np.zeros(n, dtype=bool)
    for i in range(n):
        if not brk[i]:
            continue
        lvl = level[i]
        if np.isnan(lvl):
            continue
        tol = tolerance_pct * lvl
        for j in range(i + 1, min(n, i + 1 + window)):
            touched = (l[j] <= lvl + tol) if direction == "up" else (hgh[j] >= lvl - tol)
            if not touched:
                continue
            confirmed = (c[j] > lvl) if direction == "up" else (c[j] < lvl)
            if confirmed:
                out[j] = True
            break
    return out


STRUCTURE_OUTPUTS = {
    "swing_high": "Last confirmed swing high level (known only after k bars).",
    "swing_low": "Last confirmed swing low level (known only after k bars).",
    "swing_high_age": "Bars since the confirmed swing high occurred.",
    "swing_low_age": "Bars since the confirmed swing low occurred.",
    "bos_up": "Close broke above the last confirmed swing high plus buffer.",
    "bos_down": "Close broke below the last confirmed swing low minus buffer.",
    "choch_up": "First upward break against the prevailing structural bias.",
    "choch_down": "First downward break against the prevailing structural bias.",
    "resistance": "Nearest clustered resistance level above the close.",
    "support": "Nearest clustered support level below the close.",
    "trend": "+1 higher-high/higher-low, -1 lower-high/lower-low, 0 mixed.",
    "compression": "Percentile rank of Bollinger bandwidth; low = compressed.",
}


def structure_values(state: StructureState) -> dict:
    """Expose the structure state as graph-addressable arrays."""
    return {
        "structure.swing_high": state.swing_high_level,
        "structure.swing_low": state.swing_low_level,
        "structure.swing_high_age": state.swing_high_age,
        "structure.swing_low_age": state.swing_low_age,
        "structure.bos_up": state.bos_up,
        "structure.bos_down": state.bos_down,
        "structure.choch_up": state.choch_up,
        "structure.choch_down": state.choch_down,
        "structure.resistance": state.resistance,
        "structure.support": state.support,
        "structure.trend": state.trend,
        "structure.compression": state.compression,
    }


def catalogue() -> list:
    return [{"key": k, "description": v} for k, v in STRUCTURE_OUTPUTS.items()]
