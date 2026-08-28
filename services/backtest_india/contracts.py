"""
Typed data contracts for the backtest_india engine.

Spec references: §3 (data model / information-time contract), §11 (pattern
output contract), §15 (order representation), §34 (reproducibility fields).

Everything the engine passes between stages is one of these types. Raw dicts
only appear at the API boundary (request in, JSON report out).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ── Enumerations ────────────────────────────────────────────────────────────

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"          # created, still inside the latency queue
    WORKING = "WORKING"          # live at the venue, awaiting a fill
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_STOP = "TIME_STOP"
    SIGNAL_EXIT = "SIGNAL_EXIT"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    PORTFOLIO_STOP = "PORTFOLIO_STOP"
    END_OF_TEST = "END_OF_TEST"
    DELISTED = "DELISTED"


class RealismLevel(int, Enum):
    """Spec §32 — microstructure realism the run actually achieved."""
    L1_OHLCV = 1                 # bar prices only
    L2_SYNTHETIC_SPREAD = 2      # + synthetic spread / slippage model
    L3_PARTICIPATION = 3         # + volume participation + latency
    L4_TICK_REPLAY = 4           # + real bid/ask or tick replay (not available)


class IntrabarPolicy(str, Enum):
    """Spec §16 — how to resolve stop-and-target-in-the-same-bar ambiguity."""
    CONSERVATIVE = "conservative"   # adverse event assumed first  (default)
    OPTIMISTIC = "optimistic"       # favourable event assumed first
    PRIORITY_STOP = "priority_stop"
    PRIORITY_TARGET = "priority_target"


class ConfidenceLabel(str, Enum):
    """Spec §35 — headline confidence label. Never a probability."""
    ROBUST = "Robust"
    VALIDATED = "Validated"
    RESEARCH = "Research"
    FRAGILE = "Fragile"
    FAILED = "Failed"


# ── Market data ─────────────────────────────────────────────────────────────

@dataclass
class Bar:
    """
    A single point-in-time OHLCV observation (spec §3).

    `event_time` is when the bar's period ended. `availability_time` is when a
    strategy is legally allowed to read it. For a daily bar operating at close,
    availability_time == event_time and the earliest executable event is the
    NEXT bar — the engine enforces this, never the strategy.
    """
    instrument: str
    event_time: datetime
    availability_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    # corporate-action state carried on the bar it applies to
    dividend: float = 0.0
    split_ratio: float = 1.0
    # data-quality flags raised by the feed auditor
    flags: tuple = ()
    session: str = "REGULAR"

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def median(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def traded_value(self) -> float:
        return self.close * self.volume


# ── Orders, fills, positions, trades ────────────────────────────────────────

@dataclass
class Order:
    """Spec §15 — an order request, before any fill is known."""
    order_id: str
    instrument: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    created_time: datetime
    # the bar index at which the order becomes eligible for execution
    # (creation bar + latency bars). Enforces "no same-bar close fills".
    eligible_index: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force_bars: int = 1
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    reason: str = ""
    intent: str = "ENTRY"        # ENTRY | EXIT | REVERSE | REBALANCE
    meta: dict = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        return max(0, self.quantity - self.filled_quantity)


@dataclass
class Fill:
    """A realised execution. Every rupee of cost traces back to one of these."""
    fill_id: str
    order_id: str
    instrument: str
    side: OrderSide
    quantity: int
    price: float                 # final execution price incl. slippage/impact
    reference_price: float       # pre-slippage reference the model started from
    timestamp: datetime
    bar_index: int
    slippage_value: float = 0.0
    impact_value: float = 0.0
    costs: dict = field(default_factory=dict)   # component -> rupees
    total_cost: float = 0.0
    participation: float = 0.0   # quantity / bar volume
    notes: str = ""


@dataclass
class Position:
    """Open exposure in one instrument, average-cost accounted."""
    instrument: str
    quantity: int = 0
    avg_price: float = 0.0
    entry_time: Optional[datetime] = None
    entry_index: int = 0
    entry_cost: float = 0.0      # cumulative transaction cost attributed
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    initial_stop: Optional[float] = None
    trail_anchor: Optional[float] = None
    breakeven_armed: bool = False
    bars_held: int = 0
    mae: float = 0.0             # worst adverse excursion, fraction
    mfe: float = 0.0             # best favourable excursion, fraction
    r_unit: float = 0.0          # |entry - initial stop| in price terms

    @property
    def is_open(self) -> bool:
        return self.quantity != 0

    @property
    def direction(self) -> int:
        return 1 if self.quantity > 0 else (-1 if self.quantity < 0 else 0)


@dataclass
class Trade:
    """A completed round trip, reconstructed from the fill ledger."""
    trade_id: str
    instrument: str
    direction: str               # LONG | SHORT
    entry_time: datetime
    exit_time: datetime
    entry_index: int
    exit_index: int
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    costs: float
    net_pnl: float
    return_pct: float            # net, on deployed capital
    r_multiple: Optional[float]
    bars_held: int
    exit_reason: str
    mae: float
    mfe: float
    entry_reason: str = ""
    cost_breakdown: dict = field(default_factory=dict)


# ── Run configuration ───────────────────────────────────────────────────────

@dataclass
class RunConfig:
    """
    The complete, hashable description of one experiment (spec §34).

    Two runs with the same config hash MUST produce identical output. The
    engine seeds every stochastic component from `seed`.
    """
    # universe / data
    symbols: list
    start: str
    end: str
    timeframe: str = "1d"
    exchange: str = "NSE"
    survivorship_mode: str = "point_in_time"   # or "current_members" (flagged)

    # strategy
    strategy: dict = field(default_factory=dict)     # the strategy graph
    strategy_name: str = "custom"

    # capital & sizing
    initial_capital: float = 1_000_000.0
    sizing: dict = field(default_factory=lambda: {"model": "percent_equity", "weight": 0.10})
    max_concurrent_positions: int = 5
    max_position_weight: float = 0.25
    allow_short: bool = False

    # risk
    risk: dict = field(default_factory=dict)

    # execution
    execution: dict = field(default_factory=dict)
    intrabar_policy: str = IntrabarPolicy.CONSERVATIVE.value

    # costs
    cost_schedule: str = "INDIA_EQUITY_DELIVERY_v20250401"

    # validation & analysis
    validation: dict = field(default_factory=dict)
    benchmark: str = "^NSEI"
    diagnostics: dict = field(default_factory=dict)
    robustness: dict = field(default_factory=dict)

    seed: int = 42
    engine_version: str = "2.0.0"

    def to_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        """Deterministic hash over the whole config — the run's identity."""
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def strategy_hash(self) -> str:
        payload = json.dumps(self.strategy, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_dict(cls, data: dict) -> "RunConfig":
        known = {f for f in cls.__dataclass_fields__}          # noqa: F821
        clean = {k: v for k, v in (data or {}).items() if k in known}
        if isinstance(clean.get("symbols"), str):
            clean["symbols"] = [s.strip() for s in clean["symbols"].split(",") if s.strip()]
        return cls(**clean)


# ── Pattern / signal contracts ──────────────────────────────────────────────

@dataclass
class PatternEvent:
    """
    Spec §11 — every detector emits this shape. `anchor_index` may point at
    bars far in the past; `detection_index` is the first bar at which the
    pattern was knowable; `confirmation_index` is when it became tradable.
    Forward-outcome fields deliberately live in a separate table.
    """
    pattern_id: str
    instrument: str
    direction: str                       # BULLISH | BEARISH | NEUTRAL
    anchor_indices: list
    detection_index: int
    confirmation_index: Optional[int]
    trigger_level: Optional[float]
    invalidation_level: Optional[float]
    quality: dict = field(default_factory=dict)   # component scores, not a probability
    params: dict = field(default_factory=dict)
    tolerance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Signal:
    """Strategy-graph output for one instrument at one bar."""
    instrument: str
    bar_index: int
    timestamp: datetime
    action: str                          # ENTER_LONG | ENTER_SHORT | EXIT | NONE
    strength: float = 1.0
    reason: str = ""
    context: dict = field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
