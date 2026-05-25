"""
yfinance-backed MarketDataProvider.

This wraps the existing yfinance usage patterns from stock_service.py so that
the rest of the codebase can depend on the MarketDataProvider interface
instead of calling yfinance directly. Behavior is intentionally identical to
the existing code — same lazy import, same Render sleep hack, same NSE
symbol suffixing.

Migration note: existing call sites in stock_service.py, finance_orchestrator.py,
etc. are NOT changed. They will be migrated incrementally in later steps.
"""

import logging
import os
import random
import time
from datetime import datetime
from typing import Optional

from services.market_data.base import (
    MarketDataProvider,
    Quote,
    Candle,
    SymbolMatch,
    Fundamentals,
    MarketDataError,
    SymbolNotFoundError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

# Lazy yfinance import — mirrors stock_service.py pattern to keep startup fast.
_yf = None


def _get_yf():
    global _yf
    if _yf is None:
        import yfinance as yf
        try:
            yf.set_tz_cache_location("/tmp/yfinance_tz_cache")
        except Exception:
            pass
        _yf = yf
    return _yf


IS_RENDER = str(os.getenv("RENDER", "")).lower() in ("true", "1", "yes")


def _sleep_before_call():
    """Anti-rate-limit jitter — stricter on Render."""
    if IS_RENDER:
        time.sleep(random.uniform(3.0, 8.0))
    else:
        time.sleep(random.uniform(0.5, 2.0))


def _normalize_symbol(symbol: str) -> str:
    """
    Apply NSE suffix for bare Indian tickers. This is the same behavior the
    codebase already relies on; the proper symbol resolver (Phase 1.4) will
    replace this heuristic.
    """
    s = symbol.strip().upper()
    if "." in s or "^" in s or "=" in s:
        return s
    return f"{s}.NS"


class YFinanceProvider(MarketDataProvider):
    """MarketDataProvider implementation backed by yfinance."""

    name = "yfinance"

    def get_quote(self, symbol: str) -> Quote:
        yf = _get_yf()
        yf_symbol = _normalize_symbol(symbol)
        try:
            _sleep_before_call()
            ticker = yf.Ticker(yf_symbol)
            info = ticker.fast_info if hasattr(ticker, "fast_info") else {}

            price = None
            for key in ("last_price", "lastPrice", "regularMarketPrice"):
                try:
                    v = info[key] if not callable(info) else None
                    if v:
                        price = float(v)
                        break
                except Exception:
                    continue

            if price is None:
                hist = ticker.history(period="1d")
                if hist is None or hist.empty:
                    raise SymbolNotFoundError(f"No data for symbol {symbol!r}")
                price = float(hist["Close"].iloc[-1])

            def _safe(key):
                try:
                    v = info[key]
                    return float(v) if v is not None else None
                except Exception:
                    return None

            prev_close = _safe("previous_close") or _safe("previousClose")
            change = None
            change_pct = None
            if prev_close and price:
                change = price - prev_close
                change_pct = (change / prev_close) * 100 if prev_close else None

            return Quote(
                symbol=symbol.upper(),
                price=price,
                currency="INR",
                change=change,
                change_percent=change_pct,
                volume=int(_safe("last_volume") or _safe("lastVolume") or 0) or None,
                day_high=_safe("day_high") or _safe("dayHigh"),
                day_low=_safe("day_low") or _safe("dayLow"),
                open=_safe("open"),
                previous_close=prev_close,
                timestamp=datetime.utcnow(),
                exchange="NSE" if yf_symbol.endswith(".NS") else (
                    "BSE" if yf_symbol.endswith(".BO") else None
                ),
                extras={"yf_symbol": yf_symbol},
            )
        except SymbolNotFoundError:
            raise
        except Exception as e:
            logger.warning("yfinance get_quote failed for %s: %s", symbol, e)
            raise ProviderUnavailableError(
                f"Could not fetch quote for {symbol!r}"
            ) from e

    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> list[Candle]:
        yf = _get_yf()
        yf_symbol = _normalize_symbol(symbol)
        try:
            _sleep_before_call()
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval)
            if df is None or df.empty:
                raise SymbolNotFoundError(f"No history for {symbol!r}")

            candles: list[Candle] = []
            for ts, row in df.iterrows():
                try:
                    candles.append(
                        Candle(
                            timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                            open=float(row["Open"]),
                            high=float(row["High"]),
                            low=float(row["Low"]),
                            close=float(row["Close"]),
                            volume=int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                        )
                    )
                except Exception:
                    continue
            return candles
        except SymbolNotFoundError:
            raise
        except Exception as e:
            logger.warning("yfinance get_history failed for %s: %s", symbol, e)
            raise ProviderUnavailableError(
                f"Could not fetch history for {symbol!r}"
            ) from e

    def search_symbols(self, query: str, limit: int = 5) -> list[SymbolMatch]:
        """
        yfinance has no first-class symbol search. The existing codebase uses
        services/nse_symbols.py for this. For now this provider returns a
        single best-effort match by assuming the query is already a ticker.
        Phase 1.4 will replace this with a proper resolver backed by the
        NSE/BSE master lists.
        """
        q = query.strip().upper()
        if not q:
            return []
        yf_symbol = _normalize_symbol(q)
        return [
            SymbolMatch(
                symbol=q,
                name=q,
                exchange="NSE" if yf_symbol.endswith(".NS") else "UNKNOWN",
                confidence=0.5,
            )
        ]

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        yf = _get_yf()
        yf_symbol = _normalize_symbol(symbol)
        try:
            _sleep_before_call()
            ticker = yf.Ticker(yf_symbol)
            info = {}
            try:
                info = ticker.info or {}
            except Exception as e:
                logger.debug("yfinance .info failed for %s: %s", symbol, e)

            def _f(key) -> Optional[float]:
                v = info.get(key)
                try:
                    return float(v) if v is not None else None
                except Exception:
                    return None

            return Fundamentals(
                symbol=symbol.upper(),
                market_cap=_f("marketCap"),
                pe_ratio=_f("trailingPE") or _f("forwardPE"),
                pb_ratio=_f("priceToBook"),
                eps=_f("trailingEps") or _f("forwardEps"),
                dividend_yield=_f("dividendYield"),
                roe=_f("returnOnEquity"),
                debt_to_equity=_f("debtToEquity"),
                book_value=_f("bookValue"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                extras={
                    "long_name": info.get("longName"),
                    "website": info.get("website"),
                },
            )
        except Exception as e:
            logger.warning("yfinance get_fundamentals failed for %s: %s", symbol, e)
            raise ProviderUnavailableError(
                f"Could not fetch fundamentals for {symbol!r}"
            ) from e

    # Headline line items per statement. yfinance row labels vary slightly
    # between companies / data revisions, so we accept multiple aliases.
    _INCOME_LINE_ITEMS = [
        ("Total Revenue", ["Total Revenue", "TotalRevenue", "Revenue"]),
        ("Cost of Revenue", ["Cost Of Revenue", "CostOfRevenue"]),
        ("Gross Profit", ["Gross Profit", "GrossProfit"]),
        ("Operating Expense", ["Operating Expense", "OperatingExpense", "Total Operating Expenses"]),
        ("Operating Income", ["Operating Income", "OperatingIncome"]),
        ("EBITDA", ["EBITDA", "Normalized EBITDA"]),
        ("EBIT", ["EBIT"]),
        ("Interest Expense", ["Interest Expense", "InterestExpense"]),
        ("Tax Provision", ["Tax Provision", "Income Tax Expense", "IncomeTaxExpense"]),
        ("Net Income", ["Net Income", "NetIncome", "Net Income Common Stockholders"]),
        ("Diluted EPS", ["Diluted EPS", "DilutedEPS"]),
        ("Basic EPS", ["Basic EPS", "BasicEPS"]),
    ]

    _BALANCE_LINE_ITEMS = [
        ("Total Assets", ["Total Assets", "TotalAssets"]),
        ("Total Liabilities", ["Total Liabilities Net Minority Interest", "Total Liab", "TotalLiabilitiesNetMinorityInterest"]),
        ("Total Equity", ["Total Equity Gross Minority Interest", "Stockholders Equity", "Total Stockholder Equity"]),
        ("Total Debt", ["Total Debt", "TotalDebt"]),
        ("Cash & Equivalents", ["Cash And Cash Equivalents", "CashAndCashEquivalents", "Cash Cash Equivalents And Short Term Investments"]),
        ("Current Assets", ["Current Assets", "CurrentAssets", "Total Current Assets"]),
        ("Current Liabilities", ["Current Liabilities", "CurrentLiabilities", "Total Current Liabilities"]),
        ("Working Capital", ["Working Capital", "WorkingCapital"]),
        ("Net Tangible Assets", ["Net Tangible Assets", "NetTangibleAssets"]),
    ]

    _CASHFLOW_LINE_ITEMS = [
        ("Operating Cash Flow", ["Operating Cash Flow", "OperatingCashFlow", "Cash Flow From Continuing Operating Activities", "Total Cash From Operating Activities"]),
        ("Investing Cash Flow", ["Investing Cash Flow", "InvestingCashFlow", "Cash Flow From Continuing Investing Activities", "Total Cashflows From Investing Activities"]),
        ("Financing Cash Flow", ["Financing Cash Flow", "FinancingCashFlow", "Cash Flow From Continuing Financing Activities", "Total Cash From Financing Activities"]),
        ("Capital Expenditure", ["Capital Expenditure", "CapitalExpenditure", "Capital Expenditures"]),
        ("Free Cash Flow", ["Free Cash Flow", "FreeCashFlow"]),
        ("Net Income", ["Net Income", "NetIncome"]),
    ]

    @staticmethod
    def _pick_row(df, aliases):
        """Find the first matching row label in a yfinance financials DataFrame."""
        if df is None or getattr(df, "empty", True):
            return None
        # df.index contains row labels
        idx = list(df.index)
        for alias in aliases:
            if alias in idx:
                return df.loc[alias]
        # Loose match — case-insensitive contains
        lowered = {str(i).strip().lower(): i for i in idx}
        for alias in aliases:
            key = alias.strip().lower()
            if key in lowered:
                return df.loc[lowered[key]]
        return None

    def get_financials(
        self,
        symbol: str,
        statement: str = "income",
        period: str = "quarterly",
        num_periods: int = 4,
    ) -> dict:
        yf = _get_yf()
        yf_symbol = _normalize_symbol(symbol)
        statement = (statement or "income").strip().lower()
        period = (period or "quarterly").strip().lower()
        num_periods = max(1, min(int(num_periods or 4), 12))

        if statement not in ("income", "balance", "cashflow"):
            raise MarketDataError(f"Unknown statement '{statement}'. Use income | balance | cashflow.")
        if period not in ("quarterly", "annual"):
            raise MarketDataError(f"Unknown period '{period}'. Use quarterly | annual.")

        try:
            _sleep_before_call()
            ticker = yf.Ticker(yf_symbol)

            if statement == "income":
                df = ticker.quarterly_financials if period == "quarterly" else ticker.financials
                items = self._INCOME_LINE_ITEMS
            elif statement == "balance":
                df = ticker.quarterly_balance_sheet if period == "quarterly" else ticker.balance_sheet
                items = self._BALANCE_LINE_ITEMS
            else:  # cashflow
                df = ticker.quarterly_cashflow if period == "quarterly" else ticker.cashflow
                items = self._CASHFLOW_LINE_ITEMS

            if df is None or getattr(df, "empty", True):
                raise SymbolNotFoundError(
                    f"No {statement} statement found for {symbol}. The ticker may be invalid or this data is unavailable."
                )

            # Columns are period-end dates (most-recent first in yfinance)
            cols = list(df.columns)[:num_periods]

            periods_out = []
            for col in cols:
                line_items = {}
                for label, aliases in items:
                    row = self._pick_row(df, aliases)
                    if row is None:
                        continue
                    try:
                        val = row.get(col)
                    except Exception:
                        val = None
                    # NaN / None handling
                    if val is None:
                        continue
                    try:
                        import math
                        f = float(val)
                        if math.isnan(f) or math.isinf(f):
                            continue
                        line_items[label] = f
                    except (TypeError, ValueError):
                        continue

                period_end = (
                    col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)[:10]
                )
                periods_out.append({"period_end": period_end, "line_items": line_items})

            # Currency: yfinance Indian stocks are in INR; foreign in USD. We default to INR
            # for *.NS and *.BO; otherwise leave empty for the LLM to interpret.
            currency = "INR" if yf_symbol.endswith(".NS") or yf_symbol.endswith(".BO") else None

            return {
                "symbol": symbol.upper().strip(),
                "yf_symbol": yf_symbol,
                "statement": statement,
                "period": period,
                "currency": currency,
                "periods": periods_out,
            }

        except SymbolNotFoundError:
            raise
        except Exception as e:
            logger.error("get_financials failed for %s (%s/%s): %s", symbol, statement, period, e)
            raise ProviderUnavailableError(
                f"Could not fetch {statement} statement for {symbol}: {e}"
            ) from e

    def get_index_quote(self, index: str) -> Quote:
        """
        Map common Indian index names to yfinance symbols and reuse get_quote.
        """
        index_map = {
            "NIFTY": "^NSEI",
            "NIFTY50": "^NSEI",
            "NIFTY 50": "^NSEI",
            "SENSEX": "^BSESN",
            "BANKNIFTY": "^NSEBANK",
            "BANK NIFTY": "^NSEBANK",
            "NIFTY BANK": "^NSEBANK",
            "NIFTY IT": "^CNXIT",
        }
        key = index.strip().upper()
        yf_symbol = index_map.get(key, key)
        # Bypass _normalize_symbol — index symbols already have the ^ prefix.
        quote = self.get_quote(yf_symbol)
        quote.symbol = key
        quote.exchange = "NSE"
        return quote
