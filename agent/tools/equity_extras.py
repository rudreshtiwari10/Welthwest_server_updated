"""Equity extras: dividend history, corporate actions, earnings calendar.

Wraps yfinance, which exposes:
  - ticker.dividends    (Series indexed by date, values = dividend amount)
  - ticker.splits       (Series indexed by date, values = split ratio)
  - ticker.actions      (DataFrame with Dividends + Stock Splits columns)
  - ticker.calendar     (next earnings, dividend, etc.)
"""

import logging
from datetime import datetime

from agent.tools.base import Tool, ToolResult
from services.market_data.providers.yfinance_provider import _get_yf, _normalize_symbol, _sleep_before_call

logger = logging.getLogger(__name__)


def _safe_ticker(symbol: str):
    yf = _get_yf()
    yf_symbol = _normalize_symbol(symbol)
    _sleep_before_call()
    return yf.Ticker(yf_symbol), yf_symbol


# =============================================================================

class GetDividendHistoryTool(Tool):
    name = "get_dividend_history"
    description = (
        "Get dividend history for an Indian stock — past payouts with dates and amounts. "
        "Use for 'dividend history of TCS', 'how much has ITC paid in dividends', etc. "
        "Also returns trailing 12-month dividend yield estimate."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "limit": {"type": "integer", "description": "Number of most-recent payouts to return (1-30). Default 12."},
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol, limit=12, **_) -> ToolResult:
        try:
            limit = max(1, min(int(limit or 12), 30))
            ticker, yf_symbol = _safe_ticker(symbol)
            divs = ticker.dividends
            if divs is None or len(divs) == 0:
                return ToolResult(success=False, error=f"No dividend history found for {symbol}")
            # divs is a pandas Series
            recent = divs.tail(limit)
            payouts = []
            for d, amt in recent.items():
                payouts.append({"date": d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10], "amount": round(float(amt), 4)})
            payouts = list(reversed(payouts))  # most-recent first

            # Trailing 12 months estimate
            from datetime import date as _date, timedelta
            cutoff = _date.today() - timedelta(days=365)
            ttm_total = 0.0
            for d, amt in divs.items():
                d_d = d.date() if hasattr(d, "date") else d
                if d_d >= cutoff:
                    ttm_total += float(amt)

            # Current price for yield estimate
            yield_pct = None
            try:
                quote = ticker.fast_info if hasattr(ticker, "fast_info") else {}
                price = None
                for key in ("last_price", "lastPrice", "regularMarketPrice"):
                    try:
                        v = quote[key]
                        if v:
                            price = float(v)
                            break
                    except (KeyError, TypeError):
                        continue
                if price and price > 0:
                    yield_pct = ttm_total / price * 100
            except Exception:
                pass

            return ToolResult(success=True, data={
                "symbol": symbol.upper().strip(),
                "yf_symbol": yf_symbol,
                "payouts_count_returned": len(payouts),
                "trailing_12mo_total": round(ttm_total, 4),
                "trailing_12mo_yield_pct": round(yield_pct, 3) if yield_pct is not None else None,
                "payouts": payouts,
                "note": "Yields are based on the trailing 12 months — a low yield can mean recent dividend cuts OR strong price appreciation.",
            }, display_hint="dividend_history")
        except Exception as e:
            return ToolResult(success=False, error=f"Dividend history failed for {symbol}: {e}")


class GetCorporateActionsTool(Tool):
    name = "get_corporate_actions"
    description = (
        "Get corporate-action history (dividends + stock splits) for an Indian stock. "
        "Use for 'has TCS done any splits', 'corporate-action timeline of WIPRO', etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "limit": {"type": "integer", "description": "Most-recent N events. Default 20."},
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol, limit=20, **_) -> ToolResult:
        try:
            limit = max(1, min(int(limit or 20), 100))
            ticker, yf_symbol = _safe_ticker(symbol)
            actions = ticker.actions
            if actions is None or len(actions) == 0:
                return ToolResult(success=False, error=f"No corporate actions found for {symbol}")

            events = []
            for d, row in actions.iterrows():
                date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                div = float(row.get("Dividends", 0) or 0)
                split = float(row.get("Stock Splits", 0) or 0)
                if div > 0:
                    events.append({"date": date_str, "type": "dividend", "amount": round(div, 4)})
                if split > 0:
                    events.append({"date": date_str, "type": "stock_split", "ratio": round(split, 4)})
            events.sort(key=lambda e: e["date"], reverse=True)
            events = events[:limit]

            return ToolResult(success=True, data={
                "symbol": symbol.upper().strip(),
                "yf_symbol": yf_symbol,
                "events_count": len(events),
                "events": events,
                "note": (
                    "yfinance reports dividends and splits. Bonus issues are sometimes reported "
                    "as splits, sometimes missed entirely — verify with NSE/BSE for definitive data. "
                    "Buybacks are NOT in this feed."
                ),
            }, display_hint="corporate_actions")
        except Exception as e:
            return ToolResult(success=False, error=f"Corporate actions failed for {symbol}: {e}")


class GetEarningsCalendarTool(Tool):
    name = "get_earnings_calendar"
    description = (
        "Get the upcoming earnings / results date for a stock (and recent ones if available). "
        "Use for 'when is TCS results out', 'next earnings of RELIANCE'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol, **_) -> ToolResult:
        try:
            ticker, yf_symbol = _safe_ticker(symbol)
            cal = None
            try:
                cal = ticker.calendar
            except Exception as e:
                logger.warning("calendar fetch failed: %s", e)

            data = {
                "symbol": symbol.upper().strip(),
                "yf_symbol": yf_symbol,
                "next_earnings": None,
                "raw": {},
            }

            if cal is None:
                return ToolResult(success=False, error=f"No earnings calendar available for {symbol}")

            # cal can be a dict OR a DataFrame depending on yfinance version
            if isinstance(cal, dict):
                raw = {}
                for k, v in cal.items():
                    if hasattr(v, "isoformat"):
                        raw[k] = v.isoformat()
                    elif isinstance(v, list):
                        raw[k] = [x.isoformat() if hasattr(x, "isoformat") else x for x in v]
                    else:
                        raw[k] = v
                data["raw"] = raw
                # Pull next earnings date
                ed = cal.get("Earnings Date") or cal.get("earnings_date")
                if isinstance(ed, list) and ed:
                    data["next_earnings"] = ed[0].isoformat() if hasattr(ed[0], "isoformat") else str(ed[0])
                elif ed and hasattr(ed, "isoformat"):
                    data["next_earnings"] = ed.isoformat()
            else:
                # DataFrame
                try:
                    if "Earnings Date" in cal.index:
                        v = cal.loc["Earnings Date"].iloc[0]
                        if hasattr(v, "strftime"):
                            data["next_earnings"] = v.strftime("%Y-%m-%d")
                except Exception:
                    pass

            if not data["next_earnings"] and not data["raw"]:
                return ToolResult(success=False, error=f"Earnings calendar empty for {symbol}")

            return ToolResult(success=True, data={
                **data,
                "note": "Earnings dates are estimates from yfinance. Verify with the company IR page or NSE / BSE filings.",
            }, display_hint="earnings_calendar")
        except Exception as e:
            return ToolResult(success=False, error=f"Earnings calendar failed for {symbol}: {e}")
