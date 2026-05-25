"""Insurance calculators: term cover need, health cover need, endowment IRR."""

from agent.tools.base import Tool, ToolResult


class ComputeTermCoverNeedTool(Tool):
    name = "compute_term_cover_need"
    description = (
        "Estimate the term-insurance sum-assured a user needs, using two industry methods: "
        "(1) Income-Replacement Method (10–15× annual income), (2) Human Life Value (HLV) "
        "= present value of expected future income. Returns both with the larger as the "
        "recommended cover. Adjusts for existing cover and outstanding liabilities."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_income": {"type": "number"},
            "current_age": {"type": "integer"},
            "retirement_age": {"type": "integer", "description": "Default 60."},
            "dependents": {"type": "integer", "description": "Default 1."},
            "outstanding_liabilities": {"type": "number", "description": "Loans, debts. Default 0."},
            "existing_cover": {"type": "number", "description": "Existing term cover already in place. Default 0."},
            "discount_rate_pct": {"type": "number", "description": "PV discount rate for HLV. Default 7."},
        },
        "required": ["annual_income", "current_age"],
    }

    def execute(self, *, annual_income, current_age, retirement_age=60, dependents=1,
                outstanding_liabilities=0, existing_cover=0, discount_rate_pct=7, **_) -> ToolResult:
        try:
            inc = float(annual_income); age = int(current_age); ret = int(retirement_age)
            deps = max(0, int(dependents))
            liabs = float(outstanding_liabilities or 0); existing = float(existing_cover or 0)
            r = float(discount_rate_pct) / 100.0

            years_to_retirement = max(1, ret - age)
            # Income replacement: scale by dependents (1 dep = 10x, 2+ deps = 12-15x)
            multiplier = 10 if deps <= 1 else 12 if deps == 2 else 15
            irm_cover = inc * multiplier + liabs

            # HLV: PV of income stream till retirement (annual annuity)
            if r > 0:
                hlv_cover = inc * ((1 - (1 + r) ** -years_to_retirement) / r) + liabs
            else:
                hlv_cover = inc * years_to_retirement + liabs

            recommended = max(irm_cover, hlv_cover)
            additional_needed = max(0, recommended - existing)

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "term_cover_need",
                "inputs": {
                    "annual_income": inc, "current_age": age, "retirement_age": ret,
                    "dependents": deps, "outstanding_liabilities": liabs,
                    "existing_cover": existing, "discount_rate_pct": discount_rate_pct,
                },
                "result": {
                    "income_replacement_method": {
                        "multiplier": multiplier,
                        "cover": round(irm_cover, 2),
                        "explanation": f"{multiplier}× annual income + outstanding liabilities",
                    },
                    "human_life_value_method": {
                        "years_of_income": years_to_retirement,
                        "discount_rate_pct": discount_rate_pct,
                        "cover": round(hlv_cover, 2),
                        "explanation": "PV of future income stream + outstanding liabilities",
                    },
                    "recommended_total_cover": round(recommended, 2),
                    "existing_cover": round(existing, 2),
                    "additional_cover_needed": round(additional_needed, 2),
                },
                "note": (
                    "Term insurance is pure life cover — pays only on death, no maturity benefit. "
                    "Premium is cheap. Buy a term plan, not endowment / ULIP / money-back. "
                    "Cover should typically last till retirement age (60-65). Add critical-illness "
                    "and accidental-death riders if affordable."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Term cover calc failed: {e}")


class ComputeHealthCoverNeedTool(Tool):
    name = "compute_health_cover_need"
    description = (
        "Estimate the health-insurance sum-insured a family should carry, based on city "
        "tier (medical-cost inflation), family size, and existing cover. Use for 'how "
        "much health insurance do we need'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "family_size": {"type": "integer", "description": "Number of people on the policy."},
            "city_tier": {"type": "string", "enum": ["metro", "tier1", "tier2", "tier3"], "description": "Affects baseline. Default 'metro'."},
            "max_age_in_family": {"type": "integer", "description": "Oldest member's age — drives risk."},
            "existing_cover": {"type": "number", "description": "Default 0."},
            "include_critical_illness": {"type": "boolean", "description": "Recommend a CI top-up. Default true."},
        },
        "required": ["family_size"],
    }

    _BASE_PER_PERSON = {"metro": 500000, "tier1": 400000, "tier2": 300000, "tier3": 250000}

    def execute(self, *, family_size, city_tier="metro", max_age_in_family=40, existing_cover=0, include_critical_illness=True, **_) -> ToolResult:
        try:
            n = max(1, int(family_size))
            tier = (city_tier or "metro").strip().lower()
            base = self._BASE_PER_PERSON.get(tier, 500000)
            age = int(max_age_in_family or 40)
            existing = float(existing_cover or 0)

            # Family floater base
            recommended = base * (1.0 + 0.5 * (n - 1))   # diminishing-marginal scaling

            # Age bump: above 60, add 50%; above 70, double
            if age >= 70:
                recommended *= 2.0
            elif age >= 60:
                recommended *= 1.5
            elif age >= 50:
                recommended *= 1.25

            ci_topup = 1500000 if include_critical_illness else 0

            additional = max(0, recommended - existing)

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "health_cover_need",
                "inputs": {"family_size": n, "city_tier": tier, "max_age_in_family": age, "existing_cover": existing, "include_critical_illness": include_critical_illness},
                "result": {
                    "recommended_family_floater_cover": round(recommended, 2),
                    "recommended_critical_illness_topup": round(ci_topup, 2),
                    "total_recommended_cover": round(recommended + ci_topup, 2),
                    "existing_cover": round(existing, 2),
                    "additional_floater_needed": round(additional, 2),
                },
                "note": (
                    "Heuristic for typical Indian-metro hospital costs (~₹3-5L for a non-ICU admission, "
                    "₹15-30L for ICU/major surgery). Always check: room-rent capping, co-pay, sub-limits "
                    "on disease, no-claim-bonus, pre-existing-disease waiting period, network hospital list. "
                    "Premium is 80D-deductible (₹25k self / additional ₹25-50k for parents) under old regime."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Health cover calc failed: {e}")


class ComputeEndowmentIrrTool(Tool):
    name = "compute_endowment_irr"
    description = (
        "Compute the actual IRR (XIRR) of a traditional life-insurance endowment / money-"
        "back / LIC plan: annual premium for N years, then a maturity payout. Reveals what "
        "the policy ACTUALLY returns vs the agent's marketing numbers — typically 4-6%, "
        "well below the comparable term + MF combination."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_premium": {"type": "number"},
            "premium_payment_term_years": {"type": "integer"},
            "policy_term_years": {"type": "integer"},
            "maturity_payout": {"type": "number"},
        },
        "required": ["annual_premium", "premium_payment_term_years", "policy_term_years", "maturity_payout"],
    }

    def execute(self, *, annual_premium, premium_payment_term_years, policy_term_years, maturity_payout, **_) -> ToolResult:
        try:
            P = float(annual_premium); ppt = int(premium_payment_term_years); pt = int(policy_term_years); M = float(maturity_payout)
            if pt < ppt:
                return ToolResult(success=False, error="policy_term_years must be ≥ premium_payment_term_years")

            # Build cash flows: -P each year of PPT, +M at the end of PT
            flows = [(-P) for _ in range(ppt)] + [0.0 for _ in range(pt - ppt)]
            flows[-1] += M

            # IRR via bisection
            def npv(rate, fs):
                return sum(f / ((1 + rate) ** (i + 1)) for i, f in enumerate(fs))

            lo, hi = -0.50, 1.00
            # Find a sign change
            for _ in range(200):
                mid = (lo + hi) / 2
                v = npv(mid, flows)
                if abs(v) < 1e-3:
                    break
                if npv(lo, flows) * v < 0:
                    hi = mid
                else:
                    lo = mid
            irr = (lo + hi) / 2 * 100

            total_paid = P * ppt
            absolute_return = (M - total_paid) / total_paid * 100 if total_paid else 0

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "endowment_irr",
                "inputs": {"annual_premium": P, "premium_payment_term_years": ppt, "policy_term_years": pt, "maturity_payout": M},
                "result": {
                    "total_premiums_paid": round(total_paid, 2),
                    "maturity_payout": round(M, 2),
                    "absolute_return_pct": round(absolute_return, 2),
                    "annualised_irr_pct": round(irr, 2),
                },
                "note": (
                    "Endowment IRRs of 4-6% are normal — they include a small mortality cover plus "
                    "guaranteed savings. A term plan + ELSS / index fund mix typically delivers far "
                    "higher post-tax returns. Use this calculator to objectively compare offers."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Endowment IRR calc failed: {e}")
