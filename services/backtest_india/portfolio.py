"""
Portfolio ledger (spec §20).

Every rupee that moves is written to the cash ledger with a reason and a
timestamp, so every headline metric in the report can be reconstructed from
primitive events. Nothing is inferred; equity is computed, not accumulated.

Accounting choices, stated explicitly:
  * Average-cost basis for positions (lot-level accounting is a roadmap item).
  * Dividends are paid as cash on the ex-date bar for positions held into it,
    rather than being folded into prices. Executable prices stay honest.
  * Splits adjust quantity and average cost so no artificial P&L appears.
  * Short positions are supported only when the run enables them; the ledger
    credits proceeds and marks the liability every bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from services.backtest_india.contracts import (
    ExitReason, Fill, OrderSide, Position, Trade,
)


@dataclass
class LedgerEntry:
    timestamp: datetime
    bar_index: int
    kind: str            # FILL_BUY | FILL_SELL | COST | DIVIDEND | SPLIT | INITIAL
    instrument: str
    amount: float        # signed change to cash
    balance: float       # cash balance after this entry
    note: str = ""


@dataclass
class EquityPoint:
    timestamp: datetime
    bar_index: int
    cash: float
    holdings_value: float
    equity: float
    gross_equity: float      # the same run with zero costs, for the cost waterfall
    drawdown: float
    gross_exposure: float
    net_exposure: float
    open_positions: int


class Portfolio:
    """The one place that owns cash, positions and their history."""

    def __init__(self, initial_capital: float, allow_short: bool = False):
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.allow_short = allow_short
        self.positions: dict[str, Position] = {}
        self.ledger: list[LedgerEntry] = []
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []
        self.peak_equity = float(initial_capital)
        self.total_costs = 0.0
        self.total_slippage = 0.0
        self.cost_by_component: dict[str, float] = {}
        self._trade_seq = 0
        # gross book: identical fills, zero costs and zero slippage. This is
        # what makes the cost waterfall exact rather than an estimate.
        self._gross_cash = float(initial_capital)
        self._open_context: dict[str, dict] = {}

    # ── ledger ──
    def _post(self, ts: datetime, idx: int, kind: str, instrument: str,
              amount: float, note: str = "") -> None:
        self.cash += amount
        self.ledger.append(LedgerEntry(ts, idx, kind, instrument,
                                       round(amount, 4), round(self.cash, 4), note))

    def seed(self, ts: datetime) -> None:
        self.ledger.append(LedgerEntry(ts, 0, "INITIAL", "-", self.initial_capital,
                                       self.initial_capital, "Opening capital"))

    # ── fills ──
    def apply_fill(self, fill: Fill, entry_reason: str = "",
                   exit_reason: Optional[str] = None,
                   stop: Optional[float] = None, target: Optional[float] = None,
                   r_unit: float = 0.0) -> Optional[Trade]:
        """
        Apply one fill to cash and positions. Returns a Trade when the fill
        closes (or flips) a position.
        """
        pos = self.positions.get(fill.instrument) or Position(instrument=fill.instrument)
        signed = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
        gross_value = fill.price * fill.quantity
        ref_value = fill.reference_price * fill.quantity

        # cash: buying spends, selling receives; costs always leave the account
        cash_delta = -gross_value if fill.side == OrderSide.BUY else gross_value
        self._post(fill.timestamp, fill.bar_index,
                   "FILL_BUY" if fill.side == OrderSide.BUY else "FILL_SELL",
                   fill.instrument, cash_delta,
                   f"{fill.quantity} @ {fill.price:.2f}")
        self._post(fill.timestamp, fill.bar_index, "COST", fill.instrument,
                   -fill.total_cost, "transaction charges")

        self._gross_cash += (-ref_value if fill.side == OrderSide.BUY else ref_value)

        self.total_costs += fill.total_cost
        self.total_slippage += fill.slippage_value + fill.impact_value
        for k, v in (fill.costs or {}).items():
            self.cost_by_component[k] = self.cost_by_component.get(k, 0.0) + v
        self.cost_by_component["slippage_and_impact"] = (
            self.cost_by_component.get("slippage_and_impact", 0.0)
            + fill.slippage_value + fill.impact_value
        )
        self.fills.append(fill)

        trade: Optional[Trade] = None
        old_qty = pos.quantity
        new_qty = old_qty + signed

        opening = old_qty == 0 or (old_qty > 0 and signed > 0) or (old_qty < 0 and signed < 0)
        if opening:
            total_cost_basis = pos.avg_price * abs(old_qty) + fill.price * fill.quantity
            pos.avg_price = total_cost_basis / max(1, abs(new_qty))
            pos.quantity = new_qty
            if old_qty == 0:
                pos.entry_time = fill.timestamp
                pos.entry_index = fill.bar_index
                pos.bars_held = 0
                pos.mae = pos.mfe = 0.0
                pos.stop_price = stop
                pos.initial_stop = stop
                pos.target_price = target
                pos.r_unit = r_unit
                pos.trail_anchor = fill.price
                pos.breakeven_armed = False
                self._open_context[fill.instrument] = {
                    "entry_reason": entry_reason,
                    "entry_costs": fill.total_cost,
                    "entry_price": fill.price,
                    "gross_entry": fill.reference_price,
                }
            else:
                self._open_context.setdefault(fill.instrument, {})
                self._open_context[fill.instrument]["entry_costs"] = (
                    self._open_context[fill.instrument].get("entry_costs", 0.0) + fill.total_cost
                )
            pos.entry_cost += fill.total_cost
        else:
            closed_qty = min(abs(old_qty), fill.quantity)
            direction = 1 if old_qty > 0 else -1
            ctx = self._open_context.get(fill.instrument, {})
            gross_pnl = direction * (fill.price - pos.avg_price) * closed_qty
            entry_cost_share = ctx.get("entry_costs", 0.0) * (closed_qty / max(1, abs(old_qty)))
            exit_cost_share = fill.total_cost * (closed_qty / max(1, fill.quantity))
            costs = entry_cost_share + exit_cost_share
            net_pnl = gross_pnl - costs
            deployed = pos.avg_price * closed_qty
            self._trade_seq += 1
            trade = Trade(
                trade_id=f"T{self._trade_seq:05d}",
                instrument=fill.instrument,
                direction="LONG" if direction > 0 else "SHORT",
                entry_time=pos.entry_time or fill.timestamp,
                exit_time=fill.timestamp,
                entry_index=pos.entry_index,
                exit_index=fill.bar_index,
                quantity=int(closed_qty),
                entry_price=round(pos.avg_price, 4),
                exit_price=round(fill.price, 4),
                gross_pnl=round(gross_pnl, 2),
                costs=round(costs, 2),
                net_pnl=round(net_pnl, 2),
                return_pct=round(100.0 * net_pnl / deployed, 4) if deployed else 0.0,
                r_multiple=(round(net_pnl / (pos.r_unit * closed_qty), 3)
                            if pos.r_unit and pos.r_unit > 0 else None),
                bars_held=int(fill.bar_index - pos.entry_index),
                exit_reason=exit_reason or ExitReason.SIGNAL_EXIT.value,
                mae=round(pos.mae, 4), mfe=round(pos.mfe, 4),
                entry_reason=ctx.get("entry_reason", ""),
                cost_breakdown={k: round(v, 2) for k, v in (fill.costs or {}).items()},
            )
            self.trades.append(trade)

            pos.quantity = new_qty
            if new_qty == 0:
                pos.avg_price = 0.0
                pos.entry_time = None
                pos.stop_price = pos.target_price = pos.initial_stop = None
                pos.entry_cost = 0.0
                pos.r_unit = 0.0
                self._open_context.pop(fill.instrument, None)
            elif (old_qty > 0) != (new_qty > 0):
                # reversal: the residual is a brand-new position
                pos.avg_price = fill.price
                pos.entry_time = fill.timestamp
                pos.entry_index = fill.bar_index
                pos.bars_held = 0
                pos.mae = pos.mfe = 0.0
                pos.stop_price = stop
                pos.initial_stop = stop
                pos.target_price = target
                pos.r_unit = r_unit
                pos.trail_anchor = fill.price
                self._open_context[fill.instrument] = {
                    "entry_reason": entry_reason, "entry_costs": 0.0,
                    "entry_price": fill.price, "gross_entry": fill.reference_price,
                }

        self.positions[fill.instrument] = pos
        return trade

    # ── corporate actions ──
    def apply_dividend(self, instrument: str, per_share: float,
                       ts: datetime, idx: int) -> None:
        pos = self.positions.get(instrument)
        if not pos or pos.quantity == 0 or per_share <= 0:
            return
        amount = per_share * pos.quantity        # negative for shorts, correctly
        self._post(ts, idx, "DIVIDEND", instrument, amount,
                   f"Rs.{per_share:.4f}/share on {pos.quantity} shares")
        self._gross_cash += amount

    def apply_split(self, instrument: str, ratio: float, ts: datetime, idx: int) -> None:
        pos = self.positions.get(instrument)
        if not pos or pos.quantity == 0 or ratio <= 0 or abs(ratio - 1.0) < 1e-9:
            return
        old_qty, old_avg = pos.quantity, pos.avg_price
        pos.quantity = int(round(old_qty * ratio))
        pos.avg_price = old_avg / ratio
        for attr in ("stop_price", "target_price", "initial_stop", "trail_anchor"):
            v = getattr(pos, attr)
            if v:
                setattr(pos, attr, v / ratio)
        pos.r_unit = pos.r_unit / ratio if pos.r_unit else 0.0
        self.ledger.append(LedgerEntry(
            ts, idx, "SPLIT", instrument, 0.0, round(self.cash, 4),
            f"{ratio}:1 — {old_qty}@{old_avg:.2f} -> {pos.quantity}@{pos.avg_price:.2f}"))

    # ── marking ──
    def mark(self, prices: dict, ts: datetime, idx: int) -> EquityPoint:
        """Mark the book to market and append one equity-curve point."""
        holdings = 0.0
        gross_abs = 0.0
        net_signed = 0.0
        open_n = 0
        gross_holdings = 0.0
        for sym, pos in self.positions.items():
            if pos.quantity == 0:
                continue
            px = prices.get(sym)
            if px is None or not np.isfinite(px):
                continue
            mv = pos.quantity * px
            holdings += mv
            gross_holdings += mv
            gross_abs += abs(mv)
            net_signed += mv
            open_n += 1
            pos.bars_held += 1

        equity = self.cash + holdings
        gross_equity = self._gross_cash + gross_holdings
        self.peak_equity = max(self.peak_equity, equity)
        dd = (equity / self.peak_equity - 1.0) if self.peak_equity > 0 else 0.0

        point = EquityPoint(
            timestamp=ts, bar_index=idx,
            cash=round(self.cash, 2),
            holdings_value=round(holdings, 2),
            equity=round(equity, 2),
            gross_equity=round(gross_equity, 2),
            drawdown=round(dd, 6),
            gross_exposure=round(gross_abs / equity, 4) if equity > 0 else 0.0,
            net_exposure=round(net_signed / equity, 4) if equity > 0 else 0.0,
            open_positions=open_n,
        )
        self.equity_curve.append(point)
        return point

    def update_excursions(self, sym: str, bar_high: float, bar_low: float) -> None:
        """Track MAE/MFE while the position is open (spec §21)."""
        pos = self.positions.get(sym)
        if not pos or pos.quantity == 0 or pos.avg_price <= 0:
            return
        if pos.quantity > 0:
            pos.mae = min(pos.mae, (bar_low - pos.avg_price) / pos.avg_price)
            pos.mfe = max(pos.mfe, (bar_high - pos.avg_price) / pos.avg_price)
        else:
            pos.mae = min(pos.mae, (pos.avg_price - bar_high) / pos.avg_price)
            pos.mfe = max(pos.mfe, (pos.avg_price - bar_low) / pos.avg_price)

    # ── views ──
    @property
    def equity(self) -> float:
        return self.equity_curve[-1].equity if self.equity_curve else self.initial_capital

    @property
    def open_positions(self) -> dict:
        return {k: v for k, v in self.positions.items() if v.quantity != 0}

    def available_cash(self, reserve_fraction: float = 0.0) -> float:
        return max(0.0, self.cash * (1.0 - reserve_fraction))

    def turnover(self) -> float:
        """Sum of traded value / average portfolio value (spec §21)."""
        traded = sum(abs(f.quantity * f.price) for f in self.fills)
        avg_equity = (np.mean([p.equity for p in self.equity_curve])
                      if self.equity_curve else self.initial_capital)
        return float(traded / avg_equity) if avg_equity > 0 else 0.0

    def cost_waterfall(self) -> dict:
        """Spec §35 — gross P&L -> slippage -> charges -> net P&L, exactly."""
        gross_final = (self.equity_curve[-1].gross_equity
                       if self.equity_curve else self.initial_capital)
        net_final = self.equity
        gross_pnl = gross_final - self.initial_capital
        components = {k: round(v, 2) for k, v in self.cost_by_component.items()
                      if abs(v) > 1e-9}
        return {
            "gross_pnl": round(gross_pnl, 2),
            "components": components,
            "total_costs": round(self.total_costs, 2),
            "total_slippage_and_impact": round(self.total_slippage, 2),
            "net_pnl": round(net_final - self.initial_capital, 2),
            "cost_as_pct_of_gross": (
                round(100.0 * (self.total_costs + self.total_slippage) / abs(gross_pnl), 2)
                if abs(gross_pnl) > 1e-9 else None
            ),
        }

    def ledger_dicts(self, limit: int = 500) -> list:
        rows = self.ledger[-limit:]
        return [
            {"timestamp": e.timestamp.isoformat(), "bar": e.bar_index, "kind": e.kind,
             "instrument": e.instrument, "amount": e.amount, "balance": e.balance,
             "note": e.note}
            for e in rows
        ]
