"""Derivatives + macro extras: options strategy suggester, futures margin, purchasing power."""

from agent.tools.base import Tool, ToolResult


class SuggestOptionsStrategyTool(Tool):
    name = "suggest_options_strategy"
    description = (
        "Suggest one or two appropriate options strategies for a directional/volatility "
        "view + risk preference. Returns the strategy name, leg structure, risk profile, "
        "and when it works best. Use as a starting point — always run compute_options_payoff "
        "afterwards to see actual P&L."
    )
    parameters = {
        "type": "object",
        "properties": {
            "view": {"type": "string", "enum": ["bullish", "bearish", "neutral", "volatile", "low_volatility"], "description": "Market view."},
            "risk": {"type": "string", "enum": ["limited", "unlimited"], "description": "Limited (defined max loss) or unlimited (naked short). Default 'limited'."},
            "magnitude": {"type": "string", "enum": ["mild", "strong"], "description": "How big a move expected. Default 'mild'."},
        },
        "required": ["view"],
    }

    _STRATEGIES = {
        ("bullish", "limited", "mild"): [
            {"name": "Bull Call Spread", "legs": "Buy ATM call + Sell OTM call", "max_profit": "Strike difference − net debit", "max_loss": "Net debit", "best_when": "Mild upside; want to cap cost via short call premium"},
            {"name": "Bull Put Spread (credit)", "legs": "Sell ATM put + Buy OTM put", "max_profit": "Net credit", "max_loss": "Strike difference − net credit", "best_when": "Sideways-to-up; collect premium with defined risk"},
        ],
        ("bullish", "limited", "strong"): [
            {"name": "Long Call", "legs": "Buy ATM or slightly OTM call", "max_profit": "Unlimited", "max_loss": "Premium paid", "best_when": "Strong upside expected; willing to pay full premium"},
            {"name": "Long Call Calendar", "legs": "Sell near-month call + Buy far-month call (same strike)", "max_profit": "Variable (vol-dependent)", "max_loss": "Net debit", "best_when": "Slow grinding move up; benefits from rising IV in later month"},
        ],
        ("bullish", "unlimited", "strong"): [
            {"name": "Long Future / Long Call", "legs": "Buy futures or buy deep ITM call", "max_profit": "Unlimited", "max_loss": "Underlying × notional (futures) / premium (call)", "best_when": "Conviction trade with margin available"},
        ],
        ("bearish", "limited", "mild"): [
            {"name": "Bear Put Spread", "legs": "Buy ATM put + Sell OTM put", "max_profit": "Strike difference − net debit", "max_loss": "Net debit", "best_when": "Mild downside; cap cost via short put premium"},
            {"name": "Bear Call Spread (credit)", "legs": "Sell ATM call + Buy OTM call", "max_profit": "Net credit", "max_loss": "Strike difference − net credit", "best_when": "Sideways-to-down; collect premium"},
        ],
        ("bearish", "limited", "strong"): [
            {"name": "Long Put", "legs": "Buy ATM or slightly OTM put", "max_profit": "Up to strike − premium", "max_loss": "Premium paid", "best_when": "Strong downside expected"},
        ],
        ("neutral", "limited", "mild"): [
            {"name": "Iron Condor", "legs": "Sell OTM call spread + Sell OTM put spread", "max_profit": "Net credit", "max_loss": "Wing width − net credit", "best_when": "Range-bound market; collecting premium with defined risk"},
            {"name": "Iron Butterfly", "legs": "Sell ATM straddle + Buy OTM strangle", "max_profit": "Net credit", "max_loss": "Wing distance − net credit", "best_when": "Pin-the-strike thesis at expiry"},
        ],
        ("neutral", "unlimited", "mild"): [
            {"name": "Short Strangle", "legs": "Sell OTM call + Sell OTM put", "max_profit": "Total premium received", "max_loss": "Unlimited (theoretically)", "best_when": "High IV, expecting range-bound; needs margin and discipline"},
        ],
        ("volatile", "limited", "strong"): [
            {"name": "Long Straddle", "legs": "Buy ATM call + Buy ATM put", "max_profit": "Unlimited (either side)", "max_loss": "Total premium paid", "best_when": "Big move expected, direction uncertain (e.g., before results)"},
            {"name": "Long Strangle", "legs": "Buy OTM call + Buy OTM put", "max_profit": "Unlimited", "max_loss": "Total premium paid", "best_when": "Cheaper than straddle; needs bigger move to break even"},
        ],
        ("low_volatility", "limited", "mild"): [
            {"name": "Iron Condor", "legs": "Same as neutral", "max_profit": "Net credit", "max_loss": "Wing − credit", "best_when": "IV expected to stay low; theta works for you"},
            {"name": "Calendar Spread", "legs": "Sell near-month + Buy far-month (same strike)", "max_profit": "Variable", "max_loss": "Net debit", "best_when": "Expect IV term-structure to widen / rise"},
        ],
    }

    def execute(self, *, view, risk="limited", magnitude="mild", **_) -> ToolResult:
        try:
            view = (view or "").strip().lower()
            risk = (risk or "limited").strip().lower()
            magnitude = (magnitude or "mild").strip().lower()
            key = (view, risk, magnitude)

            # Try exact match, then loosen
            options = self._STRATEGIES.get(key)
            if not options:
                # Try magnitude flip
                for k in self._STRATEGIES:
                    if k[0] == view and k[1] == risk:
                        options = self._STRATEGIES[k]
                        break
            if not options:
                # Try with limited risk
                for k in self._STRATEGIES:
                    if k[0] == view and k[1] == "limited":
                        options = self._STRATEGIES[k]
                        break

            if not options:
                return ToolResult(success=False, error=f"No matching strategy for view={view}, risk={risk}, magnitude={magnitude}")

            return ToolResult(success=True, data={
                "kind": "strategy_suggestion",
                "inputs": {"view": view, "risk": risk, "magnitude": magnitude},
                "suggested_strategies": options,
                "note": (
                    "These are templates. Always run compute_options_payoff with concrete strikes / "
                    "premiums / quantities + compute_options_greeks for theta and vega exposure "
                    "before deploying. NIFTY / BANKNIFTY weekly options are most liquid."
                ),
            }, display_hint="strategy_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Strategy suggester failed: {e}")


class ComputeFuturesMarginTool(Tool):
    name = "compute_futures_margin"
    description = (
        "Estimate the initial margin required to buy / sell an Indian futures contract. "
        "Uses a SPAN + Exposure approximation — typically 10–18% of contract value for "
        "index futures, 15–25% for stock futures. Real margin from your broker may differ "
        "by ±2-3pp due to volatility-state adjustments."
    )
    parameters = {
        "type": "object",
        "properties": {
            "contract_value": {"type": "number", "description": "Lot size × current price (rupees)."},
            "underlying_type": {"type": "string", "enum": ["index", "stock", "commodity"], "description": "Default 'index'."},
        },
        "required": ["contract_value"],
    }

    def execute(self, *, contract_value, underlying_type="index", **_) -> ToolResult:
        try:
            cv = float(contract_value)
            t = (underlying_type or "index").strip().lower()
            ranges = {"index": (0.10, 0.13), "stock": (0.18, 0.22), "commodity": (0.07, 0.10)}
            lo, hi = ranges.get(t, (0.10, 0.18))
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "futures_margin",
                "inputs": {"contract_value": cv, "underlying_type": t},
                "result": {
                    "margin_pct_low": round(lo * 100, 1),
                    "margin_pct_high": round(hi * 100, 1),
                    "margin_required_low": round(cv * lo, 2),
                    "margin_required_high": round(cv * hi, 2),
                    "notional_value": round(cv, 2),
                },
                "note": (
                    "SPAN margin is volatility-driven and changes intraday. NSE publishes the SPAN "
                    "calculator for exact numbers. Brokers may charge additional 'exposure margin' "
                    "and intraday cushioning. Always verify with your broker before placing the order."
                ),
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Futures margin failed: {e}")


class ComputePurchasingPowerTool(Tool):
    name = "compute_purchasing_power"
    description = (
        "Compute how an amount's purchasing power changes between two years using inflation. "
        "Use for '₹1 crore in 1995 = how much today', '₹50,000/month today = what in 2050'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "from_year": {"type": "integer"},
            "to_year": {"type": "integer"},
            "average_inflation_pct": {"type": "number", "description": "Default 6 (Indian CPI long-term)."},
        },
        "required": ["amount", "from_year", "to_year"],
    }

    def execute(self, *, amount, from_year, to_year, average_inflation_pct=6, **_) -> ToolResult:
        try:
            A = float(amount); fy = int(from_year); ty = int(to_year)
            infl = float(average_inflation_pct) / 100
            yrs = ty - fy
            equivalent = A * ((1 + infl) ** yrs) if yrs >= 0 else A / ((1 + infl) ** abs(yrs))
            direction = "future_terms" if yrs >= 0 else "past_terms"
            return ToolResult(success=True, data={
                "kind": "calculator", "calculator": "purchasing_power",
                "inputs": {"amount": A, "from_year": fy, "to_year": ty, "average_inflation_pct": average_inflation_pct},
                "result": {
                    "input_amount": round(A, 2),
                    "input_year": fy,
                    "equivalent_amount": round(equivalent, 2),
                    "equivalent_year": ty,
                    "years_apart": abs(yrs),
                    "direction": direction,
                    "interpretation": (
                        f"₹{A:,.0f} in {fy} has the same purchasing power as ~₹{equivalent:,.0f} in {ty} "
                        f"(assuming average inflation of {average_inflation_pct}%/year)."
                    ),
                },
                "note": "India's long-run CPI averaged 5-7%. Use 5% for a soft estimate, 7% for conservative planning.",
            }, display_hint="calculator_card")
        except Exception as e:
            return ToolResult(success=False, error=f"Purchasing power failed: {e}")
