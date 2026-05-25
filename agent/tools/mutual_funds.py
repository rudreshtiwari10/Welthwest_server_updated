"""Tools: get_mf_data, compare_mf, screen_mf — Indian mutual-fund lookup via AMFI."""

from agent.tools.base import Tool, ToolResult


def _format_scheme(s: dict) -> dict:
    return {
        "code": s.get("code"),
        "name": s.get("name"),
        "amc": s.get("amc") or "",
        "category": s.get("category") or "",
        "nav": s.get("nav"),
        "nav_date": s.get("nav_date") or "",
        "isin_growth": s.get("isin_growth"),
        "isin_div": s.get("isin_div"),
    }


class GetMfDataTool(Tool):
    name = "get_mf_data"
    description = (
        "Look up an Indian mutual-fund scheme by name (fuzzy) or AMFI scheme code. "
        "Returns current NAV, NAV date, AMC, scheme category, and ISINs. Use whenever "
        "the user mentions a specific MF scheme — e.g., 'NAV of Parag Parikh Flexi Cap', "
        "'how much is HDFC Top 100 today', 'show me the Mirae Asset Large Cap fund'. "
        "If the query is ambiguous, the tool returns the top matches and you should ask "
        "the user to pick."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Scheme name (or partial name) — e.g., 'Parag Parikh Flexi Cap', 'HDFC Top 100 Direct Growth'.",
            },
            "scheme_code": {
                "type": "integer",
                "description": "AMFI scheme code (5–6 digit integer). If both provided, scheme_code wins.",
            },
        },
    }

    def execute(self, *, query: str = None, scheme_code: int = None, **_) -> ToolResult:
        try:
            from services.amfi_service import lookup_by_code, search_by_name
            if scheme_code:
                s = lookup_by_code(int(scheme_code))
                if not s:
                    return ToolResult(success=False, error=f"No AMFI scheme found with code {scheme_code}")
                return ToolResult(success=True, data={"scheme": _format_scheme(s)}, display_hint="mf_card")

            if not query or not query.strip():
                return ToolResult(success=False, error="Provide a scheme name or scheme_code")

            matches = search_by_name(query, limit=8)
            if not matches:
                return ToolResult(success=False, error=f"No AMFI scheme found matching '{query}'")
            if len(matches) == 1:
                return ToolResult(success=True, data={"scheme": _format_scheme(matches[0])}, display_hint="mf_card")
            return ToolResult(
                success=True,
                data={
                    "ambiguous": True,
                    "query": query,
                    "matches": [_format_scheme(s) for s in matches],
                    "note": "Multiple schemes matched. Ask the user which one they meant — direct vs regular, growth vs IDCW, etc.",
                },
                display_hint="mf_picker",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"MF lookup failed: {e}")


class CompareMfTool(Tool):
    name = "compare_mf"
    description = (
        "Compare 2 to 5 mutual-fund schemes side-by-side using AMFI data: current NAV, "
        "NAV date, AMC, category. Use when the user asks 'compare HDFC Top 100 vs SBI "
        "Bluechip', 'NAV of these three funds', etc. Note: this returns NAV-level data "
        "only — historical returns / AUM / expense ratio require a paid feed (coming later)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of 2–5 scheme names (fuzzy match each).",
            },
        },
        "required": ["queries"],
    }

    def execute(self, *, queries, **_) -> ToolResult:
        try:
            from services.amfi_service import search_by_name
            if not isinstance(queries, (list, tuple)) or not queries:
                return ToolResult(success=False, error="queries must be a list of 2–5 scheme names")
            queries = [str(q).strip() for q in queries if str(q).strip()]
            if len(queries) < 2:
                return ToolResult(success=False, error="provide at least 2 schemes to compare")
            queries = queries[:5]

            results = []
            ambiguous = []
            for q in queries:
                matches = search_by_name(q, limit=3)
                if not matches:
                    results.append({"query": q, "found": False})
                elif len(matches) > 1:
                    # Best-effort: use the first match but flag ambiguity
                    ambiguous.append({"query": q, "candidates": [_format_scheme(m) for m in matches]})
                    results.append({"query": q, "found": True, "best_match_uncertain": True, **_format_scheme(matches[0])})
                else:
                    results.append({"query": q, "found": True, **_format_scheme(matches[0])})

            return ToolResult(
                success=True,
                data={
                    "comparison": results,
                    "ambiguous_queries": ambiguous,
                    "note": (
                        "AMFI provides NAV + scheme metadata only. For historical returns, "
                        "expense ratio, AUM, holdings — those require a paid feed (Value "
                        "Research, Morningstar). When asked about returns/expenses, say so."
                    ),
                },
                display_hint="mf_comparison",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"MF comparison failed: {e}")


class ScreenMfTool(Tool):
    name = "screen_mf"
    description = (
        "Screen Indian mutual-fund schemes by category (e.g., 'Multi Cap', 'Mid Cap', "
        "'Equity-Linked Savings Scheme'), AMC name, and/or scheme-name keyword. Returns "
        "matching schemes with NAV. Use when the user asks 'show me ELSS funds', 'list "
        "Parag Parikh's schemes', 'small cap mutual funds'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "category_contains": {
                "type": "string",
                "description": "Substring match on scheme category (e.g., 'Multi Cap', 'ELSS', 'Equity-Linked', 'Liquid', 'Mid Cap').",
            },
            "amc_contains": {
                "type": "string",
                "description": "Substring match on AMC name (e.g., 'HDFC', 'Parag Parikh', 'SBI').",
            },
            "name_contains": {
                "type": "string",
                "description": "Substring match on scheme name (e.g., 'Direct', 'Growth', 'Bluechip').",
            },
            "limit": {
                "type": "integer",
                "description": "Max schemes to return (1 to 50). Default 15.",
            },
        },
    }

    def execute(self, *, category_contains: str = None, amc_contains: str = None, name_contains: str = None, limit: int = 15, **_) -> ToolResult:
        try:
            from services.amfi_service import filter_schemes
            limit = max(1, min(int(limit or 15), 50))
            schemes = filter_schemes(
                category_contains=category_contains,
                amc_contains=amc_contains,
                name_contains=name_contains,
                limit=limit,
            )
            return ToolResult(
                success=True,
                data={
                    "filters": {
                        "category_contains": category_contains or "",
                        "amc_contains": amc_contains or "",
                        "name_contains": name_contains or "",
                    },
                    "count": len(schemes),
                    "schemes": [_format_scheme(s) for s in schemes],
                },
                display_hint="mf_list",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"MF screening failed: {e}")
