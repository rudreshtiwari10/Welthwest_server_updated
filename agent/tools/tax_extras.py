"""Tools: compute_income_tax (single regime), compute_advance_tax, compute_hra_exemption,
compute_gst, compute_80c_optimizer."""

from agent.tools.base import Tool, ToolResult
from agent.tools.tax import _compute_old_regime, _compute_new_regime, _resolve_taxable


class ComputeIncomeTaxTool(Tool):
    name = "compute_income_tax"
    description = (
        "Compute income tax under a SINGLE specified regime (old or new) for FY 2025-26. "
        "Use when the user has already chosen a regime and just wants the tax number — "
        "no comparison. For 'which is better' use compare_tax_regimes instead."
    )
    parameters = {
        "type": "object",
        "properties": {
            "regime": {"type": "string", "enum": ["old", "new"]},
            "gross_income": {"type": "number"},
            "is_salaried": {"type": "boolean", "description": "Default true."},
            "age_group": {"type": "string", "enum": ["below_60", "senior", "super_senior"]},
            "deductions": {"type": "object", "description": "Same shape as compare_tax_regimes — old regime uses all, new ignores all except section_80ccd_2."},
        },
        "required": ["regime", "gross_income"],
    }

    def execute(self, *, regime, gross_income, is_salaried=True, age_group="below_60", deductions=None, **_) -> ToolResult:
        try:
            regime = (regime or "").strip().lower()
            if regime not in ("old", "new"):
                return ToolResult(success=False, error="regime must be 'old' or 'new'")
            r = _resolve_taxable(regime, float(gross_income), bool(is_salaried), deductions)
            tax = _compute_old_regime(r["taxable_income"], age_group) if regime == "old" else _compute_new_regime(r["taxable_income"])
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "income_tax",
                "fy": "2025-26", "ay": "2026-27",
                "inputs": {"regime": regime, "gross_income": float(gross_income), "is_salaried": is_salaried, "age_group": age_group, "deductions": deductions or {}},
                "deductions_applied": r["applied"],
                "total_deductions": r["total_deduction"],
                "taxable_income": r["taxable_income"],
                "result": tax,
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Income tax calc failed: {e}")


class ComputeAdvanceTaxTool(Tool):
    name = "compute_advance_tax"
    description = (
        "Compute the advance-tax instalment schedule for the current FY: 15% by 15-Jun, "
        "45% by 15-Sep, 75% by 15-Dec, 100% by 15-Mar. Required if total tax liability "
        "exceeds ₹10,000. Use for 'do I need to pay advance tax', 'next instalment'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "estimated_annual_tax": {"type": "number", "description": "Total tax expected for the FY."},
            "tax_already_paid": {"type": "number", "description": "Total advance tax + TDS already paid this FY. Default 0."},
        },
        "required": ["estimated_annual_tax"],
    }

    def execute(self, *, estimated_annual_tax, tax_already_paid=0, **_) -> ToolResult:
        try:
            T = float(estimated_annual_tax); paid = float(tax_already_paid or 0)
            if T <= 10000:
                return ToolResult(success=True, data={
                    "kind": "calculator", "calculator": "advance_tax",
                    "inputs": {"estimated_annual_tax": T, "tax_already_paid": paid},
                    "result": {"required": False, "reason": "Advance tax not required — total liability ≤ ₹10,000."},
                }, display_hint="calculator_card")

            schedule = [
                {"due_by": "15-Jun", "cumulative_pct": 15, "cumulative_amount": round(T * 0.15, 2)},
                {"due_by": "15-Sep", "cumulative_pct": 45, "cumulative_amount": round(T * 0.45, 2)},
                {"due_by": "15-Dec", "cumulative_pct": 75, "cumulative_amount": round(T * 0.75, 2)},
                {"due_by": "15-Mar", "cumulative_pct": 100, "cumulative_amount": round(T, 2)},
            ]
            for s in schedule:
                s["pending_after_paid"] = round(max(0, s["cumulative_amount"] - paid), 2)

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "advance_tax",
                "inputs": {"estimated_annual_tax": T, "tax_already_paid": paid},
                "result": {
                    "required": True,
                    "total_for_fy": round(T, 2),
                    "schedule": schedule,
                },
                "note": (
                    "Senior citizens (60+) without business income are exempt from advance tax. "
                    "Underpayment attracts interest under sections 234B / 234C."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Advance tax calc failed: {e}")


class ComputeHraExemptionTool(Tool):
    name = "compute_hra_exemption"
    description = (
        "Compute HRA tax exemption (old regime only). Exemption = LEAST of: actual HRA, "
        "50% of (basic+DA) for metro / 40% for non-metro, or rent paid minus 10% of "
        "(basic+DA). Use for 'how much HRA can I claim'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "annual_basic_da": {"type": "number", "description": "Annual basic + DA in rupees."},
            "annual_hra_received": {"type": "number"},
            "annual_rent_paid": {"type": "number"},
            "is_metro": {"type": "boolean", "description": "True for Delhi/Mumbai/Chennai/Kolkata. Default false."},
        },
        "required": ["annual_basic_da", "annual_hra_received", "annual_rent_paid"],
    }

    def execute(self, *, annual_basic_da, annual_hra_received, annual_rent_paid, is_metro=False, **_) -> ToolResult:
        try:
            basic = float(annual_basic_da); hra = float(annual_hra_received); rent = float(annual_rent_paid)
            metro = bool(is_metro)
            cap1 = hra
            cap2 = basic * (0.50 if metro else 0.40)
            cap3 = max(0, rent - 0.10 * basic)
            exemption = max(0, min(cap1, cap2, cap3))
            taxable_hra = max(0, hra - exemption)
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "hra_exemption",
                "inputs": {"annual_basic_da": basic, "annual_hra_received": hra, "annual_rent_paid": rent, "is_metro": metro},
                "result": {
                    "actual_hra_received": round(hra, 2),
                    "metro_or_non_metro_cap": round(cap2, 2),
                    "rent_minus_10pct_basic": round(cap3, 2),
                    "exemption_least_of_three": round(exemption, 2),
                    "taxable_portion_of_hra": round(taxable_hra, 2),
                },
                "note": (
                    "HRA exemption available only under the OLD regime. "
                    "If annual rent exceeds ₹1L, the landlord's PAN must be furnished. "
                    "Rent receipts and a rental agreement should be retained for assessment."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"HRA calc failed: {e}")


class ComputeGstTool(Tool):
    name = "compute_gst"
    description = (
        "Compute GST splits — CGST/SGST (intra-state) or IGST (inter-state) — given an "
        "amount, GST rate, and whether the rate is exclusive or inclusive. Use for "
        "'GST on ₹50,000 at 18%', 'reverse-calculate base from inclusive amount'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "description": "Amount in rupees."},
            "gst_rate_pct": {"type": "number", "description": "Total GST rate (5/12/18/28 etc.)."},
            "amount_is_inclusive": {"type": "boolean", "description": "True if amount already includes GST. Default false."},
            "interstate": {"type": "boolean", "description": "True for IGST, false for CGST+SGST split. Default false."},
        },
        "required": ["amount", "gst_rate_pct"],
    }

    def execute(self, *, amount, gst_rate_pct, amount_is_inclusive=False, interstate=False, **_) -> ToolResult:
        try:
            A = float(amount); rate = float(gst_rate_pct) / 100.0
            if amount_is_inclusive:
                base = A / (1 + rate)
                gst = A - base
            else:
                base = A
                gst = base * rate
            total = base + gst
            split = {"igst": round(gst, 2)} if interstate else {"cgst": round(gst / 2, 2), "sgst": round(gst / 2, 2)}
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "gst",
                "inputs": {"amount": A, "gst_rate_pct": gst_rate_pct, "amount_is_inclusive": amount_is_inclusive, "interstate": interstate},
                "result": {
                    "base_amount": round(base, 2),
                    "total_gst": round(gst, 2),
                    **split,
                    "total_with_gst": round(total, 2),
                },
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"GST calc failed: {e}")


class Compute80cOptimizerTool(Tool):
    name = "compute_80c_optimizer"
    description = (
        "Given the user's current 80C usage, compute the remaining headroom up to ₹1.5L "
        "and suggest instruments to fill the gap, with their pros/cons. Use for 'how much "
        "more can I invest under 80C', 'best way to fill ₹1L 80C gap'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "current_80c_used": {"type": "number", "description": "Current 80C amount already invested/committed this FY."},
            "tax_slab_pct": {"type": "number", "description": "User's marginal slab — used to compute tax-saved. Default 30."},
        },
        "required": ["current_80c_used"],
    }

    def execute(self, *, current_80c_used, tax_slab_pct=30, **_) -> ToolResult:
        try:
            used = float(current_80c_used); slab = float(tax_slab_pct)
            cap = 150000.0
            headroom = max(0, cap - used)
            tax_saved_at_cap = (used + headroom) * slab / 100 if used + headroom > 0 else 0
            additional_savings = headroom * slab / 100
            options = [
                {"instrument": "ELSS Mutual Fund", "lock_in_years": 3, "expected_return": "~12% (market-linked)", "tax_status": "LTCG 12.5% above ₹1.25L/yr at sale"},
                {"instrument": "PPF", "lock_in_years": 15, "expected_return": "~7.1% (govt-set)", "tax_status": "EEE — fully tax-free"},
                {"instrument": "EPF (employee contribution)", "lock_in_years": "till retirement", "expected_return": "~8.25% (govt-set)", "tax_status": "EEE if held 5+ years"},
                {"instrument": "5-year Tax-Saver FD", "lock_in_years": 5, "expected_return": "~7% (bank-set)", "tax_status": "Interest fully taxable"},
                {"instrument": "NSC (National Savings Certificate)", "lock_in_years": 5, "expected_return": "~7.7% (govt-set)", "tax_status": "Interest taxable; reinvested NSC interest is itself 80C-eligible (years 1-4)"},
                {"instrument": "Sukanya Samriddhi (girl child)", "lock_in_years": "till girl is 21 / married after 18", "expected_return": "~8.2%", "tax_status": "EEE"},
                {"instrument": "Life-insurance premium", "lock_in_years": "policy term", "expected_return": "varies (avoid endowment for IRR)", "tax_status": "Maturity tax-free if conditions met"},
                {"instrument": "Home-loan principal repayment", "lock_in_years": "loan tenure", "expected_return": "n/a", "tax_status": "Counts only if home is not sold within 5 years"},
            ]
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "80c_optimizer",
                "inputs": {"current_80c_used": used, "tax_slab_pct": slab},
                "result": {
                    "cap": cap,
                    "currently_used": round(used, 2),
                    "remaining_headroom": round(headroom, 2),
                    "tax_already_saved_estimate": round(used * slab / 100, 2),
                    "additional_tax_savings_at_cap": round(additional_savings, 2),
                    "total_tax_savings_at_full_cap": round(tax_saved_at_cap, 2),
                },
                "options_to_fill_gap": options,
                "note": (
                    "80C is allowed only under the old regime. Under the new regime, only "
                    "section 80CCD(2) (employer NPS) is allowed. NPS 80CCD(1B) gives an "
                    "additional ₹50k OVER AND ABOVE the 80C cap — independent."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"80C optimiser failed: {e}")
