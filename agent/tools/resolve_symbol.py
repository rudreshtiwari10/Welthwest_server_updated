"""Tool: resolve_symbol — disambiguate a company name to NSE ticker(s)."""

from agent.tools.base import Tool, ToolResult


class ResolveSymbolTool(Tool):
    name = "resolve_symbol"
    description = (
        "Resolve a company name, alias, or partial ticker to one or more NSE "
        "ticker symbols with confidence scores. Use this when the user mentions "
        "a company by name (e.g., 'Infosys', 'HDFC') and you need the exact "
        "ticker. If multiple candidates are returned, ask the user to clarify."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Company name, alias, or partial ticker to resolve",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of candidates to return (default 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def execute(self, *, query: str, limit: int = 5, **_) -> ToolResult:
        try:
            from services.market_data.resolver import resolve_symbol, is_ambiguous

            matches = resolve_symbol(query, limit=limit)
            if not matches:
                return ToolResult(
                    success=True,
                    data={"query": query, "matches": [], "ambiguous": False},
                )

            ambiguous = is_ambiguous(query)
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "ambiguous": ambiguous,
                    "matches": [
                        {
                            "symbol": m.symbol,
                            "name": m.name,
                            "exchange": m.exchange,
                            "confidence": round(m.confidence, 3),
                        }
                        for m in matches
                    ],
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Symbol resolution failed for '{query}'")
