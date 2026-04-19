"""Tool: get_price_history — fetch OHLCV candle data for charting/analysis."""

from agent.tools.base import Tool, ToolResult


class GetPriceHistoryTool(Tool):
    name = "get_price_history"
    description = (
        "Get historical OHLCV (Open/High/Low/Close/Volume) candle data for a "
        "stock. Useful for charting, trend analysis, and computing indicators."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE ticker symbol (e.g., RELIANCE)",
            },
            "period": {
                "type": "string",
                "description": "Time period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max",
                "default": "3mo",
            },
            "interval": {
                "type": "string",
                "description": "Candle interval: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo",
                "default": "1d",
            },
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol: str, period: str = "3mo", interval: str = "1d", **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            provider = get_default_provider()
            candles = provider.get_history(symbol, period=period, interval=interval)
            if not candles:
                return ToolResult(success=False, error=f"No history data for {symbol}")

            # Return summary + last 10 candles (full data too large for LLM context)
            summary = {
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "total_candles": len(candles),
                "date_range": {
                    "from": str(candles[0].timestamp.date()) if candles else None,
                    "to": str(candles[-1].timestamp.date()) if candles else None,
                },
                "latest_close": candles[-1].close if candles else None,
                "period_high": max(c.high for c in candles),
                "period_low": min(c.low for c in candles),
                "recent_candles": [
                    {
                        "date": str(c.timestamp.date()),
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in candles[-5:]
                ],
            }
            return ToolResult(success=True, data=summary, display_hint="chart")
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch history for {symbol}")
