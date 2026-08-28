"""
Report assembly (spec §34, §35).

Takes the base pass and runs everything the specification demands around it:
benchmarks, diagnostics, walk-forward validation, robustness, the stress
matrix, the quality score and the bias audit. Then serialises the whole thing
into one JSON-safe document the frontend can render without further maths.

Serialisation rules:
  * numpy scalars become Python scalars, NaN/Inf become null
  * long series are thinned for transport, never truncated at one end
  * every headline number is reconstructible from the ledger that ships with it
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

from services.backtest_india import benchmarks as bench_lib
from services.backtest_india import diagnostics as diag_lib
from services.backtest_india import quality as quality_lib
from services.backtest_india import robustness as robust_lib
from services.backtest_india import validation as valid_lib
from services.backtest_india.costs import capital_gains_note, get_cost_schedule
from services.backtest_india.execution import ExecutionModel
from services.backtest_india.riskrules import RiskConfig

logger = logging.getLogger(__name__)

MAX_SERIES_POINTS = 900


def _num(x):
    """JSON-safe scalar."""
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return v if math.isfinite(v) else None
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    return x


def _clean(obj):
    """Recursively make a structure JSON-safe."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_num(v) for v in obj.tolist()]
    return _num(obj)


def _thin(items: list, cap: int = MAX_SERIES_POINTS) -> list:
    """Evenly sample a long series, always keeping the first and last points."""
    if len(items) <= cap:
        return items
    step = len(items) / cap
    idx = sorted({int(i * step) for i in range(cap)} | {0, len(items) - 1})
    return [items[i] for i in idx if i < len(items)]


def build_report(cfg, base, series_map: dict, benchmark_series) -> dict:
    """Assemble the complete run report."""
    pf = base.portfolio
    metrics = base.metrics
    ppy = base.ppy
    schedule = get_cost_schedule(cfg.cost_schedule)
    execution = ExecutionModel.from_dict(cfg.execution)
    risk = RiskConfig.from_dict(cfg.risk)

    # ── re-run helpers, each varying exactly one thing ──
    def run_variant_metrics(strategy: dict, **kw):
        from services.backtest_india.engine import run_single_pass
        res = run_single_pass(cfg, series_map=series_map,
                              benchmark_series=benchmark_series,
                              strategy_override=strategy, **kw)
        return res.metrics

    def run_stress_metrics(**kw):
        from services.backtest_india.engine import run_single_pass
        res = run_single_pass(cfg, series_map=series_map,
                              benchmark_series=benchmark_series, **kw)
        return res.metrics

    def run_window(start_map, end_map):
        from services.backtest_india.engine import run_single_pass
        return run_single_pass(cfg, series_map=series_map,
                               benchmark_series=benchmark_series,
                               start_index_by_symbol=start_map,
                               end_index_by_symbol=end_map)

    n_bars = min(len(s.bars) for s in series_map.values())
    equity = np.array([p.equity for p in pf.equity_curve], float)
    timestamps = [p.timestamp for p in pf.equity_curve]

    # ── liquidity feasibility ──
    liquidity = _liquidity_report(base, execution)

    # ── diagnostics ──
    dcfg = cfg.diagnostics or {}
    bootstrap = (diag_lib.bootstrap_confidence(
        equity, ppy, int(dcfg.get("bootstrap_iterations", 400)),
        int(dcfg.get("bootstrap_block", 10)), cfg.seed)
        if dcfg.get("bootstrap", True) else {"available": False, "reason": "disabled"})

    monte_carlo = (diag_lib.monte_carlo_trade_order(
        pf.trades, cfg.initial_capital,
        int(dcfg.get("monte_carlo_iterations", 800)), cfg.seed)
        if dcfg.get("monte_carlo", True) else {"available": False, "reason": "disabled"})

    primary = series_map[list(series_map)[0]]
    regime_info = diag_lib.classify_regimes(
        primary.analysis["Close"].to_numpy(float),
        [b.event_time for b in primary.bars], ppy)
    regime_labels = _align_regimes(regime_info["labels"], primary, base.calendar)
    regimes = diag_lib.regime_breakdown(pf.equity_curve, regime_labels, pf.trades, ppy)
    if regimes.get("available"):
        regimes["definition"] = regime_info["definition"]

    # ── validation ──
    max_hold = int(max([t.bars_held for t in pf.trades], default=20))
    max_lookback = int(max((p.warmup for p in base.plans.values()), default=50))
    walk_forward = {"available": False, "reason": "walk-forward not enabled for this run"}
    if (cfg.validation or {}).get("enabled"):
        try:
            wf_cfg = dict(cfg.validation)
            wf_cfg["periods_per_year"] = ppy
            cfg_wf = cfg
            cfg_wf.validation = wf_cfg
            walk_forward = valid_lib.run_walk_forward(
                cfg_wf, series_map, benchmark_series, run_window,
                max_lookback, max_hold)
        except Exception as exc:
            logger.warning("backtest_india: walk-forward failed: %s", exc)
            walk_forward = {"available": False, "reason": f"walk-forward failed: {exc}"}

    # ── stress + robustness ──
    stress = {"available": False}
    if (cfg.robustness or {}).get("stress", True):
        try:
            stress = robust_lib.stress_matrix(cfg, run_stress_metrics)
        except Exception as exc:
            logger.warning("backtest_india: stress matrix failed: %s", exc)
            stress = {"available": False, "reason": str(exc)}

    param_robust = {"available": False}
    if (cfg.robustness or {}).get("parameters", True):
        try:
            param_robust = robust_lib.parameter_robustness(
                metrics, cfg.strategy, run_variant_metrics,
                int((cfg.robustness or {}).get("max_variants", 12)))
        except Exception as exc:
            logger.warning("backtest_india: parameter robustness failed: %s", exc)
            param_robust = {"available": False, "reason": str(exc)}

    # ── baselines ──
    controls = {"available": False}
    if (cfg.diagnostics or {}).get("controls", True):
        try:
            controls = bench_lib.run_controls(cfg, metrics, run_variant_metrics,
                                              n_bars, cfg.seed)
        except Exception as exc:
            logger.warning("backtest_india: controls failed: %s", exc)
            controls = {"available": False, "reason": str(exc)}

    buy_hold = {}
    for sym, s in series_map.items():
        try:
            buy_hold[sym] = bench_lib.buy_and_hold(s, cfg.initial_capital, schedule, ppy)
        except Exception:
            pass

    # ── quality + audit ──
    q = quality_lib.compute_quality(metrics, walk_forward, param_robust,
                                    regimes, stress, liquidity, cfg.strategy)
    confidence = quality_lib.confidence_label(metrics, walk_forward, param_robust,
                                              stress, q["score"])
    audit = quality_lib.bias_audit(cfg, base, series_map, liquidity, walk_forward)

    # ── serialise ──
    report = {
        "success": True,
        "run": {
            "run_id": cfg.fingerprint(),
            "engine_version": cfg.engine_version,
            "strategy_hash": cfg.strategy_hash(),
            "strategy_name": cfg.strategy_name,
            "symbols": [s for s in series_map],
            "requested_symbols": cfg.symbols,
            "timeframe": cfg.timeframe,
            "start": cfg.start, "end": cfg.end,
            "initial_capital": cfg.initial_capital,
            "seed": cfg.seed,
            "cost_schedule": cfg.cost_schedule,
            "intrabar_policy": cfg.intrabar_policy,
            "survivorship_mode": cfg.survivorship_mode,
            "data_version": _data_version(series_map),
            "config": cfg.to_dict(),
        },
        "headline": _headline(metrics, q, confidence, pf),
        "metrics": metrics,
        "equity_curve": _equity_series(pf, base),
        "drawdown_curve": _drawdown_series(pf),
        "monthly_returns": _monthly(pf),
        "yearly_returns": _yearly(pf),
        "trades": _trades(pf),
        "orders": _orders(base),
        "cost_waterfall": pf.cost_waterfall(),
        "cost_schedule": schedule.to_dict(),
        "capital_gains_note": capital_gains_note(
            [max(0, (t.exit_time - t.entry_time).days) for t in pf.trades]),
        "ledger": pf.ledger_dicts(400),
        "execution_model": execution.describe(),
        "risk_rules": risk.describe(),
        "liquidity": liquidity,
        "diagnostics": {
            "bootstrap": bootstrap,
            "monte_carlo": monte_carlo,
            "trade_concentration": diag_lib.trade_concentration(pf.trades),
            "return_distribution": diag_lib.return_distribution(equity),
            "attribution": diag_lib.attribution(pf.trades),
            "rolling": _rolling(pf, ppy),
        },
        "regimes": regimes,
        "walk_forward": walk_forward,
        "robustness": param_robust,
        "stress_matrix": stress,
        "cost_sensitivity": robust_lib.cost_sensitivity(stress.get("rows", [])),
        "benchmarks": {"buy_and_hold": buy_hold, "controls": controls},
        "quality_score": q,
        "confidence": confidence,
        "bias_audit": audit,
        "data_quality": {sym: s.quality.to_dict() for sym, s in series_map.items()},
        "chart_data": _chart_data(base, series_map),
        "warnings": base.warnings,
        "halted": base.halted_reason,
    }

    from services.backtest_india.registry import record_run
    record_run(report)

    return _clean(report)


# ── section builders ────────────────────────────────────────────────────────

def _headline(metrics: dict, q: dict, confidence: dict, pf) -> dict:
    """Spec §35 — the numbers that appear above the fold, gross and net apart."""
    bm = metrics.get("benchmark") or {}
    return {
        "net_cagr": metrics.get("cagr"),
        "gross_cagr": metrics.get("cagr_gross"),
        "net_total_return": metrics.get("total_return"),
        "gross_total_return": metrics.get("total_return_gross"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "sortino": metrics.get("sortino"),
        "calmar": metrics.get("calmar"),
        "profit_factor": metrics.get("profit_factor"),
        "turnover": metrics.get("turnover"),
        "total_costs": round(pf.total_costs + pf.total_slippage, 2),
        "total_trades": metrics.get("total_trades"),
        "hit_rate": metrics.get("hit_rate"),
        "benchmark_excess_cagr": bm.get("excess_cagr"),
        "quality_score": q.get("score"),
        "confidence_label": confidence.get("label"),
        "confidence_summary": confidence.get("summary"),
    }


def _equity_series(pf, base) -> list:
    bench = base.benchmark_equity
    bench_ts = {t: i for i, t in enumerate(base.benchmark_timestamps or [])}
    rows = []
    for p in pf.equity_curve:
        bi = bench_ts.get(p.timestamp)
        rows.append({
            "t": p.timestamp.isoformat(),
            "equity": p.equity,
            "gross": p.gross_equity,
            "cash": p.cash,
            "benchmark": (round(float(bench[bi]), 2)
                          if bench is not None and bi is not None and bi < len(bench)
                          else None),
            "exposure": p.gross_exposure,
            "positions": p.open_positions,
        })
    return _thin(rows)


def _drawdown_series(pf) -> list:
    return _thin([{"t": p.timestamp.isoformat(), "drawdown": p.drawdown}
                  for p in pf.equity_curve])


def _monthly(pf) -> list:
    from services.backtest_india.metrics import monthly_returns
    if not pf.equity_curve:
        return []
    return monthly_returns(np.array([p.equity for p in pf.equity_curve], float),
                           [p.timestamp for p in pf.equity_curve])


def _yearly(pf) -> list:
    from services.backtest_india.metrics import yearly_returns
    if not pf.equity_curve:
        return []
    return yearly_returns(np.array([p.equity for p in pf.equity_curve], float),
                          [p.timestamp for p in pf.equity_curve])


def _rolling(pf, ppy: int) -> list:
    from services.backtest_india.metrics import rolling_metrics
    if len(pf.equity_curve) < 80:
        return []
    return rolling_metrics(np.array([p.equity for p in pf.equity_curve], float),
                           [p.timestamp for p in pf.equity_curve], ppy)


def _trades(pf) -> list:
    return [{
        "trade_id": t.trade_id, "instrument": t.instrument, "direction": t.direction,
        "entry_time": t.entry_time.isoformat(), "exit_time": t.exit_time.isoformat(),
        "entry_price": t.entry_price, "exit_price": t.exit_price,
        "quantity": t.quantity, "gross_pnl": t.gross_pnl, "costs": t.costs,
        "net_pnl": t.net_pnl, "return_pct": t.return_pct,
        "r_multiple": t.r_multiple, "bars_held": t.bars_held,
        "exit_reason": t.exit_reason, "mae": t.mae, "mfe": t.mfe,
        "entry_reason": t.entry_reason,
    } for t in pf.trades]


def _orders(base) -> dict:
    filled = sum(1 for o in base.orders if o.status.value == "FILLED")
    partial = sum(1 for o in base.orders if o.status.value == "PARTIAL")
    return {
        "total_created": len(base.orders),
        "filled": filled,
        "partially_filled": partial,
        "unfilled_or_expired": len(base.rejected_orders),
        "rejections": base.rejected_orders[:120],
        "note": ("Orders that never filled are shown so a strategy cannot look "
                 "profitable on trades it could not have taken."),
    }


def _liquidity_report(base, execution: ExecutionModel) -> dict:
    entries = [o for o in base.orders if o.intent == "ENTRY"]
    if not entries:
        return {"available": False, "participation_rate": execution.participation_rate}

    constrained = sum(1 for o in entries
                      if o.meta.get("binding_constraint") == "liquidity")
    cash_bound = sum(1 for o in entries if o.meta.get("binding_constraint") == "cash")
    weight_bound = sum(1 for o in entries if o.meta.get("binding_constraint") == "max_weight")
    fills = [f for f in base.portfolio.fills if f.participation]
    part = [f.participation for f in fills]

    return {
        "available": True,
        "participation_rate": execution.participation_rate,
        "entry_orders": len(entries),
        "liquidity_constrained_pct": round(100.0 * constrained / len(entries), 2),
        "cash_constrained_pct": round(100.0 * cash_bound / len(entries), 2),
        "weight_constrained_pct": round(100.0 * weight_bound / len(entries), 2),
        "rejected_pct": round(100.0 * len(base.rejected_orders) /
                              max(1, len(base.orders)), 2),
        "avg_participation": round(float(np.mean(part)), 6) if part else 0.0,
        "max_participation": round(float(np.max(part)), 6) if part else 0.0,
        "warning": (
            f"{constrained} of {len(entries)} entries were size-capped by the volume "
            "participation limit. At larger capital this strategy would not fill as "
            "modelled." if constrained else
            "No entry was constrained by liquidity at this capital level."
        ),
    }


def _align_regimes(labels: np.ndarray, primary, calendar: list) -> np.ndarray:
    """Map the primary instrument's regime labels onto the master calendar."""
    idx = {b.event_time: i for i, b in enumerate(primary.bars)}
    out = []
    last = "UNDEFINED"
    for ts in calendar:
        i = idx.get(ts)
        if i is not None and i < len(labels):
            last = labels[i]
        out.append(last)
    return np.array(out)


def _chart_data(base, series_map: dict) -> dict:
    """Price bars, markers and pattern anchors for the primary instrument."""
    sym = list(series_map)[0]
    plan = base.plans[sym]
    series = series_map[sym]
    bars = series.bars

    rows = _thin([{
        "t": b.event_time.isoformat(),
        "o": round(b.open, 2), "h": round(b.high, 2),
        "l": round(b.low, 2), "c": round(b.close, 2),
        "v": int(b.volume),
    } for b in bars])

    overlays = {}
    for fid, arr in list(plan.plot_series.items())[:4]:
        pts = [{"t": bars[i].event_time.isoformat(),
                "v": (round(float(arr[i]), 4) if np.isfinite(arr[i]) else None)}
               for i in range(min(len(arr), len(bars)))]
        overlays[fid] = _thin(pts)

    markers = []
    for t in base.portfolio.trades:
        if t.instrument != sym:
            continue
        markers.append({"t": t.entry_time.isoformat(), "price": t.entry_price,
                        "kind": "ENTRY", "direction": t.direction})
        markers.append({"t": t.exit_time.isoformat(), "price": t.exit_price,
                        "kind": "EXIT", "reason": t.exit_reason,
                        "pnl": t.net_pnl})

    pattern_events = [{
        "pattern": e.pattern_id, "direction": e.direction,
        "detected_at": bars[e.detection_index].event_time.isoformat()
        if e.detection_index < len(bars) else None,
        "confirmed_at": bars[e.confirmation_index].event_time.isoformat()
        if e.confirmation_index is not None and e.confirmation_index < len(bars) else None,
        "trigger_level": e.trigger_level,
        "invalidation_level": e.invalidation_level,
        "quality": e.quality,
    } for e in plan.pattern_events[:60]]

    return {
        "symbol": sym,
        "bars": rows,
        "overlays": overlays,
        "markers": markers[:600],
        "levels": plan.structure.levels[:30],
        "pattern_events": pattern_events,
        "pivots": [{"t": bars[p.index].event_time.isoformat(),
                    "detected_at": bars[min(p.detected, len(bars) - 1)].event_time.isoformat(),
                    "price": p.price, "kind": p.kind}
                   for p in plan.structure.pivots[-80:]],
    }


def _data_version(series_map: dict) -> str:
    """A hash over the actual bars used, so a data revision creates a new run."""
    import hashlib
    h = hashlib.sha256()
    for sym in sorted(series_map):
        s = series_map[sym]
        h.update(sym.encode())
        h.update(str(len(s.bars)).encode())
        h.update(f"{s.bars[0].event_time}{s.bars[-1].event_time}".encode())
        h.update(f"{s.bars[-1].close:.4f}".encode())
    return h.hexdigest()[:16]
