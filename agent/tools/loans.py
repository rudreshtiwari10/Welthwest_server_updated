"""Tools: compute_emi, compute_loan_amortization."""

from agent.tools.base import Tool, ToolResult


def _emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard amortising EMI formula. Handles 0% gracefully."""
    if tenure_months <= 0:
        raise ValueError("tenure_months must be > 0")
    r = annual_rate / 12.0 / 100.0
    if r == 0:
        return principal / tenure_months
    return principal * r * (1 + r) ** tenure_months / ((1 + r) ** tenure_months - 1)


class ComputeEmiTool(Tool):
    name = "compute_emi"
    description = (
        "Calculate the monthly EMI for a loan, plus total payment and total interest. "
        "Use for any home / car / personal / education / business loan EMI question. "
        "Returns the headline EMI and a breakdown of how much of the total goes to "
        "principal vs interest."
    )
    parameters = {
        "type": "object",
        "properties": {
            "principal": {
                "type": "number",
                "description": "Loan amount in rupees (₹). Examples: 5000000 for ₹50 lakh.",
            },
            "annual_rate": {
                "type": "number",
                "description": "Annual interest rate in percent (e.g., 8.5 for 8.5% p.a.).",
            },
            "tenure_months": {
                "type": "integer",
                "description": "Loan tenure in months (e.g., 240 for a 20-year loan).",
            },
        },
        "required": ["principal", "annual_rate", "tenure_months"],
    }

    def execute(self, *, principal: float, annual_rate: float, tenure_months: int, **_) -> ToolResult:
        try:
            principal = float(principal)
            annual_rate = float(annual_rate)
            tenure_months = int(tenure_months)
            if principal <= 0 or annual_rate < 0 or tenure_months <= 0:
                return ToolResult(success=False, error="principal>0, annual_rate≥0, tenure_months>0 required")

            emi = _emi(principal, annual_rate, tenure_months)
            total = emi * tenure_months
            interest = total - principal

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "emi",
                    "inputs": {
                        "principal": round(principal, 2),
                        "annual_rate": annual_rate,
                        "tenure_months": tenure_months,
                        "tenure_years": round(tenure_months / 12, 2),
                    },
                    "result": {
                        "monthly_emi": round(emi, 2),
                        "total_payment": round(total, 2),
                        "total_interest": round(interest, 2),
                        "interest_to_principal_ratio": round(interest / principal, 3),
                    },
                    "breakdown": {
                        "principal_pct_of_total": round(principal / total * 100, 1),
                        "interest_pct_of_total": round(interest / total * 100, 1),
                    },
                    "formula": "EMI = P × r × (1+r)^n / ((1+r)^n − 1), r = annual_rate / 12 / 100, n = tenure_months",
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"EMI calculation failed: {e}")


class ComputeLoanAmortizationTool(Tool):
    name = "compute_loan_amortization"
    description = (
        "Build a year-wise amortisation schedule for a loan — principal-paid, interest-paid, "
        "and outstanding balance for each year. Optional one-time prepayment in a chosen month. "
        "Use when the user asks 'how much interest in year 5', 'when does principal exceed "
        "interest', 'how much do I save by prepaying ₹X in month Y', etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "principal": {"type": "number", "description": "Loan amount in rupees."},
            "annual_rate": {"type": "number", "description": "Annual rate in percent."},
            "tenure_months": {"type": "integer", "description": "Tenure in months."},
            "prepayment_amount": {
                "type": "number",
                "description": "Optional one-time prepayment in rupees (default 0).",
            },
            "prepayment_month": {
                "type": "integer",
                "description": "Month number (1-indexed) to apply prepayment in. Required if prepayment_amount > 0.",
            },
        },
        "required": ["principal", "annual_rate", "tenure_months"],
    }

    def execute(
        self,
        *,
        principal: float,
        annual_rate: float,
        tenure_months: int,
        prepayment_amount: float = 0,
        prepayment_month: int = 0,
        **_,
    ) -> ToolResult:
        try:
            principal = float(principal)
            annual_rate = float(annual_rate)
            tenure_months = int(tenure_months)
            prepayment_amount = float(prepayment_amount or 0)
            prepayment_month = int(prepayment_month or 0)

            if principal <= 0 or annual_rate < 0 or tenure_months <= 0:
                return ToolResult(success=False, error="invalid loan inputs")

            r = annual_rate / 12.0 / 100.0
            emi = _emi(principal, annual_rate, tenure_months)

            balance = principal
            yearly = []
            year_principal = 0.0
            year_interest = 0.0
            actual_months = 0

            for m in range(1, tenure_months + 1):
                if balance <= 0:
                    break
                interest_portion = balance * r
                principal_portion = emi - interest_portion
                if principal_portion > balance:
                    principal_portion = balance
                balance -= principal_portion
                year_interest += interest_portion
                year_principal += principal_portion
                actual_months = m

                # Apply prepayment AFTER the regular EMI for that month.
                if prepayment_amount > 0 and m == prepayment_month and balance > 0:
                    apply = min(prepayment_amount, balance)
                    balance -= apply
                    year_principal += apply

                if m % 12 == 0 or balance <= 0 or m == tenure_months:
                    yearly.append({
                        "year": (m + 11) // 12,
                        "principal_paid": round(year_principal, 2),
                        "interest_paid": round(year_interest, 2),
                        "ending_balance": round(max(0, balance), 2),
                    })
                    year_principal = 0.0
                    year_interest = 0.0

            total_interest_paid = sum(y["interest_paid"] for y in yearly)
            total_principal_paid = sum(y["principal_paid"] for y in yearly)
            total_paid = total_interest_paid + total_principal_paid

            # Compare against no-prepayment baseline so the user sees the saving
            saving = None
            months_saved = None
            if prepayment_amount > 0:
                baseline_interest = emi * tenure_months - principal
                saving = round(max(0, baseline_interest - total_interest_paid), 2)
                months_saved = max(0, tenure_months - actual_months)

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "loan_amortization",
                    "inputs": {
                        "principal": round(principal, 2),
                        "annual_rate": annual_rate,
                        "tenure_months": tenure_months,
                        "prepayment_amount": round(prepayment_amount, 2) if prepayment_amount else 0,
                        "prepayment_month": prepayment_month if prepayment_amount else 0,
                    },
                    "result": {
                        "monthly_emi": round(emi, 2),
                        "actual_months": actual_months,
                        "total_paid": round(total_paid, 2),
                        "total_principal_paid": round(total_principal_paid, 2),
                        "total_interest_paid": round(total_interest_paid, 2),
                        "interest_saved_by_prepayment": saving,
                        "months_saved_by_prepayment": months_saved,
                    },
                    "yearly_schedule": yearly,
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Amortisation calculation failed: {e}")
