"""Planning calculators: emergency fund, retirement, education, goal SIP, FIRE,
inflation-adjusted, asset allocation."""

from agent.tools.base import Tool, ToolResult


def _required_sip(target_corpus: float, years: float, expected_return_pct: float) -> float:
    """Reverse-SIP: monthly SIP needed to reach target_corpus."""
    if years <= 0:
        return target_corpus
    n = years * 12
    r = expected_return_pct / 12 / 100
    if r == 0:
        return target_corpus / n
    # FV = P × [((1+r)^n − 1)/r] × (1+r)
    factor = (((1 + r) ** n - 1) / r) * (1 + r)
    return target_corpus / factor


# =============================================================================

class ComputeEmergencyFundNeedTool(Tool):
    name = "compute_emergency_fund_need"
    description = (
        "Compute the recommended emergency-fund corpus given monthly essential expenses, "
        "income stability, and number of dependents. Returns a low/mid/high band so the "
        "user can pick based on their risk tolerance."
    )
    parameters = {
        "type": "object",
        "properties": {
            "monthly_expenses": {"type": "number", "description": "Essential monthly expenses (rent, utilities, food, EMIs)."},
            "income_stability": {"type": "string", "enum": ["stable", "moderate", "variable"], "description": "Salaried with steady job = stable; freelance / single-customer dependence = variable. Default 'stable'."},
            "dependents": {"type": "integer", "description": "Default 0."},
            "current_emergency_fund": {"type": "number", "description": "What's already saved. Default 0."},
        },
        "required": ["monthly_expenses"],
    }

    def execute(self, *, monthly_expenses, income_stability="stable", dependents=0, current_emergency_fund=0, **_) -> ToolResult:
        try:
            E = float(monthly_expenses); deps = int(dependents); have = float(current_emergency_fund or 0)
            base = {"stable": 6, "moderate": 9, "variable": 12}.get(income_stability, 6)
            bump = 1 if deps >= 2 else 0
            mid = base + bump
            low = max(3, mid - 3); high = mid + 3
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "emergency_fund_need",
                "inputs": {"monthly_expenses": E, "income_stability": income_stability, "dependents": deps, "current_emergency_fund": have},
                "result": {
                    "low_band": {"months": low, "amount": round(E * low, 2)},
                    "recommended": {"months": mid, "amount": round(E * mid, 2)},
                    "high_band": {"months": high, "amount": round(E * high, 2)},
                    "current": round(have, 2),
                    "additional_needed_to_recommended": round(max(0, E * mid - have), 2),
                },
                "note": (
                    "Park the emergency fund in liquid instruments — sweep-in FDs, liquid mutual "
                    "funds, or a high-yield savings account. NEVER in equity. The point is "
                    "instant access without selling at a loss when stress hits."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Emergency fund calc failed: {e}")


class ComputeRetirementCorpusTool(Tool):
    name = "compute_retirement_corpus"
    description = (
        "Compute the corpus needed at retirement to fund your post-retirement life, given "
        "current monthly expenses, current age, retirement age, life expectancy, and "
        "inflation. Inflates expenses to retirement, then computes the corpus needed "
        "using a 4% safe withdrawal rule (or specified). Also returns the required SIP."
    )
    parameters = {
        "type": "object",
        "properties": {
            "current_monthly_expenses": {"type": "number"},
            "current_age": {"type": "integer"},
            "retirement_age": {"type": "integer", "description": "Default 60."},
            "life_expectancy": {"type": "integer", "description": "Default 85."},
            "inflation_pct": {"type": "number", "description": "Default 6."},
            "post_retirement_return_pct": {"type": "number", "description": "Default 7 (conservative)."},
            "pre_retirement_return_pct": {"type": "number", "description": "Default 12 (equity-heavy SIP)."},
            "current_savings": {"type": "number", "description": "Already saved towards retirement. Default 0."},
        },
        "required": ["current_monthly_expenses", "current_age"],
    }

    def execute(self, *, current_monthly_expenses, current_age, retirement_age=60, life_expectancy=85,
                inflation_pct=6, post_retirement_return_pct=7, pre_retirement_return_pct=12,
                current_savings=0, **_) -> ToolResult:
        try:
            E = float(current_monthly_expenses); age = int(current_age); ret = int(retirement_age)
            le = int(life_expectancy)
            infl = float(inflation_pct) / 100
            r_post = float(post_retirement_return_pct) / 100
            r_pre = float(pre_retirement_return_pct)
            cs = float(current_savings or 0)

            years_to_retire = max(1, ret - age)
            years_in_retirement = max(1, le - ret)

            # Inflate monthly expenses to retirement
            monthly_at_retirement = E * ((1 + infl) ** years_to_retire)
            annual_at_retirement = monthly_at_retirement * 12

            # Corpus needed: PV of inflation-adjusted post-retirement annuity
            real_return = (1 + r_post) / (1 + infl) - 1
            if real_return > 0:
                corpus_needed = annual_at_retirement * ((1 - (1 + real_return) ** -years_in_retirement) / real_return)
            else:
                corpus_needed = annual_at_retirement * years_in_retirement

            # Deduct what current_savings will grow to
            future_value_existing = cs * ((1 + r_post) ** years_to_retire)  # conservative growth assumption
            corpus_to_build = max(0, corpus_needed - future_value_existing)

            required_sip = _required_sip(corpus_to_build, years_to_retire, r_pre)

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "retirement_corpus",
                "inputs": {
                    "current_monthly_expenses": E, "current_age": age, "retirement_age": ret,
                    "life_expectancy": le, "inflation_pct": inflation_pct,
                    "post_retirement_return_pct": post_retirement_return_pct,
                    "pre_retirement_return_pct": pre_retirement_return_pct,
                    "current_savings": cs,
                },
                "result": {
                    "years_to_retirement": years_to_retire,
                    "years_in_retirement": years_in_retirement,
                    "monthly_expenses_at_retirement": round(monthly_at_retirement, 2),
                    "annual_expenses_at_retirement": round(annual_at_retirement, 2),
                    "corpus_needed_at_retirement": round(corpus_needed, 2),
                    "future_value_of_current_savings": round(future_value_existing, 2),
                    "corpus_still_to_build": round(corpus_to_build, 2),
                    "required_monthly_sip": round(required_sip, 2),
                },
                "note": (
                    "Uses real-return (post inflation) PV annuity for the post-retirement phase. "
                    "Add a buffer for medical costs (which inflate faster than headline CPI). "
                    "Diversify post-retirement: laddered FDs + SCSS for income, balanced funds for growth."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Retirement calc failed: {e}")


class ComputeEducationCorpusTool(Tool):
    name = "compute_education_corpus"
    description = (
        "Compute the corpus needed at admission age for a child's education and the "
        "required monthly SIP today. Education inflation is typically 8-10% in India "
        "(higher than headline CPI)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "child_current_age": {"type": "number"},
            "admission_age": {"type": "integer", "description": "Default 18."},
            "current_course_cost": {"type": "number", "description": "Today's cost of the target course (tuition + fees + living)."},
            "education_inflation_pct": {"type": "number", "description": "Default 9."},
            "expected_return_pct": {"type": "number", "description": "Default 12."},
            "current_savings": {"type": "number", "description": "Already saved towards this goal. Default 0."},
        },
        "required": ["child_current_age", "current_course_cost"],
    }

    def execute(self, *, child_current_age, current_course_cost, admission_age=18,
                education_inflation_pct=9, expected_return_pct=12, current_savings=0, **_) -> ToolResult:
        try:
            ca = float(child_current_age); aa = int(admission_age)
            cost = float(current_course_cost); infl = float(education_inflation_pct) / 100
            r = float(expected_return_pct); cs = float(current_savings or 0)

            years_to_admission = max(1, aa - ca)
            future_cost = cost * ((1 + infl) ** years_to_admission)
            future_value_existing = cs * ((1 + r / 100) ** years_to_admission)
            corpus_to_build = max(0, future_cost - future_value_existing)
            required_sip = _required_sip(corpus_to_build, years_to_admission, r)

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "education_corpus",
                "inputs": {
                    "child_current_age": ca, "admission_age": aa, "current_course_cost": cost,
                    "education_inflation_pct": education_inflation_pct,
                    "expected_return_pct": expected_return_pct, "current_savings": cs,
                },
                "result": {
                    "years_to_admission": years_to_admission,
                    "future_cost_at_admission": round(future_cost, 2),
                    "future_value_of_current_savings": round(future_value_existing, 2),
                    "corpus_still_to_build": round(corpus_to_build, 2),
                    "required_monthly_sip": round(required_sip, 2),
                },
                "note": (
                    "Indian education inflation (especially for foreign degrees) often runs 8-12% — "
                    "higher than CPI. Sukanya Samriddhi for a girl child gives ~8.2% tax-free. "
                    "Equity SIPs handle the corpus better than endowment / child-plan ULIPs."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Education calc failed: {e}")


class ComputeGoalRequiredSipTool(Tool):
    name = "compute_goal_required_sip"
    description = (
        "Reverse-calculate the monthly SIP needed to hit a target corpus by a target year, "
        "given an expected return. Use whenever the user has a goal amount + horizon."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target_corpus": {"type": "number"},
            "years_to_goal": {"type": "number"},
            "expected_return_pct": {"type": "number", "description": "Default 12."},
            "current_savings_for_goal": {"type": "number", "description": "Default 0."},
        },
        "required": ["target_corpus", "years_to_goal"],
    }

    def execute(self, *, target_corpus, years_to_goal, expected_return_pct=12, current_savings_for_goal=0, **_) -> ToolResult:
        try:
            T = float(target_corpus); yrs = float(years_to_goal); r = float(expected_return_pct); cs = float(current_savings_for_goal or 0)
            future_value_existing = cs * ((1 + r / 100) ** yrs)
            corpus_to_build = max(0, T - future_value_existing)
            sip = _required_sip(corpus_to_build, yrs, r)
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "goal_required_sip",
                "inputs": {"target_corpus": T, "years_to_goal": yrs, "expected_return_pct": r, "current_savings_for_goal": cs},
                "result": {
                    "target_corpus": round(T, 2),
                    "future_value_of_current_savings": round(future_value_existing, 2),
                    "corpus_still_to_build": round(corpus_to_build, 2),
                    "required_monthly_sip": round(sip, 2),
                    "total_invested_through_sip": round(sip * yrs * 12, 2),
                },
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Goal SIP calc failed: {e}")


class ComputeFireNumberTool(Tool):
    name = "compute_fire_number"
    description = (
        "Compute the FIRE number — the corpus needed for Financial Independence / Retire "
        "Early. Default rule: 25× annual expenses (4% safe withdrawal). For India, a more "
        "conservative 30-35× is often used because of higher inflation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_expenses": {"type": "number"},
            "withdrawal_rate_pct": {"type": "number", "description": "Default 4. Use 3 for ultra-conservative, 3.5 for India-tuned."},
            "current_age": {"type": "integer"},
            "current_corpus": {"type": "number", "description": "Current investments. Default 0."},
            "expected_return_pct": {"type": "number", "description": "Default 12."},
            "current_monthly_savings": {"type": "number", "description": "Current monthly savings rate. Default 0."},
        },
        "required": ["annual_expenses"],
    }

    def execute(self, *, annual_expenses, withdrawal_rate_pct=4, current_age=30,
                current_corpus=0, expected_return_pct=12, current_monthly_savings=0, **_) -> ToolResult:
        try:
            E = float(annual_expenses); wr = float(withdrawal_rate_pct) / 100
            age = int(current_age); cc = float(current_corpus or 0)
            r = float(expected_return_pct) / 100; ms = float(current_monthly_savings or 0)
            fire_number = E / wr if wr > 0 else float("inf")
            multiplier = 1 / wr if wr > 0 else 0

            # Years to FIRE given current corpus + current saving rate
            years_to_fire = None
            if ms > 0 and cc < fire_number:
                # Simulate yearly
                bal = cc
                yr = 0
                while bal < fire_number and yr < 60:
                    bal = bal * (1 + r) + ms * 12
                    yr += 1
                years_to_fire = yr if bal >= fire_number else None

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "fire_number",
                "inputs": {
                    "annual_expenses": E, "withdrawal_rate_pct": withdrawal_rate_pct,
                    "current_age": age, "current_corpus": cc,
                    "expected_return_pct": expected_return_pct,
                    "current_monthly_savings": ms,
                },
                "result": {
                    "fire_number": round(fire_number, 2),
                    "multiple_of_annual_expenses": round(multiplier, 1),
                    "current_corpus_pct_of_fire": round(cc / fire_number * 100, 1) if fire_number > 0 else 0,
                    "years_to_fire_at_current_savings": years_to_fire,
                    "fire_age_estimate": age + years_to_fire if years_to_fire is not None else None,
                },
                "note": (
                    "The 4% rule was calibrated on US data with ~3% inflation. Indian inflation "
                    "is structurally higher (5-6%), so 3-3.5% withdrawal rate is safer here. "
                    "Beyond money, plan for what you'll do with your time — 'retired early' "
                    "without a purpose is harder than it sounds."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"FIRE calc failed: {e}")


class ComputeInflationAdjustedTool(Tool):
    name = "compute_inflation_adjusted"
    description = (
        "Compute the future / present value of an amount adjusted for inflation. "
        "Use for 'what's ₹1 crore today worth in 25 years', 'how much is ₹50k/month "
        "in 2050 in today's terms'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "years": {"type": "number"},
            "inflation_pct": {"type": "number", "description": "Default 6."},
            "direction": {"type": "string", "enum": ["future_value", "present_value"], "description": "future_value = inflate today's amount, present_value = deflate a future amount. Default 'future_value'."},
        },
        "required": ["amount", "years"],
    }

    def execute(self, *, amount, years, inflation_pct=6, direction="future_value", **_) -> ToolResult:
        try:
            A = float(amount); yrs = float(years); infl = float(inflation_pct) / 100
            if direction == "future_value":
                result = A * ((1 + infl) ** yrs)
                erosion = A - (A / ((1 + infl) ** yrs))
            else:
                result = A / ((1 + infl) ** yrs)
                erosion = A - result
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "inflation_adjusted",
                "inputs": {"amount": A, "years": yrs, "inflation_pct": inflation_pct, "direction": direction},
                "result": {
                    "input_amount": round(A, 2),
                    "adjusted_amount": round(result, 2),
                    "purchasing_power_lost": round(erosion, 2) if direction == "future_value" else None,
                    "purchasing_power_today_equivalent": round(result, 2) if direction == "present_value" else None,
                },
                "formula": "FV = PV × (1+i)^t  |  PV = FV / (1+i)^t",
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Inflation calc failed: {e}")


class OptimizeAssetAllocationTool(Tool):
    name = "optimize_asset_allocation"
    description = (
        "Suggest a model asset-allocation split (equity / debt / gold / cash) given the "
        "user's age, risk profile, and investment horizon. Returns a recommended split "
        "with rationale. Heuristic, not portfolio optimisation."
    )
    parameters = {
        "type": "object",
        "properties": {
            "age": {"type": "integer"},
            "risk_profile": {"type": "string", "enum": ["conservative", "moderate", "aggressive"], "description": "Default 'moderate'."},
            "horizon_years": {"type": "number", "description": "Years till the money is needed. Default 10."},
        },
        "required": ["age"],
    }

    def execute(self, *, age, risk_profile="moderate", horizon_years=10, **_) -> ToolResult:
        try:
            a = int(age); rp = (risk_profile or "moderate").strip().lower(); h = float(horizon_years or 10)

            # Base equity from "100 minus age"
            base_equity = max(20, min(90, 100 - a))

            # Risk profile shift
            shift = {"conservative": -15, "moderate": 0, "aggressive": 15}.get(rp, 0)
            equity = max(10, min(95, base_equity + shift))

            # Horizon clamp: short horizon caps equity
            if h < 3:
                equity = min(equity, 30)
            elif h < 5:
                equity = min(equity, 50)

            debt = max(5, 100 - equity - 10 - 5)  # carve out gold + cash
            gold = 10
            cash = 5
            # Normalise
            total = equity + debt + gold + cash
            equity_pct = round(equity / total * 100, 1)
            debt_pct = round(debt / total * 100, 1)
            gold_pct = round(gold / total * 100, 1)
            cash_pct = round(cash / total * 100, 1)

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "asset_allocation",
                "inputs": {"age": a, "risk_profile": rp, "horizon_years": h},
                "result": {
                    "equity_pct": equity_pct,
                    "debt_pct": debt_pct,
                    "gold_pct": gold_pct,
                    "cash_pct": cash_pct,
                    "rationale": f"Started from '100 minus age' = {100 - a}%, adjusted by {rp} risk profile, capped by {h}-year horizon.",
                },
                "note": (
                    "Heuristic only — review against actual goals, existing assets, and tax bracket. "
                    "Within equity, diversify across large/mid/small cap. Within debt, ladder by "
                    "maturity. Rebalance annually or when a sleeve drifts >5pp from target."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Asset allocation failed: {e}")
