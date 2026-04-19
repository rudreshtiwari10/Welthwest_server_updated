"""Tool: get_fundamentals — fetch fundamental metrics for a stock."""

from agent.tools.base import Tool, ToolResult


class GetFundamentalsTool(Tool):
    name = "get_fundamentals"
    description = (
        "Get fundamental metrics for an Indian stock: market cap, P/E ratio, "
        "P/B ratio, EPS, dividend yield, ROE, debt-to-equity, book value, "
        "sector, and industry."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE ticker symbol (e.g., RELIANCE)",
            },
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol: str, **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            provider = get_default_provider()
            f = provider.get_fundamentals(symbol)
            return ToolResult(
                success=True,
                data={
                    "symbol": f.symbol,
                    "market_cap": f.market_cap,
                    "pe_ratio": f.pe_ratio,
                    "pb_ratio": f.pb_ratio,
                    "eps": f.eps,
                    "dividend_yield": f.dividend_yield,
                    "roe": f.roe,
                    "roce": f.roce,
                    "debt_to_equity": f.debt_to_equity,
                    "book_value": f.book_value,
                    "sector": f.sector,
                    "industry": f.industry,
                },
                display_hint="table",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch fundamentals for {symbol}")
