"""User-context extras: portfolio XIRR, simulate portfolio change, track goal progress."""

from datetime import date, datetime
from typing import List, Tuple

from agent.tools.base import Tool, ToolResult


def _parse_date(s) -> date:
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    s = str(s)
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return date.today()


def _xnpv(rate: float, flows: List[Tuple[date, float]]) -> float:
    """Net present value of irregular cash flows. flows: [(date, amount), ...] — amount<0 outflow, >0 inflow."""
    if not flows:
        return 0.0
    t0 = flows[0][0]
    return sum(amount / ((1 + rate) ** ((d - t0).days / 365.25)) for d, amount in flows)


def _xirr(flows: List[Tuple[date, float]], guess: float = 0.10) -> float:
    """XIRR via bisection. flows must contain at least one negative and one positive value."""
    if len(flows) < 2:
        return 0.0
    has_neg = any(a < 0 for _, a in flows)
    has_pos = any(a > 0 for _, a in flows)
    if not (has_neg and has_pos):
        return 0.0
    lo, hi = -0.95, 5.00
    for _ in range(200):
        mid = (lo + hi) / 2
        v = _xnpv(mid, flows)
        if abs(v) < 1e-2:
            return mid
        if _xnpv(lo, flows) * v < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# =============================================================================

class ComputePortfolioXirrTool(Tool):
    name = "compute_portfolio_xirr"
    description = (
        "Compute the XIRR (annualised time-weighted IRR) of the user's saved portfolio "
        "using buy_date + invested amount as outflows and a current market value as the "
        "single inflow. Requires a current_value override OR (in this MVP) the saved "
        "buy-price snapshot — live-price valuation is a Phase 5 item."
    )
    parameters = {
        "type": "object",
        "properties": {
            "current_total_value_override": {
                "type": "number",
                "description": "Manually-supplied current portfolio value. If omitted, uses saved buy-prices (returns 0% — useful as a placeholder).",
            },
        },
    }

    def execute(self, *, _ctx: dict = None, current_total_value_override=None, **_) -> ToolResult:
        try:
            uid = (_ctx or {}).get("user_id")
            if not uid:
                return ToolResult(success=False, error="Sign in to use this calculator")
            from services.user_context_service import get_portfolio
            pf = get_portfolio(uid)
            holdings = pf.get("holdings") or []
            if not holdings:
                return ToolResult(success=False, error="No saved holdings — add some via Account → Money Profile")

            flows: List[Tuple[date, float]] = []
            invested_total = 0.0
            for h in holdings:
                qty = float(h.get("quantity") or 0); buy = float(h.get("avg_buy_price") or 0)
                amt = qty * buy
                if amt <= 0:
                    continue
                d = _parse_date(h.get("buy_date") or date.today().isoformat())
                flows.append((d, -amt))
                invested_total += amt

            cv = float(current_total_value_override) if current_total_value_override else invested_total
            flows.append((date.today(), cv))
            flows.sort(key=lambda x: x[0])

            xirr = _xirr(flows) * 100
            absolute_gain = cv - invested_total
            absolute_pct = (cv / invested_total - 1) * 100 if invested_total else 0

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "portfolio_xirr",
                "inputs": {
                    "holdings_count": len(holdings),
                    "current_total_value_override": current_total_value_override,
                },
                "result": {
                    "total_invested": round(invested_total, 2),
                    "current_value_used": round(cv, 2),
                    "absolute_gain": round(absolute_gain, 2),
                    "absolute_return_pct": round(absolute_pct, 2),
                    "xirr_pct": round(xirr, 2),
                    "live_price_valuation_used": current_total_value_override is not None,
                },
                "note": (
                    "When current_total_value_override is omitted, this MVP returns XIRR using "
                    "the buy-price snapshot — i.e., 0% return (since no growth is applied). "
                    "Pass the current portfolio value (sum of qty × today's price) for a real "
                    "XIRR. Live-price aggregation will arrive in a later phase."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Portfolio XIRR failed: {e}")


class SimulatePortfolioChangeTool(Tool):
    name = "simulate_portfolio_change"
    description = (
        "Simulate the effect of adding or removing a holding in the user's saved portfolio: "
        "shows the new asset-class breakdown, new top-holdings, and concentration flags "
        "WITHOUT actually saving the change. Use for 'what if I add ₹2L of HDFC Bank', "
        "'what if I sell my RELIANCE position'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "remove"]},
            "asset_type": {"type": "string", "description": "equity, equity_mf, debt_mf, fd, ppf, gold, etc."},
            "symbol": {"type": "string"},
            "name": {"type": "string"},
            "quantity": {"type": "number"},
            "price": {"type": "number", "description": "For 'add', the buy price; for 'remove', the sale price."},
        },
        "required": ["action", "asset_type"],
    }

    def execute(self, *, _ctx: dict = None, action, asset_type, symbol="", name="", quantity=0, price=0, **_) -> ToolResult:
        try:
            uid = (_ctx or {}).get("user_id")
            if not uid:
                return ToolResult(success=False, error="Sign in to use this calculator")
            from services.user_context_service import get_portfolio, analyze_portfolio
            pf = get_portfolio(uid)
            current_holdings = list(pf.get("holdings") or [])
            current_analysis = analyze_portfolio(uid)

            # Build a simulated holdings list (in-memory, not saved)
            sim = list(current_holdings)
            qty = float(quantity or 0); pr = float(price or 0); sym = (symbol or "").upper()

            if action == "add":
                sim.append({
                    "asset_type": asset_type, "symbol": sym, "name": name or sym or "(simulated)",
                    "quantity": qty, "avg_buy_price": pr,
                    "buy_date": date.today().isoformat(),
                })
            elif action == "remove":
                # Remove first matching by symbol
                removed_idx = None
                for i, h in enumerate(sim):
                    if h.get("symbol") == sym:
                        removed_idx = i
                        break
                if removed_idx is None:
                    return ToolResult(success=False, error=f"No holding with symbol '{sym}' to remove")
                sim.pop(removed_idx)
            else:
                return ToolResult(success=False, error="action must be 'add' or 'remove'")

            # Replicate the same analysis logic statically
            by_class = {}
            invested_rows = []
            for h in sim:
                inv = h["quantity"] * h["avg_buy_price"]
                invested_rows.append({**h, "invested": inv})
                by_class[h["asset_type"]] = by_class.get(h["asset_type"], 0) + inv
            total = sum(by_class.values())
            sim_breakdown = sorted(
                [{"asset_type": k, "invested": round(v, 2), "pct": round(v / total * 100, 1) if total else 0} for k, v in by_class.items()],
                key=lambda x: x["invested"], reverse=True,
            )
            sim_top = sorted(invested_rows, key=lambda x: x["invested"], reverse=True)[:5]
            sim_top = [{
                "name": h["name"], "symbol": h.get("symbol", ""), "asset_type": h["asset_type"],
                "invested": round(h["invested"], 2),
                "pct_of_portfolio": round(h["invested"] / total * 100, 1) if total else 0,
            } for h in sim_top]
            sim_flags = []
            for h in sim_top:
                if h["pct_of_portfolio"] > 25:
                    sim_flags.append(f"{h['name']} would be {h['pct_of_portfolio']}% — above 25% threshold")

            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "simulate_portfolio_change",
                "inputs": {"action": action, "asset_type": asset_type, "symbol": sym, "name": name, "quantity": qty, "price": pr},
                "before": {
                    "summary": current_analysis.get("summary"),
                    "asset_class_breakdown": current_analysis.get("asset_class_breakdown"),
                    "top_holdings": current_analysis.get("top_holdings"),
                    "concentration_flags": current_analysis.get("concentration_flags"),
                },
                "after_simulation": {
                    "holding_count": len(sim),
                    "total_invested": round(total, 2),
                    "asset_class_breakdown": sim_breakdown,
                    "top_holdings": sim_top,
                    "concentration_flags": sim_flags or ["No new concentration issues detected."],
                },
                "note": "This is a what-if — the saved portfolio has NOT been modified.",
            }, display_hint="portfolio_simulation")
        except Exception as e:
            return ToolResult(success=False, error=f"Simulation failed: {e}")


class TrackGoalProgressTool(Tool):
    name = "track_goal_progress"
    description = (
        "For each saved goal: project the corpus the user will actually have at target_year "
        "given current_progress and monthly_sip + expected_return. Compare to target_amount "
        "and flag goals that are off-track."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        try:
            uid = (_ctx or {}).get("user_id")
            if not uid:
                return ToolResult(success=False, error="Sign in to use this calculator")
            from services.user_context_service import get_goals
            goals = get_goals(uid)
            if not goals:
                return ToolResult(success=False, error="No saved goals — add some via Account → Money Profile")
            today = date.today()
            results = []
            for g in goals:
                target_year = int(g.get("target_year") or today.year)
                yrs = max(0.1, target_year - today.year + (1 - today.month / 12))
                progress = float(g.get("current_progress") or 0)
                sip = float(g.get("monthly_sip") or 0)
                r = float(g.get("expected_return_pct") or 12) / 100
                r_m = r / 12
                n = yrs * 12
                # FV of progress + SIP
                fv_progress = progress * ((1 + r) ** yrs)
                fv_sip = sip * (((1 + r_m) ** n - 1) / r_m) * (1 + r_m) if r_m > 0 else sip * n
                projected_corpus = fv_progress + fv_sip
                target = float(g.get("target_amount") or 0)
                gap = target - projected_corpus
                pct_to_target = projected_corpus / target * 100 if target else 0
                shortfall_sip = 0
                if gap > 0 and yrs > 0:
                    extra_factor = (((1 + r_m) ** n - 1) / r_m) * (1 + r_m) if r_m > 0 else n
                    shortfall_sip = gap / extra_factor if extra_factor else 0
                results.append({
                    "goal_id": g.get("id"),
                    "name": g.get("name"),
                    "type": g.get("type"),
                    "target_amount": round(target, 2),
                    "target_year": target_year,
                    "years_remaining": round(yrs, 2),
                    "current_progress": round(progress, 2),
                    "current_monthly_sip": round(sip, 2),
                    "expected_return_pct": float(g.get("expected_return_pct") or 12),
                    "projected_corpus_at_target_year": round(projected_corpus, 2),
                    "shortfall_amount": round(max(0, gap), 2),
                    "surplus_amount": round(max(0, -gap), 2),
                    "pct_to_target": round(pct_to_target, 1),
                    "on_track": projected_corpus >= target,
                    "additional_monthly_sip_to_close_shortfall": round(shortfall_sip, 2),
                })
            on_track = [g for g in results if g["on_track"]]
            off_track = [g for g in results if not g["on_track"]]
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "track_goal_progress",
                "result": {
                    "goal_count": len(results),
                    "on_track_count": len(on_track),
                    "off_track_count": len(off_track),
                    "goals": results,
                },
                "note": "Projections use the expected_return saved on each goal. Reality varies — review annually and step up SIPs if returns disappoint.",
            }, display_hint="goal_tracker")
        except Exception as e:
            return ToolResult(success=False, error=f"Goal tracking failed: {e}")
