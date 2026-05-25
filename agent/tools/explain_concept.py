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

    # ---- Tax (Indian FY) -------------------------------------------------

    "old tax regime": {
        "term": "Old Tax Regime",
        "explanation": (
            "The old (legacy) Indian income-tax regime offers numerous deductions "
            "and exemptions — 80C, 80D, HRA, LTA, home-loan interest, etc. — but "
            "with higher slab rates. It generally suits taxpayers with significant "
            "investments, home loans, or rent-paying salaried roles. Switchable each "
            "FY for salaried taxpayers; once-in-a-lifetime for business income."
        ),
    },
    "new tax regime": {
        "term": "New Tax Regime",
        "explanation": (
            "The new Indian income-tax regime offers lower slab rates but disallows "
            "most deductions (80C, 80D, HRA, LTA, etc.). The standard deduction "
            "and employer NPS contribution under 80CCD(2) are still allowed. From "
            "FY 2023-24 it is the default — taxpayers must opt out to use the old "
            "regime. Generally suits those without major deductions to claim."
        ),
    },
    "80c": {
        "term": "Section 80C",
        "explanation": (
            "Section 80C allows a deduction of up to ₹1.5 lakh per FY from taxable "
            "income for specified investments and expenses — EPF, PPF, ELSS mutual "
            "funds, life-insurance premiums, NSC, tax-saving FDs (5y), home-loan "
            "principal, Sukanya Samriddhi, ULIP, NPS Tier-1 (also under 80CCD), and "
            "tuition fees. Available only under the old regime."
        ),
    },
    "80d": {
        "term": "Section 80D",
        "explanation": (
            "Section 80D allows deduction for health-insurance premiums: up to "
            "₹25,000 for self/spouse/children, plus an additional ₹25,000 for "
            "parents (₹50,000 if parents are senior citizens). Preventive health "
            "check-ups up to ₹5,000 are included in the limit. Available only "
            "under the old regime."
        ),
    },
    "80ccd": {
        "term": "Section 80CCD",
        "explanation": (
            "Section 80CCD covers NPS contributions. 80CCD(1) is your own "
            "contribution (within the ₹1.5L 80C limit). 80CCD(1B) is an extra "
            "₹50,000 deduction for self-NPS — over and above 80C. 80CCD(2) "
            "is your employer's NPS contribution (up to 10% of basic+DA, "
            "14% for govt employees) — allowed in BOTH old and new regimes."
        ),
    },
    "ltcg": {
        "term": "LTCG (Long-Term Capital Gains)",
        "explanation": (
            "LTCG is profit from assets held beyond a holding-period threshold: "
            "1 year for listed equity / equity MFs, 2 years for property, 3 years "
            "for debt MFs and gold. Equity LTCG above ₹1 lakh per FY is taxed at "
            "10% without indexation. Debt-MF LTCG (units bought after 1-Apr-2023) "
            "is taxed at slab rates. Property LTCG is 20% with indexation."
        ),
    },
    "stcg": {
        "term": "STCG (Short-Term Capital Gains)",
        "explanation": (
            "STCG is profit from assets sold within the LTCG holding-period "
            "threshold. Equity STCG (held under 1 year, sold via STT-paid trade) "
            "is taxed at a flat 15%. Debt-MF STCG and other STCG is taxed at the "
            "investor's slab rate. STCG cannot be set off against the ₹1 lakh "
            "equity-LTCG exemption."
        ),
    },
    "indexation": {
        "term": "Indexation",
        "explanation": (
            "Indexation adjusts an asset's purchase cost for inflation using the "
            "government's Cost Inflation Index (CII), reducing the taxable LTCG. "
            "Available for property, gold, and pre-Apr-2023 debt MFs. Formula: "
            "Indexed Cost = Original Cost × (CII of sale year / CII of purchase year). "
            "Equity gains do not get indexation."
        ),
    },
    "hra": {
        "term": "HRA (House Rent Allowance) Exemption",
        "explanation": (
            "HRA exemption is the LEAST of: actual HRA received, 50% of "
            "(basic+DA) for metro / 40% for non-metro, or rent paid minus 10% of "
            "(basic+DA). Available only under the old regime, only if you actually "
            "pay rent. Rent above ₹1 lakh/year requires the landlord's PAN."
        ),
    },
    "advance tax": {
        "term": "Advance Tax",
        "explanation": (
            "Advance tax is the 'pay as you earn' system: if your annual tax "
            "liability exceeds ₹10,000, you must pay it in 4 instalments — 15% by "
            "15-Jun, 45% by 15-Sep, 75% by 15-Dec, 100% by 15-Mar. Senior citizens "
            "without business income are exempt. Underpayment attracts interest "
            "under sections 234B and 234C."
        ),
    },
    "tds": {
        "term": "TDS (Tax Deducted at Source)",
        "explanation": (
            "TDS is income tax withheld by the payer (employer, bank, broker) and "
            "deposited with the government on the recipient's behalf. Common rates: "
            "salary as per slab, FD interest 10% above ₹40,000 (₹50,000 for "
            "seniors), MF redemption (NRIs), property sale 1% above ₹50L. The "
            "deductee can claim credit by filing the ITR."
        ),
    },
    "form 16": {
        "term": "Form 16",
        "explanation": (
            "Form 16 is the TDS certificate your employer issues annually (by "
            "15 June for the prior FY). Part A shows tax deducted and deposited; "
            "Part B shows salary breakup, deductions claimed (80C, HRA, etc.), and "
            "tax computed. It's the primary document for filing your ITR if you're "
            "salaried."
        ),
    },

    # ---- Mutual Funds ----------------------------------------------------

    "elss": {
        "term": "ELSS (Equity-Linked Savings Scheme)",
        "explanation": (
            "ELSS is an equity mutual-fund category that qualifies for 80C "
            "deduction (up to ₹1.5L). It has the shortest lock-in among 80C "
            "instruments — 3 years. Returns are market-linked. Only available "
            "under the old tax regime since the new regime disallows 80C."
        ),
    },
    "expense ratio": {
        "term": "Expense Ratio",
        "explanation": (
            "Expense ratio is the annual fee a mutual fund charges for managing "
            "your money, expressed as a percentage of AUM. SEBI caps it by fund "
            "type. Direct plans have lower expense ratios than regular plans "
            "because they exclude distributor commissions. Over 20 years, a 1% "
            "difference can compound into a ~25% gap in final corpus."
        ),
    },
    "direct vs regular": {
        "term": "Direct vs Regular Plan",
        "explanation": (
            "Direct plans are bought straight from the AMC website / direct "
            "platforms (Zerodha Coin, MFCentral, AMC sites) — no distributor "
            "commission, lower expense ratio. Regular plans are sold by "
            "advisors / brokers / banks who earn trail commission baked into a "
            "higher expense ratio. Same scheme, same portfolio — direct just "
            "compounds faster."
        ),
    },
    "exit load": {
        "term": "Exit Load",
        "explanation": (
            "Exit load is a fee a mutual fund charges if you redeem within a "
            "specified window — typically 1% if redeemed within 1 year for equity "
            "funds. It's deducted from the redemption value before paying you "
            "out. Liquid funds usually have no exit load (or a graded micro-load "
            "for under-7-day redemptions)."
        ),
    },
    "swp": {
        "term": "SWP (Systematic Withdrawal Plan)",
        "explanation": (
            "SWP is the reverse of an SIP — you withdraw a fixed amount monthly "
            "from your mutual-fund corpus while the rest stays invested. Common "
            "for retirees creating a monthly-income stream. Tax efficiency depends "
            "on holding period: long-term equity SWPs trigger LTCG (10% above ₹1L "
            "annual gain), short-term hits 15% STCG."
        ),
    },
    "stp": {
        "term": "STP (Systematic Transfer Plan)",
        "explanation": (
            "STP transfers a fixed amount periodically from one MF scheme to "
            "another within the same AMC — typically from a debt/liquid fund "
            "into an equity fund. Used to deploy a lumpsum gradually instead of "
            "investing it all at once. Tax-wise, each STP instalment is treated "
            "as a redemption from the source fund."
        ),
    },
    "amfi": {
        "term": "AMFI (Association of Mutual Funds in India)",
        "explanation": (
            "AMFI is the industry body for Indian asset-management companies. It "
            "publishes the daily NAV file used everywhere, certifies MF "
            "distributors (ARN code), and runs the 'Mutual Funds Sahi Hai' "
            "investor-education campaign. SEBI is the regulator; AMFI is the "
            "self-regulatory trade body."
        ),
    },
    "nfo": {
        "term": "NFO (New Fund Offer)",
        "explanation": (
            "NFO is the launch period of a brand-new mutual-fund scheme — "
            "typically 15 days during which units are sold at ₹10 face value. "
            "Unlike IPOs, the ₹10 NAV doesn't mean it's 'cheap' — there's no "
            "track record. Most experienced investors prefer existing schemes "
            "with at least 3-5 years of vintage."
        ),
    },

    # ---- Loans, Credit, Banking -----------------------------------------

    "emi": {
        "term": "EMI (Equated Monthly Instalment)",
        "explanation": (
            "EMI is the fixed monthly payment that combines principal + interest "
            "on a loan. Formula: EMI = P × R × (1+R)^N / ((1+R)^N - 1), where P "
            "is principal, R is monthly rate (annual ÷ 12 ÷ 100), N is months. "
            "Early EMIs are mostly interest; later EMIs are mostly principal "
            "(reverse-amortisation curve)."
        ),
    },
    "amortization": {
        "term": "Amortization Schedule",
        "explanation": (
            "An amortisation schedule is the month-by-month breakup of an EMI "
            "into principal and interest components. In a typical 20-year home "
            "loan, the first year's EMIs are ~80%+ interest; only in the last "
            "few years does principal dominate. Useful for prepayment timing "
            "and tax-deduction planning under section 24 / 80C."
        ),
    },
    "prepayment": {
        "term": "Prepayment / Foreclosure",
        "explanation": (
            "Prepayment is paying extra principal beyond the EMI; foreclosure is "
            "closing the loan entirely before tenure end. RBI prohibits prepayment "
            "penalties on floating-rate retail loans (since 2012). Fixed-rate "
            "loans may carry 1–3% penalty. Prepayment is more impactful early in "
            "the tenure when interest dominates the EMI."
        ),
    },
    "fixed vs floating rate": {
        "term": "Fixed vs Floating Rate Loan",
        "explanation": (
            "Fixed-rate loans lock the interest rate for the tenure (or a sub-"
            "period); floating-rate loans move with a benchmark — typically the "
            "RBI repo rate (after the Oct-2019 EBLR mandate for retail loans). "
            "Floating-rate loans are usually cheaper at origination but expose "
            "the borrower to rate-cycle risk."
        ),
    },
    "credit score": {
        "term": "Credit Score (CIBIL etc.)",
        "explanation": (
            "Indian credit scores range 300–900. CIBIL (TransUnion), Experian, "
            "Equifax, and CRIF High Mark are the four RBI-approved bureaus. "
            "Above 750 is generally treated as prime for loan approval. Score is "
            "driven by repayment history, credit utilisation (keep <30%), credit "
            "mix, account age, and recent enquiries."
        ),
    },
    "balance transfer": {
        "term": "Balance Transfer (Loan)",
        "explanation": (
            "A loan balance transfer moves your outstanding loan from one lender "
            "to another offering a lower interest rate. Most worthwhile early in "
            "the tenure (when interest dominates) and for a rate gap of at least "
            "0.5–1%. Account for processing fees (typically 0.5–1% of loan) and "
            "valuation/legal costs before deciding."
        ),
    },

    # ---- Insurance -------------------------------------------------------

    "term insurance": {
        "term": "Term Insurance",
        "explanation": (
            "Term insurance is pure life cover — pays the sum assured to "
            "nominees if the insured dies during the policy term, nothing if they "
            "survive. Cheapest form of life insurance because it has no savings/"
            "investment component. Typical cover advice: 10–15× annual income, "
            "term up to age 60–65."
        ),
    },
    "ulip": {
        "term": "ULIP (Unit-Linked Insurance Plan)",
        "explanation": (
            "ULIP combines life insurance with market-linked investment — a "
            "portion of the premium goes to insurance, rest into equity/debt fund "
            "units. 5-year lock-in. Generally has higher costs than 'term + MF' "
            "separated. From Apr-2023, ULIP premiums above ₹2.5L per year lose "
            "tax-free maturity status."
        ),
    },
    "endowment": {
        "term": "Endowment / Money-Back Plan",
        "explanation": (
            "Endowment policies bundle life insurance with guaranteed savings, "
            "paying a lump sum at maturity (or earlier on death). Effective IRR "
            "is typically 4–6%, well below alternatives. Most financial advisors "
            "recommend separating insurance (term plan) from investing (MFs / "
            "PPF / NPS) for better outcomes."
        ),
    },
    "health insurance": {
        "term": "Health Insurance / Mediclaim",
        "explanation": (
            "Health insurance reimburses medical costs — hospitalisation, day-"
            "care procedures, pre/post-hospitalisation. Key features to check: "
            "sum insured, room-rent capping, co-payment, no-claim bonus, "
            "pre-existing-disease waiting period. Premiums up to ₹25,000 (₹50,000 "
            "for senior parents) qualify for 80D deduction in the old regime."
        ),
    },

    # ---- Macro / RBI -----------------------------------------------------

    "repo rate": {
        "term": "Repo Rate",
        "explanation": (
            "The repo rate is the rate at which the RBI lends short-term funds "
            "to commercial banks against govt securities. It is the primary "
            "monetary-policy lever — cuts make borrowing cheaper across the "
            "economy, hikes tighten liquidity. Floating-rate retail loans "
            "(home, auto, MSME) reset against the repo via the EBLR linkage."
        ),
    },
    "reverse repo rate": {
        "term": "Reverse Repo Rate",
        "explanation": (
            "The reverse repo rate is the rate at which RBI borrows from "
            "commercial banks (the inverse of repo). Used to absorb excess "
            "liquidity from the system. Typically set 25–50bps below repo. RBI "
            "also operates the SDF (Standing Deposit Facility) which has "
            "effectively replaced reverse repo as the floor of the liquidity "
            "corridor since Apr 2022."
        ),
    },
    "crr": {
        "term": "CRR (Cash Reserve Ratio)",
        "explanation": (
            "CRR is the percentage of net demand and time liabilities (NDTL) "
            "every commercial bank must keep with the RBI as cash reserves, "
            "earning no interest. Raising CRR drains liquidity from banks; "
            "cutting it releases lendable funds. A blunter tool than the repo "
            "rate, used sparingly."
        ),
    },
    "slr": {
        "term": "SLR (Statutory Liquidity Ratio)",
        "explanation": (
            "SLR is the percentage of NDTL that banks must invest in approved "
            "liquid assets — primarily Indian govt securities. It ensures "
            "solvency and creates a captive demand for sovereign debt. Distinct "
            "from CRR: SLR earns interest on G-secs while CRR is non-earning "
            "cash with the RBI."
        ),
    },
    "mpc": {
        "term": "MPC (Monetary Policy Committee)",
        "explanation": (
            "The MPC is the 6-member RBI committee that sets the repo rate. "
            "Three members are from RBI (governor, deputy governor, executive "
            "director); three are external academics/economists nominated by the "
            "central govt. It meets bi-monthly (6 times a year) and operates "
            "under a 4% (+/- 2%) inflation-targeting mandate."
        ),
    },
    "cpi": {
        "term": "CPI Inflation",
        "explanation": (
            "CPI (Consumer Price Index) measures the change in retail prices "
            "of a representative basket of goods and services. India's headline "
            "CPI is published by NSO (formerly CSO) monthly. RBI's monetary-"
            "policy target is CPI inflation at 4% (with a 2–6% tolerance band). "
            "Food and fuel typically drive the largest swings."
        ),
    },
    "wpi": {
        "term": "WPI Inflation",
        "explanation": (
            "WPI (Wholesale Price Index) tracks bulk-stage prices of manufactured "
            "goods, primary articles, and fuel — released monthly by the Ministry "
            "of Commerce. WPI is more sensitive to commodity / input costs and "
            "tends to be more volatile than CPI. RBI targets CPI, not WPI, but "
            "WPI is a useful early signal for cost-side pressure."
        ),
    },
    "fii dii": {
        "term": "FII / DII",
        "explanation": (
            "FII (Foreign Institutional Investor — now formally FPI, Foreign "
            "Portfolio Investor) and DII (Domestic Institutional Investor — MFs, "
            "insurers, pension funds) are the two big institutional flows on "
            "Indian markets. Their daily buy/sell numbers are published by NSE/"
            "BSE and often move sectoral sentiment, especially around US Fed "
            "decisions and rupee moves."
        ),
    },

    # ---- Personal Finance Concepts --------------------------------------

    "emergency fund": {
        "term": "Emergency Fund",
        "explanation": (
            "An emergency fund is liquid savings set aside for unexpected events "
            "— job loss, medical emergencies, major repairs. Standard guidance: "
            "6 months of essential monthly expenses (more if income is variable "
            "or you have dependents). Park in liquid funds, sweep-in FDs, or "
            "high-yield savings — not in equity."
        ),
    },
    "asset allocation": {
        "term": "Asset Allocation",
        "explanation": (
            "Asset allocation is how you split investments across asset classes "
            "— equity, debt, gold, real estate, cash. It is the single biggest "
            "driver of long-term portfolio returns and risk. A common rule-of-"
            "thumb is '100 minus age' in equity, but real allocation should match "
            "your goals, horizon, and risk tolerance."
        ),
    },
    "rule of 72": {
        "term": "Rule of 72",
        "explanation": (
            "The Rule of 72 estimates how many years it takes for money to "
            "double at a fixed annual return: years ≈ 72 / annual return %. At "
            "8% (typical FD), money doubles in ~9 years. At 12% (long-term "
            "equity assumption), it doubles in 6 years. Useful mental shortcut "
            "for compounding intuition."
        ),
    },
    "compound interest": {
        "term": "Compound Interest",
        "explanation": (
            "Compound interest is interest earned on both the original principal "
            "and on previously accumulated interest. Formula: A = P(1+r/n)^(nt), "
            "where n is compounding frequency. The 'magic' is non-linear: a "
            "₹10k SIP for 20 years at 12% is ~₹1 crore — most of which is gain, "
            "not contribution."
        ),
    },
    "cagr vs irr": {
        "term": "CAGR vs IRR",
        "explanation": (
            "CAGR (Compound Annual Growth Rate) assumes a single lumpsum and a "
            "single end value — it gives a smoothed annual rate. IRR / XIRR "
            "handles irregular cash flows (SIPs, withdrawals, top-ups) and is "
            "the right metric for any portfolio with multiple transaction dates. "
            "All MF dashboards use XIRR for SIP returns."
        ),
    },
    "real return": {
        "term": "Real Return (Inflation-Adjusted)",
        "explanation": (
            "Real return is the nominal return minus inflation — what your money "
            "actually gained in purchasing-power terms. A 7% FD when CPI is 6% "
            "gives a 1% real return; minus tax on the interest, the real return "
            "can turn negative. Always evaluate long-horizon investments on real, "
            "post-tax returns."
        ),
    },
    "fire": {
        "term": "FIRE (Financial Independence, Retire Early)",
        "explanation": (
            "FIRE is a movement that targets early retirement by saving aggressively "
            "and reaching a corpus that can sustain expenses indefinitely. The "
            "common rule is the '25× rule' — corpus = 25 × annual expenses, "
            "supported by a 4% safe-withdrawal-rate assumption. Indian variants "
            "often use 30–35× to account for higher inflation."
        ),
    },

    # ---- Derivatives basics ---------------------------------------------

    "futures": {
        "term": "Futures Contract",
        "explanation": (
            "A futures contract is an obligation to buy or sell a specified "
            "quantity of an underlying (stock, index, commodity) at a fixed price "
            "on a future date. Indian equity futures expire on the last Thursday "
            "of the contract month. Traders post initial margin (~10–20% via SPAN "
            "+ exposure) and are MTM-settled daily."
        ),
    },
    "options": {
        "term": "Options Contract",
        "explanation": (
            "An option is a right (not obligation) to buy (call) or sell (put) "
            "an underlying at a strike price by expiry. Buyers pay a premium and "
            "have limited risk; sellers (writers) collect premium and take "
            "unlimited or large risk. NSE's NIFTY/BANKNIFTY weekly options are "
            "among the world's most-traded contracts by volume."
        ),
    },
    "call put": {
        "term": "Call vs Put Option",
        "explanation": (
            "A CALL gives the right to BUY the underlying at strike. Profitable "
            "when the underlying rises above strike + premium. A PUT gives the "
            "right to SELL the underlying at strike. Profitable when the "
            "underlying falls below strike − premium. Both lose only the premium "
            "paid (for buyers) if the option expires out-of-the-money."
        ),
    },
    "options greeks": {
        "term": "Options Greeks",
        "explanation": (
            "Greeks measure an option's sensitivity to changing factors: "
            "Delta (price), Gamma (rate-of-change of delta), Theta (time decay), "
            "Vega (volatility), Rho (interest rate). Delta of a call is ~0.5 ATM, "
            "rising toward 1 deep-ITM. Theta is always negative for option "
            "buyers — every passing day eats premium."
        ),
    },
    "moneyness": {
        "term": "ITM / ATM / OTM",
        "explanation": (
            "An option is in-the-money (ITM) if exercising would yield a profit "
            "ignoring premium — call ITM when spot > strike; put ITM when spot < "
            "strike. At-the-money (ATM) when spot ≈ strike. Out-of-the-money "
            "(OTM) is the opposite of ITM. ATM/near-ATM options have the highest "
            "liquidity and the steepest theta decay."
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
