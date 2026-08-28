"""
Single source of truth for everything the strategy builder UI can offer.

The frontend renders its entire builder from this payload — indicator params,
candle tolerances, pattern options, operators, sizing models, risk rules,
execution options and cost schedules. Adding an indicator here makes it
appear in the UI with no frontend change.
"""

from __future__ import annotations

from services.backtest_india import candles as candle_lib
from services.backtest_india import execution as exec_lib
from services.backtest_india import features as feat_lib
from services.backtest_india import graph as graph_lib
from services.backtest_india import patterns as pattern_lib
from services.backtest_india import riskrules
from services.backtest_india import sizing as sizing_lib
from services.backtest_india import structure as struct_lib
from services.backtest_india.costs import list_cost_schedules
from services.backtest_india.datafeed import PERIODS_PER_YEAR
from services.backtest_india.presets import list_presets


def indicator_catalogue() -> list:
    return feat_lib.catalogue()


def candle_catalogue() -> list:
    return candle_lib.catalogue()


def structure_catalogue() -> list:
    return struct_lib.catalogue()


def chart_pattern_catalogue() -> list:
    return pattern_lib.catalogue()


def sizing_catalogue() -> list:
    return sizing_lib.catalogue()


def execution_catalogue() -> dict:
    return exec_lib.catalogue()


# A curated starting universe so the symbol picker is useful before the user
# types anything. Not an index membership list, and deliberately not presented
# as one — point-in-time constituents are a separate data problem.
STARTER_UNIVERSE = [
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Financials"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Financials"},
    {"symbol": "INFY", "name": "Infosys", "sector": "IT"},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Financials"},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "ITC", "name": "ITC", "sector": "FMCG"},
    {"symbol": "LT", "name": "Larsen & Toubro", "sector": "Industrials"},
    {"symbol": "AXISBANK", "name": "Axis Bank", "sector": "Financials"},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "sector": "Financials"},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"symbol": "MARUTI", "name": "Maruti Suzuki", "sector": "Auto"},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"symbol": "TATAMOTORS", "name": "Tata Motors", "sector": "Auto"},
    {"symbol": "TATASTEEL", "name": "Tata Steel", "sector": "Metals"},
    {"symbol": "ASIANPAINT", "name": "Asian Paints", "sector": "Materials"},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "sector": "Financials"},
    {"symbol": "WIPRO", "name": "Wipro", "sector": "IT"},
    {"symbol": "HCLTECH", "name": "HCL Technologies", "sector": "IT"},
    {"symbol": "ADANIENT", "name": "Adani Enterprises", "sector": "Conglomerate"},
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement", "sector": "Materials"},
    {"symbol": "NESTLEIND", "name": "Nestle India", "sector": "FMCG"},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation", "sector": "Utilities"},
    {"symbol": "NTPC", "name": "NTPC", "sector": "Utilities"},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corp", "sector": "Energy"},
    {"symbol": "JSWSTEEL", "name": "JSW Steel", "sector": "Metals"},
    {"symbol": "COALINDIA", "name": "Coal India", "sector": "Energy"},
    {"symbol": "DRREDDY", "name": "Dr Reddy's Laboratories", "sector": "Pharma"},
]

BENCHMARKS = [
    {"symbol": "^NSEI", "label": "NIFTY 50"},
    {"symbol": "^NSEBANK", "label": "NIFTY Bank"},
    {"symbol": "^BSESN", "label": "SENSEX"},
    {"symbol": "^CNXIT", "label": "NIFTY IT"},
]

TIMEFRAMES = [
    {"key": "1d", "label": "Daily", "note": "Full history available."},
    {"key": "1wk", "label": "Weekly", "note": "Full history available."},
    {"key": "60m", "label": "Hourly", "note": "Provider limits history to ~720 days."},
    {"key": "30m", "label": "30 minute", "note": "Provider limits history to ~60 days."},
    {"key": "15m", "label": "15 minute", "note": "Provider limits history to ~60 days."},
    {"key": "5m", "label": "5 minute", "note": "Provider limits history to ~60 days."},
]


def full_catalogue() -> dict:
    """Everything the builder needs, in one request."""
    return {
        "engine_version": "2.0.0",
        "indicators": indicator_catalogue(),
        "candles": candle_catalogue(),
        "chart_patterns": chart_pattern_catalogue(),
        "structure_outputs": structure_catalogue(),
        "operators": graph_lib.operator_catalogue(),
        "sizing_models": sizing_catalogue(),
        "risk_rules": riskrules.catalogue(),
        "execution": execution_catalogue(),
        "cost_schedules": list_cost_schedules(),
        "presets": list_presets(),
        "universe": STARTER_UNIVERSE,
        "benchmarks": BENCHMARKS,
        "timeframes": TIMEFRAMES,
        "periods_per_year": PERIODS_PER_YEAR,
        "price_sources": ["close", "open", "high", "low", "hl2", "typical"],
        "principles": [
            "Gross and net results are always reported separately.",
            "A signal generated at a bar's close can never be filled at that close.",
            "Swing pivots stay hidden until later bars confirm them.",
            "Chart patterns are actionable only on their confirmation bar.",
            "When a stop and a target share a bar, the stop is assumed first.",
            "Every rupee of cost traces back to an individual fill.",
            "A strategy that fails is a valid result, and the report explains why.",
        ],
    }
