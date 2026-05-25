"""Tools: compare_tax_regimes, compute_capital_gains_tax (FY 2025-26)."""

from datetime import date

from agent.tools.base import Tool, ToolResult


# ---- FY 2025-26 slab tables -------------------------------------------------

NEW_REGIME_SLABS_2025_26 = [
    (0,        400000,   0),
    (400000,   800000,   5),
    (800000,   1200000,  10),
    (1200000,  1600000,  15),
    (1600000,  2000000,  20),
    (2000000,  2400000,  25),
    (2400000,  None,     30),
]

OLD_REGIME_SLABS_BELOW_60 = [
    (0,        250000,   0),
    (250000,   500000,   5),
    (500000,   1000000,  20),
    (1000000,  None,     30),
]

OLD_REGIME_SLABS_SENIOR = [   # 60-79 yrs
    (0,        300000,   0),
    (300000,   500000,   5),
    (500000,   1000000,  20),
    (1000000,  None,     30),
]

OLD_REGIME_SLABS_SUPER_SENIOR = [   # 80+ yrs
    (0,        500000,   0),
    (500000,   1000000,  20),
    (1000000,  None,     30),
]


def _slab_tax(taxable_income: float, slabs) -> float:
    """Walk the slab table and accumulate the slab-wise tax."""
    tax = 0.0
    for lo, hi, rate in slabs:
        if taxable_income <= lo:
            break
        upper = hi if hi is not None else taxable_income
        applicable = min(taxable_income, upper) - lo
        tax += applicable * rate / 100.0
    return tax


def _surcharge_old(tax: float, taxable_income: float) -> float:
    """Old-regime surcharge — full ladder up to 37%."""
    if taxable_income <= 5_000_000:
        return 0
    if taxable_income <= 10_000_000:
        return tax * 0.10
    if taxable_income <= 20_000_000:
        return tax * 0.15
    if taxable_income <= 50_000_000:
        return tax * 0.25
    return tax * 0.37


def _surcharge_new(tax: float, taxable_income: float) -> float:
    """New-regime surcharge — capped at 25% per the FY 2023-24 rule."""
    if taxable_income <= 5_000_000:
        return 0
    if taxable_income <= 10_000_000:
        return tax * 0.10
    if taxable_income <= 20_000_000:
        return tax * 0.15
    return tax * 0.25


def _compute_old_regime(taxable_income: float, age_group: str) -> dict:
    if age_group == "super_senior":
        slabs = OLD_REGIME_SLABS_SUPER_SENIOR
    elif age_group == "senior":
        slabs = OLD_REGIME_SLABS_SENIOR
    else:
        slabs = OLD_REGIME_SLABS_BELOW_60

    slab_tax = _slab_tax(taxable_income, slabs)
    rebate = min(slab_tax, 12500) if taxable_income <= 500000 else 0
    after_rebate = slab_tax - rebate
    surcharge = _surcharge_old(after_rebate, taxable_income)
    cess = (after_rebate + surcharge) * 0.04
    total = after_rebate + surcharge + cess

    return {
        "slab_tax": round(slab_tax, 2),
        "rebate_87A": round(rebate, 2),
        "tax_after_rebate": round(after_rebate, 2),
        "surcharge": round(surcharge, 2),
        "cess": round(cess, 2),
        "total_tax": round(total, 2),
    }


def _compute_new_regime(taxable_income: float) -> dict:
    slab_tax = _slab_tax(taxable_income, NEW_REGIME_SLABS_2025_26)

    # 87A rebate: full rebate up to ₹12L; marginal relief above.
    if taxable_income <= 1_200_000:
        rebate = slab_tax
    else:
        excess_over_threshold = taxable_income - 1_200_000
        if slab_tax > excess_over_threshold:
            rebate = slab_tax - excess_over_threshold
        else:
            rebate = 0

    after_rebate = slab_tax - rebate
    surcharge = _surcharge_new(after_rebate, taxable_income)
    cess = (after_rebate + surcharge) * 0.04
    total = after_rebate + surcharge + cess

    return {
        "slab_tax": round(slab_tax, 2),
        "rebate_87A": round(rebate, 2),
        "tax_after_rebate": round(after_rebate, 2),
        "surcharge": round(surcharge, 2),
        "cess": round(cess, 2),
        "total_tax": round(total, 2),
    }


def _resolve_taxable(regime: str, gross_income: float, is_salaried: bool, deductions: dict) -> dict:
    """
    Apply standard deduction + regime-allowed deductions to gross_income.
    Returns a dict with the breakdown and the final taxable_income.
    """
    deductions = deductions or {}

    if regime == "old":
        std = 50000 if is_salaried else 0
        applied = {
            "standard_deduction": std,
            "section_80c":          min(float(deductions.get("section_80c", 0) or 0),         150000),
            "section_80d":          min(float(deductions.get("section_80d", 0) or 0),          75000),
            "section_80ccd_1b":     min(float(deductions.get("section_80ccd_1b", 0) or 0),     50000),
            "section_80ccd_2":      float(deductions.get("section_80ccd_2", 0) or 0),
            "home_loan_interest":   min(float(deductions.get("home_loan_interest", 0) or 0),  200000),
            "hra_exempt":           float(deductions.get("hra_exempt", 0) or 0),
            "section_80e":          float(deductions.get("section_80e", 0) or 0),
            "section_80g":          float(deductions.get("section_80g", 0) or 0),
            "other_deductions":     float(deductions.get("other_deductions", 0) or 0),
        }
    else:  # new regime — only std deduction + 80CCD(2) employer NPS allowed
        std = 75000 if is_salaried else 0
        applied = {
            "standard_deduction": std,
            "section_80ccd_2":    float(deductions.get("section_80ccd_2", 0) or 0),
        }

    total_deduction = sum(applied.values())
    taxable_income = max(0.0, gross_income - total_deduction)
    return {
        "applied": {k: round(v, 2) for k, v in applied.items()},
        "total_deduction": round(total_deduction, 2),
        "taxable_income": round(taxable_income, 2),
    }


# ============================================================================

class CompareTaxRegimesTool(Tool):
    name = "compare_tax_regimes"
    description = (
        "Compute and compare the user's income-tax liability under the OLD and NEW regimes "
        "for FY 2025-26 (AY 2026-27) using their actual income and deductions, then recommend "
        "which regime is cheaper. Handles standard deduction, 80C/80D/80CCD, HRA exemption, "
        "home-loan interest, 87A rebate (with marginal relief in new regime), surcharge, "
        "and 4% cess. Use when the user asks 'old vs new regime', 'which regime saves more', "
        "or 'compute my tax'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "gross_income": {
                "type": "number",
                "description": "Gross annual income in rupees, before any deductions or std deduction.",
            },
            "is_salaried": {
                "type": "boolean",
                "description": "Is the user salaried? Drives standard deduction (₹50k old / ₹75k new). Default True.",
            },
            "age_group": {
                "type": "string",
                "enum": ["below_60", "senior", "super_senior"],
                "description": "Age group — affects old-regime slab thresholds. Default 'below_60'.",
            },
            "deductions": {
                "type": "object",
                "description": (
                    "Object with keys: section_80c (max ₹1.5L), section_80d (health ins, "
                    "max ₹75k for self+senior parents), section_80ccd_1b (NPS extra ₹50k), "
                    "section_80ccd_2 (employer NPS — allowed in BOTH regimes), "
                    "home_loan_interest (max ₹2L self-occupied), hra_exempt (computed externally), "
                    "section_80e (education loan interest), section_80g (charity), other_deductions. "
                    "All values in rupees. Old regime uses everything; new regime ignores all except section_80ccd_2."
                ),
            },
        },
        "required": ["gross_income"],
    }

    def execute(
        self,
        *,
        gross_income: float,
        is_salaried: bool = True,
        age_group: str = "below_60",
        deductions: dict = None,
        **_,
    ) -> ToolResult:
        try:
            gross_income = float(gross_income)
            if gross_income < 0:
                return ToolResult(success=False, error="gross_income must be ≥ 0")
            age_group = (age_group or "below_60").strip().lower()
            if age_group not in ("below_60", "senior", "super_senior"):
                return ToolResult(success=False, error=f"Invalid age_group '{age_group}'")

            old_in = _resolve_taxable("old", gross_income, is_salaried, deductions)
            new_in = _resolve_taxable("new", gross_income, is_salaried, deductions)

            old_tax = _compute_old_regime(old_in["taxable_income"], age_group)
            new_tax = _compute_new_regime(new_in["taxable_income"])

            recommended = "new" if new_tax["total_tax"] <= old_tax["total_tax"] else "old"
            savings = round(abs(old_tax["total_tax"] - new_tax["total_tax"]), 2)

            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "tax_regime_compare",
                    "fy": "2025-26",
                    "ay": "2026-27",
                    "inputs": {
                        "gross_income": round(gross_income, 2),
                        "is_salaried": is_salaried,
                        "age_group": age_group,
                        "deductions": deductions or {},
                    },
                    "old_regime": {
                        "deductions_applied": old_in["applied"],
                        "total_deductions": old_in["total_deduction"],
                        "taxable_income": old_in["taxable_income"],
                        **old_tax,
                    },
                    "new_regime": {
                        "deductions_applied": new_in["applied"],
                        "total_deductions": new_in["total_deduction"],
                        "taxable_income": new_in["taxable_income"],
                        **new_tax,
                    },
                    "result": {
                        "recommended_regime": recommended,
                        "savings_by_choosing_recommended": savings,
                        "old_total_tax": old_tax["total_tax"],
                        "new_total_tax": new_tax["total_tax"],
                    },
                    "note": (
                        "FY 2025-26 (AY 2026-27) rules. New regime: full 87A rebate up to "
                        "₹12L taxable income (with marginal relief above), surcharge capped "
                        "at 25%. Old regime: 87A rebate up to ₹5L, full surcharge ladder. "
                        "Cess at 4% applied on tax+surcharge in both. This is an estimate — "
                        "consult a CA for edge cases (capital gains, foreign income, ESOPs, "
                        "presumptive taxation, surcharge marginal relief)."
                    ),
                },
                display_hint="calculator_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Tax comparison failed: {e}")


# ============================================================================
# Capital gains
# ============================================================================

# Finance Act 2024 changed capital-gains rules effective 23-Jul-2024.
_FA_2024_CUTOFF = date(2024, 7, 23)


def _holding_days(buy_iso: str, sell_iso: str) -> tuple:
    buy = date.fromisoformat(buy_iso)
    sell = date.fromisoformat(sell_iso) if sell_iso else date.today()
    if sell < buy:
        raise ValueError("sell_date is before buy_date")
    return (sell - buy).days, buy, sell


def _equity_listed_tax(gain: float, holding_days: int, sell_date: date) -> dict:
    new_rules = sell_date >= _FA_2024_CUTOFF
    if holding_days <= 365:
        rate = 20.0 if new_rules else 15.0
        tax = max(0, gain) * rate / 100.0
        return {
            "gain_type": "STCG",
            "rate_pct": rate,
            "exemption": 0,
            "taxable_gain": max(0, gain),
            "tax": tax,
            "rule_note": (
                f"Listed equity / equity MF held ≤ 1 year → STCG at {rate}% "
                + ("(post 23-Jul-2024 rate)." if new_rules else "(pre 23-Jul-2024 rate).")
            ),
        }
    # LTCG
    exemption = 125000 if new_rules else 100000
    rate = 12.5 if new_rules else 10.0
    taxable = max(0, gain - exemption)
    tax = taxable * rate / 100.0
    return {
        "gain_type": "LTCG",
        "rate_pct": rate,
        "exemption": exemption,
        "taxable_gain": taxable,
        "tax": tax,
        "rule_note": (
            f"Listed equity / equity MF held > 1 year → LTCG at {rate}% above ₹{exemption:,} "
            f"per-FY exemption ({'post 23-Jul-2024' if new_rules else 'pre 23-Jul-2024'})."
        ),
    }


def _debt_mf_tax(gain: float, slab_pct: float) -> dict:
    rate = slab_pct
    tax = max(0, gain) * rate / 100.0
    return {
        "gain_type": "Slab-rate",
        "rate_pct": rate,
        "exemption": 0,
        "taxable_gain": max(0, gain),
        "tax": tax,
        "rule_note": (
            "Debt MF (units bought after 1-Apr-2023): all gains taxed at the investor's "
            "slab rate, regardless of holding period. For units bought before 1-Apr-2023, "
            "different rules may apply — consult a CA."
        ),
    }


def _property_tax(gain: float, holding_days: int, buy_date: date, sell_date: date, slab_pct: float) -> dict:
    new_rules = sell_date >= _FA_2024_CUTOFF
    if holding_days <= 730:  # 2 years
        rate = slab_pct
        tax = max(0, gain) * rate / 100.0
        return {
            "gain_type": "STCG",
            "rate_pct": rate,
            "exemption": 0,
            "taxable_gain": max(0, gain),
            "tax": tax,
            "rule_note": "Property held ≤ 2 years → STCG at the investor's slab rate.",
        }
    # LTCG
    if new_rules:
        rate = 12.5
        tax = max(0, gain) * rate / 100.0
        note = "Property LTCG at 12.5% (no indexation) per the post 23-Jul-2024 Finance Act rule."
        if buy_date < _FA_2024_CUTOFF:
            note += (
                " Since the property was purchased BEFORE 23-Jul-2024, the taxpayer may "
                "alternatively elect 20% WITH indexation — compute both and pick the lower. "
                "This calculator shows the 12.5% number; indexation needs CII lookup."
            )
        return {
            "gain_type": "LTCG",
            "rate_pct": rate,
            "exemption": 0,
            "taxable_gain": max(0, gain),
            "tax": tax,
            "rule_note": note,
        }
    # Pre-Jul-2024 sale — 20% with indexation (we don't apply CII here)
    rate = 20.0
    tax = max(0, gain) * rate / 100.0
    return {
        "gain_type": "LTCG",
        "rate_pct": rate,
        "exemption": 0,
        "taxable_gain": max(0, gain),
        "tax": tax,
        "rule_note": (
            "Property LTCG at 20% with indexation (pre 23-Jul-2024). This calculator does NOT "
            "apply CII-based indexation — the actual taxable gain after indexation will be lower. "
            "Look up the relevant year's CII and recompute."
        ),
    }


def _gold_tax(gain: float, holding_days: int, sell_date: date, slab_pct: float) -> dict:
    new_rules = sell_date >= _FA_2024_CUTOFF
    threshold = 730 if new_rules else 1095   # 2y post / 3y pre
    if holding_days <= threshold:
        rate = slab_pct
        tax = max(0, gain) * rate / 100.0
        return {
            "gain_type": "STCG",
            "rate_pct": rate,
            "exemption": 0,
            "taxable_gain": max(0, gain),
            "tax": tax,
            "rule_note": (
                f"Gold held ≤ {threshold // 365} years → STCG at the investor's slab rate."
            ),
        }
    rate = 12.5 if new_rules else 20.0
    tax = max(0, gain) * rate / 100.0
    return {
        "gain_type": "LTCG",
        "rate_pct": rate,
        "exemption": 0,
        "taxable_gain": max(0, gain),
        "tax": tax,
        "rule_note": (
            f"Gold LTCG at {rate}% "
            + ("(no indexation, post 23-Jul-2024)." if new_rules else "(with indexation, pre 23-Jul-2024 — CII not applied here).")
        ),
    }


class ComputeCapitalGainsTaxTool(Tool):
    name = "compute_capital_gains_tax"
    description = (
        "Compute capital-gains tax on a sale: equity / equity MF, debt MF, property, or gold. "
        "Applies the post 23-Jul-2024 Finance Act 2024 rules when sell_date is on/after that "
        "cutoff, otherwise the prior rules. Returns the gain type (LTCG vs STCG), applicable "
        "rate, exemption, taxable gain, tax owed, and net amount after tax."
    )
    parameters = {
        "type": "object",
        "properties": {
            "asset_type": {
                "type": "string",
                "enum": ["equity_listed", "equity_mf", "debt_mf", "property", "gold", "unlisted_equity"],
                "description": (
                    "Type of asset sold. 'equity_listed' / 'equity_mf' use STT-paid equity rules. "
                    "'debt_mf' is Indian debt mutual fund. 'property' is real estate. "
                    "'gold' covers physical gold + jewellery + ETF. 'unlisted_equity' for unlisted shares."
                ),
            },
            "buy_price": {"type": "number", "description": "Total purchase price in rupees."},
            "sell_price": {"type": "number", "description": "Total sale price in rupees."},
            "buy_date": {"type": "string", "description": "Purchase date in YYYY-MM-DD."},
            "sell_date": {"type": "string", "description": "Sale date in YYYY-MM-DD. Defaults to today if omitted."},
            "slab_pct": {
                "type": "number",
                "description": "User's marginal tax slab in percent — used for STCG and debt-MF cases. Default 30.",
            },
        },
        "required": ["asset_type", "buy_price", "sell_price", "buy_date"],
    }

    def execute(
        self,
        *,
        asset_type: str,
        buy_price: float,
        sell_price: float,
        buy_date: str,
        sell_date: str = None,
        slab_pct: float = 30.0,
        **_,
    ) -> ToolResult:
        try:
            asset_type = (asset_type or "").strip().lower()
            buy_price = float(buy_price)
            sell_price = float(sell_price)
            slab_pct = float(slab_pct or 30.0)

            holding, b_date, s_date = _holding_days(buy_date, sell_date)
            gain = sell_price - buy_price

            if asset_type in ("equity_listed", "equity_mf"):
                calc = _equity_listed_tax(gain, holding, s_date)
            elif asset_type in ("debt_mf", "debt"):
                calc = _debt_mf_tax(gain, slab_pct)
            elif asset_type in ("property", "real_estate"):
                calc = _property_tax(gain, holding, b_date, s_date, slab_pct)
            elif asset_type == "gold":
                calc = _gold_tax(gain, holding, s_date, slab_pct)
            elif asset_type == "unlisted_equity":
                # Same holding-period thresholds and rules as property post-Jul-2024:
                # ≤ 24 months → STCG at slab; > 24 months → 12.5% LTCG (no indexation).
                calc = _property_tax(gain, holding, b_date, s_date, slab_pct)
                calc["rule_note"] = "Unlisted equity: " + calc["rule_note"].replace("Property", "Unlisted equity")
            else:
                return ToolResult(success=False, error=f"Unknown asset_type '{asset_type}'")

            tax = round(calc["tax"], 2)
            return ToolResult(
                success=True,
                data={
                    "kind": "calculator",
                    "calculator": "capital_gains_tax",
                    "inputs": {
                        "asset_type": asset_type,
                        "buy_price": round(buy_price, 2),
                        "sell_price": round(sell_price, 2),
                        "buy_date": buy_date,
                        "sell_date": s_date.isoformat(),
                        "slab_pct": slab_pct,
                    },
                    "result": {
                        "holding_period_days": holding,
                        "holding_period_years": round(holding / 365.25, 2),
                        "gross_gain": round(gain, 2),
                        "gain_type": calc["gain_type"],
                        "rate_pct": calc["rate_pct"],
                        "exemption_applied": calc["exemption"],
                        "taxable_gain": round(calc["taxable_gain"], 2),
                        "tax": tax,
                        "net_after_tax": round(sell_price - tax, 2),
                    },
                    "rule_note": calc["rule_note"],
                    "general_note": (
                        "Cess of 4% may additionally apply on the computed tax in some "
                        "scenarios (e.g., when computed alongside slab-tax cases). For "
                        "high-value transactions, surcharge may also apply. Treat this as "
                        "an estimate; use a CA for filing."
                    ),
                },
                display_hint="calculator_card",
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Capital gains calculation failed: {e}")
