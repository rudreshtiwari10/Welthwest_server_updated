"""Tools: compute_options_greeks, compute_options_payoff."""

import math
from typing import List

from agent.tools.base import Tool, ToolResult


# ---- Black-Scholes helpers --------------------------------------------------


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using the math.erf identity."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_d1_d2(S, K, T, r, sigma, q=0.0):
    """d1, d2 for European Black-Scholes with continuous dividend yield q."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        raise ValueError("S, K must be > 0; T and sigma must be > 0")
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def _bs_price(S, K, T, r, sigma, option_type, q=0.0):
    d1, d2 = _bs_d1_d2(S, K, T, r, sigma, q)
    if option_type == "call":
        return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


def _bs_greeks(S, K, T, r, sigma, option_type, q=0.0):
    d1, d2 = _bs_d1_d2(S, K, T, r, sigma, q)
    pdf = _norm_pdf(d1)
    sqrtT = math.sqrt(T)
    if option_type == "call":
        delta = math.exp(-q * T) * _norm_cdf(d1)
        theta_year = (
            -(S * pdf * sigma * math.exp(-q * T)) / (2.0 * sqrtT)
            - r * K * math.exp(-r * T) * _norm_cdf(d2)
            + q * S * math.exp(-q * T) * _norm_cdf(d1)
        )
        rho = K * T * math.exp(-r * T) * _norm_cdf(d2)
    else:
        delta = -math.exp(-q * T) * _norm_cdf(-d1)
        theta_year = (
            -(S * pdf * sigma * math.exp(-q * T)) / (2.0 * sqrtT)
            + r * K * math.exp(-r * T) * _norm_cdf(-d2)
            - q * S * math.exp(-q * T) * _norm_cdf(-d1)
        )
        rho = -K * T * math.exp(-r * T) * _norm_cdf(-d2)
    gamma = math.exp(-q * T) * pdf / (S * sigma * sqrtT)
    vega = S * math.exp(-q * T) * pdf * sqrtT  # per 1.00 (100%) vol move
    return {
        "delta": delta,
        "gamma": gamma,
        "theta_per_day": theta_year / 365.0,
        "vega_per_1_pct_vol": vega / 100.0,
        "rho_per_1_pct_rate": rho / 100.0,
    }


# ---- Tools ------------------------------------------------------------------


class ComputeOptionsGreeksTool(Tool):
    name = "compute_options_greeks"
    description = (
        "Compute Black-Scholes price + Greeks (delta, gamma, theta, vega, rho) for a "
        "European call or put. Use for any 'what's the delta of …', 'theta of an ATM call', "
        "'how much does the option lose to time decay', etc. Theta is given per day; vega "
        "and rho are scaled per 1 percentage-point move so they're directly intuitive. "
        "Treats Indian index options as European (correct for NIFTY / BANKNIFTY)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "option_type": {
                "type": "string",
                "enum": ["call", "put"],
                "description": "Call or put.",
            },
            "spot": {"type": "number", "description": "Current spot price of the underlying."},
            "strike": {"type": "number", "description": "Strike price."},
            "days_to_expiry": {
                "type": "number",
                "description": "Days remaining until expiry. Fractional OK (e.g., 7.5).",
            },
            "volatility_pct": {
                "type": "number",
                "description": "Annualised volatility in percent (e.g., 18 for 18%). Use historical or implied vol.",
            },
            "risk_free_rate_pct": {
                "type": "number",
                "description": "Annualised risk-free rate in percent (e.g., 6.5 for India 10-year G-sec). Default 6.5.",
            },
            "dividend_yield_pct": {
                "type": "number",
                "description": "Continuous dividend yield in percent (default 0). For NIFTY use ~1.4.",
            },
        },
        "required": ["option_type", "spot", "strike", "days_to_expiry", "volatility_pct"],
    }

    def execute(
        self,
        *,
        option_type: str,
        spot: float,
        strike: float,
        days_to_expiry: float,
        volatility_pct: float,
        risk_free_rate_pct: float = 6.5,
        dividend_yield_pct: float = 0.0,
        **_,
    ) -> ToolResult:
        try:
            option_type = (option_type or "").strip().lower()
            if option_type not in ("call", "put"):
                return ToolResult(success=False, error="option_type must be 'call' or 'put'")
            S = float(spot)
            K = float(strike)
            T = float(days_to_expiry) / 365.0
            sigma = float(volatility_pct) / 100.0
            r = float(risk_free_rate_pct) / 100.0
            q = float(dividend_yield_pct or 0) / 100.0
            if T <= 0:
                return ToolResult(success=False, error="days_to_expiry must be > 0")

            price = _bs_price(S, K, T, r, sigma, option_type, q)
            greeks = _bs_greeks(S, K, T, r, sigma, option_type, q)

            moneyness = "ITM" if (option_type == "call" and S > K) or (option_type == "put" and S < K) else (
                "ATM" if abs(S - K) / K < 0.005 else "OTM"
            )
            intrinsic = max(0, S - K) if option_type == "call" else max(0, K - S)
            time_value = price - intrinsic

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "options_greeks",
                    "inputs": {
                        "option_type": option_type,
                        "spot": S,
                        "strike": K,
                        "days_to_expiry": days_to_expiry,
                        "volatility_pct": volatility_pct,
                        "risk_free_rate_pct": risk_free_rate_pct,
                        "dividend_yield_pct": dividend_yield_pct,
                    },
                    "result": {
                        "theoretical_price": round(price, 2),
                        "intrinsic_value": round(intrinsic, 2),
                        "time_value": round(time_value, 2),
                        "moneyness": moneyness,
                        "delta": round(greeks["delta"], 4),
                        "gamma": round(greeks["gamma"], 6),
                        "theta_per_day": round(greeks["theta_per_day"], 2),
                        "vega_per_1_pct_vol": round(greeks["vega_per_1_pct_vol"], 2),
                        "rho_per_1_pct_rate": round(greeks["rho_per_1_pct_rate"], 2),
                    },
                    "note": (
                        "Greeks computed on Black-Scholes assuming European exercise (correct "
                        "for NIFTY / BANKNIFTY index options). For American single-stock "
                        "options, BS price is a good approximation but exercise can deviate."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Greeks calculation failed: {e}")


class ComputeOptionsPayoffTool(Tool):
    name = "compute_options_payoff"
    description = (
        "Compute the expiry-payoff curve for a multi-leg options strategy (e.g., long call, "
        "iron condor, bull-call spread). Returns the P&L at a range of underlying prices, "
        "the breakevens, max profit, and max loss. Each leg has type (call/put), action "
        "(buy/sell), strike, premium, and quantity. Use for 'iron condor on NIFTY 22000/22200/22800/23000', "
        "'payoff of a covered call', etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "legs": {
                "type": "array",
                "description": "List of legs. Each leg: {option_type: 'call'|'put', action: 'buy'|'sell', strike: number, premium: number, quantity: integer}.",
                "items": {"type": "object"},
            },
            "spot_at_open": {
                "type": "number",
                "description": "Current spot price — used to centre the payoff range.",
            },
            "lot_size": {
                "type": "integer",
                "description": "Lot size (e.g., 25 for NIFTY, 15 for BANKNIFTY). Default 1 for single-share treatment.",
            },
            "spot_range_pct": {
                "type": "number",
                "description": "Width of the payoff range as % around spot (default 20 = ±20%).",
            },
        },
        "required": ["legs", "spot_at_open"],
    }

    def execute(
        self,
        *,
        legs: List[dict],
        spot_at_open: float,
        lot_size: int = 1,
        spot_range_pct: float = 20.0,
        **_,
    ) -> ToolResult:
        try:
            if not legs or not isinstance(legs, (list, tuple)):
                return ToolResult(success=False, error="legs must be a non-empty list")
            spot = float(spot_at_open)
            lot_size = max(1, int(lot_size or 1))
            range_pct = max(1.0, float(spot_range_pct or 20.0))

            normalized = []
            for i, leg in enumerate(legs):
                ot = (leg.get("option_type") or leg.get("type") or "").strip().lower()
                act = (leg.get("action") or leg.get("side") or "").strip().lower()
                if ot not in ("call", "put"):
                    return ToolResult(success=False, error=f"leg {i}: option_type must be 'call' or 'put'")
                if act not in ("buy", "sell"):
                    return ToolResult(success=False, error=f"leg {i}: action must be 'buy' or 'sell'")
                normalized.append({
                    "option_type": ot,
                    "action": act,
                    "strike": float(leg["strike"]),
                    "premium": float(leg["premium"]),
                    "quantity": int(leg.get("quantity") or 1),
                })

            # Build a price grid: 41 points centred on spot
            lo = spot * (1 - range_pct / 100.0)
            hi = spot * (1 + range_pct / 100.0)
            step = (hi - lo) / 40.0
            grid = []
            for i in range(41):
                ST = lo + i * step
                pnl = 0.0
                for leg in normalized:
                    intrinsic = max(0, ST - leg["strike"]) if leg["option_type"] == "call" else max(0, leg["strike"] - ST)
                    if leg["action"] == "buy":
                        leg_pnl = (intrinsic - leg["premium"]) * leg["quantity"] * lot_size
                    else:  # sell
                        leg_pnl = (leg["premium"] - intrinsic) * leg["quantity"] * lot_size
                    pnl += leg_pnl
                grid.append({"underlying": round(ST, 2), "pnl": round(pnl, 2)})

            # Net premium (positive = paid, negative = received)
            net_premium = 0.0
            for leg in normalized:
                contribution = leg["premium"] * leg["quantity"] * lot_size
                net_premium += contribution if leg["action"] == "buy" else -contribution

            # Find breakevens — sign changes in the grid
            breakevens: List[float] = []
            for i in range(1, len(grid)):
                a, b = grid[i - 1], grid[i]
                if (a["pnl"] <= 0 < b["pnl"]) or (a["pnl"] >= 0 > b["pnl"]):
                    # Linear interpolation
                    if a["pnl"] != b["pnl"]:
                        x = a["underlying"] + (0 - a["pnl"]) * (b["underlying"] - a["underlying"]) / (b["pnl"] - a["pnl"])
                        breakevens.append(round(x, 2))

            max_profit = max(p["pnl"] for p in grid)
            max_loss = min(p["pnl"] for p in grid)

            # Detect "unbounded" payoff at the edges (naked long/short)
            def _slope(g, head=True):
                if len(g) < 2:
                    return 0.0
                a, b = (g[0], g[1]) if head else (g[-2], g[-1])
                dx = b["underlying"] - a["underlying"]
                return (b["pnl"] - a["pnl"]) / dx if dx else 0.0

            left_slope = _slope(grid, head=True)
            right_slope = _slope(grid, head=False)
            unbounded_loss = (left_slope < 0 and grid[0]["pnl"] < 0) or (right_slope > 0 and False) or (right_slope < 0 and grid[-1]["pnl"] < 0)
            unbounded_profit = (left_slope < 0 and grid[0]["pnl"] > 0) or (right_slope > 0 and grid[-1]["pnl"] > 0)

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "options_payoff",
                    "inputs": {
                        "legs": normalized,
                        "spot_at_open": spot,
                        "lot_size": lot_size,
                        "spot_range_pct": range_pct,
                    },
                    "result": {
                        "net_premium": round(net_premium, 2),
                        "net_premium_meaning": "positive = paid (debit), negative = received (credit)",
                        "max_profit_in_range": round(max_profit, 2),
                        "max_loss_in_range": round(max_loss, 2),
                        "breakevens": breakevens,
                        "unbounded_profit": bool(unbounded_profit),
                        "unbounded_loss": bool(unbounded_loss),
                    },
                    "payoff_grid": grid,
                    "note": (
                        "Payoff is computed at expiry only. Pre-expiry P&L includes time "
                        "value and depends on volatility — use compute_options_greeks for "
                        "intra-life sensitivity. 'Unbounded' flags trip when the payoff is "
                        "still rising/falling at the edge of the grid; widen spot_range_pct "
                        "or accept that loss/profit is theoretically unlimited."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Payoff calculation failed: {e}")
