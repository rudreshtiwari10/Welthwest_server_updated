"""
Parameter robustness and the realism stress matrix (spec §26, §37).

Two questions this module exists to answer:

  1. Is the result a broad plateau or a narrow spike? A spike is fragile no
     matter how profitable it looks.
  2. Does the result survive worse costs, worse slippage, more latency, less
     liquidity and a few missed signals?

Both are scored against the BASE run, and both can legitimately conclude that
a strategy fails.
"""

from __future__ import annotations

import copy
from typing import Callable, Optional

import numpy as np

from services.backtest_india.costs import get_cost_schedule, scale_schedule
from services.backtest_india.execution import ExecutionModel


SCORE_KEY = "sharpe"


def _score(metrics: dict) -> float:
    """Risk-adjusted return is the ranking score — never net profit alone."""
    v = metrics.get(SCORE_KEY)
    return float(v) if v is not None and np.isfinite(v) else -99.0


def perturb_numeric(value, pct: float):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        # abs() must wrap the whole product: a -30% step is 6 bars, not 1
        step = max(1, int(round(abs(value * pct))))
        return max(1, value + (step if pct > 0 else -step))
    if isinstance(value, float):
        return round(value * (1.0 + pct), 6)
    return value


def enumerate_neighbourhood(strategy: dict, deltas=(-0.30, -0.20, -0.10, 0.10, 0.20, 0.30),
                            max_variants: int = 18) -> list:
    """
    Build the neighbourhood N(theta*) by perturbing each numeric feature
    parameter independently. Integer periods also move to adjacent values.
    """
    variants: list = []
    features = strategy.get("features") or []
    for fi, feat in enumerate(features):
        for pname, pval in feat.items():
            if pname in ("id", "type", "source") or isinstance(pval, (str, bool, list, dict)):
                continue
            if not isinstance(pval, (int, float)):
                continue
            for d in deltas:
                new_val = perturb_numeric(pval, d)
                if new_val == pval:
                    continue
                variant = copy.deepcopy(strategy)
                variant["features"][fi][pname] = new_val
                variants.append({
                    "label": f"{feat.get('id', feat.get('type'))}.{pname} {d:+.0%}",
                    "parameter": f"{feat.get('id')}.{pname}",
                    "base_value": pval, "value": new_val, "delta": d,
                    "strategy": variant,
                })
                if len(variants) >= max_variants:
                    return variants
    return variants


def parameter_robustness(base_metrics: dict, strategy: dict,
                         run_variant: Callable, max_variants: int = 18) -> dict:
    """
    Spec §26 — stability = median(score(N)) / max(score(N)), plus the IQR and
    the worst neighbour. A narrow high-profit spike is labelled fragile.
    """
    variants = enumerate_neighbourhood(strategy, max_variants=max_variants)
    if not variants:
        return {"available": False,
                "reason": "the strategy has no numeric parameters to perturb"}

    base_score = _score(base_metrics)
    rows = [{
        "label": "base", "parameter": "-", "value": "-", "delta": 0.0,
        "score": round(base_score, 4),
        "total_return": base_metrics.get("total_return"),
        "max_drawdown": base_metrics.get("max_drawdown"),
        "total_trades": base_metrics.get("total_trades"),
    }]

    scores = [base_score]
    for v in variants:
        try:
            m = run_variant(v["strategy"])
        except Exception as exc:
            rows.append({"label": v["label"], "parameter": v["parameter"],
                         "value": v["value"], "delta": v["delta"],
                         "score": None, "error": str(exc)})
            continue
        s = _score(m)
        scores.append(s)
        rows.append({
            "label": v["label"], "parameter": v["parameter"],
            "value": v["value"], "delta": v["delta"],
            "score": round(s, 4),
            "total_return": m.get("total_return"),
            "max_drawdown": m.get("max_drawdown"),
            "total_trades": m.get("total_trades"),
        })

    arr = np.array([s for s in scores if s is not None and s > -99], float)
    if len(arr) < 2:
        return {"available": False, "reason": "no neighbour completed successfully"}

    best = float(arr.max())
    worst = float(arr.min())
    median = float(np.median(arr))
    q75, q25 = np.percentile(arr, [75, 25])

    if best <= 0:
        # The whole neighbourhood fails. That is NOT fragility — it is a
        # consistent negative result, and saying "fragile" here would be wrong.
        stability = 0.0
        verdict = "uniformly_negative"
        verdict_text = ("Every neighbouring parameter set is also unprofitable. The "
                        "failure is not an artefact of the specific parameters — the "
                        "whole region does not work on this data.")
    else:
        stability = float(np.clip(median / best, 0.0, 1.0))
        if stability >= 0.70 and worst > 0:
            verdict = "plateau"
            verdict_text = ("Neighbouring parameter sets score similarly and none turns "
                            "negative. This looks like a plateau rather than a lucky point.")
        elif stability >= 0.40:
            verdict = "mixed"
            verdict_text = ("Performance degrades noticeably away from the chosen "
                            "parameters. Treat the exact values as a fitted choice.")
        else:
            verdict = "fragile"
            verdict_text = ("The result collapses under small parameter changes. This is "
                            "the signature of a fitted spike, not a robust edge.")

    return {
        "available": True,
        "score_metric": SCORE_KEY,
        "base_score": round(base_score, 4),
        "median_score": round(median, 4),
        "best_score": round(best, 4),
        "worst_score": round(worst, 4),
        "interquartile_range": round(float(q75 - q25), 4),
        "stability": round(float(stability), 4),
        "verdict": verdict,
        "verdict_text": verdict_text,
        "variants_tested": len(rows) - 1,
        "rows": rows,
    }


def stress_matrix(cfg, run_stress: Callable) -> dict:
    """
    Spec §37 — the realism stress matrix. Each row changes exactly ONE thing
    relative to base, which is what makes the deltas interpretable.
    """
    base_schedule = get_cost_schedule(cfg.cost_schedule)
    base_exec = ExecutionModel.from_dict(cfg.execution)

    scenarios = [
        {"key": "base", "label": "Base (selected costs and slippage)",
         "kwargs": {}},
        {"key": "cost_1_5x", "label": "Costs 1.5x",
         "kwargs": {"cost_override": scale_schedule(base_schedule, 1.5)}},
        {"key": "cost_2x", "label": "Costs 2x",
         "kwargs": {"cost_override": scale_schedule(base_schedule, 2.0)}},
        {"key": "slip_1_5x", "label": "Slippage 1.5x",
         "kwargs": {"exec_override": _scaled_exec(base_exec, slip=1.5)}},
        {"key": "slip_2x", "label": "Slippage 2x",
         "kwargs": {"exec_override": _scaled_exec(base_exec, slip=2.0)}},
        {"key": "latency_plus_1", "label": "Execution delayed by 1 extra bar",
         "kwargs": {"extra_latency_bars": 1}},
        {"key": "latency_plus_5", "label": "Execution delayed by 5 extra bars",
         "kwargs": {"extra_latency_bars": 5}},
        {"key": "liquidity_half", "label": "Allowed participation halved",
         "kwargs": {"exec_override": _scaled_exec(base_exec, participation=0.5)}},
        {"key": "signal_skip_10", "label": "10% of signals randomly missed",
         "kwargs": {"signal_skip_pct": 0.10, "seed_offset": 7}},
        {"key": "signal_skip_25", "label": "25% of signals randomly missed",
         "kwargs": {"signal_skip_pct": 0.25, "seed_offset": 11}},
    ]

    rows, base_row = [], None
    for sc in scenarios:
        try:
            m = run_stress(**sc["kwargs"])
        except Exception as exc:
            rows.append({"key": sc["key"], "label": sc["label"], "error": str(exc)})
            continue
        row = {
            "key": sc["key"], "label": sc["label"],
            "total_return": m.get("total_return"),
            "cagr": m.get("cagr"),
            "sharpe": m.get("sharpe"),
            "max_drawdown": m.get("max_drawdown"),
            "profit_factor": m.get("profit_factor"),
            "total_trades": m.get("total_trades"),
            "net_profit": m.get("net_profit"),
        }
        if sc["key"] == "base":
            base_row = row
        rows.append(row)

    if base_row:
        base_ret = base_row.get("total_return") or 0.0
        for row in rows:
            if "error" in row or row.get("total_return") is None:
                continue
            row["return_delta"] = round(row["total_return"] - base_ret, 6)
            row["survives"] = row["total_return"] > 0

    survived = sum(1 for r in rows if r.get("survives"))
    testable = sum(1 for r in rows if "survives" in r)

    return {
        "available": bool(rows),
        "rows": rows,
        "survival_rate": round(survived / testable, 4) if testable else None,
        "scenarios_survived": survived,
        "scenarios_tested": testable,
        "note": ("Each scenario changes exactly one assumption relative to base. "
                 "A strategy that only clears zero under the base assumption has "
                 "no margin for the real world."),
    }


def _scaled_exec(base: ExecutionModel, slip: float = 1.0,
                 participation: float = 1.0) -> ExecutionModel:
    """Copy the execution model with one dimension scaled."""
    m = ExecutionModel(**{k: getattr(base, k) for k in base.__dataclass_fields__})
    m.slippage_bps = base.slippage_bps * slip
    m.synthetic_spread_bps = base.synthetic_spread_bps * slip
    m.liquidity_coeff = base.liquidity_coeff * slip
    m.participation_rate = base.participation_rate * participation
    return m


def cost_sensitivity(rows: list) -> dict:
    """Pull the cost ladder out of the stress matrix for the headline panel."""
    keys = {"base": "1.0x", "cost_1_5x": "1.5x", "cost_2x": "2.0x"}
    out = []
    for r in rows:
        if r.get("key") in keys and "error" not in r:
            out.append({"multiple": keys[r["key"]],
                        "total_return": r.get("total_return"),
                        "sharpe": r.get("sharpe"),
                        "net_profit": r.get("net_profit")})
    return {"available": len(out) > 1, "ladder": out}
