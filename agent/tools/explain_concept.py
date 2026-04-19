"""Tool: explain_concept — explain a finance/trading concept in Welth's voice."""

from agent.tools.base import Tool, ToolResult

# Curated WelthWest-authored explanations for common concepts.
# Grounds answers in our voice instead of raw LLM-generated text.
# Expand this dict over time — initial seed of ~30 concepts.
_CONCEPTS = {
    "rsi": {
        "term": "RSI (Relative Strength Index)",
        "explanation": (
            "RSI is a momentum oscillator that measures the speed and magnitude "
            "of recent price changes on a scale of 0 to 100. It's calculated "
            "using the average gain and loss over a lookback period (typically "
            "14 days). RSI helps traders understand whether a stock's recent "
            "price movement has been unusually strong in either direction."
        ),
        "key_levels": "Below 30 and above 70 are commonly watched thresholds.",
    },
    "macd": {
        "term": "MACD (Moving Average Convergence Divergence)",
        "explanation": (
            "MACD is a trend-following momentum indicator that shows the "
            "relationship between two exponential moving averages (typically "
            "12-period and 26-period). The MACD line is the difference between "
            "these two EMAs, and a 9-period EMA of the MACD line (the signal "
            "line) is plotted alongside it. The histogram shows the distance "
            "between the MACD line and signal line."
        ),
    },
    "sma": {
        "term": "SMA (Simple Moving Average)",
        "explanation": (
            "SMA is the arithmetic mean of a stock's closing prices over a "
            "specified number of periods. A 50-day SMA, for example, is the "
            "average closing price over the last 50 trading days. SMAs smooth "
            "out price data to help identify the direction and strength of a trend."
        ),
    },
    "ema": {
        "term": "EMA (Exponential Moving Average)",
        "explanation": (
            "EMA is similar to SMA but gives more weight to recent prices, "
            "making it more responsive to new information. The weighting factor "
            "decreases exponentially with each older data point. Traders often "
            "use EMAs when they want an average that reacts faster to price changes."
        ),
    },
    "bollinger bands": {
        "term": "Bollinger Bands",
        "explanation": (
            "Bollinger Bands consist of a middle band (typically a 20-day SMA) "
            "and two outer bands set at 2 standard deviations above and below. "
            "When bands widen, volatility is increasing; when they narrow "
            "(a 'squeeze'), volatility is decreasing. The bands contain "
            "approximately 95% of price action under normal conditions."
        ),
    },
    "pe ratio": {
        "term": "P/E Ratio (Price-to-Earnings)",
        "explanation": (
            "The P/E ratio measures how much investors are paying per rupee of "
            "earnings. It's calculated as the stock price divided by earnings per "
            "share (EPS). A trailing P/E uses past 12-month earnings; a forward "
            "P/E uses estimated future earnings. P/E is commonly used to compare "
            "stocks within the same industry."
        ),
    },
    "market cap": {
        "term": "Market Capitalisation",
        "explanation": (
            "Market cap is the total market value of a company's outstanding "
            "shares, calculated as share price × total shares. In India, "
            "companies are classified as large-cap (top 100 by market cap), "
            "mid-cap (101-250), and small-cap (251+). SEBI uses these "
            "classifications for mutual fund categorisation."
        ),
    },
    "nifty": {
        "term": "NIFTY 50",
        "explanation": (
            "NIFTY 50 is the benchmark index of the National Stock Exchange "
            "(NSE), comprising 50 of the largest and most liquid Indian "
            "companies across 13 sectors. It's maintained by NSE Indices "
            "(formerly IISL) and is the most-tracked index for Indian equities. "
            "NIFTY uses free-float market capitalisation weighting."
        ),
    },
    "sensex": {
        "term": "BSE SENSEX",
        "explanation": (
            "SENSEX is the benchmark index of the Bombay Stock Exchange (BSE), "
            "comprising 30 financially sound and well-established companies. "
            "It's India's oldest stock market index, established in 1986 with a "
            "base year of 1978-79. Like NIFTY, it uses free-float market "
            "capitalisation weighting."
        ),
    },
    "sip": {
        "term": "SIP (Systematic Investment Plan)",
        "explanation": (
            "SIP is a method of investing a fixed amount regularly (usually "
            "monthly) in a mutual fund scheme. It leverages rupee-cost averaging "
            "— buying more units when prices are low and fewer when prices are "
            "high. SIPs are popular in India for long-term wealth building and "
            "are available starting from as low as ₹500 per month."
        ),
    },
    "mutual fund": {
        "term": "Mutual Fund",
        "explanation": (
            "A mutual fund pools money from many investors and invests it in "
            "stocks, bonds, or other securities. In India, mutual funds are "
            "regulated by SEBI and managed by Asset Management Companies (AMCs). "
            "They are categorised into equity, debt, hybrid, and solution-oriented "
            "schemes. NAV (Net Asset Value) represents the per-unit value."
        ),
    },
    "dividend yield": {
        "term": "Dividend Yield",
        "explanation": (
            "Dividend yield is the annual dividend per share divided by the "
            "stock price, expressed as a percentage. It shows how much income "
            "an investor receives relative to the stock price. In India, "
            "dividends are taxable in the hands of the investor at their "
            "applicable income tax slab rate."
        ),
    },
    "roe": {
        "term": "ROE (Return on Equity)",
        "explanation": (
            "ROE measures how efficiently a company uses shareholders' equity "
            "to generate profits. It's calculated as Net Income ÷ Shareholders' "
            "Equity. A consistently high ROE (above 15-20%) generally indicates "
            "efficient capital allocation. ROE is best compared within the same "
            "industry."
        ),
    },
    "atr": {
        "term": "ATR (Average True Range)",
        "explanation": (
            "ATR measures market volatility by calculating the average of true "
            "ranges over a period (typically 14 days). True range is the "
            "greatest of: current high minus low, absolute value of current "
            "high minus previous close, or absolute value of current low minus "
            "previous close. Higher ATR means higher volatility."
        ),
    },
    "vwap": {
        "term": "VWAP (Volume-Weighted Average Price)",
        "explanation": (
            "VWAP is the average price a stock has traded at throughout the "
            "day, weighted by volume. It's calculated as cumulative "
            "(price × volume) divided by cumulative volume. Institutional "
            "traders often use VWAP as a benchmark — buying below VWAP and "
            "selling above it is considered favourable execution."
        ),
    },
    "debt to equity": {
        "term": "Debt-to-Equity Ratio",
        "explanation": (
            "The debt-to-equity ratio compares a company's total debt to its "
            "shareholders' equity. A ratio above 1 means the company has more "
            "debt than equity. What's 'good' varies by industry — capital-"
            "intensive sectors (infrastructure, utilities) typically carry "
            "higher D/E ratios than IT or FMCG companies."
        ),
    },
    "sebi": {
        "term": "SEBI (Securities and Exchange Board of India)",
        "explanation": (
            "SEBI is the regulatory authority for the securities market in "
            "India, established in 1992. It regulates stock exchanges, brokers, "
            "mutual funds, and other market participants. SEBI's mandate is to "
            "protect investor interests, promote market development, and "
            "regulate the securities market."
        ),
    },
    "ipo": {
        "term": "IPO (Initial Public Offering)",
        "explanation": (
            "An IPO is when a private company first offers its shares to the "
            "public on a stock exchange. In India, IPOs are regulated by SEBI "
            "and listed on NSE/BSE. The process involves filing a DRHP (Draft "
            "Red Herring Prospectus), a roadshow, and a bidding period. "
            "Retail investors can apply through ASBA (Application Supported "
            "by Blocked Amount) via their bank."
        ),
    },
    "demat": {
        "term": "Demat Account",
        "explanation": (
            "A Demat (dematerialised) account holds stocks and securities in "
            "electronic form instead of physical certificates. In India, Demat "
            "accounts are maintained by depositories — NSDL and CDSL. You need "
            "a Demat account to buy/sell shares on NSE/BSE. It's linked to "
            "your trading account and bank account."
        ),
    },
    "stochastic": {
        "term": "Stochastic Oscillator",
        "explanation": (
            "The Stochastic Oscillator compares a stock's closing price to its "
            "price range over a period (typically 14 days). %K is the main "
            "line showing where the close sits in the range (0-100), and %D "
            "is a smoothed moving average of %K. It helps identify the "
            "position of the current price relative to recent highs and lows."
        ),
    },
}


class ExplainConceptTool(Tool):
    name = "explain_concept"
    description = (
        "Explain a financial or trading concept using WelthWest's curated "
        "definitions. Use this when a user asks 'what is RSI?', 'explain P/E "
        "ratio', 'what does SEBI do?', etc. Returns a clear, beginner-friendly "
        "explanation grounded in the Indian market context."
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": "The concept to explain (e.g., 'RSI', 'P/E ratio', 'SIP', 'NIFTY')",
            },
        },
        "required": ["concept"],
    }

    def execute(self, *, concept: str, **_) -> ToolResult:
        key = concept.lower().strip()

        # Try exact match first, then partial matches.
        entry = _CONCEPTS.get(key)
        if entry is None:
            for k, v in _CONCEPTS.items():
                if key in k or k in key:
                    entry = v
                    break

        if entry is None:
            # Not in curated set — return empty so LLM generates from its
            # own knowledge (which is fine for education, just not grounded
            # in our voice). The LLM synthesizer will handle this gracefully.
            return ToolResult(
                success=True,
                data={
                    "concept": concept,
                    "curated": False,
                    "explanation": None,
                    "note": "No curated explanation available. You may explain from general knowledge.",
                },
            )

        return ToolResult(
            success=True,
            data={
                "concept": concept,
                "curated": True,
                **entry,
            },
        )
