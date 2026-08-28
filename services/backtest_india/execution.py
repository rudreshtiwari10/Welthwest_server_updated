"""
Order and execution simulator (spec §15, §16, §17, §32).

The single hard rule: fills are produced HERE and nowhere else. The signal
engine may only create orders. This is what makes "never assume every order
fills at the candle close" structurally true rather than a promise.

Timeline for a decision taken on bar i:
    bar i close  -> signal
                 -> order created, stamped eligible at bar i + latency_bars
                    (latency_bars >= 1, always)
    bar i+L      -> the simulator attempts a fill against bar i+L's own
                    OHLCV, using the reference price implied by the order type

A market order therefore fills near the NEXT bar's open, not the signal bar's
close. Nothing in the engine can shortcut that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from services.backtest_india.contracts import (
    Bar, Fill, Order, OrderSide, OrderStatus, IntrabarPolicy, RealismLevel,
)
from services.backtest_india.costs import CostSchedule


# ── Slippage / spread / impact models ───────────────────────────────────────

@dataclass
class ExecutionModel:
    """
    Everything about how an order becomes a price.

    slippage_model:
      "fixed_bps"        — constant s, the honest baseline
      "volatility"       — s scales with the bar's ATR/close ratio
      "liquidity"        — s scales with sqrt(order size / bar volume)
      "vol_liquidity"    — both, added
      "none"             — analytical control (used by the test suite)
    """
    slippage_model: str = "vol_liquidity"
    slippage_bps: float = 5.0            # base s, in basis points
    volatility_coeff: float = 0.5        # multiplies normalised ATR (in bps terms)
    liquidity_coeff: float = 15.0        # multiplies sqrt(participation)
    synthetic_spread_bps: float = 3.0    # used only when no bid/ask exists
    use_synthetic_spread: bool = True
    impact_enabled: bool = False         # spec §15 research-mode impact model
    impact_a: float = 0.0
    impact_b: float = 10.0
    impact_c: float = 5.0
    impact_gamma: float = 0.6
    latency_bars: int = 1                # >= 1, enforced
    latency_ms: int = 500                # reported for the audit trail
    participation_rate: float = 0.05     # max fraction of a bar's volume
    allow_partial_fills: bool = True
    time_in_force_bars: int = 3
    market_reference: str = "open"       # open | typical  (of the execution bar)

    def realism_level(self) -> RealismLevel:
        if self.participation_rate > 0 and self.latency_bars >= 1:
            return RealismLevel.L3_PARTICIPATION
        if self.use_synthetic_spread or self.slippage_model != "none":
            return RealismLevel.L2_SYNTHETIC_SPREAD
        return RealismLevel.L1_OHLCV

    def describe(self) -> dict:
        return {
            "slippage_model": self.slippage_model,
            "slippage_bps": self.slippage_bps,
            "synthetic_spread_bps": self.synthetic_spread_bps if self.use_synthetic_spread else 0,
            "impact_enabled": self.impact_enabled,
            "latency_bars": self.latency_bars,
            "latency_ms": self.latency_ms,
            "participation_rate": self.participation_rate,
            "allow_partial_fills": self.allow_partial_fills,
            "time_in_force_bars": self.time_in_force_bars,
            "realism_level": int(self.realism_level()),
            "realism_note": (
                "Level 3: OHLCV bars with a synthetic spread, a volatility- and "
                "liquidity-linked slippage model, volume participation caps and "
                "at least one bar of execution latency. No real bid/ask or tick "
                "data is used, so the spread is modelled, not observed."
            ),
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "ExecutionModel":
        d = dict(d or {})
        model = cls()
        for k, v in d.items():
            if hasattr(model, k) and v is not None:
                setattr(model, k, type(getattr(model, k))(v)
                        if not isinstance(getattr(model, k), bool)
                        else bool(v))
        model.latency_bars = max(1, int(model.latency_bars))
        model.participation_rate = max(0.0, float(model.participation_rate))
        return model


def slippage_bps(model: ExecutionModel, bar: Bar, quantity: int,
                 atr_value: Optional[float]) -> float:
    """Total one-way slippage in basis points for this order on this bar."""
    if model.slippage_model == "none":
        return 0.0

    s = float(model.slippage_bps)

    if model.slippage_model in ("volatility", "vol_liquidity") and atr_value:
        if bar.close > 0 and np.isfinite(atr_value):
            natr_bps = 10000.0 * (atr_value / bar.close)
            s += model.volatility_coeff * natr_bps * 0.01   # 1% of the ATR band

    if model.slippage_model in ("liquidity", "vol_liquidity"):
        if bar.volume and bar.volume > 0:
            participation = min(1.0, abs(quantity) / bar.volume)
            s += model.liquidity_coeff * math.sqrt(participation)
        else:
            s += model.liquidity_coeff   # no volume observed: assume the worst

    if model.use_synthetic_spread:
        # crossing the spread costs half of it per side
        s += model.synthetic_spread_bps / 2.0

    return max(0.0, s)


def impact_bps(model: ExecutionModel, quantity: int, adv: float,
               volatility: float) -> float:
    """Spec §15 research-mode impact: a + b*sigma*sqrt(Q/ADV) + c*(Q/ADV)^gamma."""
    if not model.impact_enabled or not adv or adv <= 0:
        return 0.0
    ratio = abs(quantity) / adv
    sigma = volatility if (volatility and np.isfinite(volatility)) else 0.0
    return (model.impact_a
            + model.impact_b * sigma * math.sqrt(ratio)
            + model.impact_c * (ratio ** model.impact_gamma))


# ── Fill attempt ────────────────────────────────────────────────────────────

@dataclass
class FillAttempt:
    filled_quantity: int = 0
    price: float = 0.0
    reference_price: float = 0.0
    slippage_value: float = 0.0
    impact_value: float = 0.0
    participation: float = 0.0
    rejected_reason: str = ""


def _reference_price(order: Order, bar: Bar, model: ExecutionModel) -> tuple[float, str]:
    """
    The pre-slippage price the order would transact against on this bar.

    Returns (price, reason) — reason is non-empty when the order cannot trade
    on this bar at all (limit not touched, stop not triggered).
    """
    if order.order_type.value == "MARKET":
        ref = bar.open if model.market_reference == "open" else bar.typical
        return float(ref), ""

    if order.order_type.value == "LIMIT":
        lp = float(order.limit_price)
        if order.side == OrderSide.BUY:
            if bar.low <= lp:
                # if the bar gapped through the limit, we get the better open
                return (min(lp, bar.open), "")
            return 0.0, "limit not touched"
        if bar.high >= lp:
            return (max(lp, bar.open), "")
        return 0.0, "limit not touched"

    # STOP
    sp = float(order.stop_price)
    if order.side == OrderSide.BUY:
        if bar.high >= sp:
            return (max(sp, bar.open), "")
        return 0.0, "stop not triggered"
    if bar.low <= sp:
        return (min(sp, bar.open), "")
    return 0.0, "stop not triggered"


def attempt_fill(order: Order, bar: Bar, model: ExecutionModel,
                 atr_value: Optional[float] = None,
                 adv: Optional[float] = None,
                 volatility: Optional[float] = None) -> FillAttempt:
    """Try to execute `order` against `bar`. May return a partial fill."""
    ref, reason = _reference_price(order, bar, model)
    if reason:
        return FillAttempt(rejected_reason=reason)
    if ref <= 0 or not np.isfinite(ref):
        return FillAttempt(rejected_reason="no usable reference price")

    want = order.remaining
    if want <= 0:
        return FillAttempt(rejected_reason="nothing left to fill")

    # participation constraint
    fillable = want
    if model.participation_rate > 0:
        if bar.volume and bar.volume > 0:
            cap = int(math.floor(model.participation_rate * bar.volume))
            if cap < want:
                if not model.allow_partial_fills:
                    return FillAttempt(rejected_reason="participation cap, partials disabled")
                fillable = max(0, cap)
        else:
            return FillAttempt(rejected_reason="zero volume bar — no liquidity to trade against")
    if fillable <= 0:
        return FillAttempt(rejected_reason="participation cap allows zero quantity")

    sign = 1 if order.side == OrderSide.BUY else -1
    s_bps = slippage_bps(model, bar, fillable, atr_value)
    i_bps = impact_bps(model, fillable, adv or 0.0, volatility or 0.0)

    # Slippage always worsens the fill: buys pay up, sells receive less.
    price = ref * (1.0 + sign * (s_bps + i_bps) / 10000.0)
    price = max(0.01, float(price))

    # a fill can never print outside the bar's own range
    price = float(np.clip(price, bar.low * 0.995, bar.high * 1.005))

    return FillAttempt(
        filled_quantity=int(fillable),
        price=price,
        reference_price=float(ref),
        slippage_value=abs(price - ref) * fillable * (s_bps / max(1e-9, s_bps + i_bps))
        if (s_bps + i_bps) > 0 else 0.0,
        impact_value=abs(price - ref) * fillable * (i_bps / max(1e-9, s_bps + i_bps))
        if (s_bps + i_bps) > 0 else 0.0,
        participation=(fillable / bar.volume) if bar.volume else 0.0,
    )


def build_fill(order: Order, attempt: FillAttempt, bar: Bar, bar_index: int,
               schedule: CostSchedule, fill_seq: int) -> Fill:
    """Turn a successful attempt into a costed Fill ledger entry."""
    total_cost, breakdown = schedule.compute(order.side, attempt.filled_quantity, attempt.price)
    return Fill(
        fill_id=f"F{fill_seq:06d}",
        order_id=order.order_id,
        instrument=order.instrument,
        side=order.side,
        quantity=attempt.filled_quantity,
        price=round(attempt.price, 4),
        reference_price=round(attempt.reference_price, 4),
        timestamp=bar.event_time,
        bar_index=bar_index,
        slippage_value=round(attempt.slippage_value, 4),
        impact_value=round(attempt.impact_value, 4),
        costs=breakdown,
        total_cost=total_cost,
        participation=round(attempt.participation, 6),
    )


# ── Intrabar ambiguity (spec §16) ───────────────────────────────────────────

def resolve_intrabar(bar: Bar, direction: int, stop: Optional[float],
                     target: Optional[float], policy: str) -> tuple[Optional[str], Optional[float]]:
    """
    Decide what happened first when BOTH a stop and a target sit inside one bar.

    Daily OHLC genuinely cannot tell us the order of events. The engine refuses
    to guess favourably by default: CONSERVATIVE assumes the adverse level was
    hit first, which is the only assumption that cannot flatter a backtest.

    Returns (event, price) where event is "STOP" | "TARGET" | None.
    """
    hit_stop = hit_target = False
    if stop is not None:
        hit_stop = (bar.low <= stop) if direction > 0 else (bar.high >= stop)
    if target is not None:
        hit_target = (bar.high >= target) if direction > 0 else (bar.low <= target)

    if not hit_stop and not hit_target:
        return None, None
    if hit_stop and not hit_target:
        return "STOP", stop
    if hit_target and not hit_stop:
        return "TARGET", target

    # both inside the same bar — the ambiguous case
    p = (policy or IntrabarPolicy.CONSERVATIVE.value).lower()
    if p == IntrabarPolicy.OPTIMISTIC.value:
        return "TARGET", target
    if p == IntrabarPolicy.PRIORITY_TARGET.value:
        return "TARGET", target
    # conservative / priority_stop
    return "STOP", stop


def gap_adjusted_exit(bar: Bar, direction: int, level: float, kind: str) -> float:
    """
    A stop does not fill at the stop price when the bar gaps through it. The
    realistic fill is the open, and pretending otherwise is one of the largest
    silent sources of backtest optimism.
    """
    if kind == "STOP":
        if direction > 0 and bar.open < level:
            return float(bar.open)
        if direction < 0 and bar.open > level:
            return float(bar.open)
    else:  # TARGET — a favourable gap is real and should be credited
        if direction > 0 and bar.open > level:
            return float(bar.open)
        if direction < 0 and bar.open < level:
            return float(bar.open)
    return float(level)


def catalogue() -> dict:
    return {
        "slippage_models": [
            {"key": "none", "label": "None (analytical control)",
             "description": "No slippage at all. Use only to verify the engine's arithmetic."},
            {"key": "fixed_bps", "label": "Fixed basis points",
             "description": "Constant cost per side, independent of size or volatility."},
            {"key": "volatility", "label": "Volatility-linked",
             "description": "Scales with the bar's ATR relative to price."},
            {"key": "liquidity", "label": "Liquidity-linked",
             "description": "Scales with sqrt(order size / bar volume)."},
            {"key": "vol_liquidity", "label": "Volatility + liquidity (default)",
             "description": "Both effects added. The most defensible OHLCV-only model."},
        ],
        "order_types": ["MARKET", "LIMIT", "STOP"],
        "intrabar_policies": [
            {"key": "conservative", "label": "Conservative (default)",
             "description": "When a stop and a target both sit inside one bar, assume "
                            "the stop was hit first. Cannot flatter the result."},
            {"key": "optimistic", "label": "Optimistic",
             "description": "Assume the target was hit first. Clearly labelled as "
                            "optimistic wherever it is used."},
            {"key": "priority_stop", "label": "Deterministic: stop first",
             "description": "Explicit priority rule, stop wins."},
            {"key": "priority_target", "label": "Deterministic: target first",
             "description": "Explicit priority rule, target wins."},
        ],
        "realism_levels": [
            {"level": 1, "label": "OHLCV only"},
            {"level": 2, "label": "OHLCV + synthetic spread / slippage"},
            {"level": 3, "label": "+ participation cap + latency (this engine's default)"},
            {"level": 4, "label": "Tick / order-book replay (data not available)"},
        ],
    }
