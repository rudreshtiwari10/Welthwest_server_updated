"""
Indian transaction-cost and levy engine (spec §18).

Design rules taken directly from the specification:

  * No rate is hard-coded inside strategy or execution code. Rates live in
    versioned CostSchedule objects with effective dates.
  * A schedule is immutable once published; changing rates means publishing a
    NEW version id, never mutating an old one. Old runs stay reproducible.
  * Transaction levies (STT, stamp duty, GST, exchange/SEBI charges) belong in
    the trade ledger. Capital-gains taxation is a SEPARATE reporting concern
    and is deliberately not folded into P&L here.
  * Every schedule carries `verified_on` and a disclaimer. A static rate table
    is never presented as permanently correct.

Every schedule below must be re-verified against the current official
exchange / SEBI / broker circulars before commercial use.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from services.backtest_india.contracts import OrderSide


@dataclass
class ChargeComponent:
    """One levy line. `basis` says what the rate multiplies."""
    name: str
    rate: float                      # fraction of the basis (0.001 = 0.1%)
    basis: str = "turnover"          # turnover | brokerage | taxable_services
    side: str = "BOTH"               # BUY | SELL | BOTH
    minimum: float = 0.0
    maximum: Optional[float] = None
    percent_cap: Optional[float] = None   # cap as fraction of turnover
    note: str = ""


@dataclass
class CostSchedule:
    """A dated, versioned, segment-specific charge schedule."""
    schedule_id: str
    label: str
    segment: str                      # EQUITY_DELIVERY | EQUITY_INTRADAY | FUTURES | OPTIONS
    effective_from: str
    effective_to: Optional[str]
    currency: str = "INR"
    components: list = field(default_factory=list)
    gst_rate: float = 0.18
    verified_on: str = ""
    source_note: str = ""
    disclaimer: str = (
        "Rates are a point-in-time snapshot of published exchange, SEBI, "
        "state stamp and broker schedules. They change. Re-verify against the "
        "current official circulars before relying on net figures."
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["components"] = [asdict(c) if not isinstance(c, dict) else c
                           for c in self.components]
        return d

    # ── the only calculation entry point ──
    def compute(self, side: OrderSide, quantity: int, price: float) -> tuple[float, dict]:
        """
        Return (total_cost, breakdown) for one fill.

        GST is applied to the taxable service components (brokerage plus the
        exchange/SEBI service charges), matching how Indian brokers bill it.
        """
        turnover = abs(quantity * price)
        side_str = "BUY" if side == OrderSide.BUY else "SELL"
        breakdown: dict = {}
        taxable_services = 0.0

        for comp in self.components:
            c = comp if isinstance(comp, ChargeComponent) else ChargeComponent(**comp)
            if c.side != "BOTH" and c.side != side_str:
                continue
            if c.basis == "turnover":
                amount = c.rate * turnover
            elif c.basis == "brokerage":
                amount = c.rate * breakdown.get("brokerage", 0.0)
            else:
                amount = c.rate * turnover

            if c.percent_cap is not None:
                amount = min(amount, c.percent_cap * turnover)
            if c.minimum:
                amount = max(amount, c.minimum) if turnover > 0 else 0.0
            if c.maximum is not None:
                amount = min(amount, c.maximum)

            amount = round(float(amount), 4)
            breakdown[c.name] = breakdown.get(c.name, 0.0) + amount
            if c.name in ("brokerage", "exchange_transaction_charge", "sebi_turnover_fee"):
                taxable_services += amount

        gst = round(self.gst_rate * taxable_services, 4)
        if gst:
            breakdown["gst"] = gst

        total = round(sum(breakdown.values()), 4)
        return total, breakdown


# ── Published schedules ─────────────────────────────────────────────────────
# Each entry is a snapshot. To change a rate, ADD a new schedule id — never
# edit one in place, or historical runs stop being reproducible.

_SCHEDULES: dict[str, CostSchedule] = {}


def _publish(s: CostSchedule) -> CostSchedule:
    _SCHEDULES[s.schedule_id] = s
    return s


_publish(CostSchedule(
    schedule_id="INDIA_EQUITY_DELIVERY_v20250401",
    label="NSE Equity Delivery — discount broker",
    segment="EQUITY_DELIVERY",
    effective_from="2025-04-01",
    effective_to=None,
    verified_on="2026-08-14",
    source_note=(
        "Modelled on a typical zero-brokerage discount-broker delivery plan "
        "plus published NSE transaction, SEBI turnover, STT and Maharashtra "
        "stamp rates. Verify against your own broker's tariff."
    ),
    components=[
        ChargeComponent("brokerage", 0.0, "turnover", "BOTH",
                        note="Zero-brokerage delivery plan."),
        ChargeComponent("stt", 0.001, "turnover", "BOTH",
                        note="Securities Transaction Tax, delivery, both sides."),
        ChargeComponent("exchange_transaction_charge", 0.0000297, "turnover", "BOTH",
                        note="NSE cash-segment transaction charge."),
        ChargeComponent("sebi_turnover_fee", 0.000001, "turnover", "BOTH",
                        note="SEBI turnover fee (Rs.10 per crore)."),
        ChargeComponent("stamp_duty", 0.00015, "turnover", "BUY",
                        note="Stamp duty on delivery purchases, buy side only."),
    ],
))

_publish(CostSchedule(
    schedule_id="INDIA_EQUITY_INTRADAY_v20250401",
    label="NSE Equity Intraday — discount broker",
    segment="EQUITY_INTRADAY",
    effective_from="2025-04-01",
    effective_to=None,
    verified_on="2026-08-14",
    source_note=(
        "Flat per-order brokerage capped at Rs.20 or 0.03% of turnover, "
        "whichever is lower; STT on the sell leg only."
    ),
    components=[
        ChargeComponent("brokerage", 0.0003, "turnover", "BOTH", maximum=20.0,
                        note="0.03% of turnover, capped at Rs.20 per executed order."),
        ChargeComponent("stt", 0.00025, "turnover", "SELL",
                        note="STT on intraday equity, sell side only."),
        ChargeComponent("exchange_transaction_charge", 0.0000297, "turnover", "BOTH"),
        ChargeComponent("sebi_turnover_fee", 0.000001, "turnover", "BOTH"),
        ChargeComponent("stamp_duty", 0.00003, "turnover", "BUY",
                        note="Intraday stamp duty, buy side only."),
    ],
))

_publish(CostSchedule(
    schedule_id="INDIA_EQUITY_FULL_SERVICE_v20250401",
    label="NSE Equity Delivery — full-service broker",
    segment="EQUITY_DELIVERY",
    effective_from="2025-04-01",
    effective_to=None,
    verified_on="2026-08-14",
    source_note="Percentage brokerage typical of a full-service broker.",
    components=[
        ChargeComponent("brokerage", 0.003, "turnover", "BOTH", minimum=20.0,
                        note="0.30% of turnover with a Rs.20 per-order floor."),
        ChargeComponent("stt", 0.001, "turnover", "BOTH"),
        ChargeComponent("exchange_transaction_charge", 0.0000297, "turnover", "BOTH"),
        ChargeComponent("sebi_turnover_fee", 0.000001, "turnover", "BOTH"),
        ChargeComponent("stamp_duty", 0.00015, "turnover", "BUY"),
    ],
))

_publish(CostSchedule(
    schedule_id="ZERO_COST_v1",
    label="Zero cost (analytical control)",
    segment="EQUITY_DELIVERY",
    effective_from="1900-01-01",
    effective_to=None,
    verified_on="2026-08-14",
    gst_rate=0.0,
    source_note=(
        "Deliberately free of every levy. Used by the engine's own test suite "
        "to prove gross P&L matches the analytical result, and available in the "
        "UI to isolate how much of a result the costs are eating."
    ),
    components=[],
))


def list_cost_schedules() -> list:
    return [
        {
            "schedule_id": s.schedule_id, "label": s.label, "segment": s.segment,
            "effective_from": s.effective_from, "effective_to": s.effective_to,
            "verified_on": s.verified_on, "gst_rate": s.gst_rate,
            "source_note": s.source_note, "disclaimer": s.disclaimer,
            "components": [
                {"name": c.name, "rate": c.rate, "side": c.side, "basis": c.basis,
                 "minimum": c.minimum, "maximum": c.maximum, "note": c.note}
                for c in s.components
            ],
        }
        for s in _SCHEDULES.values()
    ]


def get_cost_schedule(schedule_id: str) -> CostSchedule:
    s = _SCHEDULES.get(schedule_id)
    if not s:
        raise KeyError(
            f"Unknown cost schedule '{schedule_id}'. Available: "
            + ", ".join(sorted(_SCHEDULES))
        )
    return s


def scale_schedule(schedule: CostSchedule, factor: float) -> CostSchedule:
    """
    Produce a stress variant (spec §37: 1.5x / 2x cost runs) as a NEW schedule
    object with its own id. The base schedule is never mutated.
    """
    scaled = CostSchedule(
        schedule_id=f"{schedule.schedule_id}__x{factor:g}",
        label=f"{schedule.label} ({factor:g}x stress)",
        segment=schedule.segment,
        effective_from=schedule.effective_from,
        effective_to=schedule.effective_to,
        gst_rate=schedule.gst_rate,
        verified_on=schedule.verified_on,
        source_note=f"Stress variant of {schedule.schedule_id}; all rates x{factor:g}.",
        components=[
            ChargeComponent(
                name=c.name, rate=c.rate * factor, basis=c.basis, side=c.side,
                minimum=c.minimum * factor,
                maximum=(c.maximum * factor if c.maximum is not None else None),
                percent_cap=c.percent_cap, note=c.note,
            )
            for c in schedule.components
        ],
    )
    return scaled


def capital_gains_note(holding_days_by_trade: list) -> dict:
    """
    Spec §18 — capital-gains treatment is a SEPARATE reporting module, not a
    trade-ledger cost. This returns only a classification summary so the report
    can state holding-period exposure without pretending to compute tax.
    """
    short = sum(1 for d in holding_days_by_trade if d < 365)
    long_ = sum(1 for d in holding_days_by_trade if d >= 365)
    return {
        "trades_under_365_days": short,
        "trades_over_365_days": long_,
        "note": (
            "Holding-period classification only. Capital-gains and business-income "
            "tax depend on instrument, holding period, taxpayer status and "
            "applicable law, and are deliberately excluded from net P&L. "
            "Transaction levies above ARE included."
        ),
    }
