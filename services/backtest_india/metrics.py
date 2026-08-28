"""
Performance metrics with the exact definitions from spec §21.

Every function here takes primitives (an equity series, a trade list) so that
each headline number in the report is reconstructible from ledger data —
Appendix C's acceptance criterion. Nothing is carried forward from an earlier
stage as an opaque total.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


def _safe(x, default=0.0):
    return float(x) if x is not None and np.isfinite(x) else default


def returns_from_equity(equity: np.ndarray) -> np.ndarray:
    """r_t = V_t / V_{t-1} - 1, with no external cash flows in this engine."""
    e = np.asarray(equity, float)
    if len(e) < 2:
        return np.array([])
    with np.errstate(divide="ignore", invalid="ignore"):
        r = e[1:] / e[:-1] - 1.0
    return np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)


def total_return(equity: np.ndarray) -> float:
    e = np.asarray(equity, float)
    if len(e) < 2 or e[0] <= 0:
        return 0.0
    return float(e[-1] / e[0] - 1.0)


def cagr(equity: np.ndarray, days: float) -> float:
    """CAGR = (V_T/V_0)^(365.25/days) - 1."""
    e = np.asarray(equity, float)
    if len(e) < 2 or e[0] <= 0 or days <= 0 or e[-1] <= 0:
        return 0.0
    return float((e[-1] / e[0]) ** (365.25 / days) - 1.0)


def annualized_volatility(r: np.ndarray, ppy: int) -> float:
    if len(r) < 2:
        return 0.0
    return float(np.std(r, ddof=1) * math.sqrt(ppy))


def sharpe(r: np.ndarray, ppy: int, rf_annual: float = 0.0) -> float:
    """(mean(r - rf) / std(r)) * sqrt(periods_per_year)."""
    if len(r) < 2:
        return 0.0
    sd = np.std(r, ddof=1)
    if sd <= 0:
        return 0.0
    rf_per = rf_annual / ppy
    return float((np.mean(r) - rf_per) / sd * math.sqrt(ppy))


def downside_deviation(r: np.ndarray, mar_annual: float, ppy: int) -> float:
    """sqrt(mean(min(r - MAR, 0)^2)), MAR stated per period. Annualised."""
    if len(r) < 2:
        return 0.0
    mar = mar_annual / ppy
    d = np.minimum(r - mar, 0.0)
    return float(math.sqrt(float(np.mean(d ** 2))) * math.sqrt(ppy))


def sortino(r: np.ndarray, ppy: int, mar_annual: float = 0.0) -> float:
    dd = downside_deviation(r, mar_annual, ppy)
    if dd <= 0:
        return 0.0
    excess = (np.mean(r) * ppy) - mar_annual
    return float(excess / dd)


def drawdown_series(equity: np.ndarray) -> np.ndarray:
    """DD_t = V_t / max_{u<=t} V_u - 1."""
    e = np.asarray(equity, float)
    peak = np.maximum.accumulate(np.where(e > 0, e, np.nan))
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = e / peak - 1.0
    return np.nan_to_num(dd, nan=0.0)


def max_drawdown(equity: np.ndarray) -> float:
    dd = drawdown_series(equity)
    return float(dd.min()) if len(dd) else 0.0


def drawdown_durations(equity: np.ndarray) -> dict:
    """Longest and current underwater stretches, in bars."""
    dd = drawdown_series(equity)
    longest = current = 0
    for v in dd:
        if v < -1e-12:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return {"longest_bars": int(longest), "current_bars": int(current)}


def ulcer_index(equity: np.ndarray) -> float:
    """sqrt(mean(drawdown_percent^2))."""
    dd = drawdown_series(equity) * 100.0
    if not len(dd):
        return 0.0
    return float(math.sqrt(float(np.mean(dd ** 2))))


def calmar(cagr_value: float, mdd: float) -> float:
    return float(cagr_value / abs(mdd)) if mdd < -1e-12 else 0.0


def recovery_factor(net_profit: float, mdd_value: float) -> float:
    return float(net_profit / abs(mdd_value)) if abs(mdd_value) > 1e-9 else 0.0


def var_es(r: np.ndarray, confidence: float = 0.95) -> tuple[float, float]:
    """Historical VaR and Expected Shortfall at the stated confidence."""
    if len(r) < 10:
        return 0.0, 0.0
    q = float(np.percentile(r, (1 - confidence) * 100))
    tail = r[r <= q]
    es = float(np.mean(tail)) if len(tail) else q
    return q, es


def trade_stats(trades: list) -> dict:
    """Everything computed from closed round trips."""
    if not trades:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "hit_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0,
            "payoff_ratio": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0,
            "avg_holding_bars": 0.0, "median_holding_bars": 0.0,
            "max_consecutive_wins": 0, "max_consecutive_losses": 0,
            "avg_mae": 0.0, "avg_mfe": 0.0, "avg_r_multiple": None,
            "total_costs": 0.0, "cost_pct_of_gross_pnl": None,
        }

    pnl = np.array([t.net_pnl for t in trades], float)
    gross = np.array([t.gross_pnl for t in trades], float)
    costs = np.array([t.costs for t in trades], float)
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    holds = np.array([t.bars_held for t in trades], float)

    streak_w = streak_l = best_w = best_l = 0
    for p in pnl:
        if p > 0:
            streak_w += 1; streak_l = 0
        else:
            streak_l += 1; streak_w = 0
        best_w = max(best_w, streak_w)
        best_l = max(best_l, streak_l)

    gp, gl = float(wins.sum()), float(abs(losses.sum()))
    hit = len(wins) / len(pnl)
    avg_w = float(wins.mean()) if len(wins) else 0.0
    avg_l = float(abs(losses.mean())) if len(losses) else 0.0
    r_mults = [t.r_multiple for t in trades if t.r_multiple is not None]
    total_gross = float(gross.sum())

    return {
        "total_trades": len(trades),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "hit_rate": round(hit, 4),
        "profit_factor": round(gp / gl, 4) if gl > 1e-9 else (float("inf") if gp > 0 else 0.0),
        "expectancy": round(hit * avg_w - (1 - hit) * avg_l, 2),
        "payoff_ratio": round(avg_w / avg_l, 4) if avg_l > 1e-9 else 0.0,
        "avg_win": round(avg_w, 2), "avg_loss": round(avg_l, 2),
        "best_trade": round(float(pnl.max()), 2),
        "worst_trade": round(float(pnl.min()), 2),
        "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
        "avg_holding_bars": round(float(holds.mean()), 2),
        "median_holding_bars": round(float(np.median(holds)), 2),
        "max_consecutive_wins": int(best_w),
        "max_consecutive_losses": int(best_l),
        "avg_mae": round(float(np.mean([t.mae for t in trades])), 4),
        "avg_mfe": round(float(np.mean([t.mfe for t in trades])), 4),
        "avg_r_multiple": round(float(np.mean(r_mults)), 3) if r_mults else None,
        "total_costs": round(float(costs.sum()), 2),
        "cost_pct_of_gross_pnl": (round(100.0 * float(costs.sum()) / abs(total_gross), 2)
                                  if abs(total_gross) > 1e-9 else None),
    }


def benchmark_regression(r: np.ndarray, rb: np.ndarray, ppy: int) -> dict:
    """Alpha/beta from an OLS regression of strategy on benchmark returns."""
    n = min(len(r), len(rb))
    if n < 20:
        return {"beta": None, "alpha_annual": None, "correlation": None, "r2": None}
    a, b = np.asarray(r[-n:], float), np.asarray(rb[-n:], float)
    var_b = float(np.var(b, ddof=1))
    if var_b <= 0:
        return {"beta": None, "alpha_annual": None, "correlation": None, "r2": None}
    beta = float(np.cov(a, b, ddof=1)[0, 1] / var_b)
    alpha_per = float(np.mean(a) - beta * np.mean(b))
    corr = float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else 0.0
    return {
        "beta": round(beta, 4),
        "alpha_annual": round(alpha_per * ppy, 6),
        "correlation": round(corr, 4),
        "r2": round(corr ** 2, 4),
    }


def rolling_metrics(equity: np.ndarray, timestamps: list, ppy: int,
                    window: int = 63) -> list:
    """Rolling Sharpe and drawdown for the diagnostics panel."""
    r = returns_from_equity(equity)
    if len(r) < window:
        return []
    s = pd.Series(r)
    roll_sharpe = (s.rolling(window).mean() / s.rolling(window).std(ddof=1)
                   * math.sqrt(ppy))
    dd = drawdown_series(equity)
    out = []
    for i in range(window, len(r) + 1):
        v = roll_sharpe.iloc[i - 1]
        out.append({
            "timestamp": timestamps[i].isoformat() if i < len(timestamps) else None,
            "rolling_sharpe": round(float(v), 3) if np.isfinite(v) else None,
            "drawdown": round(float(dd[i]), 4) if i < len(dd) else None,
        })
    return out[::max(1, len(out) // 260)]     # thin for transport


def monthly_returns(equity: np.ndarray, timestamps: list) -> list:
    """Calendar month returns for the heatmap."""
    if len(equity) < 2:
        return []
    s = pd.Series(equity, index=pd.DatetimeIndex(timestamps))
    m = s.resample("ME").last().dropna()
    if len(m) < 2:
        return []
    first = pd.Series([s.iloc[0]], index=[m.index[0] - pd.offsets.MonthEnd(1)])
    m = pd.concat([first, m])
    rets = m.pct_change().dropna()
    return [
        {"year": int(idx.year), "month": int(idx.month),
         "return": round(float(v), 6)}
        for idx, v in rets.items()
    ]


def yearly_returns(equity: np.ndarray, timestamps: list) -> list:
    if len(equity) < 2:
        return []
    s = pd.Series(equity, index=pd.DatetimeIndex(timestamps))
    y = s.resample("YE").last().dropna()
    if len(y) < 1:
        return []
    first = pd.Series([s.iloc[0]], index=[y.index[0] - pd.offsets.YearEnd(1)])
    y = pd.concat([first, y])
    rets = y.pct_change().dropna()
    return [{"year": int(i.year), "return": round(float(v), 6)} for i, v in rets.items()]


def exposure_stats(equity_points: list) -> dict:
    if not equity_points:
        return {"time_in_market": 0.0, "avg_gross_exposure": 0.0, "avg_net_exposure": 0.0,
                "max_gross_exposure": 0.0, "avg_open_positions": 0.0}
    invested = [p for p in equity_points if p.open_positions > 0]
    gross = [p.gross_exposure for p in equity_points]
    net = [p.net_exposure for p in equity_points]
    return {
        "time_in_market": round(len(invested) / len(equity_points), 4),
        "avg_gross_exposure": round(float(np.mean(gross)), 4),
        "avg_net_exposure": round(float(np.mean(net)), 4),
        "max_gross_exposure": round(float(np.max(gross)), 4),
        "avg_open_positions": round(float(np.mean([p.open_positions for p in equity_points])), 2),
    }


def compute_all(equity_points: list, trades: list, ppy: int,
                benchmark_equity: Optional[np.ndarray] = None,
                risk_free_annual: float = 0.0,
                turnover_value: float = 0.0) -> dict:
    """Assemble the full metric block. Gross and net are always separated."""
    if not equity_points:
        return {"error": "no equity curve produced"}

    equity = np.array([p.equity for p in equity_points], float)
    gross_equity = np.array([p.gross_equity for p in equity_points], float)
    ts = [p.timestamp for p in equity_points]
    days = max(1.0, (ts[-1] - ts[0]).total_seconds() / 86400.0)

    r = returns_from_equity(equity)
    r_gross = returns_from_equity(gross_equity)
    mdd = max_drawdown(equity)
    net_cagr = cagr(equity, days)
    net_profit = float(equity[-1] - equity[0])
    v95, es95 = var_es(r, 0.95)

    out = {
        "start": ts[0].isoformat(), "end": ts[-1].isoformat(),
        "days": round(days, 1), "bars": len(equity),
        "initial_capital": round(float(equity[0]), 2),
        "final_equity": round(float(equity[-1]), 2),
        "final_equity_gross": round(float(gross_equity[-1]), 2),

        "total_return": round(total_return(equity), 6),
        "total_return_gross": round(total_return(gross_equity), 6),
        "cagr": round(net_cagr, 6),
        "cagr_gross": round(cagr(gross_equity, days), 6),
        "net_profit": round(net_profit, 2),

        "annualized_volatility": round(annualized_volatility(r, ppy), 6),
        "sharpe": round(sharpe(r, ppy, risk_free_annual), 4),
        "sharpe_gross": round(sharpe(r_gross, ppy, risk_free_annual), 4),
        "sortino": round(sortino(r, ppy, risk_free_annual), 4),
        "downside_deviation": round(downside_deviation(r, risk_free_annual, ppy), 6),

        "max_drawdown": round(mdd, 6),
        "calmar": round(calmar(net_cagr, mdd), 4),
        "ulcer_index": round(ulcer_index(equity), 4),
        "recovery_factor": round(recovery_factor(net_profit, mdd * float(equity[0])), 4),
        "drawdown_duration": drawdown_durations(equity),

        "var_95": round(v95, 6), "expected_shortfall_95": round(es95, 6),
        "skewness": round(float(pd.Series(r).skew()), 4) if len(r) > 3 else None,
        "kurtosis": round(float(pd.Series(r).kurtosis()), 4) if len(r) > 3 else None,

        "turnover": round(turnover_value, 4),
        "periods_per_year": ppy,
    }
    out.update(trade_stats(trades))
    out.update(exposure_stats(equity_points))

    if benchmark_equity is not None and len(benchmark_equity) > 20:
        rb = returns_from_equity(np.asarray(benchmark_equity, float))
        out["benchmark"] = benchmark_regression(r, rb, ppy)
        out["benchmark"]["total_return"] = round(total_return(benchmark_equity), 6)
        out["benchmark"]["cagr"] = round(cagr(benchmark_equity, days), 6)
        out["benchmark"]["max_drawdown"] = round(max_drawdown(benchmark_equity), 6)
        out["benchmark"]["sharpe"] = round(sharpe(rb, ppy, risk_free_annual), 4)
        out["benchmark"]["excess_cagr"] = round(net_cagr - cagr(benchmark_equity, days), 6)

    return out
