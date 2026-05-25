"""Tool: get_financials — quarterly / annual income, balance, or cashflow statement."""

from agent.tools.base import Tool, ToolResult


class GetFinancialsTool(Tool):
    name = "get_financials"
    description = (
        "Fetch a financial statement for an Indian stock — income statement (revenue, "
        "operating profit, net income, EPS), balance sheet (assets, liabilities, equity, "
        "debt, cash), or cash flow (operating, investing, financing CF, capex, free CF). "
        "Returns the last N periods (quarterly or annual) so trends can be compared. "
        "Use this whenever the user asks about a company's revenue, profit, margins, "
        "earnings history, debt levels, cash flow, or any 'how is the business doing' question."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE ticker symbol (e.g., RELIANCE, TCS, HDFCBANK).",
            },
            "statement": {
                "type": "string",
                "enum": ["income", "balance", "cashflow"],
                "description": (
                    "Which statement: 'income' for revenue/profit/EPS, "
                    "'balance' for assets/liabilities/debt/equity, "
                    "'cashflow' for operating/investing/financing cash flow + capex + FCF."
                ),
            },
            "period": {
                "type": "string",
                "enum": ["quarterly", "annual"],
                "description": "Reporting cadence. Default 'quarterly' (most-recent quarters).",
            },
            "num_periods": {
                "type": "integer",
                "description": "How many recent periods to return (1 to 12). Default 4.",
            },
        },
        "required": ["symbol"],
    }

    def execute(
        self,
        *,
        symbol: str,
        statement: str = "income",
        period: str = "quarterly",
        num_periods: int = 4,
        **_,
    ) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            provider = get_default_provider()
            data = provider.get_financials(
                symbol=symbol,
                statement=statement,
                period=period,
                num_periods=num_periods,
            )
            if not data.get("periods"):
                return ToolResult(
                    success=False,
                    error=(
                        f"No {statement} data found for {symbol}. "
                        f"Verify the ticker symbol is correct."
                    ),
                )
            return ToolResult(
                success=True,
                data=data,
                display_hint="financials_table",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not fetch {statement} statement for {symbol}: {e}",
            )
