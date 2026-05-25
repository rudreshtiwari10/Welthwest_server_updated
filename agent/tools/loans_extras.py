"""Loan + credit extras: eligibility, prepay-vs-invest, compare offers, credit-score impact."""

from agent.tools.base import Tool, ToolResult
from agent.tools.loans import _emi


class ComputeLoanEligibilityTool(Tool):
    name = "compute_loan_eligibility"
    description = (
        "Estimate the maximum loan a bank will likely sanction, using the standard FOIR "
        "(Fixed Obligation to Income Ratio) cap of ~50% of net monthly income going to "
        "EMIs. Use for 'how much home/car/personal loan can I get'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "monthly_income_net": {"type": "number", "description": "Take-home monthly income."},
            "existing_monthly_emis": {"type": "number", "description": "Total EMIs already running. Default 0."},
            "annual_rate": {"type": "number", "description": "Loan rate in percent (e.g., 8.5 for home, 12 for personal)."},
            "tenure_months": {"type": "integer", "description": "Loan tenure in months."},
            "foir_pct": {"type": "number", "description": "Bank's FOIR cap. Default 50."},
        },
        "required": ["monthly_income_net", "annual_rate", "tenure_months"],
    }

    def execute(self, *, monthly_income_net, annual_rate, tenure_months, existing_monthly_emis=0, foir_pct=50, **_) -> ToolResult:
        try:
            inc = float(monthly_income_net); rate = float(annual_rate); n = int(tenure_months)
            existing = float(existing_monthly_emis or 0); foir = float(foir_pct) / 100
            max_total_emi = inc * foir
            available_emi = max(0, max_total_emi - existing)
            # Reverse-EMI: P = EMI × ((1+r)^n − 1) / (r × (1+r)^n)
            r = rate / 12 / 100
            if r == 0:
                max_loan = available_emi * n
            else:
                max_loan = available_emi * (((1 + r) ** n - 1) / (r * (1 + r) ** n))
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "loan_eligibility",
                "inputs": {
                    "monthly_income_net": inc, "existing_monthly_emis": existing,
                    "annual_rate": rate, "tenure_months": n, "foir_pct": foir_pct,
                },
                "result": {
                    "max_total_emi_at_foir": round(max_total_emi, 2),
                    "available_emi_after_existing": round(available_emi, 2),
                    "max_loan_eligibility": round(max(0, max_loan), 2),
                },
                "note": (
                    "FOIR varies by bank and product (40% common for personal loans, 50-60% "
                    "for home loans). Banks also check credit score, employment stability, "
                    "and property/asset value (LTV ≤ 75-80% for home loans)."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Loan eligibility failed: {e}")


class ComparePrepayVsInvestTool(Tool):
    name = "compare_prepay_vs_invest"
    description = (
        "The classic question: 'should I prepay my home loan or invest the surplus?' "
        "Computes both scenarios over the loan tenure. Prepayment saves interest at the "
        "loan rate (with tax adjustment); investing earns the expected return (post-tax). "
        "Returns the winner and the gap."
    )
    parameters = {
        "type": "object",
        "properties": {
            "outstanding_principal": {"type": "number"},
            "loan_rate_pct": {"type": "number"},
            "remaining_months": {"type": "integer"},
            "surplus_amount": {"type": "number", "description": "Lump sum available to either prepay or invest."},
            "expected_investment_return_pct": {"type": "number", "description": "Default 12 (equity)."},
            "investment_tax_pct": {"type": "number", "description": "LTCG rate on investment. Default 12.5."},
            "loan_interest_tax_benefit_pct": {"type": "number", "description": "Marginal slab — used only for home-loan interest tax shield (Sec 24). Default 0 (no shield)."},
        },
        "required": ["outstanding_principal", "loan_rate_pct", "remaining_months", "surplus_amount"],
    }

    def execute(self, *, outstanding_principal, loan_rate_pct, remaining_months, surplus_amount,
                expected_investment_return_pct=12, investment_tax_pct=12.5,
                loan_interest_tax_benefit_pct=0, **_) -> ToolResult:
        try:
            P = float(outstanding_principal); rate = float(loan_rate_pct); n = int(remaining_months)
            S = float(surplus_amount); inv_r = float(expected_investment_return_pct)
            tax = float(investment_tax_pct or 0); shield = float(loan_interest_tax_benefit_pct or 0) / 100

            # Scenario A: prepay S today, recompute EMI for remaining tenure
            new_principal = max(0, P - S)
            old_emi = _emi(P, rate, n)
            new_emi = _emi(new_principal, rate, n) if new_principal > 0 else 0
            interest_saved_gross = (old_emi * n - P) - (new_emi * n - new_principal) if new_principal > 0 else (old_emi * n - P)
            # Effective interest saved net of tax shield (only applies to home loans)
            interest_saved_net = interest_saved_gross * (1 - shield)

            # Scenario B: invest S at inv_r for n months, post-tax
            yrs = n / 12.0
            inv_fv = S * ((1 + inv_r / 100) ** yrs)
            inv_gain = inv_fv - S
            inv_tax_owed = max(0, inv_gain * tax / 100)
            inv_post_tax_gain = inv_gain - inv_tax_owed

            difference = inv_post_tax_gain - interest_saved_net
            recommendation = "invest" if difference > 0 else "prepay" if difference < 0 else "tie"

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "prepay_vs_invest",
                "inputs": {
                    "outstanding_principal": P, "loan_rate_pct": rate, "remaining_months": n,
                    "surplus_amount": S,
                    "expected_investment_return_pct": inv_r,
                    "investment_tax_pct": investment_tax_pct,
                    "loan_interest_tax_benefit_pct": loan_interest_tax_benefit_pct,
                },
                "result": {
                    "prepay_scenario": {
                        "interest_saved_gross": round(interest_saved_gross, 2),
                        "interest_saved_net_of_tax_shield": round(interest_saved_net, 2),
                        "new_emi": round(new_emi, 2),
                    },
                    "invest_scenario": {
                        "future_value": round(inv_fv, 2),
                        "gross_gain": round(inv_gain, 2),
                        "tax_on_gain": round(inv_tax_owed, 2),
                        "post_tax_gain": round(inv_post_tax_gain, 2),
                    },
                    "winner": recommendation,
                    "advantage_amount": round(abs(difference), 2),
                },
                "note": (
                    "This is a financial-only comparison. Other factors: psychological comfort "
                    "of being debt-free, behaviour discipline (will the surplus actually be "
                    "invested?), tax shield under Sec 24 (₹2L cap on self-occupied home interest), "
                    "EMI as a 'forced savings' anchor."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Prepay-vs-invest calc failed: {e}")


class CompareLoanOffersTool(Tool):
    name = "compare_loan_offers"
    description = (
        "Compare 2 to 5 loan offers on a level playing field — same principal, same tenure "
        "— accounting for processing fees and any one-time costs. Returns the cheapest "
        "and the gap."
    )
    parameters = {
        "type": "object",
        "properties": {
            "principal": {"type": "number", "description": "Same loan amount across offers."},
            "tenure_months": {"type": "integer"},
            "offers": {
                "type": "array",
                "description": "List of offers. Each: {lender: 'name', annual_rate: 8.5, processing_fee_pct: 0.5, processing_fee_flat: 0, other_charges: 0}.",
                "items": {"type": "object"},
            },
        },
        "required": ["principal", "tenure_months", "offers"],
    }

    def execute(self, *, principal, tenure_months, offers, **_) -> ToolResult:
        try:
            P = float(principal); n = int(tenure_months)
            if not isinstance(offers, (list, tuple)) or len(offers) < 2:
                return ToolResult(success=False, error="Provide at least 2 offers")
            results = []
            for o in offers[:5]:
                rate = float(o.get("annual_rate", 0))
                pf_pct = float(o.get("processing_fee_pct", 0))
                pf_flat = float(o.get("processing_fee_flat", 0))
                other = float(o.get("other_charges", 0))
                emi = _emi(P, rate, n)
                processing_fee = max(P * pf_pct / 100, pf_flat)
                total_outflow = emi * n + processing_fee + other
                results.append({
                    "lender": o.get("lender", "(unnamed)"),
                    "annual_rate": rate,
                    "monthly_emi": round(emi, 2),
                    "total_emi_paid": round(emi * n, 2),
                    "processing_fee": round(processing_fee, 2),
                    "other_charges": round(other, 2),
                    "total_outflow": round(total_outflow, 2),
                })
            results.sort(key=lambda x: x["total_outflow"])
            cheapest = results[0]
            most_expensive = results[-1]
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "compare_loan_offers",
                "inputs": {"principal": P, "tenure_months": n, "offers": offers},
                "result": {
                    "ranked_offers": results,
                    "cheapest_lender": cheapest["lender"],
                    "savings_vs_most_expensive": round(most_expensive["total_outflow"] - cheapest["total_outflow"], 2),
                },
                "note": "Also confirm prepayment terms (RBI bans prepayment penalty on floating-rate retail loans), foreclosure charges, and rate-reset triggers.",
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Compare offers failed: {e}")


class ComputeCreditScoreImpactTool(Tool):
    name = "compute_credit_score_impact"
    description = (
        "Qualitative model that scores hypothetical credit actions: utilization, missed "
        "payment, new credit, credit mix changes, account age. Returns directional impact "
        "(strong positive / mild positive / neutral / mild negative / strong negative) "
        "with rationale. Not a numeric prediction — bureaus' models are proprietary."
    )
    parameters = {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "description": (
                    "List of action strings. Supported: 'pay_off_credit_card', 'miss_emi', "
                    "'utilization_above_30', 'utilization_above_70', 'utilization_below_10', "
                    "'apply_new_credit_card', 'close_old_card', 'consolidate_loans', "
                    "'check_score_self', 'multiple_loan_inquiries', 'increase_credit_limit'."
                ),
                "items": {"type": "string"},
            },
        },
        "required": ["actions"],
    }

    _IMPACTS = {
        "pay_off_credit_card": ("strong_positive", "On-time / full payment is the single biggest score driver."),
        "miss_emi": ("strong_negative", "A missed EMI is reported and can drop the score 50-100 points."),
        "utilization_above_30": ("mild_negative", "Carrying balance above 30% of limit hurts utilization sub-score."),
        "utilization_above_70": ("strong_negative", "Above 70% utilization signals over-leverage to bureaus."),
        "utilization_below_10": ("mild_positive", "Low utilization shows discipline; ideal range 1-10%."),
        "apply_new_credit_card": ("mild_negative", "Hard inquiry costs ~5 points; new account drops average age."),
        "close_old_card": ("mild_negative", "Reduces total credit limit (raises utilization) and shortens average account age."),
        "consolidate_loans": ("mild_positive", "Replacing multiple high-rate loans with one is usually scored positively over 6-12 months."),
        "check_score_self": ("neutral", "Soft inquiries (you checking your own score) do NOT affect the score."),
        "multiple_loan_inquiries": ("strong_negative", "5+ hard inquiries in a short window signals desperation; can drop score 30-50 points."),
        "increase_credit_limit": ("mild_positive", "Higher limit at same spend = lower utilization, mild boost."),
    }

    def execute(self, *, actions, **_) -> ToolResult:
        try:
            if not isinstance(actions, (list, tuple)):
                return ToolResult(success=False, error="actions must be a list of strings")
            assessed = []
            score_direction_map = {"strong_positive": 2, "mild_positive": 1, "neutral": 0, "mild_negative": -1, "strong_negative": -2}
            net = 0
            for a in actions:
                key = str(a).strip().lower().replace("-", "_").replace(" ", "_")
                impact = self._IMPACTS.get(key)
                if impact:
                    direction, rationale = impact
                    assessed.append({"action": key, "impact": direction, "rationale": rationale})
                    net += score_direction_map[direction]
                else:
                    assessed.append({"action": key, "impact": "unknown", "rationale": "Action not in the known model set."})
            net_label = (
                "strong_positive" if net >= 3 else
                "mild_positive" if net >= 1 else
                "neutral" if net == 0 else
                "mild_negative" if net >= -2 else
                "strong_negative"
            )
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "credit_score_impact",
                "inputs": {"actions": list(actions)},
                "result": {
                    "per_action": assessed,
                    "net_directional_impact": net_label,
                    "score_change_units": net,
                },
                "note": (
                    "Bureaus (CIBIL, Experian, Equifax, CRIF) use proprietary scorecards — "
                    "exact point change is not predictable. This tool gives directional guidance. "
                    "Pillars of a strong score: on-time payments (35%), low utilization (30%), "
                    "long account age (15%), credit mix (10%), few hard inquiries (10%)."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Credit score model failed: {e}")
