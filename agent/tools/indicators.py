"""Tool: compute_indicator — compute a technical indicator for a stock."""

from agent.tools.base import Tool, ToolResult


class ComputeIndicatorTool(Tool):
    name = "compute_indicator"
    description = (
        "Compute a technical indicator (RSI, MACD, SMA, EMA, Bollinger Bands, "
        "ATR, Stochastic, Williams %R, OBV, VWAP, CCI, WMA) for a stock. "
        "Returns the latest value with a neutral, factual description — no "
        "directional interpretation or buy/sell signals."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE ticker symbol (e.g., RELIANCE)",
            },
            "indicator": {
                "type": "string",
                "description": "Indicator name: rsi, macd, sma, ema, wma, bollinger, atr, stochastic, williams_r, obv, vwap, cci",
            },
            "period": {
                "type": "integer",
                "description": "Lookback period (default depends on indicator, e.g., 14 for RSI)",
            },
        },
        "required": ["symbol", "indicator"],
    }

    def execute(self, *, symbol: str, indicator: str, period: int = None, **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            from services.market_data.indicators import compute_indicator, list_indicators

            indicator = indicator.lower().strip()
            if indicator not in list_indicators():
                return ToolResult(
                    success=False,
                    error=f"Unknown indicator '{indicator}'. Available: {list_indicators()}",
                )

            # Fetch enough history for the indicator to stabilize
            provider = get_default_provider()
            candles = provider.get_history(symbol, period="1y", interval="1d")
            if not candles or len(candles) < 30:
                return ToolResult(success=False, error=f"Not enough history for {symbol}")

            kwargs = {}
            if period is not None:
                kwargs["period"] = period

            result = compute_indicator(candles, indicator, symbol=symbol, **kwargs)
            return ToolResult(
                success=True,
                data={
                    "symbol": symbol,
                    "indicator": result.name,
                    "value": result.value,
                    "context": result.context,
                    "percentile_52w": result.percentile_52w,
                    "params": result.params,
                },
                display_hint="card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not compute {indicator} for {symbol}")
