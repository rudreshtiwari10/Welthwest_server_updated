"""Fixed-income & savings calculators: RD, PPF, NPS, SSY, SCSS, lumpsum, SWP."""

from agent.tools.base import Tool, ToolResult


def _annual_compound_with_contrib(annual_contrib: float, rate_pct: float, years: int, contrib_at_start: bool = True) -> dict:
    """
    Annual-contribution compounding (the standard Indian-savings-scheme model).
    Returns the corpus after each year + total invested + final maturity.
    """
    r = rate_pct / 100.0
    corpus = 0.0
    invested = 0.0
    yearly = []
    for y in range(1, years + 1):
        if contrib_at_start:
            corpus = (corpus + annual_contrib) * (1 + r)
        else:
            corpus = corpus * (1 + r) + annual_contrib
        invested += annual_contrib
        yearly.append({
            "year": y,
            "invested_to_date": round(invested, 2),
            "corpus_end_of_year": round(corpus, 2),
        })
    return {
        "total_invested": round(invested, 2),
        "maturity_value": round(corpus, 2),
        "interest_earned": round(corpus - invested, 2),
        "yearly_corpus": yearly,
    }


# =============================================================================

class ComputeRdMaturityTool(Tool):
    name = "compute_rd_maturity"
    description = (
        "Compute the maturity value of a Recurring Deposit (RD) — fixed monthly "
        "deposit, typically quarterly compounding for Indian banks/Post Office. "
        "Use for 'RD of ₹5000/month for 3 years at 7%', 'PO RD maturity'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "monthly_deposit": {"type": "number", "description": "Monthly deposit in rupees."},
            "annual_rate": {"type": "number", "description": "Annual interest rate in percent."},
            "years": {"type": "number", "description": "Tenure in years (fractional OK)."},
            "compounding": {"type": "string", "enum": ["quarterly", "monthly"], "description": "Compounding frequency. Default 'quarterly' (typical for banks)."},
        },
        "required": ["monthly_deposit", "annual_rate", "years"],
    }

    def execute(self, *, monthly_deposit, annual_rate, years, compounding="quarterly", **_) -> ToolResult:
        try:
            P = float(monthly_deposit); rate = float(annual_rate); yrs = float(years)
            n = 4 if compounding == "quarterly" else 12
            r = rate / 100.0
            total_months = int(round(yrs * 12))
            # Standard RD formula (quarterly compounding): A = sum P*(1 + r/n)^(n*t_remaining/12)
            # where t_remaining is months from contribution to maturity.
            corpus = 0.0
            invested = 0.0
            for m in range(1, total_months + 1):
                t_years = (total_months - m + 1) / 12.0
                corpus += P * ((1 + r / n) ** (n * t_years))
                invested += P
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "rd_maturity",
                "inputs": {"monthly_deposit": P, "annual_rate": rate, "years": yrs, "compounding": compounding},
                "result": {
                    "total_invested": round(invested, 2),
                    "maturity_value": round(corpus, 2),
                    "interest_earned": round(corpus - invested, 2),
                    "effective_yield_pct": round(((corpus / invested) ** (1 / yrs) - 1) * 100, 3) if yrs > 0 else 0,
                },
                "note": "RD interest is fully taxable at slab rate. TDS at 10% kicks in if interest exceeds ₹40,000/year (₹50,000 for seniors).",
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"RD calc failed: {e}")


class ComputePpfCorpusTool(Tool):
    name = "compute_ppf_corpus"
    description = (
        "Compute the maturity value of a Public Provident Fund (PPF) account — annual "
        "contribution, 15-year minimum tenure, current rate ~7.1%, EEE tax status. "
        "Use for 'PPF maturity if I deposit ₹1.5L/year for 15 years'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_deposit": {"type": "number", "description": "Annual deposit (max ₹1.5L per FY)."},
            "years": {"type": "integer", "description": "Years (minimum 15, can be extended in 5y blocks). Default 15."},
            "annual_rate": {"type": "number", "description": "Current PPF rate. Default 7.1 (Q1 FY26)."},
        },
        "required": ["annual_deposit"],
    }

    def execute(self, *, annual_deposit, years=15, annual_rate=7.1, **_) -> ToolResult:
        try:
            ad = min(float(annual_deposit), 150000)  # PPF cap
            yrs = max(15, int(years or 15))
            calc = _annual_compound_with_contrib(ad, float(annual_rate), yrs, contrib_at_start=True)
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "ppf_corpus",
                "inputs": {"annual_deposit": ad, "years": yrs, "annual_rate": annual_rate},
                "result": calc,
                "note": (
                    "PPF: EEE tax status (deposit qualifies under 80C, interest tax-free, maturity tax-free). "
                    "Lock-in 15 years; partial withdrawals allowed from year 7. "
                    "Rate set by govt quarterly — verify the current rate."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"PPF calc failed: {e}")


class ComputeNpsCorpusTool(Tool):
    name = "compute_nps_corpus"
    description = (
        "Project the National Pension System (NPS) corpus at retirement, given monthly "
        "contribution, years to retirement, and the asset-allocation split between "
        "equity (E) / corporate-debt (C) / G-sec (G). Tier-1 only. 60% of corpus tax-"
        "free at maturity, 40% must buy an annuity."
    )
    parameters = {
        "type": "object",
        "properties": {
            "monthly_contribution": {"type": "number"},
            "years_to_retirement": {"type": "number"},
            "equity_pct": {"type": "number", "description": "% in equity (E). Default 50."},
            "corporate_debt_pct": {"type": "number", "description": "% in corporate debt (C). Default 30."},
            "gsec_pct": {"type": "number", "description": "% in govt securities (G). Default 20."},
            "expected_return_equity_pct": {"type": "number", "description": "Default 12."},
            "expected_return_cdebt_pct": {"type": "number", "description": "Default 8."},
            "expected_return_gsec_pct": {"type": "number", "description": "Default 7."},
        },
        "required": ["monthly_contribution", "years_to_retirement"],
    }

    def execute(self, *, monthly_contribution, years_to_retirement,
                equity_pct=50, corporate_debt_pct=30, gsec_pct=20,
                expected_return_equity_pct=12, expected_return_cdebt_pct=8, expected_return_gsec_pct=7, **_) -> ToolResult:
        try:
            P = float(monthly_contribution); yrs = float(years_to_retirement)
            we = float(equity_pct)/100; wc = float(corporate_debt_pct)/100; wg = float(gsec_pct)/100
            if abs(we + wc + wg - 1) > 0.02:
                return ToolResult(success=False, error="equity_pct + corporate_debt_pct + gsec_pct must total 100")
            # Weighted return
            r_blended = (we * float(expected_return_equity_pct) + wc * float(expected_return_cdebt_pct) + wg * float(expected_return_gsec_pct)) / 100
            r_m = r_blended / 12
            n = int(round(yrs * 12))
            # Standard SIP FV
            fv = P * (((1 + r_m) ** n - 1) / r_m) * (1 + r_m) if r_m > 0 else P * n
            invested = P * n
            tax_free_lumpsum = fv * 0.60
            annuity_corpus = fv * 0.40
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "nps_corpus",
                "inputs": {
                    "monthly_contribution": P, "years": yrs,
                    "asset_allocation": {"equity": equity_pct, "corporate_debt": corporate_debt_pct, "gsec": gsec_pct},
                    "expected_returns": {"equity": expected_return_equity_pct, "corporate_debt": expected_return_cdebt_pct, "gsec": expected_return_gsec_pct},
                },
                "result": {
                    "blended_return_pct": round(r_blended * 100, 2),
                    "total_invested": round(invested, 2),
                    "corpus_at_retirement": round(fv, 2),
                    "tax_free_lumpsum_60pct": round(tax_free_lumpsum, 2),
                    "annuity_corpus_40pct": round(annuity_corpus, 2),
                    "estimated_monthly_pension_at_6pct_annuity": round(annuity_corpus * 0.06 / 12, 2),
                },
                "note": (
                    "NPS Tier-1 has age-driven max equity caps (75% till 50; tapers down). "
                    "60% lumpsum tax-free at retirement; 40% must buy an annuity. "
                    "80CCD(1B) gives ₹50k extra deduction over and above the ₹1.5L 80C limit. "
                    "Employer's 80CCD(2) contribution is allowed in BOTH old and new regimes."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"NPS calc failed: {e}")


class ComputeSukanyaSamriddhiTool(Tool):
    name = "compute_sukanya_samriddhi"
    description = (
        "Compute the maturity of a Sukanya Samriddhi Yojana (SSY) account for a girl child. "
        "Deposits allowed for first 15 years; account matures 21 years from opening or on "
        "marriage after age 18. EEE tax status."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_deposit": {"type": "number", "description": "Annual deposit (₹250 to ₹1.5L cap)."},
            "annual_rate": {"type": "number", "description": "Current SSY rate. Default 8.2 (Q1 FY26)."},
            "child_current_age": {"type": "number", "description": "Child's age now (must be < 10 to open). Default 5."},
            "deposit_years": {"type": "integer", "description": "Years of deposits (max 15). Default 15."},
            "maturity_age": {"type": "integer", "description": "Maturity age (typically 21). Default 21."},
        },
        "required": ["annual_deposit"],
    }

    def execute(self, *, annual_deposit, annual_rate=8.2, child_current_age=5, deposit_years=15, maturity_age=21, **_) -> ToolResult:
        try:
            ad = max(250, min(float(annual_deposit), 150000))
            rate = float(annual_rate)
            child_age = float(child_current_age)
            dep_yrs = min(int(deposit_years or 15), 15)
            mat_age = int(maturity_age or 21)

            years_to_maturity = max(1, int(mat_age - child_age))

            # Phase 1: deposit years (compound annually with contribution)
            r = rate / 100.0
            corpus = 0.0
            invested = 0.0
            yearly = []
            for y in range(1, years_to_maturity + 1):
                if y <= dep_yrs:
                    corpus = (corpus + ad) * (1 + r)
                    invested += ad
                else:
                    # Phase 2: just compound, no further deposits
                    corpus = corpus * (1 + r)
                yearly.append({"year": y, "child_age": child_age + y, "corpus": round(corpus, 2)})

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "sukanya_samriddhi",
                "inputs": {
                    "annual_deposit": ad, "annual_rate": rate,
                    "child_current_age": child_age, "deposit_years": dep_yrs, "maturity_age": mat_age,
                },
                "result": {
                    "total_invested": round(invested, 2),
                    "maturity_value": round(corpus, 2),
                    "interest_earned": round(corpus - invested, 2),
                    "yearly_corpus": yearly,
                },
                "note": (
                    "SSY: EEE tax status, deposit under 80C (₹1.5L cap shared with other 80C). "
                    "Min ₹250/year required to keep active. Rate is set quarterly by govt — verify."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"SSY calc failed: {e}")


class ComputeScssReturnsTool(Tool):
    name = "compute_scss_returns"
    description = (
        "Compute the quarterly interest payout and maturity value of the Senior Citizens "
        "Savings Scheme (SCSS) — for citizens 60+. Lock-in 5 years, extendable in 3-year "
        "blocks. Interest paid quarterly to bank account."
    )
    parameters = {
        "type": "object",
        "properties": {
            "principal": {"type": "number", "description": "Lump sum (₹1k min, ₹30L cap)."},
            "annual_rate": {"type": "number", "description": "Current SCSS rate. Default 8.2 (Q1 FY26)."},
            "years": {"type": "number", "description": "Tenure. Default 5."},
        },
        "required": ["principal"],
    }

    def execute(self, *, principal, annual_rate=8.2, years=5, **_) -> ToolResult:
        try:
            P = min(float(principal), 3000000)
            rate = float(annual_rate)
            yrs = float(years)
            quarterly_interest = P * rate / 100.0 / 4.0
            total_interest = quarterly_interest * 4 * yrs
            maturity = P + total_interest  # SCSS pays out interest, principal returned at maturity
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "scss_returns",
                "inputs": {"principal": P, "annual_rate": rate, "years": yrs},
                "result": {
                    "quarterly_interest_payout": round(quarterly_interest, 2),
                    "annual_interest": round(quarterly_interest * 4, 2),
                    "total_interest_over_tenure": round(total_interest, 2),
                    "principal_returned_at_maturity": round(P, 2),
                    "total_received": round(maturity, 2),
                },
                "note": (
                    "SCSS: deposit qualifies under 80C (old regime). Interest is fully taxable "
                    "at slab; TDS at 10% if interest > ₹50,000/yr. Premature withdrawal allowed "
                    "with penalty after 1 year."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"SCSS calc failed: {e}")


class ComputeLumpsumReturnTool(Tool):
    name = "compute_lumpsum_return"
    description = (
        "Project the future value of a lump-sum investment over a horizon at an expected "
        "annualised return. Use for 'if I invest ₹10L today at 12% for 15 years', "
        "'one-time investment growth'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "years": {"type": "number"},
            "expected_return_pct": {"type": "number"},
        },
        "required": ["amount", "years", "expected_return_pct"],
    }

    def execute(self, *, amount, years, expected_return_pct, **_) -> ToolResult:
        try:
            P = float(amount); yrs = float(years); r = float(expected_return_pct) / 100.0
            fv = P * ((1 + r) ** yrs)
            yearly = [{"year": y, "value": round(P * ((1 + r) ** y), 2)} for y in range(1, int(yrs) + 1)]
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "lumpsum_return",
                "inputs": {"amount": P, "years": yrs, "expected_return_pct": expected_return_pct},
                "result": {
                    "future_value": round(fv, 2),
                    "wealth_gained": round(fv - P, 2),
                    "multiplier": round(fv / P, 2),
                },
                "yearly_value": yearly,
                "formula": "FV = P × (1 + r)^t",
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Lumpsum calc failed: {e}")


class ComputeSwpSimulationTool(Tool):
    name = "compute_swp_simulation"
    description = (
        "Simulate a Systematic Withdrawal Plan (SWP): you have a corpus, withdraw a fixed "
        "amount monthly, while the rest stays invested at an expected return. Reports how "
        "long the corpus lasts and the year-by-year remaining balance. Use for retirement "
        "income planning."
    )
    parameters = {
        "type": "object",
        "properties": {
            "corpus": {"type": "number", "description": "Starting corpus in rupees."},
            "monthly_withdrawal": {"type": "number", "description": "Monthly withdrawal in rupees."},
            "expected_return_pct": {"type": "number", "description": "Expected annualised return on remaining corpus."},
            "max_years": {"type": "integer", "description": "Cap simulation length (default 50)."},
            "monthly_inflation_pct": {"type": "number", "description": "Optional — step up withdrawal annually for inflation. Default 0."},
        },
        "required": ["corpus", "monthly_withdrawal", "expected_return_pct"],
    }

    def execute(self, *, corpus, monthly_withdrawal, expected_return_pct, max_years=50, monthly_inflation_pct=0, **_) -> ToolResult:
        try:
            balance = float(corpus); w = float(monthly_withdrawal); r_m = float(expected_return_pct) / 12 / 100
            infl = float(monthly_inflation_pct or 0) / 100
            yearly = []
            current_w = w
            total_withdrawn = 0.0
            months_lasted = 0
            for y in range(1, int(max_years) + 1):
                if y > 1 and infl > 0:
                    current_w *= (1 + infl)
                year_withdrawn = 0.0
                exhausted_in_year = False
                for _ in range(12):
                    balance = balance * (1 + r_m)
                    if balance <= current_w:
                        year_withdrawn += balance
                        total_withdrawn += balance
                        balance = 0
                        exhausted_in_year = True
                        break
                    balance -= current_w
                    year_withdrawn += current_w
                    total_withdrawn += current_w
                    months_lasted += 1
                yearly.append({
                    "year": y,
                    "monthly_withdrawal": round(current_w, 2),
                    "year_withdrawn": round(year_withdrawn, 2),
                    "ending_balance": round(balance, 2),
                })
                if exhausted_in_year:
                    break
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "swp_simulation",
                "inputs": {
                    "corpus": float(corpus), "monthly_withdrawal": w,
                    "expected_return_pct": expected_return_pct,
                    "monthly_inflation_pct": monthly_inflation_pct,
                },
                "result": {
                    "years_corpus_lasts": yearly[-1]["year"] if yearly else 0,
                    "total_withdrawn": round(total_withdrawn, 2),
                    "ending_balance": yearly[-1]["ending_balance"] if yearly else 0,
                    "exhausted": yearly and yearly[-1]["ending_balance"] <= 0,
                },
                "yearly_schedule": yearly,
                "note": "Equity SWP redemptions: holding > 1 year → LTCG at 12.5% above ₹1.25L per FY. Plan tax accordingly.",
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"SWP calc failed: {e}")
