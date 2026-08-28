"""
Event-driven simulation core (spec §2, §44).

This is the only module that advances time. It walks the master calendar one
event at a time and, at each event, performs exactly this sequence:

    1. corporate actions for the bar
    2. mark excursions on open positions
    3. resolve resting stop / target orders against the bar (intrabar policy)
    4. attempt fills for orders whose latency has elapsed
    5. evaluate the strategy graph at the bar CLOSE and emit new orders,
       stamped eligible no earlier than the NEXT bar
    6. mark the book to market

Because step 5 comes after step 4, a signal generated on bar i can never be
filled on bar i. That ordering — not a comment, not a convention — is what
makes the look-ahead guarantee structural.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from services.backtest_india import candles as candle_lib
from services.backtest_india import execution as exec_lib
from services.backtest_india import features as feat_lib
from services.backtest_india import metrics as metric_lib
from services.backtest_india import patterns as pattern_lib
from services.backtest_india import riskrules
from services.backtest_india import sizing as sizing_lib
from services.backtest_india import structure as struct_lib
from services.backtest_india.contracts import (
    ConfidenceLabel, ExitReason, Order, OrderSide, OrderStatus, OrderType,
    RunConfig, utc_now_iso,
)
from services.backtest_india.costs import get_cost_schedule
from services.backtest_india.datafeed import (
    PERIODS_PER_YEAR, InstrumentSeries, build_master_calendar, load_instrument,
    load_universe,
)
from services.backtest_india.execution import ExecutionModel
from services.backtest_india.graph import compile_graph, validate_graph
from services.backtest_india.portfolio import Portfolio
from services.backtest_india.riskrules import RiskConfig

logger = logging.getLogger(__name__)

ENGINE_VERSION = "2.0.0"


# ── Per-instrument prepared state ───────────────────────────────────────────

@dataclass
class InstrumentPlan:
    """Everything precomputed for one instrument before the clock starts."""
    series: InstrumentSeries
    index_by_time: dict
    entry_long: np.ndarray
    exit_long: np.ndarray
    entry_short: np.ndarray
    exit_short: np.ndarray
    atr: np.ndarray
    realized_vol: np.ndarray
    structure: struct_lib.StructureState
    pattern_events: list
    warmup: int
    errors: list = field(default_factory=list)
    condition_labels: dict = field(default_factory=dict)
    plot_series: dict = field(default_factory=dict)


def prepare_instrument(series: InstrumentSeries, strategy: dict,
                       ppy: int) -> InstrumentPlan:
    """Feature -> pattern -> structure -> graph, all vectorised and causal."""
    df = series.analysis
    n = len(df)

    values, feat_warmup, errors = feat_lib.compute_features(df, strategy.get("features", []))

    candle_masks, candle_errors = candle_lib.compute_candles(df, strategy.get("candles", []))
    errors.extend(candle_errors)
    values.update(candle_masks)

    # ATR and realised volatility are always available: risk sizing and the
    # slippage model need them even when the strategy never asks for them.
    h = df["High"].to_numpy(float); l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    atr14 = feat_lib.atr(h, l, c, 14)
    rvol = feat_lib.historical_volatility(c, 20, ppy)
    values.setdefault("atr14", atr14)
    values.setdefault("rvol20", rvol)

    struct_cfg = strategy.get("structure", {}) or {}
    _, _, _, bandwidth = feat_lib.bollinger(c, 20, 2.0)
    st = struct_lib.build_structure(
        df, atr14,
        k=int(struct_cfg.get("pivot_k", 3)),
        bos_buffer_atr=float(struct_cfg.get("bos_buffer_atr", 0.10)),
        pct_tol=float(struct_cfg.get("level_pct_tolerance", 0.005)),
        atr_tol=float(struct_cfg.get("level_atr_tolerance", 0.5)),
        min_touches=int(struct_cfg.get("min_touches", 2)),
        bandwidth=bandwidth,
    )
    values.update(struct_lib.structure_values(st))

    chart_masks, chart_events, chart_errors = pattern_lib.detect_all(
        df, strategy.get("chart_patterns", []),
        pivot_k=int(struct_cfg.get("pivot_k", 3)),
        atr_series=atr14, instrument=series.symbol,
    )
    errors.extend(chart_errors)
    values.update(chart_masks)

    # structural detectors need k future bars; nothing may fire before that
    warmup = max(feat_warmup, int(struct_cfg.get("pivot_k", 3)) + 1, 20)

    compiled = compile_graph(df, strategy, values,
                             timestamps=[b.event_time for b in series.bars],
                             base_warmup=warmup)
    errors.extend(compiled.errors)

    # Random-entry control (spec §28). The graph is rewritten so the control
    # travels the identical engine path — same exits, sizing, risk and costs —
    # with only the entry timing replaced by noise at the strategy's own rate.
    rnd = strategy.get("_random_entry")
    if rnd:
        gen = np.random.default_rng(int(rnd.get("seed", 0)) + abs(hash(series.symbol)) % 10007)
        draws = gen.random(n) < float(rnd.get("rate", 0.01))
        draws[:warmup] = False
        compiled.entry_long = draws
        compiled.entry_short = np.zeros(n, dtype=bool)

    # keep a few series for the chart overlay, thinned at serialisation time
    plot = {}
    for req in (strategy.get("features") or [])[:6]:
        fid = req.get("id")
        if fid and fid in values and isinstance(values[fid], np.ndarray):
            arr = values[fid]
            if arr.dtype != bool:
                plot[fid] = arr

    return InstrumentPlan(
        series=series,
        index_by_time={b.event_time: i for i, b in enumerate(series.bars)},
        entry_long=compiled.entry_long, exit_long=compiled.exit_long,
        entry_short=compiled.entry_short, exit_short=compiled.exit_short,
        atr=atr14, realized_vol=rvol, structure=st,
        pattern_events=chart_events, warmup=warmup, errors=errors,
        condition_labels=compiled.labels, plot_series=plot,
    )


# ── Result container ────────────────────────────────────────────────────────

@dataclass
class PassResult:
    portfolio: Portfolio
    metrics: dict
    plans: dict
    warnings: list
    orders: list
    rejected_orders: list
    benchmark_equity: Optional[np.ndarray]
    benchmark_timestamps: Optional[list]
    calendar: list
    ppy: int
    halted_reason: str = ""


# ── The clock ───────────────────────────────────────────────────────────────

def run_single_pass(
    cfg: RunConfig,
    series_map: Optional[dict] = None,
    start_index_by_symbol: Optional[dict] = None,
    end_index_by_symbol: Optional[dict] = None,
    benchmark_series: Optional[InstrumentSeries] = None,
    strategy_override: Optional[dict] = None,
    exec_override: Optional[ExecutionModel] = None,
    cost_override=None,
    seed_offset: int = 0,
    signal_skip_pct: float = 0.0,
    extra_latency_bars: int = 0,
) -> PassResult:
    """
    Run one complete simulation over the supplied data.

    Every optional argument exists so validation, robustness and stress passes
    can vary exactly one thing at a time — the acceptance criterion that
    changing only the cost schedule must change costs without changing signals.
    """
    strategy = strategy_override if strategy_override is not None else cfg.strategy
    ppy = PERIODS_PER_YEAR.get(cfg.timeframe, 252)
    rng = np.random.default_rng(cfg.seed + seed_offset)

    if series_map is None:
        series_map, load_warnings = load_universe(
            cfg.symbols, cfg.start, cfg.end, cfg.timeframe, cfg.exchange)
    else:
        load_warnings = []

    warnings = list(load_warnings)

    plans: dict[str, InstrumentPlan] = {}
    for sym, series in series_map.items():
        plan = prepare_instrument(series, strategy, ppy)
        warnings.extend(f"{sym}: {e}" for e in plan.errors)
        plans[sym] = plan

    execution = exec_override or ExecutionModel.from_dict(cfg.execution)
    if extra_latency_bars:
        # copy the resolved model so an exec_override is not discarded
        execution = ExecutionModel(**{k: getattr(execution, k)
                                      for k in execution.__dataclass_fields__})
        execution.latency_bars += int(extra_latency_bars)
    schedule = cost_override or get_cost_schedule(cfg.cost_schedule)
    risk = RiskConfig.from_dict(cfg.risk)
    sizing_cfg = dict(cfg.sizing or {})
    sizing_model = sizing_cfg.get("model", "percent_equity")

    calendar = build_master_calendar(series_map)
    # window clipping for walk-forward slices
    if start_index_by_symbol or end_index_by_symbol:
        lo_times, hi_times = [], []
        for sym, plan in plans.items():
            bars = plan.series.bars
            lo = (start_index_by_symbol or {}).get(sym, 0)
            hi = (end_index_by_symbol or {}).get(sym, len(bars) - 1)
            lo = max(0, min(lo, len(bars) - 1))
            hi = max(lo, min(hi, len(bars) - 1))
            lo_times.append(bars[lo].event_time)
            hi_times.append(bars[hi].event_time)
        t0, t1 = min(lo_times), max(hi_times)
        calendar = [t for t in calendar if t0 <= t <= t1]

    if len(calendar) < 5:
        raise ValueError("The selected window contains too few bars to simulate.")

    pf = Portfolio(cfg.initial_capital, allow_short=cfg.allow_short)
    pf.seed(calendar[0])

    pending: list[Order] = []
    all_orders: list[Order] = []
    rejected: list[dict] = []
    cooldown_until: dict[str, int] = {}
    consecutive_losses = 0
    halted_reason = ""
    order_seq = fill_seq = 0
    bar_counter = -1

    for ts in calendar:
        bar_counter += 1
        prices_now: dict = {}

        # ---- per-instrument bar processing ----
        for sym, plan in plans.items():
            i = plan.index_by_time.get(ts)
            if i is None:
                # This instrument did not trade at this event time (holiday,
                # halt, or a later listing). It is simply skipped — the mark
                # step below carries its last known price forward.
                continue
            bar = plan.series.bars[i]
            prices_now[sym] = bar.close

            # 1. corporate actions
            if bar.dividend:
                pf.apply_dividend(sym, bar.dividend, ts, i)
            if bar.split_ratio and abs(bar.split_ratio - 1.0) > 1e-9:
                pf.apply_split(sym, bar.split_ratio, ts, i)

            # 2. excursions
            pf.update_excursions(sym, bar.high, bar.low)

            # 3. resting stop / target resolution
            pos = pf.positions.get(sym)
            if pos and pos.quantity != 0:
                atr_v = plan.atr[i] if i < len(plan.atr) else np.nan
                new_stop = riskrules.apply_breakeven(risk, pos, bar.open)
                pos.stop_price = new_stop
                pos.stop_price = riskrules.update_trailing(risk, pos, bar.high, bar.low, atr_v)

                event, level = exec_lib.resolve_intrabar(
                    bar, pos.direction, pos.stop_price, pos.target_price,
                    cfg.intrabar_policy)

                exit_reason = None
                exit_level = None
                if event == "STOP":
                    exit_reason = (ExitReason.TRAILING_STOP.value
                                   if risk.trailing_enabled and pos.stop_price != pos.initial_stop
                                   else ExitReason.STOP_LOSS.value)
                    exit_level = exec_lib.gap_adjusted_exit(bar, pos.direction, level, "STOP")
                elif event == "TARGET":
                    exit_reason = ExitReason.TAKE_PROFIT.value
                    exit_level = exec_lib.gap_adjusted_exit(bar, pos.direction, level, "TARGET")
                elif risk.time_stop_bars and pos.bars_held >= risk.time_stop_bars:
                    exit_reason = ExitReason.TIME_STOP.value
                    exit_level = bar.close

                if exit_reason:
                    trade = _force_exit(pf, sym, pos, bar, i, exit_level, exit_reason,
                                        schedule, execution, fill_seq)
                    fill_seq += 1
                    if trade:
                        consecutive_losses = consecutive_losses + 1 if trade.net_pnl <= 0 else 0
                        if risk.cooldown_bars:
                            cooldown_until[sym] = i + risk.cooldown_bars

        # ---- 4. execute eligible pending orders ----
        still_pending: list[Order] = []
        opened_this_bar: list[tuple] = []
        for order in pending:
            plan = plans.get(order.instrument)
            i = plan.index_by_time.get(ts) if plan else None
            if i is None:
                still_pending.append(order)
                continue
            if i < order.eligible_index:
                still_pending.append(order)
                continue

            bar = plan.series.bars[i]
            atr_v = plan.atr[i] if i < len(plan.atr) else None
            adv_v = plan.series.adv[i] if i < len(plan.series.adv) else None
            vol_v = plan.realized_vol[i] if i < len(plan.realized_vol) else None

            attempt = exec_lib.attempt_fill(order, bar, execution, atr_v, adv_v, vol_v)
            if attempt.filled_quantity <= 0:
                order.status = OrderStatus.WORKING
                age = i - order.eligible_index
                if age >= order.time_in_force_bars:
                    order.status = OrderStatus.EXPIRED
                    rejected.append({
                        "order_id": order.order_id, "instrument": order.instrument,
                        "timestamp": ts.isoformat(), "reason": attempt.rejected_reason,
                        "quantity": order.quantity, "intent": order.intent,
                    })
                else:
                    still_pending.append(order)
                continue

            fill = exec_lib.build_fill(order, attempt, bar, i, schedule, fill_seq)
            fill_seq += 1
            order.filled_quantity += attempt.filled_quantity
            order.status = (OrderStatus.FILLED if order.remaining == 0
                            else OrderStatus.PARTIAL)

            stop = order.meta.get("stop")
            target = order.meta.get("target")
            r_unit = abs(fill.price - stop) if stop else 0.0
            if order.intent == "ENTRY" and stop:
                # re-anchor the risk unit on the ACTUAL fill, not the signal price
                direction = 1 if order.side == OrderSide.BUY else -1
                if order.meta.get("target_type") == "r_multiple" and r_unit > 0:
                    target = fill.price + direction * float(order.meta.get("target_r", 2.0)) * r_unit

            trade = pf.apply_fill(
                fill,
                entry_reason=order.reason,
                exit_reason=order.meta.get("exit_reason"),
                stop=stop, target=target, r_unit=r_unit,
            )
            if order.intent == "ENTRY" and not trade:
                opened_this_bar.append((order.instrument, i, bar))
            if trade:
                consecutive_losses = consecutive_losses + 1 if trade.net_pnl <= 0 else 0
                if risk.cooldown_bars:
                    cooldown_until[order.instrument] = i + risk.cooldown_bars

            if order.remaining > 0 and (i - order.eligible_index) < order.time_in_force_bars:
                still_pending.append(order)
            elif order.remaining > 0:
                order.status = OrderStatus.EXPIRED
                rejected.append({
                    "order_id": order.order_id, "instrument": order.instrument,
                    "timestamp": ts.isoformat(),
                    "reason": f"expired with {order.remaining} unfilled (participation cap)",
                    "quantity": order.remaining, "intent": order.intent,
                })
        pending = still_pending

        # A position opened on this bar is still exposed to the REST of that
        # bar. Without this check every stop would be silently delayed by one
        # bar, which flatters exactly the trades that went wrong immediately.
        for sym, i, bar in opened_this_bar:
            pos = pf.positions.get(sym)
            if not pos or pos.quantity == 0:
                continue
            event, level = exec_lib.resolve_intrabar(
                bar, pos.direction, pos.stop_price, pos.target_price,
                cfg.intrabar_policy)
            if not event:
                continue
            reason = (ExitReason.STOP_LOSS.value if event == "STOP"
                      else ExitReason.TAKE_PROFIT.value)
            exit_level = exec_lib.gap_adjusted_exit(bar, pos.direction, level, event)
            trade = _force_exit(pf, sym, pos, bar, i, exit_level, reason,
                                schedule, execution, fill_seq)
            fill_seq += 1
            if trade:
                consecutive_losses = consecutive_losses + 1 if trade.net_pnl <= 0 else 0
                if risk.cooldown_bars:
                    cooldown_until[sym] = i + risk.cooldown_bars

        # ---- portfolio-level guards ----
        equity_now = pf.cash + sum(
            p.quantity * prices_now.get(s, p.avg_price)
            for s, p in pf.positions.items() if p.quantity
        )
        if risk.portfolio_max_drawdown and pf.peak_equity > 0:
            dd = equity_now / pf.peak_equity - 1.0
            if dd <= -abs(risk.portfolio_max_drawdown) and not halted_reason:
                halted_reason = (f"Portfolio drawdown hit {dd:.1%}, breaching the "
                                 f"-{abs(risk.portfolio_max_drawdown):.0%} halt. "
                                 "No further entries were taken.")
        if risk.max_consecutive_losses and consecutive_losses >= risk.max_consecutive_losses \
                and not halted_reason:
            halted_reason = (f"{consecutive_losses} consecutive losing trades reached the "
                             "configured halt threshold. No further entries were taken.")

        # ---- 5. signals at the bar close -> orders for LATER bars ----
        if not halted_reason:
            open_count = len(pf.open_positions)
            for sym, plan in plans.items():
                i = plan.index_by_time.get(ts)
                if i is None or i < plan.warmup or i >= len(plan.series.bars) - 1:
                    continue
                bar = plan.series.bars[i]
                pos = pf.positions.get(sym)
                held = pos.quantity if pos else 0

                # exits first: freeing a slot in the same event is correct
                if held != 0:
                    want_exit = (plan.exit_long[i] if held > 0 else plan.exit_short[i])
                    reversal = (plan.entry_short[i] if held > 0 else plan.entry_long[i])
                    if want_exit or (reversal and cfg.allow_short):
                        order_seq += 1
                        pending.append(_make_order(
                            order_seq, sym,
                            OrderSide.SELL if held > 0 else OrderSide.BUY,
                            abs(held), ts, i, execution,
                            intent="EXIT",
                            reason="signal exit" if want_exit else "signal reversal",
                            meta={"exit_reason": (ExitReason.SIGNAL_EXIT.value if want_exit
                                                  else ExitReason.SIGNAL_REVERSAL.value)},
                        ))
                        all_orders.append(pending[-1])
                    continue

                if i < cooldown_until.get(sym, -1):
                    continue
                if open_count >= cfg.max_concurrent_positions:
                    continue

                long_sig = bool(plan.entry_long[i])
                short_sig = bool(plan.entry_short[i]) and cfg.allow_short
                if not long_sig and not short_sig:
                    continue
                if signal_skip_pct > 0 and rng.random() < signal_skip_pct:
                    continue

                direction = 1 if long_sig else -1
                side = OrderSide.BUY if direction > 0 else OrderSide.SELL

                # sizing inputs are read at the SIGNAL bar; the fill happens later
                atr_v = float(plan.atr[i]) if i < len(plan.atr) and np.isfinite(plan.atr[i]) else None
                rvol_v = (float(plan.realized_vol[i])
                          if i < len(plan.realized_vol) and np.isfinite(plan.realized_vol[i]) else None)
                struct_level = (plan.structure.swing_low_level[i] if direction > 0
                                else plan.structure.swing_high_level[i])
                struct_level = float(struct_level) if np.isfinite(struct_level) else None

                ref_price = bar.close
                stop = riskrules.initial_stop(risk, ref_price, direction, atr_v, struct_level)
                if risk.stop_type != "none" and stop is None:
                    rejected.append({
                        "order_id": None, "instrument": sym, "timestamp": ts.isoformat(),
                        "reason": "no valid stop could be computed (ATR undefined)",
                        "quantity": 0, "intent": "ENTRY",
                    })
                    continue
                target = riskrules.initial_target(risk, ref_price, direction, stop, atr_v)

                stop_distance = abs(ref_price - stop) if stop else None
                raw_qty, size_note = sizing_lib.desired_quantity(
                    sizing_model, ref_price, equity_now, sizing_cfg,
                    stop_distance=stop_distance, atr=atr_v, realized_vol=rvol_v,
                    n_positions=cfg.max_concurrent_positions,
                )
                if raw_qty <= 0:
                    rejected.append({
                        "order_id": None, "instrument": sym, "timestamp": ts.isoformat(),
                        "reason": f"sizing produced zero quantity ({size_note})",
                        "quantity": 0, "intent": "ENTRY",
                    })
                    continue

                capped = sizing_lib.apply_caps(
                    raw_qty, ref_price, equity_now,
                    pf.available_cash(float(sizing_cfg.get("cash_reserve", 0.0))),
                    cfg.max_position_weight,
                    bar.volume, execution.participation_rate,
                )
                if capped.quantity <= 0:
                    rejected.append({
                        "order_id": None, "instrument": sym, "timestamp": ts.isoformat(),
                        "reason": f"size reduced to zero by the {capped.binding_constraint} constraint",
                        "quantity": 0, "intent": "ENTRY",
                    })
                    continue

                order_seq += 1
                o = _make_order(
                    order_seq, sym, side, capped.quantity, ts, i, execution,
                    intent="ENTRY",
                    reason=f"{'long' if direction > 0 else 'short'} entry — {size_note}",
                    meta={"stop": stop, "target": target,
                          "target_type": risk.target_type, "target_r": risk.target_r,
                          "binding_constraint": capped.binding_constraint,
                          "requested_quantity": capped.requested_quantity},
                )
                pending.append(o)
                all_orders.append(o)
                open_count += 1

        # ---- 6. mark ----
        marks = {}
        for sym, plan in plans.items():
            i = plan.index_by_time.get(ts)
            if i is not None:
                marks[sym] = plan.series.bars[i].close
            elif pf.positions.get(sym) and pf.positions[sym].quantity:
                marks[sym] = pf.positions[sym].avg_price
        pf.mark(marks, ts, bar_counter)

    # ---- liquidate anything still open at the end of the test ----
    last_ts = calendar[-1]
    for sym, pos in list(pf.open_positions.items()):
        plan = plans[sym]
        i = plan.index_by_time.get(last_ts, len(plan.series.bars) - 1)
        bar = plan.series.bars[i]
        _force_exit(pf, sym, pos, bar, i, bar.close, ExitReason.END_OF_TEST.value,
                    schedule, execution, fill_seq)
        fill_seq += 1
    if pf.open_positions:
        pf.mark({s: plans[s].series.bars[-1].close for s in pf.positions}, last_ts, bar_counter)
    elif pf.equity_curve:
        pf.mark({}, last_ts, bar_counter)

    bench_equity, bench_ts = _benchmark_curve(benchmark_series, calendar, cfg.initial_capital)

    results = metric_lib.compute_all(
        pf.equity_curve, pf.trades, ppy,
        benchmark_equity=bench_equity,
        risk_free_annual=float((cfg.diagnostics or {}).get("risk_free_rate", 0.0)),
        turnover_value=pf.turnover(),
    )

    return PassResult(
        portfolio=pf, metrics=results, plans=plans, warnings=warnings,
        orders=all_orders, rejected_orders=rejected,
        benchmark_equity=bench_equity, benchmark_timestamps=bench_ts,
        calendar=calendar, ppy=ppy, halted_reason=halted_reason,
    )


def _make_order(seq: int, instrument: str, side: OrderSide, quantity: int,
                ts: datetime, bar_index: int, execution: ExecutionModel,
                intent: str, reason: str, meta: Optional[dict] = None) -> Order:
    """Every order is stamped eligible at least one bar in the future."""
    return Order(
        order_id=f"O{seq:06d}", instrument=instrument, side=side,
        quantity=int(quantity), order_type=OrderType.MARKET,
        created_time=ts, eligible_index=bar_index + max(1, execution.latency_bars),
        time_in_force_bars=max(1, execution.time_in_force_bars),
        status=OrderStatus.PENDING, intent=intent, reason=reason,
        meta=meta or {},
    )


def _force_exit(pf: Portfolio, sym: str, pos, bar, bar_index: int,
                level: float, reason: str, schedule, execution: ExecutionModel,
                fill_seq: int):
    """
    Execute a resting stop / target / forced liquidation.

    A resting order is already at the venue, so it does not re-enter the
    latency queue — but it still pays slippage and the full cost schedule.
    """
    from services.backtest_india.contracts import Fill

    side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
    qty = abs(pos.quantity)
    sign = 1 if side == OrderSide.BUY else -1
    s_bps = exec_lib.slippage_bps(execution, bar, qty, None)
    price = float(np.clip(level * (1.0 + sign * s_bps / 10000.0),
                          bar.low * 0.99, bar.high * 1.01))
    total_cost, breakdown = schedule.compute(side, qty, price)

    fill = Fill(
        fill_id=f"X{fill_seq:06d}", order_id=f"REST-{sym}-{bar_index}",
        instrument=sym, side=side, quantity=qty, price=round(price, 4),
        reference_price=round(float(level), 4), timestamp=bar.event_time,
        bar_index=bar_index, slippage_value=round(abs(price - level) * qty, 4),
        impact_value=0.0, costs=breakdown, total_cost=total_cost,
        participation=(qty / bar.volume) if bar.volume else 0.0,
        notes=f"resting {reason}",
    )
    return pf.apply_fill(fill, exit_reason=reason)


def _benchmark_curve(series: Optional[InstrumentSeries], calendar: list,
                     capital: float):
    """Buy-and-hold the benchmark from bar one, marked on the master calendar."""
    if series is None:
        return None, None
    idx = {b.event_time: i for i, b in enumerate(series.bars)}
    prices, stamps = [], []
    last = None
    for ts in calendar:
        i = idx.get(ts)
        if i is not None:
            last = series.bars[i].close
        if last is not None:
            prices.append(last)
            stamps.append(ts)
    if len(prices) < 2:
        return None, None
    arr = np.array(prices, float)
    return capital * arr / arr[0], stamps


# ── Public entry point ──────────────────────────────────────────────────────

def run_backtest(config: dict) -> dict:
    """
    Run a complete experiment: base pass, benchmarks, diagnostics, validation,
    robustness and the bias audit. Returns a fully JSON-serialisable report.
    """
    started = time.time()
    cfg = RunConfig.from_dict(config)
    cfg.engine_version = ENGINE_VERSION

    problems = validate_graph(cfg.strategy)
    if problems:
        raise ValueError("Strategy graph is not valid: " + "; ".join(problems))
    if not cfg.symbols:
        raise ValueError("Select at least one instrument.")

    series_map, load_warnings = load_universe(
        cfg.symbols, cfg.start, cfg.end, cfg.timeframe, cfg.exchange)

    benchmark_series = None
    if cfg.benchmark:
        try:
            benchmark_series = load_instrument(
                cfg.benchmark, cfg.start, cfg.end, cfg.timeframe, cfg.exchange)
        except Exception as exc:
            load_warnings.append(f"Benchmark {cfg.benchmark} unavailable: {exc}")

    base = run_single_pass(cfg, series_map=series_map, benchmark_series=benchmark_series)
    base.warnings = list(load_warnings) + base.warnings

    # imported here to keep the module import graph acyclic
    from services.backtest_india import report as report_lib
    result = report_lib.build_report(cfg, base, series_map, benchmark_series)
    result["runtime_seconds"] = round(time.time() - started, 2)
    result["generated_at"] = utc_now_iso()
    return result
