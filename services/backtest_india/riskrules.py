"""
Entry / exit / risk rule library (spec §13).

These functions compute LEVELS. They never create fills and never touch the
portfolio — they hand levels to the engine, which turns them into resting
orders that the execution simulator resolves. Keeping levels separate from
fills is what lets the same stop rule behave differently under different
execution assumptions without the strategy signal changing at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class RiskConfig:
    # stop loss
    stop_type: str = "atr"              # atr | percent | structure | none
    stop_atr_multiple: float = 2.0
    stop_percent: float = 3.0
    stop_structure_buffer_atr: float = 0.25

    # take profit
    target_type: str = "r_multiple"     # r_multiple | percent | atr | none
    target_r: float = 2.0
    target_percent: float = 6.0
    target_atr_multiple: float = 4.0

    # trailing / breakeven / time
    trailing_enabled: bool = False
    trailing_type: str = "atr"          # atr | percent
    trailing_atr_multiple: float = 3.0
    trailing_percent: float = 5.0
    breakeven_enabled: bool = False
    breakeven_trigger_r: float = 1.0
    time_stop_bars: int = 0             # 0 disables

    # re-entry and portfolio guards
    cooldown_bars: int = 0
    portfolio_max_drawdown: float = 0.0   # 0 disables; 0.25 = stop at -25%
    max_consecutive_losses: int = 0       # 0 disables

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "RiskConfig":
        d = dict(d or {})
        cfg = cls()
        for k, v in d.items():
            if hasattr(cfg, k) and v is not None:
                cur = getattr(cfg, k)
                try:
                    setattr(cfg, k, bool(v) if isinstance(cur, bool) else type(cur)(v))
                except (TypeError, ValueError):
                    pass
        return cfg

    def describe(self) -> dict:
        return {
            "stop": (
                f"{self.stop_atr_multiple}x ATR" if self.stop_type == "atr" else
                f"{self.stop_percent}%" if self.stop_type == "percent" else
                "last confirmed swing level" if self.stop_type == "structure" else
                "none (position exits on signal only)"
            ),
            "target": (
                f"{self.target_r}R" if self.target_type == "r_multiple" else
                f"{self.target_percent}%" if self.target_type == "percent" else
                f"{self.target_atr_multiple}x ATR" if self.target_type == "atr" else
                "none"
            ),
            "trailing": (
                f"{self.trailing_atr_multiple}x ATR from the best price"
                if self.trailing_enabled and self.trailing_type == "atr" else
                f"{self.trailing_percent}% from the best price"
                if self.trailing_enabled else "off"
            ),
            "breakeven": (f"stop to entry at +{self.breakeven_trigger_r}R"
                          if self.breakeven_enabled else "off"),
            "time_stop": (f"{self.time_stop_bars} bars" if self.time_stop_bars else "off"),
            "cooldown": (f"{self.cooldown_bars} bars after an exit"
                         if self.cooldown_bars else "off"),
            "portfolio_stop": (f"halt new entries below -{self.portfolio_max_drawdown:.0%}"
                               if self.portfolio_max_drawdown else "off"),
        }


def initial_stop(cfg: RiskConfig, entry_price: float, direction: int,
                 atr_value: Optional[float],
                 structure_level: Optional[float] = None) -> Optional[float]:
    """The protective level placed at entry. None means "no stop"."""
    if cfg.stop_type == "none":
        return None

    if cfg.stop_type == "atr":
        if not atr_value or not np.isfinite(atr_value) or atr_value <= 0:
            return None
        return entry_price - direction * cfg.stop_atr_multiple * atr_value

    if cfg.stop_type == "percent":
        return entry_price * (1 - direction * cfg.stop_percent / 100.0)

    if cfg.stop_type == "structure":
        if structure_level is None or not np.isfinite(structure_level):
            # fall back to ATR rather than silently running without a stop
            if atr_value and np.isfinite(atr_value):
                return entry_price - direction * cfg.stop_atr_multiple * atr_value
            return None
        buf = (cfg.stop_structure_buffer_atr * atr_value) if atr_value and np.isfinite(atr_value) else 0.0
        return structure_level - direction * buf

    return None


def initial_target(cfg: RiskConfig, entry_price: float, direction: int,
                   stop_price: Optional[float],
                   atr_value: Optional[float]) -> Optional[float]:
    if cfg.target_type == "none":
        return None

    if cfg.target_type == "r_multiple":
        if stop_price is None:
            return None
        r = abs(entry_price - stop_price)
        if r <= 0:
            return None
        return entry_price + direction * cfg.target_r * r

    if cfg.target_type == "percent":
        return entry_price * (1 + direction * cfg.target_percent / 100.0)

    if cfg.target_type == "atr":
        if not atr_value or not np.isfinite(atr_value):
            return None
        return entry_price + direction * cfg.target_atr_multiple * atr_value

    return None


def update_trailing(cfg: RiskConfig, position, bar_high: float, bar_low: float,
                    atr_value: Optional[float]) -> Optional[float]:
    """
    Trailing stop: highest_since_entry - k*ATR for longs, mirrored for shorts.
    A trailing stop may only ever tighten — it never loosens.
    """
    if not cfg.trailing_enabled or position.quantity == 0:
        return position.stop_price

    d = position.direction
    if d > 0:
        position.trail_anchor = max(position.trail_anchor or bar_high, bar_high)
    else:
        position.trail_anchor = min(position.trail_anchor or bar_low, bar_low)

    if cfg.trailing_type == "atr":
        if not atr_value or not np.isfinite(atr_value):
            return position.stop_price
        candidate = position.trail_anchor - d * cfg.trailing_atr_multiple * atr_value
    else:
        candidate = position.trail_anchor * (1 - d * cfg.trailing_percent / 100.0)

    if position.stop_price is None:
        return candidate
    return max(position.stop_price, candidate) if d > 0 else min(position.stop_price, candidate)


def apply_breakeven(cfg: RiskConfig, position, current_price: float) -> Optional[float]:
    """Move the stop to entry once the trade is +N R in the money."""
    if not cfg.breakeven_enabled or position.breakeven_armed or position.quantity == 0:
        return position.stop_price
    if not position.r_unit or position.r_unit <= 0:
        return position.stop_price

    d = position.direction
    gain_r = d * (current_price - position.avg_price) / position.r_unit
    if gain_r < cfg.breakeven_trigger_r:
        return position.stop_price

    position.breakeven_armed = True
    entry = position.avg_price
    if position.stop_price is None:
        return entry
    return max(position.stop_price, entry) if d > 0 else min(position.stop_price, entry)


def catalogue() -> dict:
    return {
        "stop_types": [
            {"key": "atr", "label": "ATR multiple", "params": {"stop_atr_multiple": 2.0}},
            {"key": "percent", "label": "Fixed percent", "params": {"stop_percent": 3.0}},
            {"key": "structure", "label": "Confirmed swing level",
             "params": {"stop_structure_buffer_atr": 0.25},
             "note": "Uses the last swing confirmed k bars earlier, never an "
                     "unconfirmed pivot."},
            {"key": "none", "label": "No stop (signal exit only)", "params": {}},
        ],
        "target_types": [
            {"key": "r_multiple", "label": "R multiple", "params": {"target_r": 2.0}},
            {"key": "percent", "label": "Fixed percent", "params": {"target_percent": 6.0}},
            {"key": "atr", "label": "ATR multiple", "params": {"target_atr_multiple": 4.0}},
            {"key": "none", "label": "No target", "params": {}},
        ],
        "modifiers": [
            {"key": "trailing_enabled", "label": "Trailing stop"},
            {"key": "breakeven_enabled", "label": "Move stop to breakeven at +R"},
            {"key": "time_stop_bars", "label": "Time stop (bars)"},
            {"key": "cooldown_bars", "label": "Cooldown after exit (bars)"},
            {"key": "portfolio_max_drawdown", "label": "Portfolio drawdown halt"},
            {"key": "max_consecutive_losses", "label": "Halt after N consecutive losses"},
        ],
    }
