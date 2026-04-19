"""Tool: get_index_quote — fetch data for market indices (NIFTY, SENSEX, etc.)."""

from agent.tools.base import Tool, ToolResult


class GetIndexQuoteTool(Tool):
    name = "get_index_quote"
    description = (
        "Get the current value, change, and change percentage for an Indian "
        "market index. Supports NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "index": {
                "type": "string",
                "description": "Index name: NIFTY, SENSEX, BANKNIFTY, NIFTY IT, etc.",
            },
        },
        "required": ["index"],
    }

    def execute(self, *, index: str, **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            provider = get_default_provider()
            quote = provider.get_index_quote(index)
            return ToolResult(
                success=True,
                data={
                    "index": quote.symbol,
                    "value": quote.price,
                    "change": quote.change,
                    "change_percent": quote.change_percent,
                    "exchange": quote.exchange,
                },
                display_hint="card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch index data for '{index}'")
