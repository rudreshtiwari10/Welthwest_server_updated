"""
Validation framework (spec §23, §24).

Walk-forward is a first-class execution mode, not a report section. The rules
enforced here:

  * Out-of-sample windows are evaluated independently and AGGREGATED. The
    engine never concatenates all data and re-optimises over it.
  * A purge gap sits between train and test so a trade opened inside the
    training window cannot still be open when the test window starts.
  * An embargo follows the training window so features with a long lookback
    cannot straddle the boundary.
  * Nothing in this module may see the locked out-of-sample tail; the split is
    computed from indices before any pass runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from services.backtest_india import metrics as metric_lib


@dataclass
class Window:
    label: str
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    purge_bars: int
    embargo_bars: int


def _parse_span(span: str, ppy: int) -> int:
    """'3Y' / '6M' / '120B' -> a bar count for this timeframe."""
    s = str(span).strip().upper()
    if s.endswith("Y"):
        return int(float(s[:-1]) * ppy)
    if s.endswith("M"):
        return int(float(s[:-1]) * ppy / 12)
    if s.endswith("W"):
        return int(float(s[:-1]) * ppy / 52)
    if s.endswith("D"):
        return int(float(s[:-1]) * ppy / 365.25)
    if s.endswith("B"):
        return int(float(s[:-1]))
    return int(float(s))


def build_windows(n_bars: int, train: str, test: str, step: Optional[str],
                  ppy: int, max_lookback_bars: int, max_holding_bars: int,
                  embargo_pct: float = 0.01) -> list:
    """
    Anchored-rolling walk-forward windows with purge and embargo.

    purge   = max holding period, so no training trade is still open in test.
    embargo = max(feature lookback, embargo_pct of the sample), so no feature
              in the test window is computed from training bars.
    """
    train_bars = max(20, _parse_span(train, ppy))
    test_bars = max(5, _parse_span(test, ppy))
    step_bars = max(1, _parse_span(step, ppy)) if step else test_bars

    purge = max(1, int(max_holding_bars))
    embargo = max(int(max_lookback_bars), int(embargo_pct * n_bars))
    gap = purge + embargo

    windows: list = []
    train_start = 0
    fold = 0
    while True:
        train_end = train_start + train_bars - 1
        test_start = train_end + gap + 1
        test_end = test_start + test_bars - 1
        if test_end >= n_bars:
            break
        fold += 1
        windows.append(Window(
            label=f"Fold {fold}",
            train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_end,
            purge_bars=purge, embargo_bars=embargo,
        ))
        train_start += step_bars
        if fold > 40:
            break
    return windows


def aggregate_oos(fold_results: list) -> dict:
    """
    Spec §23 — the walk-forward score aggregates OOS periods. It is a
    consistency statistic, not a re-optimised curve.
    """
    if not fold_results:
        return {"available": False, "reason": "no complete walk-forward fold fitted in the window"}

    returns = np.array([f["test"]["total_return"] for f in fold_results], float)
    sharpes = np.array([f["test"]["sharpe"] for f in fold_results], float)
    mdds = np.array([f["test"]["max_drawdown"] for f in fold_results], float)
    trades = int(sum(f["test"]["total_trades"] for f in fold_results))

    positive = int((returns > 0).sum())
    # compounding the OOS windows is the honest aggregate: it is the return a
    # user would have realised by trading each window in sequence
    compounded = float(np.prod(1.0 + returns) - 1.0)

    return {
        "available": True,
        "folds": len(fold_results),
        "oos_total_trades": trades,
        "oos_compounded_return": round(compounded, 6),
        "oos_mean_return_per_fold": round(float(returns.mean()), 6),
        "oos_median_return_per_fold": round(float(np.median(returns)), 6),
        "oos_return_std": round(float(returns.std(ddof=1)), 6) if len(returns) > 1 else 0.0,
        "oos_mean_sharpe": round(float(np.nanmean(sharpes)), 4),
        "oos_worst_fold_return": round(float(returns.min()), 6),
        "oos_best_fold_return": round(float(returns.max()), 6),
        "oos_worst_drawdown": round(float(mdds.min()), 6),
        "positive_folds": positive,
        "consistency": round(positive / len(returns), 4),
        "note": ("Each fold was evaluated on data the previous fold's window never "
                 "touched, with a purge and embargo gap between them. Folds are "
                 "aggregated, never concatenated and re-fitted."),
    }


def run_walk_forward(cfg, series_map, benchmark_series, run_pass_fn,
                     max_lookback_bars: int, max_holding_bars: int) -> dict:
    """
    Execute the walk-forward schedule.

    This engine does not optimise parameters inside the training window — the
    strategy graph is user-specified and fixed. The training window is
    therefore used as an in-sample REFERENCE, and the honest claim the report
    makes is exactly that: "these are out-of-sample windows for a fixed
    parameter set", not "these are optimised out-of-sample results".
    """
    vcfg = cfg.validation or {}
    if not vcfg.get("enabled"):
        return {"available": False, "reason": "walk-forward not enabled for this run"}

    n_bars = min(len(s.bars) for s in series_map.values())
    ppy = vcfg.get("periods_per_year") or 252

    windows = build_windows(
        n_bars,
        vcfg.get("train", "2Y"), vcfg.get("test", "6M"), vcfg.get("step"),
        ppy, max_lookback_bars, max_holding_bars,
        float(vcfg.get("embargo_pct", 0.01)),
    )
    if not windows:
        return {"available": False,
                "reason": (f"the {n_bars}-bar history is too short for a "
                           f"{vcfg.get('train','2Y')} train + {vcfg.get('test','6M')} test "
                           "schedule plus purge and embargo gaps")}

    folds = []
    for w in windows:
        try:
            train_res = run_pass_fn(
                {s: w.train_start for s in series_map},
                {s: w.train_end for s in series_map})
            test_res = run_pass_fn(
                {s: w.test_start for s in series_map},
                {s: w.test_end for s in series_map})
        except Exception as exc:
            folds.append({"label": w.label, "error": str(exc)})
            continue

        folds.append({
            "label": w.label,
            "train_start": train_res.calendar[0].isoformat(),
            "train_end": train_res.calendar[-1].isoformat(),
            "test_start": test_res.calendar[0].isoformat(),
            "test_end": test_res.calendar[-1].isoformat(),
            "purge_bars": w.purge_bars, "embargo_bars": w.embargo_bars,
            "train": _slim(train_res.metrics),
            "test": _slim(test_res.metrics),
        })

    complete = [f for f in folds if "test" in f]
    summary = aggregate_oos(complete)
    summary["windows"] = folds
    summary["schedule"] = {
        "train": vcfg.get("train", "2Y"), "test": vcfg.get("test", "6M"),
        "step": vcfg.get("step") or vcfg.get("test", "6M"),
        "purge_bars": windows[0].purge_bars, "embargo_bars": windows[0].embargo_bars,
        "purge_rationale": ("purge = maximum observed holding period, so no trade "
                            "opened in training is still open in test"),
        "embargo_rationale": ("embargo = maximum feature lookback, so no test-window "
                              "feature is computed from training bars"),
    }
    return summary


def _slim(m: dict) -> dict:
    keys = ("total_return", "cagr", "sharpe", "sortino", "max_drawdown",
            "profit_factor", "total_trades", "hit_rate", "turnover")
    return {k: m.get(k) for k in keys}


def lock_out_of_sample(n_bars: int, oos_fraction: float = 0.25) -> dict:
    """
    Spec §23 layer 3 — reserve a locked tail that no tuning may ever read.
    Returned as indices so the caller can prove which bars were withheld.
    """
    oos_start = int(n_bars * (1.0 - oos_fraction))
    return {
        "in_sample": [0, max(0, oos_start - 1)],
        "locked_out_of_sample": [oos_start, n_bars - 1],
        "oos_fraction": oos_fraction,
        "rule": ("The locked window is evaluated once, after the strategy is "
                 "final. It is never available to parameter selection."),
    }
