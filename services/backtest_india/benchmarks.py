"""
Benchmark and baseline system (spec §28).

A positive absolute return proves nothing. The question is whether the
strategy beat the alternatives a user actually had — including doing nothing,
and including a strategy that trades exactly as often but at random moments.

The random-entry and signal-shuffled controls are the important ones: they hold
trade frequency, exits, sizing and costs constant and change only WHEN the
strategy chose to act. If the real strategy cannot beat them, the timing has no
demonstrated value.
"""

from __future__ import annotations

import copy
from typing import Callable, Optional

import numpy as np

from services.backtest_india import metrics as metric_lib
from services.backtest_india.features import ema, sma


def buy_and_hold(series, initial_capital: float, schedule, ppy: int) -> dict:
    """Buy at the first executable open, hold to the end, pay costs both ways."""
    from services.backtest_india.contracts import OrderSide

    bars = series.bars
    if len(bars) < 3:
        return {"available": False}
    entry = bars[1].open
    exit_px = bars[-1].close
    qty = int(initial_capital // entry)
    if qty <= 0:
        return {"available": False, "reason": "capital too small for one share"}

    buy_cost, _ = schedule.compute(OrderSide.BUY, qty, entry)
    sell_cost, _ = schedule.compute(OrderSide.SELL, qty, exit_px)
    cash = initial_capital - qty * entry - buy_cost

    equity = np.array([cash + qty * b.close for b in bars[1:]], float)
    equity[-1] -= sell_cost
    equity = np.concatenate([[initial_capital], equity])
    days = max(1.0, (bars[-1].event_time - bars[0].event_time).total_seconds() / 86400.0)
    r = metric_lib.returns_from_equity(equity)

    return {
        "available": True,
        "label": f"Buy & hold {series.symbol}",
        "total_return": round(metric_lib.total_return(equity), 6),
        "cagr": round(metric_lib.cagr(equity, days), 6),
        "sharpe": round(metric_lib.sharpe(r, ppy), 4),
        "max_drawdown": round(metric_lib.max_drawdown(equity), 6),
        "total_costs": round(buy_cost + sell_cost, 2),
        "final_equity": round(float(equity[-1]), 2),
    }


def sma_crossover_baseline(strategy_symbols: list, fast: int = 50, slow: int = 200) -> dict:
    """A deliberately trivial strategy graph — the bar any real edge must clear."""
    return {
        "features": [
            {"id": "sma_fast", "type": "SMA", "period": fast},
            {"id": "sma_slow", "type": "SMA", "period": slow},
        ],
        "conditions": [
            {"id": "golden", "op": "CROSS_ABOVE", "left": "sma_fast", "right": "sma_slow"},
            {"id": "death", "op": "CROSS_BELOW", "left": "sma_fast", "right": "sma_slow"},
        ],
        "entry_long": "golden",
        "exit_long": "death",
    }


def momentum_baseline(period: int = 60, threshold: float = 5.0) -> dict:
    return {
        "features": [{"id": "roc", "type": "ROC", "period": period}],
        "conditions": [
            {"id": "up", "op": ">", "left": "roc", "right": threshold},
            {"id": "down", "op": "<", "left": "roc", "right": 0},
        ],
        "entry_long": "up", "exit_long": "down",
    }


def randomize_entries(strategy: dict, n_bars: int, entry_rate: float,
                      seed: int) -> dict:
    """
    Random-entry control (spec §28): identical exits, sizing and costs, but the
    entry timing is random at the strategy's own observed rate.

    Implemented as a graph rewrite so the control passes through the exact same
    engine path — no shortcut scoring.
    """
    variant = copy.deepcopy(strategy)
    variant["_random_entry"] = {"rate": float(entry_rate), "seed": int(seed)}
    return variant


def run_controls(cfg, base_metrics: dict, run_variant: Callable,
                 n_bars: int, seed: int = 42) -> dict:
    """
    Execute the baseline suite. Every control uses the same costs, execution
    model, sizing and risk rules as the live run — only the signal changes.
    """
    controls = []

    trades = base_metrics.get("total_trades", 0) or 0
    entry_rate = min(0.5, max(0.001, trades / max(1, n_bars)))

    def _add(key, label, strategy, note, **kw):
        try:
            m = run_variant(strategy, **kw)
        except Exception as exc:
            controls.append({"key": key, "label": label, "error": str(exc)})
            return
        controls.append({
            "key": key, "label": label, "note": note,
            "total_return": m.get("total_return"),
            "cagr": m.get("cagr"),
            "sharpe": m.get("sharpe"),
            "max_drawdown": m.get("max_drawdown"),
            "total_trades": m.get("total_trades"),
            "profit_factor": m.get("profit_factor"),
        })

    _add("sma_baseline", "SMA 50/200 crossover",
         sma_crossover_baseline(cfg.symbols),
         "The simplest trend rule there is. A complex strategy that cannot beat "
         "it has not justified its complexity.")

    _add("momentum_baseline", "60-bar momentum",
         momentum_baseline(),
         "Buy strength, exit weakness. A second trivial reference point.")

    for i, s in enumerate((seed, seed + 101, seed + 202)):
        _add(f"random_entry_{i+1}", f"Random entry (seed {s})",
             randomize_entries(cfg.strategy, n_bars, entry_rate, s),
             "Same exits, sizing, costs and trade frequency; entry timing random. "
             "This is the control the strategy's timing must beat.")

    random_rows = [c for c in controls
                   if c.get("key", "").startswith("random_entry") and "error" not in c]
    verdict = None
    if random_rows:
        rand_returns = [c["total_return"] for c in random_rows if c["total_return"] is not None]
        if rand_returns:
            base_ret = base_metrics.get("total_return", 0.0) or 0.0
            mean_rand = float(np.mean(rand_returns))
            beat = sum(1 for v in rand_returns if base_ret > v)
            verdict = {
                "beat_random_controls": f"{beat}/{len(rand_returns)}",
                "mean_random_return": round(mean_rand, 6),
                "strategy_return": round(base_ret, 6),
                "excess_over_random": round(base_ret - mean_rand, 6),
                "reading": (
                    "The strategy's entry timing added value over random entries "
                    "at the same frequency."
                    if base_ret > mean_rand else
                    "The strategy did NOT beat random entries at the same frequency. "
                    "Whatever produced the result, it was not the entry timing."
                ),
            }

    return {"available": bool(controls), "controls": controls, "random_entry_verdict": verdict}
