"""
Risk and statistical diagnostics (spec §22).

Everything here is labelled honestly. A Monte Carlo drawdown distribution is
hypothetical and says so. A bootstrap interval describes the sample we have,
not the future. The purpose of this module is to make a headline number harder
to believe, not easier.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.backtest_india import metrics as metric_lib


def block_bootstrap_returns(r: np.ndarray, n_iter: int, block: int,
                            rng: np.random.Generator) -> np.ndarray:
    """
    Circular block bootstrap — preferred over IID resampling because strategy
    returns are serially dependent and IID sampling would understate the tails.
    """
    n = len(r)
    if n < block * 2:
        block = max(1, n // 4)
    n_blocks = int(np.ceil(n / block))
    out = np.empty((n_iter, n_blocks * block))
    for it in range(n_iter):
        starts = rng.integers(0, n, size=n_blocks)
        chunks = [np.take(r, np.arange(s, s + block) % n) for s in starts]
        out[it] = np.concatenate(chunks)
    return out[:, :n]


def bootstrap_confidence(equity: np.ndarray, ppy: int, n_iter: int = 500,
                         block: int = 10, seed: int = 42) -> dict:
    """Confidence bands for CAGR / Sharpe / max drawdown from resampled returns."""
    r = metric_lib.returns_from_equity(equity)
    if len(r) < 30:
        return {"available": False,
                "reason": "fewer than 30 return observations — a bootstrap would be noise"}

    rng = np.random.default_rng(seed)
    paths = block_bootstrap_returns(r, n_iter, block, rng)
    start = float(equity[0])

    cagrs, sharpes, mdds = [], [], []
    years = len(r) / ppy
    for row in paths:
        curve = start * np.cumprod(1.0 + row)
        if curve[-1] <= 0 or years <= 0:
            continue
        cagrs.append((curve[-1] / start) ** (1.0 / years) - 1.0)
        sd = np.std(row, ddof=1)
        sharpes.append(float(np.mean(row) / sd * np.sqrt(ppy)) if sd > 0 else 0.0)
        mdds.append(metric_lib.max_drawdown(curve))

    def band(v, name):
        a = np.array(v, float)
        return {
            "metric": name,
            "median": round(float(np.median(a)), 6),
            "p05": round(float(np.percentile(a, 5)), 6),
            "p25": round(float(np.percentile(a, 25)), 6),
            "p75": round(float(np.percentile(a, 75)), 6),
            "p95": round(float(np.percentile(a, 95)), 6),
        }

    return {
        "available": True, "iterations": n_iter, "block_size": block,
        "method": "circular block bootstrap of realised bar returns",
        "bands": [band(cagrs, "cagr"), band(sharpes, "sharpe"), band(mdds, "max_drawdown")],
        "note": ("Describes the dispersion of the SAMPLE this backtest produced. "
                 "It is not a forecast and does not account for the strategy "
                 "having been selected after seeing this data."),
    }


def monte_carlo_trade_order(trades: list, initial_capital: float,
                            n_iter: int = 1000, seed: int = 42) -> dict:
    """
    Reshuffle the realised trade sequence to see how much of the drawdown was
    luck of ordering. Explicitly hypothetical (spec §22).
    """
    if len(trades) < 5:
        return {"available": False, "reason": "need at least 5 closed trades"}

    pnl = np.array([t.net_pnl for t in trades], float)
    rng = np.random.default_rng(seed)
    finals, mdds = [], []
    for _ in range(n_iter):
        shuffled = rng.permutation(pnl)
        curve = initial_capital + np.cumsum(shuffled)
        finals.append(curve[-1])
        mdds.append(metric_lib.max_drawdown(np.concatenate([[initial_capital], curve])))

    finals = np.array(finals); mdds = np.array(mdds)
    return {
        "available": True, "iterations": n_iter,
        "label": "HYPOTHETICAL — trade order reshuffled, trade outcomes held fixed",
        "final_equity": {
            "median": round(float(np.median(finals)), 2),
            "p05": round(float(np.percentile(finals, 5)), 2),
            "p95": round(float(np.percentile(finals, 95)), 2),
        },
        "max_drawdown": {
            "median": round(float(np.median(mdds)), 6),
            "p05": round(float(np.percentile(mdds, 5)), 6),
            "worst": round(float(mdds.min()), 6),
        },
        "probability_of_loss": round(float((finals < initial_capital).mean()), 4),
        "note": ("Reordering realised trades cannot tell you whether the edge is "
                 "real. It only shows how sensitive the equity path was to the "
                 "sequence in which the same trades arrived."),
    }


def trade_concentration(trades: list) -> dict:
    """Spec §22 — how much of the result came from a handful of trades."""
    if not trades:
        return {"available": False}
    pnl = np.array([t.net_pnl for t in trades], float)
    total = float(pnl.sum())
    order = np.argsort(pnl)[::-1]

    def without_top(k):
        if len(pnl) <= k:
            return None
        keep = np.delete(pnl, order[:k])
        return round(float(keep.sum()), 2)

    top1 = float(pnl[order[0]]) if len(pnl) else 0.0
    top5 = float(pnl[order[:5]].sum()) if len(pnl) >= 5 else float(pnl.sum())
    return {
        "available": True,
        "total_net_pnl": round(total, 2),
        "best_trade_contribution_pct": round(100.0 * top1 / total, 2) if abs(total) > 1e-9 else None,
        "top5_contribution_pct": round(100.0 * top5 / total, 2) if abs(total) > 1e-9 else None,
        "net_pnl_excluding_top1": without_top(1),
        "net_pnl_excluding_top5": without_top(5),
        "net_pnl_excluding_top10": without_top(10),
        "note": ("If removing the best few trades flips the result negative, the "
                 "strategy is a small-sample bet on outliers, not a repeatable edge."),
    }


def classify_regimes(close: np.ndarray, timestamps: list, ppy: int,
                     vol_window: int = 20, trend_window: int = 50) -> dict:
    """
    Point-in-time regime classifier (spec §27). Every label at bar i uses only
    data up to bar i, and the definition is returned with the run so a result
    can never be silently re-bucketed later.
    """
    s = pd.Series(close)
    ma = s.rolling(trend_window).mean()
    lr = np.diff(np.log(np.maximum(close, 1e-9)), prepend=np.log(max(close[0], 1e-9)))
    vol = pd.Series(lr).rolling(vol_window).std(ddof=1) * np.sqrt(ppy)
    vol_median = vol.expanding(min_periods=vol_window * 2).median()

    trend = np.where(close > ma.to_numpy(), "BULL", "BEAR")
    trend = np.where(np.isnan(ma.to_numpy()), "UNDEFINED", trend)
    vol_state = np.where(vol.to_numpy() > vol_median.to_numpy(), "HIGH_VOL", "LOW_VOL")
    vol_state = np.where(np.isnan(vol_median.to_numpy()), "UNDEFINED", vol_state)

    labels = np.array([f"{t}/{v}" if t != "UNDEFINED" and v != "UNDEFINED" else "UNDEFINED"
                       for t, v in zip(trend, vol_state)])
    return {
        "labels": labels,
        "definition": {
            "trend": f"close above/below its {trend_window}-bar simple moving average",
            "volatility": (f"{vol_window}-bar annualised realised volatility versus its "
                           "own expanding median, computed point-in-time"),
        },
    }


def regime_breakdown(equity_points: list, regime_labels: np.ndarray,
                     trades: list, ppy: int) -> dict:
    """Performance conditioned on market state, with sample sizes shown."""
    if not equity_points or regime_labels is None or len(regime_labels) == 0:
        return {"available": False}

    equity = np.array([p.equity for p in equity_points], float)
    r = metric_lib.returns_from_equity(equity)
    n = min(len(r), len(regime_labels) - 1)
    if n < 20:
        return {"available": False, "reason": "not enough observations to condition on regime"}

    r = r[:n]
    labels = regime_labels[1:n + 1]

    buckets = []
    for name in sorted(set(labels)):
        mask = labels == name
        count = int(mask.sum())
        if count < 10:
            continue
        rr = r[mask]
        sd = float(np.std(rr, ddof=1))
        buckets.append({
            "regime": name, "bars": count,
            "share_of_time": round(count / n, 4),
            "mean_return_annualized": round(float(np.mean(rr)) * ppy, 6),
            "volatility_annualized": round(sd * np.sqrt(ppy), 6),
            "sharpe": round(float(np.mean(rr)) / sd * np.sqrt(ppy), 3) if sd > 0 else 0.0,
            "worst_bar": round(float(rr.min()), 6),
        })

    trade_buckets: dict = {}
    for t in trades:
        idx = min(t.exit_index, len(regime_labels) - 1)
        key = regime_labels[idx] if idx >= 0 else "UNDEFINED"
        b = trade_buckets.setdefault(key, {"trades": 0, "net_pnl": 0.0, "wins": 0})
        b["trades"] += 1
        b["net_pnl"] += t.net_pnl
        b["wins"] += 1 if t.net_pnl > 0 else 0

    return {
        "available": True,
        "by_bar": buckets,
        "by_trade": [
            {"regime": k, "trades": v["trades"], "net_pnl": round(v["net_pnl"], 2),
             "hit_rate": round(v["wins"] / v["trades"], 3)}
            for k, v in sorted(trade_buckets.items())
        ],
        "note": ("Regimes are labelled point-in-time. A strategy that only works in "
                 "one bucket has not been shown to work; it has been shown to be "
                 "conditional."),
    }


def attribution(trades: list) -> dict:
    """Long/short and per-instrument attribution (spec §22)."""
    if not trades:
        return {"available": False}

    by_dir: dict = {}
    by_sym: dict = {}
    by_exit: dict = {}
    for t in trades:
        for bucket, key in ((by_dir, t.direction), (by_sym, t.instrument),
                            (by_exit, t.exit_reason)):
            b = bucket.setdefault(key, {"trades": 0, "net_pnl": 0.0, "wins": 0})
            b["trades"] += 1
            b["net_pnl"] += t.net_pnl
            b["wins"] += 1 if t.net_pnl > 0 else 0

    def rows(d, label):
        return [
            {label: k, "trades": v["trades"], "net_pnl": round(v["net_pnl"], 2),
             "hit_rate": round(v["wins"] / v["trades"], 3)}
            for k, v in sorted(d.items(), key=lambda kv: -kv[1]["net_pnl"])
        ]

    return {
        "available": True,
        "by_direction": rows(by_dir, "direction"),
        "by_instrument": rows(by_sym, "instrument"),
        "by_exit_reason": rows(by_exit, "exit_reason"),
    }


def return_distribution(equity: np.ndarray) -> dict:
    r = metric_lib.returns_from_equity(equity)
    if len(r) < 20:
        return {"available": False}
    hist, edges = np.histogram(r, bins=30)
    return {
        "available": True,
        "skewness": round(float(pd.Series(r).skew()), 4),
        "kurtosis": round(float(pd.Series(r).kurtosis()), 4),
        "percentiles": {
            f"p{p}": round(float(np.percentile(r, p)), 6)
            for p in (1, 5, 25, 50, 75, 95, 99)
        },
        "histogram": [
            {"bin_low": round(float(edges[i]), 6),
             "bin_high": round(float(edges[i + 1]), 6),
             "count": int(hist[i])}
            for i in range(len(hist))
        ],
    }
