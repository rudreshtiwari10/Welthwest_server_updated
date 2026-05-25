"""Tools: compute_sip_return, compute_fd_maturity."""

from agent.tools.base import Tool, ToolResult


class ComputeSipReturnTool(Tool):
    name = "compute_sip_return"
    description = (
        "Project the corpus from a monthly SIP given monthly contribution, tenure, and "
        "expected annualised return. Optional annual step-up (e.g., 10% means contributions "
        "increase 10% every year). Returns total invested, future value, gain, and a "
        "year-by-year corpus table for tracking."
    )
    parameters = {
        "type": "object",
        "properties": {
            "monthly_amount": {
                "type": "number",
                "description": "Monthly SIP amount in rupees (e.g., 10000 for ₹10,000/month).",
            },
            "years": {
                "type": "number",
                "description": "Investment horizon in years (can be fractional, e.g., 7.5).",
            },
            "expected_return_pct": {
                "type": "number",
                "description": "Expected annualised return in percent (e.g., 12 for 12% p.a.).",
            },
            "step_up_pct": {
                "type": "number",
                "description": "Optional annual step-up percentage (e.g., 10 means 10% increase every year). Default 0.",
            },
        },
        "required": ["monthly_amount", "years", "expected_return_pct"],
    }

    def execute(
        self,
        *,
        monthly_amount: float,
        years: float,
        expected_return_pct: float,
        step_up_pct: float = 0,
        **_,
    ) -> ToolResult:
        try:
            monthly_amount = float(monthly_amount)
            years = float(years)
            expected_return_pct = float(expected_return_pct)
            step_up_pct = float(step_up_pct or 0)

            if monthly_amount <= 0 or years <= 0:
                return ToolResult(success=False, error="monthly_amount and years must be > 0")

            r_monthly = expected_return_pct / 12.0 / 100.0
            total_months = int(round(years * 12))

            # Simulate month-by-month so step-up is exact.
            corpus = 0.0
            invested = 0.0
            current_monthly = monthly_amount
            yearly_table = []
            year_invested = 0.0

            for m in range(1, total_months + 1):
                # Step-up at the start of each new year (after year 1)
                if m > 1 and (m - 1) % 12 == 0 and step_up_pct > 0:
                    current_monthly *= (1 + step_up_pct / 100.0)
                corpus = corpus * (1 + r_monthly) + current_monthly
                invested += current_monthly
                year_invested += current_monthly

                if m % 12 == 0 or m == total_months:
                    yearly_table.append({
                        "year": (m + 11) // 12,
                        "monthly_contribution": round(current_monthly, 2),
                        "year_invested": round(year_invested, 2),
                        "cumulative_invested": round(invested, 2),
                        "corpus_end_of_year": round(corpus, 2),
                    })
                    year_invested = 0.0

            gain = corpus - invested

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "sip_return",
                    "inputs": {
                        "monthly_amount": round(monthly_amount, 2),
                        "years": years,
                        "expected_return_pct": expected_return_pct,
                        "step_up_pct": step_up_pct,
                    },
                    "result": {
                        "total_invested": round(invested, 2),
                        "future_value": round(corpus, 2),
                        "wealth_gained": round(gain, 2),
                        "gain_to_invested_ratio": round(gain / invested, 3) if invested else 0,
                    },
                    "yearly_corpus": yearly_table,
                    "formula": (
                        "Month-by-month accrual: corpus = corpus × (1 + r_monthly) + monthly_amount, "
                        "with monthly_amount stepped up annually if step_up_pct > 0."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"SIP calculation failed: {e}")


class ComputeFdMaturityTool(Tool):
    name = "compute_fd_maturity"
    description = (
        "Compute the maturity value and total interest of a fixed deposit. Supports "
        "quarterly (default for most Indian banks), monthly, half-yearly, or annual "
        "compounding. Optionally apply post-tax adjustment using the user's slab rate."
    )
    parameters = {
        "type": "object",
        "properties": {
            "principal": {
                "type": "number",
                "description": "FD principal in rupees.",
            },
            "annual_rate": {
                "type": "number",
                "description": "Annual interest rate in percent (e.g., 7.25 for 7.25% p.a.).",
            },
            "years": {
                "type": "number",
                "description": "Tenure in years (can be fractional, e.g., 1.5).",
            },
            "compounding": {
                "type": "string",
                "enum": ["monthly", "quarterly", "half_yearly", "annually"],
                "description": "Compounding frequency. Default 'quarterly' (standard for Indian banks).",
            },
            "tax_slab_pct": {
                "type": "number",
                "description": "Optional tax slab to compute post-tax return (e.g., 30 for the 30% slab). Default 0 (no tax adjustment).",
            },
        },
        "required": ["principal", "annual_rate", "years"],
    }

    _COMPOUND_N = {
        "monthly": 12,
        "quarterly": 4,
        "half_yearly": 2,
        "annually": 1,
    }

    def execute(
        self,
        *,
        principal: float,
        annual_rate: float,
        years: float,
        compounding: str = "quarterly",
        tax_slab_pct: float = 0,
        **_,
    ) -> ToolResult:
        try:
            principal = float(principal)
            annual_rate = float(annual_rate)
            years = float(years)
            tax_slab_pct = float(tax_slab_pct or 0)
            compounding = (compounding or "quarterly").strip().lower()

            if principal <= 0 or annual_rate < 0 or years <= 0:
                return ToolResult(success=False, error="invalid FD inputs")

            n = self._COMPOUND_N.get(compounding)
            if n is None:
                return ToolResult(success=False, error=f"unknown compounding '{compounding}'")

            r = annual_rate / 100.0
            maturity = principal * (1 + r / n) ** (n * years)
            interest = maturity - principal
            effective_yield = ((maturity / principal) ** (1 / years) - 1) * 100 if years > 0 else 0

            tax_owed = interest * tax_slab_pct / 100.0 if tax_slab_pct > 0 else 0
            post_tax_maturity = maturity - tax_owed
            post_tax_yield = ((post_tax_maturity / principal) ** (1 / years) - 1) * 100 if years > 0 else 0

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "fd_maturity",
                    "inputs": {
                        "principal": round(principal, 2),
                        "annual_rate": annual_rate,
                        "years": years,
                        "compounding": compounding,
                        "tax_slab_pct": tax_slab_pct,
                    },
                    "result": {
                        "maturity_value": round(maturity, 2),
                        "total_interest": round(interest, 2),
                        "effective_annual_yield_pct": round(effective_yield, 3),
                        "tax_on_interest": round(tax_owed, 2) if tax_owed else 0,
                        "post_tax_maturity": round(post_tax_maturity, 2),
                        "post_tax_yield_pct": round(post_tax_yield, 3),
                    },
                    "formula": "A = P × (1 + r/n)^(n × t), where r = annual_rate / 100, n = compounding frequency, t = years.",
                    "note": (
                        "Indian banks deduct TDS at 10% on FD interest above ₹40,000/yr "
                        "(₹50,000 for senior citizens). The tax_slab_pct parameter computes "
                        "the user's full tax liability assuming they're in that slab; "
                        "the actual TDS (10%) is a withholding, not the final tax."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"FD calculation failed: {e}")
