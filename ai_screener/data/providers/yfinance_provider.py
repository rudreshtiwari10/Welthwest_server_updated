"""PRIMARY data provider: Yahoo Finance API for Indian stock market (NSE/BSE).
yfinance is free, requires no API key, and provides OHLCV, fundamentals,
institutional holdings, earnings, and corporate actions for NSE/BSE stocks.

NSE symbols use '.NS' suffix (e.g., RELIANCE.NS)
BSE symbols use '.BO' suffix (e.g., 500325.BO)
"""
import pandas as pd
import yfinance as yf
from datetime import date, datetime, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

logger = logging.getLogger(__name__)


class YFinanceIndiaProvider:
    """Indian stock market data from Yahoo Finance API.

    Covers: NSE, BSE -- OHLCV, fundamentals, holdings, earnings, dividends.
    """

    NIFTY_INDICES = {
        "NIFTY50": "^NSEI",
        "NIFTYBANK": "^NSEBANK",
        "NIFTYNEXT50": "^NSMIDCP",
        "INDIAVIX": "^INDIAVIX",
        "NIFTYIT": "^CNXIT",
        "NIFTYPHARMA": "^CNXPHARMA",
    }

    def __init__(self, suffix: str = ".NS", exchange: str = "NSE"):
        self.suffix = suffix
        self.exchange = exchange
        self._rate_limit_delay = 0.1  # reduced from 0.25 — yfinance handles this fine
        # In-memory cache: {symbol: {"data": {...}, "fetched_at": datetime}}
        self._fundamentals_cache: dict = {}
        self._cache_ttl = 1800  # 30 minutes

    def _to_yf_symbol(self, symbol: str) -> str:
        if symbol.startswith("^"):
            return symbol
        if ".NS" in symbol or ".BO" in symbol:
            return symbol
        return f"{symbol}{self.suffix}"

    def fetch_price_data(
        self, symbol: str, start_date: date, end_date: date, interval: str = "1d"
    ) -> pd.DataFrame:
        yf_symbol = self._to_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_symbol)
            # For intraday intervals, use period-based fetch (yfinance caps at 60 days)
            if interval in ("1h", "15m"):
                df = ticker.history(period="60d", interval=interval, auto_adjust=True, actions=False)
            else:
                df = ticker.history(start=start_date, end=end_date, auto_adjust=True, actions=False)
            if df.empty:
                logger.warning(f"No data returned for {yf_symbol} (interval={interval})")
                return pd.DataFrame()
            df = df.reset_index()
            # yfinance uses "Date" for daily, "Datetime" for intraday
            ts_col = "Datetime" if "Datetime" in df.columns else "Date"
            df = df.rename(columns={
                ts_col: "timestamp", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume",
            })
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
            time.sleep(self._rate_limit_delay)
            return df[["timestamp", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            logger.error(f"Failed to fetch {yf_symbol} (interval={interval}): {e}")
            return pd.DataFrame()

    def fetch_fundamentals(self, symbol: str) -> dict:
        # Check cache first
        cached = self._fundamentals_cache.get(symbol)
        if cached:
            age = (datetime.now() - cached["fetched_at"]).total_seconds()
            if age < self._cache_ttl:
                return cached["data"]

        yf_symbol = self._to_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
            fundamentals = {
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "roe": info.get("returnOnEquity"),
                "profit_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "eps_trailing": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
                "debt_to_equity": info.get("debtToEquity"),
                "free_cashflow": info.get("freeCashflow"),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "avg_volume": info.get("averageVolume"),
                "beta": info.get("beta"),
                "book_value": info.get("bookValue"),
                "name": info.get("longName", info.get("shortName", symbol)),
            }
            time.sleep(self._rate_limit_delay)
            result = {k: v for k, v in fundamentals.items() if v is not None}

            # Store in cache
            self._fundamentals_cache[symbol] = {
                "data": result,
                "fetched_at": datetime.now(),
            }
            return result
        except Exception as e:
            logger.error(f"Fundamentals failed for {yf_symbol}: {e}")
            return {}

    def fetch_earnings(self, symbol: str) -> dict:
        yf_symbol = self._to_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_symbol)
            earnings = ticker.quarterly_earnings
            if earnings is not None and not earnings.empty:
                latest = earnings.iloc[0]
                result = {
                    "actual_eps": latest.get("Earnings", None),
                    "revenue": latest.get("Revenue", None),
                }
                if earnings is not None and len(earnings) > 1:
                    prev_eps = earnings.iloc[1].get("Earnings")
                    if prev_eps and prev_eps != 0 and result.get("actual_eps"):
                        result["eps_growth_yoy"] = (
                            (result["actual_eps"] - prev_eps) / abs(prev_eps) * 100
                        )
                time.sleep(self._rate_limit_delay)
                return result
            return {}
        except Exception as e:
            logger.error(f"Earnings fetch failed for {yf_symbol}: {e}")
            return {}

    def fetch_insider_transactions(self, symbol: str) -> list[dict]:
        yf_symbol = self._to_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_symbol)
            insiders = ticker.insider_transactions
            if insiders is not None and not insiders.empty:
                result = []
                for _, row in insiders.iterrows():
                    result.append({
                        "insider_name": row.get("Insider", ""),
                        "insider_title": row.get("Position", ""),
                        "transaction_type": row.get("Transaction", ""),
                        "filing_date": str(row.get("Start Date", "")),
                        "shares": abs(row.get("Shares", 0)),
                        "value": abs(row.get("Value", 0)),
                    })
                time.sleep(self._rate_limit_delay)
                return result
            return []
        except Exception:
            return []

    def fetch_institutional_holders(self, symbol: str) -> list[dict]:
        yf_symbol = self._to_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_symbol)
            holders = ticker.institutional_holders
            if holders is not None and not holders.empty:
                result = []
                for _, row in holders.iterrows():
                    result.append({
                        "holder": row.get("Holder", ""),
                        "shares": row.get("Shares", 0),
                        "date_reported": str(row.get("Date Reported", "")),
                        "pct_held": row.get("% Out", 0),
                        "value": row.get("Value", 0),
                    })
                time.sleep(self._rate_limit_delay)
                return result
            return []
        except Exception:
            return []

    def fetch_bulk_prices(
        self, symbols: list[str], start_date: date, end_date: date, interval: str = "1d"
    ) -> dict[str, pd.DataFrame]:
        """Batch fetch prices using yfinance.download()."""
        yf_symbols = [self._to_yf_symbol(s) for s in symbols]
        all_data = {}
        batch_size = 50

        for i in range(0, len(yf_symbols), batch_size):
            batch_yf = yf_symbols[i : i + batch_size]
            batch_raw = symbols[i : i + batch_size]
            logger.info(f"Downloading batch {i // batch_size + 1}, {len(batch_yf)} symbols (interval={interval})")

            try:
                # For intraday intervals, use period instead of start/end
                if interval in ("1h", "15m"):
                    df = yf.download(
                        tickers=batch_yf,
                        period="60d",
                        interval=interval,
                        auto_adjust=True,
                        group_by="ticker",
                        threads=False,
                    )
                else:
                    df = yf.download(
                        tickers=batch_yf,
                        start=start_date,
                        end=end_date,
                        auto_adjust=True,
                        group_by="ticker",
                        threads=False,
                    )
                if df.empty:
                    continue

                if len(batch_yf) == 1:
                    # Single symbol: yf.download with group_by="ticker" may
                    # return MultiIndex columns in newer yfinance versions,
                    # so fall back to fetch_price_data which uses ticker.history().
                    symbol = batch_raw[0]
                    single_df = self.fetch_price_data(symbol, start_date, end_date, interval=interval)
                    if not single_df.empty:
                        all_data[symbol] = single_df
                else:
                    for j, yf_sym in enumerate(batch_yf):
                        symbol = batch_raw[j]
                        try:
                            stock_df = df[yf_sym].dropna(how="all").reset_index()
                            stock_df = stock_df.rename(columns={
                                "Date": "timestamp", "Datetime": "timestamp",
                                "Open": "open", "High": "high",
                                "Low": "low", "Close": "close", "Volume": "volume",
                            })
                            if "timestamp" in stock_df.columns:
                                stock_df["timestamp"] = pd.to_datetime(stock_df["timestamp"]).dt.tz_localize(None)
                            if not stock_df.empty:
                                cols = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in stock_df.columns]
                                all_data[symbol] = stock_df[cols]
                        except (KeyError, TypeError):
                            logger.warning(f"No data for {symbol}")
            except Exception as e:
                logger.error(f"Bulk download batch failed: {e}")

            time.sleep(1)

        logger.info(f"Bulk download complete: {len(all_data)} stocks with data")
        return all_data

    def fetch_index_data(
        self, index: str = "NIFTY50", start_date: Optional[date] = None
    ) -> pd.DataFrame:
        yf_symbol = self.NIFTY_INDICES.get(index, "^NSEI")
        start = start_date or (datetime.now() - timedelta(days=730)).date()
        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=start, auto_adjust=True)
            if df.empty:
                return pd.DataFrame()
            df = df.reset_index()
            df = df.rename(columns={
                "Date": "timestamp", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume",
            })
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
            return df[["timestamp", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            logger.error(f"Index fetch failed: {e}")
            return pd.DataFrame()

    def fetch_bulk_fundamentals(
        self, symbols: list[str], max_workers: int = 8
    ) -> dict[str, dict]:
        """Fetch fundamentals for many symbols in parallel using threads.

        Returns {symbol: fundamentals_dict}.
        """
        results: dict[str, dict] = {}
        logger.info(f"Bulk fundamentals: fetching {len(symbols)} symbols with {max_workers} threads")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_fundamentals, sym): sym
                for sym in symbols
            }
            for future in as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    logger.warning(f"Bulk fundamentals failed for {sym}: {e}")
                    results[sym] = {}

        logger.info(f"Bulk fundamentals complete: {len(results)} results")
        return results

    def fetch_stock_detail_parallel(self, symbol: str, interval: str = "1d") -> dict:
        """Fetch all detail data for a single stock in parallel.

        Returns {"price_df", "fundamentals", "earnings", "insiders", "holders", "index_df"}.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=365)

        results: dict = {}

        def _price():
            return self.fetch_price_data(symbol, start_date, end_date, interval=interval)

        def _fundamentals():
            return self.fetch_fundamentals(symbol)

        def _earnings():
            return self.fetch_earnings(symbol)

        def _insiders():
            return self.fetch_insider_transactions(symbol)

        def _holders():
            return self.fetch_institutional_holders(symbol)

        def _index():
            return self.fetch_index_data("NIFTY50")

        tasks = {
            "price_df": _price,
            "fundamentals": _fundamentals,
            "earnings": _earnings,
            "insiders": _insiders,
            "holders": _holders,
            "index_df": _index,
        }

        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_key = {
                executor.submit(fn): key for key, fn in tasks.items()
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.warning(f"Detail fetch '{key}' failed for {symbol}: {e}")
                    results[key] = {} if key != "price_df" else pd.DataFrame()

        return results

    def health_check(self) -> bool:
        try:
            ticker = yf.Ticker("RELIANCE.NS")
            info = ticker.fast_info
            return info is not None
        except Exception:
            return False
