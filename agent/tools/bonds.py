"""Tools: compute_bond_pricing, compute_bond_duration."""

from typing import List

from agent.tools.base import Tool, ToolResult


def _coupon_amount(face: float, coupon_rate_pct: float, freq: int) -> float:
    return face * (coupon_rate_pct / 100.0) / freq


def _bond_cash_flows(face: float, coupon_rate_pct: float, years_to_maturity: float, freq: int) -> List[tuple]:
    """Return list of (t_in_years, cashflow) pairs."""
    n_periods = max(1, int(round(years_to_maturity * freq)))
    period_len = 1.0 / freq
    coupon = _coupon_amount(face, coupon_rate_pct, freq)
    flows = []
    for i in range(1, n_periods + 1):
        cf = coupon
        if i == n_periods:
            cf += face
        flows.append((i * period_len, cf))
    return flows


def _present_value(flows: List[tuple], ytm_pct: float, freq: int) -> float:
    r_periodic = (ytm_pct / 100.0) / freq
    return sum(cf / ((1 + r_periodic) ** (t * freq)) for t, cf in flows)


_FREQ_MAP = {
    "annual": 1, "annually": 1,
    "semiannual": 2, "semi": 2, "semi-annual": 2,
    "quarterly": 4,
    "monthly": 12,
}


class ComputeBondPricingTool(Tool):
    name = "compute_bond_pricing"
    description = (
        "Compute the present value (clean price) of a fixed-coupon bond given face "
        "value, coupon rate, years to maturity, yield-to-maturity, and coupon "
        "frequency. Use for 'price of a 10-year G-sec at 7% yield', 'how does a 50bp "
        "yield rise affect the price', etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "face_value": {"type": "number", "description": "Face / par value of the bond (e.g., 1000, 100000)."},
            "coupon_rate_pct": {"type": "number", "description": "Annual coupon rate in percent (e.g., 7.26)."},
            "years_to_maturity": {"type": "number", "description": "Years until maturity (can be fractional)."},
            "ytm_pct": {"type": "number", "description": "Yield to maturity in percent (e.g., 7.0)."},
            "frequency": {"type": "string", "enum": ["annual", "semiannual", "quarterly", "monthly"], "description": "Coupon frequency. Default 'semiannual' (most G-secs)."},
        },
        "required": ["face_value", "coupon_rate_pct", "years_to_maturity", "ytm_pct"],
    }

    def execute(
        self,
        *,
        face_value: float,
        coupon_rate_pct: float,
        years_to_maturity: float,
        ytm_pct: float,
        frequency: str = "semiannual",
        **_,
    ) -> ToolResult:
        try:
            face = float(face_value)
            coupon = float(coupon_rate_pct)
            yrs = float(years_to_maturity)
            ytm = float(ytm_pct)
            freq = _FREQ_MAP.get((frequency or "semiannual").strip().lower())
            if not freq:
                return ToolResult(success=False, error=f"unknown frequency '{frequency}'")
            if face <= 0 or yrs <= 0:
                return ToolResult(success=False, error="face_value and years_to_maturity must be > 0")

            flows = _bond_cash_flows(face, coupon, yrs, freq)
            price = _present_value(flows, ytm, freq)
            premium_or_discount = price - face

            # Current yield = annual coupon / price
            annual_coupon = face * coupon / 100.0
            current_yield = annual_coupon / price * 100.0 if price > 0 else 0

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "bond_pricing",
                    "inputs": {
                        "face_value": face,
                        "coupon_rate_pct": coupon,
                        "years_to_maturity": yrs,
                        "ytm_pct": ytm,
                        "frequency": frequency,
                    },
                    "result": {
                        "clean_price": round(price, 2),
                        "premium_or_discount": round(premium_or_discount, 2),
                        "trading_at": "premium" if premium_or_discount > 0 else "discount" if premium_or_discount < 0 else "par",
                        "current_yield_pct": round(current_yield, 3),
                        "annual_coupon_amount": round(annual_coupon, 2),
                        "num_coupon_periods_remaining": len(flows),
                    },
                    "note": (
                        "Clean price ignores accrued interest (which is added at settlement "
                        "to give the dirty price). Assumes no embedded options (callable / "
                        "puttable bonds need OAS analysis)."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Bond pricing failed: {e}")


class ComputeBondDurationTool(Tool):
    name = "compute_bond_duration"
    description = (
        "Compute Macaulay duration, modified duration, and convexity for a fixed-coupon "
        "bond — measures of interest-rate sensitivity. Modified duration ≈ % price drop "
        "for a 1pp yield rise. Use for 'how sensitive is this bond to rates', 'what's "
        "the duration of a 10y G-sec'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "face_value": {"type": "number"},
            "coupon_rate_pct": {"type": "number"},
            "years_to_maturity": {"type": "number"},
            "ytm_pct": {"type": "number"},
            "frequency": {"type": "string", "enum": ["annual", "semiannual", "quarterly", "monthly"]},
        },
        "required": ["face_value", "coupon_rate_pct", "years_to_maturity", "ytm_pct"],
    }

    def execute(
        self,
        *,
        face_value: float,
        coupon_rate_pct: float,
        years_to_maturity: float,
        ytm_pct: float,
        frequency: str = "semiannual",
        **_,
    ) -> ToolResult:
        try:
            face = float(face_value)
            coupon = float(coupon_rate_pct)
            yrs = float(years_to_maturity)
            ytm = float(ytm_pct)
            freq = _FREQ_MAP.get((frequency or "semiannual").strip().lower())
            if not freq:
                return ToolResult(success=False, error=f"unknown frequency '{frequency}'")

            flows = _bond_cash_flows(face, coupon, yrs, freq)
            r = (ytm / 100.0) / freq

            price = _present_value(flows, ytm, freq)
            if price <= 0:
                return ToolResult(success=False, error="bond price computed as 0 — check inputs")

            # Macaulay duration
            weighted_t = 0.0
            convexity_acc = 0.0
            for t, cf in flows:
                pv = cf / ((1 + r) ** (t * freq))
                weighted_t += t * pv
                # Convexity numerator: cf × t(t + dt) / (1+r)^(t*freq + 2)
                # Standard formula: sum of [cf × t × (t + period_len)] / (1+r)^(t*freq + 2) / price
                convexity_acc += cf * (t * freq) * (t * freq + 1) / ((1 + r) ** (t * freq + 2))

            macaulay = weighted_t / price
            modified = macaulay / (1 + r)
            convexity = convexity_acc / (price * (freq ** 2))

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "bond_duration",
                    "inputs": {
                        "face_value": face,
                        "coupon_rate_pct": coupon,
                        "years_to_maturity": yrs,
                        "ytm_pct": ytm,
                        "frequency": frequency,
                    },
                    "result": {
                        "clean_price": round(price, 2),
                        "macaulay_duration_years": round(macaulay, 3),
                        "modified_duration": round(modified, 3),
                        "convexity": round(convexity, 3),
                        "approx_price_change_per_1pp_yield": round(-modified, 3),
                        "approx_price_change_per_50bp_yield": round(-modified * 0.5, 3),
                    },
                    "note": (
                        "Modified duration is a linear approximation; for large yield moves "
                        "(>~100 bp) add the convexity correction: ΔP/P ≈ −D_mod × Δy + ½ × "
                        "convexity × (Δy)². Δy in decimal (e.g., 0.01 for 1pp)."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Duration calculation failed: {e}")
