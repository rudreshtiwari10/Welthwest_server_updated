"""
Position-sizing models (spec §14).

Sizing answers "how many shares", never "at what price" — that is the
execution simulator's job. Every model returns a raw desired quantity, and
`apply_caps` then reduces it by the binding constraint, reporting WHICH
constraint bound. Users should be able to see that a strategy's real position
size was set by liquidity, not by their risk rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class SizingResult:
    quantity: int
    requested_quantity: int
    binding_constraint: str      # sizing_model | cash | max_weight | liquidity | none
    notes: dict


def _floor_pos(x: float) -> int:
    if not np.isfinite(x) or x <= 0:
        return 0
    return int(math.floor(x))


def desired_quantity(
    model: str,
    price: float,
    equity: float,
    params: dict,
    stop_distance: Optional[float] = None,
    atr: Optional[float] = None,
    realized_vol: Optional[float] = None,
    n_positions: int = 1,
) -> tuple[int, str]:
    """Raw quantity from the chosen model, before any cap is applied."""
    model = (model or "percent_equity").lower()
    if price <= 0 or not np.isfinite(price):
        return 0, "invalid price"

    if model == "fixed_quantity":
        return max(0, int(params.get("quantity", 1))), "fixed quantity"

    if model == "fixed_capital":
        alloc = float(params.get("capital", 100_000))
        return _floor_pos(alloc / price), "fixed capital allocation"

    if model == "percent_equity":
        w = float(params.get("weight", 0.10))
        return _floor_pos(w * equity / price), f"{w:.1%} of equity"

    if model == "risk_per_trade":
        f = float(params.get("fraction", 0.005))
        if not stop_distance or stop_distance <= 0:
            return 0, "risk_per_trade needs a stop distance"
        return _floor_pos((f * equity) / stop_distance), \
            f"{f:.2%} equity risk / Rs.{stop_distance:.2f} stop"

    if model == "atr_risk":
        f = float(params.get("fraction", 0.005))
        k = float(params.get("atr_multiple", 2.0))
        if not atr or atr <= 0 or not np.isfinite(atr):
            return 0, "atr_risk needs a valid ATR"
        return _floor_pos((f * equity) / (k * atr)), \
            f"{f:.2%} equity risk / {k}x ATR"

    if model == "volatility_target":
        target = float(params.get("target_vol", 0.20))
        cap_w = float(params.get("max_weight", 0.25))
        if not realized_vol or realized_vol <= 0 or not np.isfinite(realized_vol):
            return 0, "volatility_target needs realised volatility"
        w = min(cap_w, target / realized_vol)
        return _floor_pos(w * equity / price), \
            f"vol target {target:.0%} / realised {realized_vol:.0%} -> {w:.1%}"

    if model == "equal_weight":
        n = max(1, int(params.get("slots", n_positions)))
        return _floor_pos((equity / n) / price), f"equal weight across {n} slots"

    if model == "inverse_volatility":
        # weight is normalised by the caller across the active basket; here we
        # take the pre-computed weight it passes in
        w = float(params.get("weight", 0.10))
        return _floor_pos(w * equity / price), f"inverse-vol weight {w:.1%}"

    if model == "kelly_capped":
        # Spec §14: research only, cap aggressively — raw Kelly is unstable
        # because p and b are themselves estimates.
        p = float(params.get("win_rate", 0.5))
        b = float(params.get("payoff", 1.0))
        cap = float(params.get("cap", 0.10))
        if b <= 0:
            return 0, "kelly needs a positive payoff ratio"
        f_star = max(0.0, p - (1 - p) / b)
        w = min(cap, f_star * float(params.get("fraction_of_kelly", 0.25)))
        return _floor_pos(w * equity / price), \
            f"capped Kelly {w:.1%} (raw f*={f_star:.2f})"

    return 0, f"unknown sizing model '{model}'"


def apply_caps(
    raw_qty: int,
    price: float,
    equity: float,
    available_cash: float,
    max_position_weight: float,
    bar_volume: float,
    participation_rate: float,
    min_quantity: int = 1,
    lot_size: int = 1,
) -> SizingResult:
    """
    Spec §14/§15 — final size is min(sizing, cash, weight cap, liquidity cap),
    and the report names the binding constraint.
    """
    notes = {"raw": raw_qty}
    qty = raw_qty
    binding = "sizing_model"

    cash_qty = _floor_pos(available_cash / price) if price > 0 else 0
    notes["cash_cap"] = cash_qty
    if cash_qty < qty:
        qty, binding = cash_qty, "cash"

    weight_qty = _floor_pos(max_position_weight * equity / price) if price > 0 else 0
    notes["weight_cap"] = weight_qty
    if weight_qty < qty:
        qty, binding = weight_qty, "max_weight"

    if participation_rate > 0 and bar_volume and bar_volume > 0:
        liq_qty = _floor_pos(participation_rate * bar_volume)
        notes["liquidity_cap"] = liq_qty
        if liq_qty < qty:
            qty, binding = liq_qty, "liquidity"
    else:
        notes["liquidity_cap"] = None

    if lot_size > 1:
        qty = (qty // lot_size) * lot_size

    if qty < min_quantity:
        qty = 0
        if binding == "sizing_model":
            binding = "below_minimum"

    return SizingResult(quantity=int(qty), requested_quantity=int(raw_qty),
                        binding_constraint=binding if qty < raw_qty else "none",
                        notes=notes)


def inverse_vol_weights(vols: dict) -> dict:
    """w_i = (1/sigma_i) / sum_j (1/sigma_j), skipping undefined vols."""
    inv = {k: 1.0 / v for k, v in vols.items()
           if v and np.isfinite(v) and v > 0}
    total = sum(inv.values())
    if total <= 0:
        n = max(1, len(vols))
        return {k: 1.0 / n for k in vols}
    return {k: v / total for k, v in inv.items()}


SIZING_MODELS = {
    "fixed_quantity": ("Fixed quantity", {"quantity": 100},
                       "Always trade the same share count."),
    "fixed_capital": ("Fixed capital", {"capital": 100000},
                      "floor(allocation / entry price)."),
    "percent_equity": ("Percent of equity", {"weight": 0.10},
                       "floor(w x equity / entry price)."),
    "risk_per_trade": ("Risk per trade", {"fraction": 0.005},
                       "risk budget = f x equity; quantity = budget / |entry - stop|. "
                       "Requires a stop to be defined."),
    "atr_risk": ("ATR risk sizing", {"fraction": 0.005, "atr_multiple": 2.0},
                 "quantity = (f x equity) / (k x ATR)."),
    "volatility_target": ("Volatility target", {"target_vol": 0.20, "max_weight": 0.25},
                          "Weight scales with target_vol / realised_vol, then capped."),
    "equal_weight": ("Equal weight", {"slots": 5},
                     "Equity split evenly across a fixed number of slots."),
    "inverse_volatility": ("Inverse volatility", {"weight": 0.10},
                           "Weight inversely proportional to realised volatility."),
    "kelly_capped": ("Capped Kelly (research only)",
                     {"win_rate": 0.5, "payoff": 1.5, "cap": 0.10,
                      "fraction_of_kelly": 0.25},
                     "f* = p - q/b, then deliberately fractioned and capped. "
                     "Raw Kelly is unstable under parameter uncertainty."),
}


def catalogue() -> list:
    return [
        {"key": k, "label": lbl, "params": p, "description": d}
        for k, (lbl, p, d) in SIZING_MODELS.items()
    ]
