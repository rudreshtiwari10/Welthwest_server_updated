"""
Typed Strategy Graph / DSL (spec §6).

A strategy is a DAG, not a flat "strategy type". The graph is compiled once per
instrument into vectorised boolean arrays, which is safe because every operator
here is causal: the value at index i depends only on indices <= i.

Graph shape
-----------
{
  "features":       [{"id":"ema20","type":"EMA","period":20}, ...],
  "candles":        [{"id":"bull_eng","type":"ENGULFING_BULL"}, ...],
  "chart_patterns": [{"id":"dbot","type":"DOUBLE_BOTTOM"}, ...],
  "structure":      {"pivot_k":3, "bos_buffer_atr":0.1, ...},
  "conditions":     [{"id":"trend","op":">","left":"ema20","right":"ema50"}, ...],
  "entry_long":     {"op":"AND","args":["trend","pullback","bull_eng"]},
  "exit_long":      {"op":"OR","args":["trend_break"]},
  "entry_short":    null,
  "exit_short":     null
}

Operand resolution order for a reference string:
  1. a compiled condition id
  2. a feature output ("ema20", "macd1.signal")
  3. a candle id / chart-pattern id
  4. a structure output ("structure.trend")
  5. a raw price series ("close", "high", "low", "open", "volume")
  6. a numeric literal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd


COMPARATORS = {">", ">=", "<", "<=", "==", "!=",
               "CROSS_ABOVE", "CROSS_BELOW", "IN_RANGE", "OUT_OF_RANGE",
               "PERCENTILE_ABOVE", "PERCENTILE_BELOW", "IS_TRUE", "IS_FALSE",
               "RISING", "FALLING", "SLOPE_ABOVE", "SLOPE_BELOW"}

LOGIC_OPS = {"AND", "OR", "NOT", "XOR"}

TEMPORAL_OPS = {"WITHIN_LAST", "FOR_AT_LEAST", "COOLDOWN", "BARS_SINCE_LT",
                "ONCE_PER_SESSION", "HIGHEST", "LOWEST"}


class GraphError(Exception):
    pass


@dataclass
class CompiledGraph:
    """Boolean entry/exit streams plus everything needed to explain them."""
    entry_long: np.ndarray
    exit_long: np.ndarray
    entry_short: np.ndarray
    exit_short: np.ndarray
    conditions: dict = field(default_factory=dict)   # id -> bool array
    values: dict = field(default_factory=dict)       # id -> numeric array
    warmup: int = 0
    errors: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)       # id -> human description


# ── Operand resolution ──────────────────────────────────────────────────────

def _as_array(x, n: int) -> np.ndarray:
    if isinstance(x, np.ndarray):
        return x
    return np.full(n, float(x))


def resolve(operand: Any, scope: dict, n: int) -> np.ndarray:
    """Turn a reference or literal into a float array of length n."""
    if operand is None:
        raise GraphError("Missing operand")
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        return np.full(n, float(operand))
    if isinstance(operand, bool):
        return np.full(n, 1.0 if operand else 0.0)
    if isinstance(operand, np.ndarray):
        return operand.astype(float)
    key = str(operand)
    if key in scope:
        arr = scope[key]
        return arr.astype(float) if arr.dtype == bool else arr
    # numeric literal typed as a string
    try:
        return np.full(n, float(key))
    except ValueError:
        raise GraphError(
            f"Unknown reference '{key}'. Define it as a feature/condition id, "
            f"or use one of: close, open, high, low, volume."
        )


def _bool(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == bool:
        return arr
    return np.nan_to_num(arr, nan=0.0) != 0.0


# ── Comparators ─────────────────────────────────────────────────────────────

def _cross_above(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    pa, pb = np.roll(a, 1), np.roll(b, 1)
    pa[0], pb[0] = np.nan, np.nan
    out = (a > b) & (pa <= pb)
    return np.nan_to_num(out.astype(float), nan=0.0).astype(bool)


def _cross_below(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    pa, pb = np.roll(a, 1), np.roll(b, 1)
    pa[0], pb[0] = np.nan, np.nan
    out = (a < b) & (pa >= pb)
    return np.nan_to_num(out.astype(float), nan=0.0).astype(bool)


def _rising(a: np.ndarray, n: int) -> np.ndarray:
    """Strictly increasing over the last n steps."""
    ok = np.ones(len(a), dtype=bool)
    for k in range(1, n + 1):
        prev = np.roll(a, k); prev[:k] = np.nan
        step = np.roll(a, k - 1); step[:max(0, k - 1)] = np.nan
        ok &= np.nan_to_num((step > prev).astype(float), nan=0.0).astype(bool)
    ok[:n] = False
    return ok


def _falling(a: np.ndarray, n: int) -> np.ndarray:
    ok = np.ones(len(a), dtype=bool)
    for k in range(1, n + 1):
        prev = np.roll(a, k); prev[:k] = np.nan
        step = np.roll(a, k - 1); step[:max(0, k - 1)] = np.nan
        ok &= np.nan_to_num((step < prev).astype(float), nan=0.0).astype(bool)
    ok[:n] = False
    return ok


def evaluate_condition(cond: dict, scope: dict, n: int) -> np.ndarray:
    op = str(cond.get("op", "")).upper()
    if op not in COMPARATORS:
        raise GraphError(f"Unsupported comparator '{op}'")

    left = resolve(cond.get("left"), scope, n)

    if op == "IS_TRUE":
        return _bool(left)
    if op == "IS_FALSE":
        return ~_bool(left)
    if op == "RISING":
        return _rising(left, int(cond.get("bars", 1)))
    if op == "FALLING":
        return _falling(left, int(cond.get("bars", 1)))

    if op in ("IN_RANGE", "OUT_OF_RANGE"):
        lo = resolve(cond.get("low", cond.get("min")), scope, n)
        hi = resolve(cond.get("high", cond.get("max")), scope, n)
        inside = (left >= lo) & (left <= hi)
        res = inside if op == "IN_RANGE" else ~inside
        return np.nan_to_num(res.astype(float), nan=0.0).astype(bool)

    if op in ("PERCENTILE_ABOVE", "PERCENTILE_BELOW"):
        window = int(cond.get("window", 100))
        thresh = float(cond.get("percentile", 80))
        s = pd.Series(left)
        rank = s.rolling(window).apply(
            lambda w: 100.0 * float((w[:-1] <= w[-1]).sum()) / max(1, len(w) - 1), raw=True
        ).to_numpy()
        res = rank >= thresh if op == "PERCENTILE_ABOVE" else rank <= thresh
        return np.nan_to_num(res.astype(float), nan=0.0).astype(bool)

    if op in ("SLOPE_ABOVE", "SLOPE_BELOW"):
        bars = int(cond.get("bars", 5))
        prev = np.roll(left, bars); prev[:bars] = np.nan
        slope = (left - prev) / bars
        thr = float(cond.get("right", 0.0))
        res = slope > thr if op == "SLOPE_ABOVE" else slope < thr
        return np.nan_to_num(res.astype(float), nan=0.0).astype(bool)

    right = resolve(cond.get("right"), scope, n)
    if op == "CROSS_ABOVE":
        return _cross_above(left, right)
    if op == "CROSS_BELOW":
        return _cross_below(left, right)

    ops = {">": np.greater, ">=": np.greater_equal, "<": np.less,
           "<=": np.less_equal, "==": np.equal, "!=": np.not_equal}
    with np.errstate(invalid="ignore"):
        res = ops[op](left, right)
    return np.nan_to_num(res.astype(float), nan=0.0).astype(bool)


# ── Expression tree ─────────────────────────────────────────────────────────

def evaluate_expr(expr: Any, scope: dict, n: int, timestamps: Optional[list] = None) -> np.ndarray:
    """Recursively evaluate a logic/temporal expression into a boolean array."""
    if expr is None:
        return np.zeros(n, dtype=bool)
    if isinstance(expr, bool):
        return np.full(n, expr)
    if isinstance(expr, str):
        return _bool(resolve(expr, scope, n))
    if isinstance(expr, list):
        return evaluate_expr({"op": "AND", "args": expr}, scope, n, timestamps)
    if not isinstance(expr, dict):
        raise GraphError(f"Cannot evaluate expression of type {type(expr).__name__}")

    op = str(expr.get("op", "")).upper()
    args = expr.get("args", [])

    if op in LOGIC_OPS:
        if not args:
            return np.zeros(n, dtype=bool)
        parts = [evaluate_expr(a, scope, n, timestamps) for a in args]
        if op == "NOT":
            return ~parts[0]
        out = parts[0].copy()
        for p in parts[1:]:
            if op == "AND":
                out &= p
            elif op == "OR":
                out |= p
            elif op == "XOR":
                out ^= p
        return out

    if op in TEMPORAL_OPS:
        inner = evaluate_expr(args[0] if args else expr.get("arg"), scope, n, timestamps)
        bars = int(expr.get("bars", expr.get("n", 1)))

        if op == "WITHIN_LAST":
            # true if the inner condition held on any of the last `bars` bars
            return pd.Series(inner.astype(float)).rolling(
                bars, min_periods=1).max().to_numpy().astype(bool)

        if op == "FOR_AT_LEAST":
            return (pd.Series(inner.astype(float)).rolling(bars).sum()
                    .to_numpy() >= bars)

        if op == "COOLDOWN":
            # suppress re-triggers for `bars` bars after each trigger
            out = np.zeros(n, dtype=bool)
            block_until = -1
            for i in range(n):
                if inner[i] and i > block_until:
                    out[i] = True
                    block_until = i + bars
            return out

        if op == "BARS_SINCE_LT":
            since = np.full(n, np.inf)
            last = None
            for i in range(n):
                if inner[i]:
                    last = i
                since[i] = (i - last) if last is not None else np.inf
            return since < bars

        if op == "ONCE_PER_SESSION":
            if not timestamps:
                return inner
            out = np.zeros(n, dtype=bool)
            seen = set()
            for i in range(n):
                day = timestamps[i].date()
                if inner[i] and day not in seen:
                    out[i] = True
                    seen.add(day)
            return out

        if op in ("HIGHEST", "LOWEST"):
            series = resolve(expr.get("of", "close"), scope, n)
            roll = pd.Series(series).rolling(bars)
            ref = (roll.max() if op == "HIGHEST" else roll.min()).to_numpy()
            res = (series >= ref) if op == "HIGHEST" else (series <= ref)
            return np.nan_to_num(res.astype(float), nan=0.0).astype(bool)

    raise GraphError(f"Unsupported operator '{op}'")


# ── Compilation ─────────────────────────────────────────────────────────────

def compile_graph(df: pd.DataFrame, strategy: dict, scope_extra: dict,
                  timestamps: Optional[list] = None,
                  base_warmup: int = 0) -> CompiledGraph:
    """
    Build the entry/exit streams for one instrument.

    `scope_extra` already contains feature arrays, candle masks, chart-pattern
    masks and structure outputs. This function only adds conditions and the
    logic/temporal layer on top.
    """
    n = len(df)
    scope: dict = dict(scope_extra)
    errors: list = []
    conditions: dict = {}
    labels: dict = {}

    for cond in strategy.get("conditions", []) or []:
        cid = cond.get("id")
        if not cid:
            errors.append("A condition is missing its 'id'")
            continue
        try:
            arr = evaluate_condition(cond, scope, n)
        except GraphError as exc:
            errors.append(f"Condition '{cid}': {exc}")
            arr = np.zeros(n, dtype=bool)
        except Exception as exc:
            errors.append(f"Condition '{cid}' failed: {exc}")
            arr = np.zeros(n, dtype=bool)
        conditions[cid] = arr
        scope[cid] = arr
        labels[cid] = _describe_condition(cond)

    def _stream(key: str) -> np.ndarray:
        expr = strategy.get(key)
        if expr is None:
            return np.zeros(n, dtype=bool)
        try:
            return evaluate_expr(expr, scope, n, timestamps)
        except Exception as exc:
            errors.append(f"'{key}' expression failed: {exc}")
            return np.zeros(n, dtype=bool)

    entry_long = _stream("entry_long")
    exit_long = _stream("exit_long")
    entry_short = _stream("entry_short")
    exit_short = _stream("exit_short")

    # Nothing may fire before every referenced feature is mathematically
    # defined. This is enforced here rather than trusted to the strategy.
    warmup = int(base_warmup)
    if warmup > 0:
        cut = min(warmup, n)
        entry_long[:cut] = False
        entry_short[:cut] = False
        exit_long[:cut] = False
        exit_short[:cut] = False

    return CompiledGraph(
        entry_long=entry_long, exit_long=exit_long,
        entry_short=entry_short, exit_short=exit_short,
        conditions=conditions, values=scope, warmup=warmup,
        errors=errors, labels=labels,
    )


def _describe_condition(cond: dict) -> str:
    op = str(cond.get("op", "")).upper()
    left = cond.get("left")
    right = cond.get("right")
    if op == "IS_TRUE":
        return f"{left} fires"
    if op == "IS_FALSE":
        return f"{left} does not fire"
    if op in ("RISING", "FALLING"):
        return f"{left} {op.lower()} for {cond.get('bars', 1)} bars"
    if op == "IN_RANGE":
        return f"{left} between {cond.get('low')} and {cond.get('high')}"
    if op in ("PERCENTILE_ABOVE", "PERCENTILE_BELOW"):
        side = "above" if op.endswith("ABOVE") else "below"
        return f"{left} {side} its {cond.get('percentile', 80)}th percentile"
    if op == "CROSS_ABOVE":
        return f"{left} crosses above {right}"
    if op == "CROSS_BELOW":
        return f"{left} crosses below {right}"
    return f"{left} {op} {right}"


def validate_graph(strategy: dict) -> list:
    """Static checks run before any data is fetched, so the user gets fast,
    specific feedback instead of an empty result."""
    problems: list = []
    if not isinstance(strategy, dict):
        return ["Strategy must be an object."]

    ids: set = set()
    for group in ("features", "candles", "chart_patterns"):
        for item in strategy.get(group, []) or []:
            i = item.get("id")
            if not i:
                problems.append(f"An item in '{group}' has no 'id'.")
            elif i in ids:
                problems.append(f"Duplicate id '{i}'.")
            else:
                ids.add(i)

    for cond in strategy.get("conditions", []) or []:
        cid = cond.get("id")
        if not cid:
            problems.append("A condition has no 'id'.")
        elif cid in ids:
            problems.append(f"Duplicate id '{cid}'.")
        else:
            ids.add(cid)
        op = str(cond.get("op", "")).upper()
        if op not in COMPARATORS:
            problems.append(f"Condition '{cid}' uses unsupported operator '{op}'.")

    if not strategy.get("entry_long") and not strategy.get("entry_short"):
        problems.append("The strategy defines no entry rule "
                        "(need 'entry_long' and/or 'entry_short').")
    return problems


def operator_catalogue() -> dict:
    return {
        "comparators": sorted(COMPARATORS),
        "logic": sorted(LOGIC_OPS),
        "temporal": sorted(TEMPORAL_OPS),
    }
