"""Tool: get_stock_quote — fetch live/near-live price for a stock."""

from dataclasses import asdict

from agent.tools.base import Tool, ToolResult


class GetStockQuoteTool(Tool):
    name = "get_stock_quote"
    description = (
        "Get the current price, change, volume, and day range for an Indian "
        "stock. Returns INR-denominated data from NSE/BSE."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE ticker symbol (e.g., RELIANCE, TCS, INFY)",
            },
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol: str, **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            provider = get_default_provider()
            quote = provider.get_quote(symbol)
            return ToolResult(
                success=True,
                data={
                    "symbol": quote.symbol,
                    "price": quote.price,
                    "currency": quote.currency,
                    "change": quote.change,
                    "change_percent": quote.change_percent,
                    "volume": quote.volume,
                    "day_high": quote.day_high,
                    "day_low": quote.day_low,
                    "open": quote.open,
                    "previous_close": quote.previous_close,
                    "exchange": quote.exchange,
                },
                display_hint="card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch quote for {symbol}")
