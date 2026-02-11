"""
Dynamic NIFTY 50 Stock List Fetcher

Fetches NIFTY 50 constituents from NSE India API dynamically
instead of using hardcoded lists.

Features:
- Real-time NIFTY 50 constituents from NSE
- 24-hour cache to reduce API calls
- Automatic fallback to backup list if API fails
- Thread-safe caching
- Sector mapping fetch
"""

import requests
import logging
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from threading import Lock
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NiftyFetcher:
    """
    Fetches NIFTY 50 stock list dynamically from NSE India
    """

    # NSE API endpoints
    NSE_NIFTY50_URL = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
    NSE_BASE_URL = "https://www.nseindia.com"

    # Fallback hardcoded list (in case API fails)
    FALLBACK_NIFTY_50 = [
        'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS',
        'HINDUNILVR.NS', 'ITC.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'KOTAKBANK.NS',
        'LT.NS', 'AXISBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS', 'TITAN.NS',
        'BAJFINANCE.NS', 'HCLTECH.NS', 'WIPRO.NS', 'ULTRACEMCO.NS', 'NESTLEIND.NS',
        'SUNPHARMA.NS', 'ONGC.NS', 'NTPC.NS', 'POWERGRID.NS', 'M&M.NS',
        'TATASTEEL.NS', 'JSWSTEEL.NS', 'TECHM.NS', 'ADANIENT.NS', 'COALINDIA.NS',
        'INDUSINDBK.NS', 'BAJAJFINSV.NS', 'HINDALCO.NS', 'GRASIM.NS',
        'DIVISLAB.NS', 'DRREDDY.NS', 'CIPLA.NS', 'EICHERMOT.NS', 'HEROMOTOCO.NS',
        'BRITANNIA.NS', 'APOLLOHOSP.NS', 'BPCL.NS', 'TATACONSUM.NS', 'UPL.NS',
        'ADANIPORTS.NS', 'SHREECEM.NS', 'BAJAJ-AUTO.NS', 'SBILIFE.NS', 'HDFCLIFE.NS'
    ]

    # Sector mapping (basic categories)
    SECTOR_CATEGORIES = {
        'Energy': ['RELIANCE', 'ONGC', 'BPCL', 'NTPC', 'POWERGRID', 'COALINDIA'],
        'IT': ['TCS', 'INFY', 'HCLTECH', 'WIPRO', 'TECHM'],
        'Banking': ['HDFCBANK', 'ICICIBANK', 'SBIN', 'KOTAKBANK', 'AXISBANK', 'INDUSINDBK'],
        'Financial Services': ['BAJFINANCE', 'BAJAJFINSV', 'SBILIFE', 'HDFCLIFE'],
        'FMCG': ['HINDUNILVR', 'ITC', 'NESTLEIND', 'BRITANNIA', 'TATACONSUM'],
        'Pharma': ['SUNPHARMA', 'DIVISLAB', 'DRREDDY', 'CIPLA', 'APOLLOHOSP'],
        'Auto': ['MARUTI', 'M&M', 'EICHERMOT', 'HEROMOTOCO', 'BAJAJ-AUTO'],
        'Metals': ['TATASTEEL', 'JSWSTEEL', 'HINDALCO'],
        'Cement': ['ULTRACEMCO', 'SHREECEM', 'GRASIM'],
        'Capital Goods': ['LT', 'ADANIENT', 'ADANIPORTS'],
        'Telecom': ['BHARTIARTL'],
        'Consumer Durables': ['TITAN', 'ASIANPAINT'],
        'Chemicals': ['UPL']
    }

    def __init__(self):
        """Initialize fetcher with cache"""
        self._cache: Optional[List[str]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._sector_cache: Optional[Dict[str, str]] = None
        self._cache_ttl = timedelta(hours=24)  # Cache for 24 hours
        self._lock = Lock()

        # Session with proper headers for NSE
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if self._cache is None or self._cache_timestamp is None:
            return False
        return (datetime.now() - self._cache_timestamp) < self._cache_ttl

    def _fetch_from_nse(self) -> Optional[List[str]]:
        """
        Fetch NIFTY 50 constituents from NSE India API

        Returns:
            List of stock symbols with .NS suffix, or None if failed
        """
        try:
            # First, visit the main page to get cookies
            self.session.get(self.NSE_BASE_URL, timeout=10)

            # Now fetch the NIFTY 50 data
            response = self.session.get(self.NSE_NIFTY50_URL, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Extract stock symbols from API response
            stocks = []
            if 'data' in data:
                for item in data['data']:
                    symbol = item.get('symbol', '')
                    if symbol and symbol not in ['NIFTY 50', 'NIFTY50']:
                        # Add .NS suffix for yfinance compatibility
                        stocks.append(f"{symbol}.NS")

            if stocks:
                logger.info(f"Successfully fetched {len(stocks)} NIFTY 50 stocks from NSE API")
                return stocks
            else:
                logger.warning("NSE API returned empty stock list")
                return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch from NSE API: {e}")
            return None
        except (KeyError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse NSE API response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching from NSE: {e}")
            return None

    def _fetch_from_alternative(self) -> Optional[List[str]]:
        """
        Alternative: Fetch from Wikipedia or other sources

        Returns:
            List of stock symbols or None
        """
        try:
            # Wikipedia table for NIFTY 50 as backup
            import pandas as pd
            url = "https://en.wikipedia.org/wiki/NIFTY_50"
            tables = pd.read_html(url)

            # Find the constituents table (usually has 'Symbol' column)
            for table in tables:
                if 'Symbol' in table.columns:
                    symbols = table['Symbol'].tolist()
                    stocks = [f"{symbol}.NS" for symbol in symbols if symbol]
                    if stocks:
                        logger.info(f"Fetched {len(stocks)} stocks from Wikipedia")
                        return stocks

            return None
        except Exception as e:
            logger.warning(f"Alternative fetch method failed: {e}")
            return None

    def get_nifty50_stocks(self, force_refresh: bool = False) -> List[str]:
        """
        Get NIFTY 50 stock list (cached or fresh)

        Args:
            force_refresh: Force refresh from API even if cache is valid

        Returns:
            List of NIFTY 50 stock symbols with .NS suffix
        """
        with self._lock:
            # Return cache if valid and not forcing refresh
            if not force_refresh and self._is_cache_valid():
                logger.debug(f"Returning cached NIFTY 50 list ({len(self._cache)} stocks)")
                return self._cache.copy()

            # Try to fetch from NSE API
            logger.info("Fetching fresh NIFTY 50 list from NSE API...")
            stocks = self._fetch_from_nse()

            # Try alternative source if NSE fails
            if not stocks:
                logger.info("Trying alternative source (Wikipedia)...")
                stocks = self._fetch_from_alternative()

            # Fallback to hardcoded list if all fails
            if not stocks:
                logger.warning("All fetch methods failed, using fallback list")
                stocks = self.FALLBACK_NIFTY_50.copy()

            # Update cache
            self._cache = stocks
            self._cache_timestamp = datetime.now()

            logger.info(f"NIFTY 50 list updated: {len(stocks)} stocks")
            return stocks.copy()

    def get_sector_mapping(self) -> Dict[str, str]:
        """
        Get sector mapping for NIFTY 50 stocks

        Returns:
            Dictionary mapping ticker to sector
        """
        if self._sector_cache is not None:
            return self._sector_cache.copy()

        # Build sector mapping from categories
        mapping = {}
        for sector, symbols in self.SECTOR_CATEGORIES.items():
            for symbol in symbols:
                mapping[f"{symbol}.NS"] = sector

        # Cache it
        self._sector_cache = mapping
        return mapping.copy()

    def get_stock_info(self) -> Dict[str, Any]:
        """
        Get comprehensive stock info including count and sectors

        Returns:
            Dictionary with stocks list, count, sectors, and metadata
        """
        stocks = self.get_nifty50_stocks()
        sectors = self.get_sector_mapping()

        # Count stocks per sector
        sector_counts = {}
        for ticker in stocks:
            sector = sectors.get(ticker, 'Unknown')
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        return {
            'stocks': stocks,
            'total_count': len(stocks),
            'sectors': sectors,
            'sector_distribution': sector_counts,
            'last_updated': self._cache_timestamp.isoformat() if self._cache_timestamp else None,
            'cache_expires': (self._cache_timestamp + self._cache_ttl).isoformat() if self._cache_timestamp else None,
            'source': 'NSE API' if self._cache else 'Fallback'
        }

    def clear_cache(self):
        """Clear the cache (force refresh on next call)"""
        with self._lock:
            self._cache = None
            self._cache_timestamp = None
            self._sector_cache = None
            logger.info("NIFTY 50 cache cleared")


# Singleton instance
_nifty_fetcher = None


def get_nifty_fetcher() -> NiftyFetcher:
    """Get singleton NiftyFetcher instance"""
    global _nifty_fetcher
    if _nifty_fetcher is None:
        _nifty_fetcher = NiftyFetcher()
    return _nifty_fetcher


# Convenience functions
def get_nifty50_stocks(force_refresh: bool = False) -> List[str]:
    """Get NIFTY 50 stocks list"""
    return get_nifty_fetcher().get_nifty50_stocks(force_refresh)


def get_sector_mapping() -> Dict[str, str]:
    """Get sector mapping for NIFTY 50 stocks"""
    return get_nifty_fetcher().get_sector_mapping()


def get_stock_info() -> Dict[str, Any]:
    """Get comprehensive stock info"""
    return get_nifty_fetcher().get_stock_info()


# API endpoint helper
def refresh_nifty50_cache() -> Dict[str, Any]:
    """
    Refresh NIFTY 50 cache (can be called via API endpoint)

    Returns:
        Status and updated info
    """
    try:
        fetcher = get_nifty_fetcher()
        stocks = fetcher.get_nifty50_stocks(force_refresh=True)
        info = fetcher.get_stock_info()

        return {
            'status': 'success',
            'message': f'NIFTY 50 cache refreshed: {len(stocks)} stocks',
            'data': info
        }
    except Exception as e:
        logger.error(f"Error refreshing NIFTY 50 cache: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }
