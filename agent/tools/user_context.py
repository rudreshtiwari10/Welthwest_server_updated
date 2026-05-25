"""Tools that read the user's saved money profile, goals, and portfolio.

These tools require the user to be authenticated. The runner injects user_id
into a `_ctx` kwarg on every tool call; tools here read it from there.
"""

from agent.tools.base import Tool, ToolResult


_NOT_AUTHED = "Not signed in. To use personalised features, sign in to WelthWest first."
_NO_PROFILE = (
    "Saved money profile not found. The user can create one from the Account → "
    "Money Profile section (age, income, dependents, tax-regime preference, risk profile)."
)
_NO_GOALS = (
    "No saved goals yet. The user can add goals (retirement, house, education, "
    "emergency fund, etc.) from the Account → Money Profile section."
)
_NO_HOLDINGS = (
    "No saved portfolio yet. The user can manually enter their holdings "
    "(equity, MFs, FDs, PPF, etc.) from the Account → Money Profile section."
)


def _user_id(ctx: dict) -> str:
    return (ctx or {}).get("user_id") or ""


class GetUserProfileTool(Tool):
    name = "get_user_profile"
    description = (
        "Read the signed-in user's saved money profile — age, annual income, salaried/"
        "non-salaried, city tier, number of dependents, preferred tax regime, risk "
        "profile, marital status. Use this whenever the user asks 'for me', 'in my "
        "case', 'given my income', etc. — so calculators (tax, retirement, EMI "
        "eligibility) can be called with the user's own numbers automatically."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        uid = _user_id(_ctx)
        if not uid:
            return ToolResult(success=False, error=_NOT_AUTHED)
        try:
            from services.user_context_service import get_profile
            profile = get_profile(uid)
            if not profile:
                return ToolResult(success=True, data={"profile": {}, "note": _NO_PROFILE})
            return ToolResult(success=True, data={"profile": profile}, display_hint="profile_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Could not load profile: {e}")


class GetUserGoalsTool(Tool):
    name = "get_user_goals"
    description = (
        "Read the signed-in user's saved financial goals — retirement, house, education, "
        "emergency fund, etc. Each goal has type, target amount, target year, current "
        "progress, monthly SIP, expected return. Use when the user asks about goal "
        "tracking, 'am I on track', or for goal-relative recommendations."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        uid = _user_id(_ctx)
        if not uid:
            return ToolResult(success=False, error=_NOT_AUTHED)
        try:
            from services.user_context_service import get_goals
            goals = get_goals(uid)
            if not goals:
                return ToolResult(success=True, data={"goals": [], "note": _NO_GOALS})
            return ToolResult(success=True, data={"goals": goals, "count": len(goals)}, display_hint="goals_list")
        except Exception as e:
            return ToolResult(success=False, error=f"Could not load goals: {e}")


class GetUserPortfolioTool(Tool):
    name = "get_user_portfolio"
    description = (
        "Read the signed-in user's saved portfolio — manually entered holdings across "
        "equity, mutual funds, FDs, PPF, NPS, gold, bonds, etc. Each holding has "
        "asset_type, symbol, name, quantity, avg buy price, buy date. Use when the "
        "user asks 'show my holdings', 'what's in my portfolio', or before any "
        "personalised analysis."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        uid = _user_id(_ctx)
        if not uid:
            return ToolResult(success=False, error=_NOT_AUTHED)
        try:
            from services.user_context_service import get_portfolio
            pf = get_portfolio(uid)
            holdings = pf.get("holdings") or []
            if not holdings:
                return ToolResult(success=True, data={"holdings": [], "note": _NO_HOLDINGS})
            return ToolResult(
                success=True,
                data={"holdings": holdings, "count": len(holdings), "last_updated": pf.get("last_updated")},
                display_hint="portfolio_table",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not load portfolio: {e}")


class AnalyzeUserPortfolioTool(Tool):
    name = "analyze_user_portfolio"
    description = (
        "Run static analysis on the user's saved portfolio: total invested, asset-class "
        "breakdown (equity / MF / FD / PPF / etc.), top holdings, concentration flags. "
        "Uses the saved buy-price snapshot — does not fetch live prices in this version. "
        "Use whenever the user asks for diversification analysis, concentration check, "
        "asset-allocation review, or 'how is my portfolio doing structurally'."
    )
    parameters = {"type": "object", "properties": {}}

    def execute(self, *, _ctx: dict = None, **_) -> ToolResult:
        uid = _user_id(_ctx)
        if not uid:
            return ToolResult(success=False, error=_NOT_AUTHED)
        try:
            from services.user_context_service import analyze_portfolio
            data = analyze_portfolio(uid)
            return ToolResult(success=True, data=data, display_hint="portfolio_analysis")
        except Exception as e:
            return ToolResult(success=False, error=f"Could not analyse portfolio: {e}")
