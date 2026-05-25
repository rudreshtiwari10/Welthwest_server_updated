"""Tools: get_macro_indicator, get_forex_rate, get_commodity_price, get_sector_performance."""

from agent.tools.base import Tool, ToolResult


# ---------------------------------------------------------------------------
# Macro indicators — static reference values.
#
# RBI publishes via the DBIE database; CPI/WPI via MOSPI; GDP via NSO. None of
# these have a clean, free, reliable JSON API. Rather than pretend we have a
# live feed, we ship known reference values with explicit `valid_as_of` stamps
# and a clear "verify with the source" disclaimer. Update this table when the
# numbers change (after each MPC, after each CPI/WPI release).
#
# When live wiring is added later, swap this dict for the real source — the
# tool API stays the same.
# ---------------------------------------------------------------------------

_MACRO: dict = {
    "repo_rate": {
        "value": 6.50, "unit": "%", "valid_as_of": "2025-04-09",
        "source": "RBI MPC", "description": "RBI repo rate — short-term lending rate to banks.",
    },
    "sdf": {
        "value": 6.25, "unit": "%", "valid_as_of": "2025-04-09",
        "source": "RBI", "description": "Standing Deposit Facility — floor of the liquidity corridor (replaced reverse repo as the active floor).",
    },
    "msf": {
        "value": 6.75, "unit": "%", "valid_as_of": "2025-04-09",
        "source": "RBI", "description": "Marginal Standing Facility — ceiling of the liquidity corridor.",
    },
    "crr": {
        "value": 4.00, "unit": "%", "valid_as_of": "2024-12-06",
        "source": "RBI", "description": "Cash Reserve Ratio — % of NDTL banks must keep with RBI as cash.",
    },
    "slr": {
        "value": 18.00, "unit": "%", "valid_as_of": "2024-04-08",
        "source": "RBI", "description": "Statutory Liquidity Ratio — % of NDTL banks must invest in approved liquid assets.",
    },
    "cpi_inflation": {
        "value": 5.40, "unit": "% YoY", "valid_as_of": "2025-03-31",
        "source": "MOSPI / NSO (CPI Combined)", "description": "Headline retail inflation — RBI's monetary-policy target metric.",
    },
    "wpi_inflation": {
        "value": 2.30, "unit": "% YoY", "valid_as_of": "2025-03-31",
        "source": "Ministry of Commerce (WPI)", "description": "Wholesale price inflation — early signal for input-cost pressure.",
    },
    "gdp_growth": {
        "value": 6.50, "unit": "% YoY", "valid_as_of": "2025-02-28",
        "source": "NSO (Q3 FY25 GDP estimate)", "description": "Real GDP growth.",
    },
    "fiscal_deficit_pct_gdp": {
        "value": 4.90, "unit": "% of GDP", "valid_as_of": "2025-02-01",
        "source": "Union Budget FY25-26 (Revised)", "description": "Government's fiscal deficit target as % of GDP.",
    },
}

_MACRO_ALIASES = {
    "repo": "repo_rate", "rbi repo rate": "repo_rate", "policy rate": "repo_rate",
    "reverse repo": "sdf", "reverse repo rate": "sdf", "sdf rate": "sdf",
    "msf rate": "msf",
    "cash reserve ratio": "crr",
    "statutory liquidity ratio": "slr",
    "cpi": "cpi_inflation", "inflation": "cpi_inflation", "retail inflation": "cpi_inflation",
    "wpi": "wpi_inflation", "wholesale inflation": "wpi_inflation",
    "gdp": "gdp_growth", "gdp growth": "gdp_growth",
    "fiscal deficit": "fiscal_deficit_pct_gdp",
}


class GetMacroIndicatorTool(Tool):
    name = "get_macro_indicator"
    description = (
        "Look up the latest known value of a key Indian macro indicator: RBI repo rate, "
        "SDF, MSF, CRR, SLR, CPI inflation, WPI inflation, GDP growth, fiscal deficit. "
        "Returns the value plus the date it's valid as of and the source. ALWAYS surface "
        "the valid_as_of date in your answer — these can change at any RBI MPC / CPI release."
    )
    parameters = {
        "type": "object",
        "properties": {
            "indicator": {
                "type": "string",
                "description": (
                    "Indicator name. Accepted (case-insensitive): repo_rate / repo, sdf / "
                    "reverse_repo, msf, crr, slr, cpi / cpi_inflation, wpi / wpi_inflation, "
                    "gdp / gdp_growth, fiscal_deficit."
                ),
            },
        },
        "required": ["indicator"],
    }

    def execute(self, *, indicator: str, **_) -> ToolResult:
        key = (indicator or "").strip().lower().replace("-", "_").replace(" ", "_")
        # Strip alias map AND check direct
        if key in _MACRO:
            data = _MACRO[key]
        elif key.replace("_", " ") in _MACRO_ALIASES:
            data = _MACRO[_MACRO_ALIASES[key.replace("_", " ")]]
        else:
            # Try without underscores
            spaced = key.replace("_", " ")
            if spaced in _MACRO_ALIASES:
                data = _MACRO[_MACRO_ALIASES[spaced]]
            else:
                avail = sorted(set(list(_MACRO.keys()) + list(_MACRO_ALIASES.keys())))
                return ToolResult(success=False, error=f"Unknown macro indicator '{indicator}'. Try one of: {', '.join(avail)}")

        return ToolResult(
            success=True,
            data={
                "indicator": indicator,
                **data,
                "disclaimer": (
                    "This is the most recent value WelthWest has on file as of "
                    f"{data['valid_as_of']}. RBI / MOSPI may have updated it since — "
                    "verify with the official source for time-critical decisions."
                ),
            },
            display_hint="macro_card",
        )


class GetForexRateTool(Tool):
    name = "get_forex_rate"
    description = (
        "Get the latest exchange rate for a currency pair via yfinance. Defaults to "
        "USD/INR if no pair given. Use for 'USD INR rate', 'EUR INR', 'GBP INR', etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pair": {
                "type": "string",
                "description": "Currency pair like 'USDINR', 'EURINR', 'GBPINR', 'JPYINR'. Default 'USDINR'.",
            },
        },
    }

    _PAIR_MAP = {
        "USDINR": "USDINR=X",
        "EURINR": "EURINR=X",
        "GBPINR": "GBPINR=X",
        "JPYINR": "JPYINR=X",
        "AUDINR": "AUDINR=X",
        "CADINR": "CADINR=X",
        "SGDINR": "SGDINR=X",
        "INRUSD": "INRUSD=X",
    }

    def execute(self, *, pair: str = "USDINR", **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            symbol = (pair or "USDINR").upper().replace("/", "").replace("-", "")
            yf_symbol = self._PAIR_MAP.get(symbol, f"{symbol}=X")
            provider = get_default_provider()
            quote = provider.get_quote(yf_symbol)
            return ToolResult(
                success=True,
                data={
                    "pair": symbol,
                    "rate": quote.price,
                    "change": quote.change,
                    "change_percent": quote.change_percent,
                    "previous_close": quote.previous_close,
                },
                display_hint="forex_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch forex rate for {pair}: {e}")


class GetCommodityPriceTool(Tool):
    name = "get_commodity_price"
    description = (
        "Get the latest price of a commodity via yfinance: gold, silver, crude oil, "
        "natural gas, copper, etc. Returns spot/futures price, change, and % change. "
        "Use for 'gold price today', 'crude oil rate', etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "commodity": {
                "type": "string",
                "description": "Commodity name: 'gold', 'silver', 'crude' / 'crude oil' / 'wti', 'brent', 'natural gas', 'copper'.",
            },
        },
        "required": ["commodity"],
    }

    _COMMODITY_MAP = {
        "gold": "GC=F",
        "silver": "SI=F",
        "crude": "CL=F", "crude oil": "CL=F", "wti": "CL=F",
        "brent": "BZ=F", "brent crude": "BZ=F",
        "natural gas": "NG=F", "ng": "NG=F",
        "copper": "HG=F",
        "platinum": "PL=F",
    }

    def execute(self, *, commodity: str, **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            key = (commodity or "").strip().lower()
            yf_symbol = self._COMMODITY_MAP.get(key)
            if not yf_symbol:
                return ToolResult(success=False, error=f"Unknown commodity '{commodity}'. Supported: {', '.join(sorted(set(self._COMMODITY_MAP.keys())))}")
            provider = get_default_provider()
            quote = provider.get_quote(yf_symbol)
            return ToolResult(
                success=True,
                data={
                    "commodity": commodity,
                    "yf_symbol": yf_symbol,
                    "price": quote.price,
                    "currency": "USD",
                    "change": quote.change,
                    "change_percent": quote.change_percent,
                    "previous_close": quote.previous_close,
                    "note": (
                        "Yahoo prices are USD-denominated futures. For Indian MCX / domestic "
                        "spot prices add forex conversion (USD/INR) and import duties / GST."
                    ),
                },
                display_hint="commodity_card",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch {commodity} price: {e}")


class GetSectorPerformanceTool(Tool):
    name = "get_sector_performance"
    description = (
        "Snapshot the performance of major Indian sector indices: Bank, IT, FMCG, Auto, "
        "Pharma, Metal, Energy, Realty, Financial Services. Returns the current value "
        "and change% for each so the LLM can identify leaders/laggards. Use for 'which "
        "sectors led today', 'sector heatmap', 'how is bank nifty doing'."
    )
    parameters = {"type": "object", "properties": {}}

    _SECTORS = [
        ("Bank", "^NSEBANK"),
        ("IT", "^CNXIT"),
        ("FMCG", "^CNXFMCG"),
        ("Auto", "^CNXAUTO"),
        ("Pharma", "^CNXPHARMA"),
        ("Metal", "^CNXMETAL"),
        ("Energy", "^CNXENERGY"),
        ("Realty", "^CNXREALTY"),
        ("Financial Services", "^CNXFIN"),
        ("PSU Bank", "^CNXPSUBANK"),
    ]

    def execute(self, **_) -> ToolResult:
        try:
            from services.market_data import get_default_provider
            provider = get_default_provider()
            sectors = []
            for label, sym in self._SECTORS:
                try:
                    q = provider.get_quote(sym)
                    sectors.append({
                        "sector": label,
                        "symbol": sym,
                        "value": q.price,
                        "change": q.change,
                        "change_percent": q.change_percent,
                    })
                except Exception as e:
                    sectors.append({"sector": label, "symbol": sym, "error": str(e)[:80]})
            # Sort by change_percent desc when available
            with_data = [s for s in sectors if s.get("change_percent") is not None]
            with_data.sort(key=lambda s: s["change_percent"], reverse=True)
            failed = [s for s in sectors if s.get("change_percent") is None]
            return ToolResult(
                success=True,
                data={
                    "sectors": with_data + failed,
                    "leaders": with_data[:3],
                    "laggards": with_data[-3:][::-1] if len(with_data) >= 3 else [],
                },
                display_hint="sector_heatmap",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch sector performance: {e}")
