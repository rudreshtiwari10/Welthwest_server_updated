"""
NSE Symbol Loader
Fetches the complete NSE equity list (~2000+ stocks) from NSE's public CSV.
Builds a lookup dict: uppercase_name_or_symbol → ticker.NS

Refreshes every 7 days; falls back to a bundled minimal list if fetch fails.
"""

import os
import json
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Local cache file path
_CACHE_FILE = os.path.join(os.path.dirname(__file__), '_nse_symbol_cache.json')
_CACHE_MAX_AGE = 7 * 24 * 3600  # 7 days

# Populated once at first call, then reused in-process
_symbol_map: Optional[Dict[str, str]] = None

# Minimal hardcoded fallback (used if NSE fetch fails and no cache exists)
_FALLBACK_MAP: Dict[str, str] = {
    # NIFTY 50
    'RELIANCE': 'RELIANCE.NS', 'TCS': 'TCS.NS', 'INFY': 'INFY.NS',
    'HDFCBANK': 'HDFCBANK.NS', 'ICICIBANK': 'ICICIBANK.NS',
    'SBIN': 'SBIN.NS', 'ITC': 'ITC.NS', 'WIPRO': 'WIPRO.NS',
    'TATAMOTORS': 'TATAMOTORS.NS', 'BHARTIAIRTEL': 'BHARTIAIRTEL.NS',
    'HINDUNILVR': 'HINDUNILVR.NS', 'MARUTI': 'MARUTI.NS',
    'TATASTEEL': 'TATASTEEL.NS', 'BAJFINANCE': 'BAJFINANCE.NS',
    'KOTAKBANK': 'KOTAKBANK.NS', 'HCLTECH': 'HCLTECH.NS',
    'AXISBANK': 'AXISBANK.NS', 'LT': 'LT.NS',
    'ASIANPAINT': 'ASIANPAINT.NS', 'SUNPHARMA': 'SUNPHARMA.NS',
    'TITAN': 'TITAN.NS', 'NTPC': 'NTPC.NS', 'POWERGRID': 'POWERGRID.NS',
    'ONGC': 'ONGC.NS', 'COALINDIA': 'COALINDIA.NS',
    'BAJAJFINSV': 'BAJAJFINSV.NS', 'ADANIPORTS': 'ADANIPORTS.NS',
    'ULTRACEMCO': 'ULTRACEMCO.NS', 'DRREDDY': 'DRREDDY.NS',
    'HEROMOTOCO': 'HEROMOTOCO.NS', 'GRASIM': 'GRASIM.NS',
    'BRITANNIA': 'BRITANNIA.NS', 'CIPLA': 'CIPLA.NS',
    'EICHERMOT': 'EICHERMOT.NS', 'INDUSINDBK': 'INDUSINDBK.NS',
    'HINDALCO': 'HINDALCO.NS', 'JSWSTEEL': 'JSWSTEEL.NS',
    'TECHM': 'TECHM.NS', 'TATACONSUM': 'TATACONSUM.NS',
    'BPCL': 'BPCL.NS', 'APOLLOHOSP': 'APOLLOHOSP.NS',
    'ADANIENT': 'ADANIENT.NS', 'HDFCLIFE': 'HDFCLIFE.NS',
    'SBILIFE': 'SBILIFE.NS', 'TRENT': 'TRENT.NS',
    'SHRIRAMFIN': 'SHRIRAMFIN.NS', 'BEL': 'BEL.NS',
    'TORNTPHARM': 'TORNTPHARM.NS', 'NESTLEIND': 'NESTLEIND.NS',
    # Popular outside NIFTY 50
    'RVNL': 'RVNL.NS', 'MRF': 'MRF.NS',
    'IRFC': 'IRFC.NS', 'IRCTC': 'IRCTC.NS',
    'SAIL': 'SAIL.NS', 'BHEL': 'BHEL.NS',
    'PNB': 'PNB.NS', 'BANKBARODA': 'BANKBARODA.NS',
    'HAL': 'HAL.NS', 'GAIL': 'GAIL.NS',
    'NHPC': 'NHPC.NS', 'SJVN': 'SJVN.NS',
    'RECLTD': 'RECLTD.NS', 'PFC': 'PFC.NS',
    'ZOMATO': 'ZOMATO.NS', 'PAYTM': 'PAYTM.NS',
    'DMART': 'DMART.NS', 'NAUKRI': 'NAUKRI.NS',
    'DLF': 'DLF.NS', 'HAVELLS': 'HAVELLS.NS',
    'LUPIN': 'LUPIN.NS', 'BIOCON': 'BIOCON.NS',
    'MPHASIS': 'MPHASIS.NS', 'PERSISTENT': 'PERSISTENT.NS',
    'COFORGE': 'COFORGE.NS', 'LTIM': 'LTIM.NS',
    'DIXON': 'DIXON.NS', 'POLYCAB': 'POLYCAB.NS',
    'TVSMOTOR': 'TVSMOTOR.NS', 'CEAT': 'CEAT.NS',
    'BALKRISIND': 'BALKRISIND.NS', 'APOLLOTYRE': 'APOLLOTYRE.NS',
    'CHOLAFIN': 'CHOLAFIN.NS', 'MUTHOOTFIN': 'MUTHOOTFIN.NS',
    'SBICARD': 'SBICARD.NS', 'IDFCFIRSTB': 'IDFCFIRSTB.NS',
    'VEDL': 'VEDL.NS', 'NMDC': 'NMDC.NS',
    'TATAPOWER': 'TATAPOWER.NS', 'JSWENERGY': 'JSWENERGY.NS',
    'GODREJCP': 'GODREJCP.NS', 'MARICO': 'MARICO.NS',
    'DABUR': 'DABUR.NS', 'PIDILITIND': 'PIDILITIND.NS',
    'SIEMENS': 'SIEMENS.NS', 'ABB': 'ABB.NS',
    'CGPOWER': 'CGPOWER.NS', 'THERMAX': 'THERMAX.NS',
    'VOLTAS': 'VOLTAS.NS', 'INDHOTEL': 'INDHOTEL.NS',
    'RAILTEL': 'RAILTEL.NS', 'RITES': 'RITES.NS', 'IRCON': 'IRCON.NS',
    # Aliases
    'INFOSYS': 'INFY.NS', 'AIRTEL': 'BHARTIAIRTEL.NS',
    'HUL': 'HINDUNILVR.NS', 'HDFC': 'HDFCBANK.NS',
    'EICHER': 'EICHERMOT.NS', 'TVS': 'TVSMOTOR.NS',
    'HERO': 'HEROMOTOCO.NS', 'RAILVIKAS': 'RVNL.NS',
}


def _fetch_from_nse() -> Optional[Dict[str, str]]:
    """
    Download NSE's public EQUITY_L.csv and build symbol map.
    Returns {SYMBOL_UPPER: 'SYMBOL.NS', COMPANY_NAME_UPPER: 'SYMBOL.NS', ...}
    or None on failure.
    """
    try:
        import requests
        import io
        import pandas as pd

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.nseindia.com/',
        }

        url = 'https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv'
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        df = pd.read_csv(io.StringIO(resp.text))
        # Columns: SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, ...
        symbol_col = 'SYMBOL'
        name_col = 'NAME OF COMPANY'

        if symbol_col not in df.columns:
            logger.warning(f"NSE CSV missing expected columns: {df.columns.tolist()}")
            return None

        result: Dict[str, str] = {}
        for _, row in df.iterrows():
            sym = str(row[symbol_col]).strip().upper()
            if not sym or sym == 'NAN':
                continue
            ticker_ns = f"{sym}.NS"
            result[sym] = ticker_ns  # e.g. RVNL → RVNL.NS

            if name_col in df.columns:
                name = str(row[name_col]).strip().upper()
                if name and name != 'NAN':
                    result[name] = ticker_ns  # e.g. RAIL VIKAS NIGAM LIMITED → RVNL.NS
                    # Also add short name (first word) if ≥ 4 chars to avoid false matches
                    first_word = name.split()[0] if name.split() else ''
                    if len(first_word) >= 4 and first_word not in result:
                        result[first_word] = ticker_ns

        logger.info(f"NSE symbol map loaded: {len(result)} entries from {len(df)} stocks")
        return result

    except Exception as e:
        logger.warning(f"Failed to fetch NSE equity list: {e}")
        return None


def _load_cache() -> Optional[Dict[str, str]]:
    """Load symbol map from local cache file if fresh enough."""
    try:
        if not os.path.exists(_CACHE_FILE):
            return None
        age = time.time() - os.path.getmtime(_CACHE_FILE)
        if age > _CACHE_MAX_AGE:
            logger.info("NSE symbol cache is stale, will refresh")
            return None
        with open(_CACHE_FILE, 'r') as f:
            data = json.load(f)
        logger.info(f"Loaded NSE symbol cache: {len(data)} entries")
        return data
    except Exception as e:
        logger.warning(f"Failed to load NSE symbol cache: {e}")
        return None


def _save_cache(data: Dict[str, str]) -> None:
    """Persist symbol map to local cache file."""
    try:
        with open(_CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Failed to save NSE symbol cache: {e}")


def get_nse_symbol_map() -> Dict[str, str]:
    """
    Returns the full NSE symbol map (symbol/name → ticker.NS).
    Loads from in-memory cache → disk cache → live NSE fetch → fallback dict.
    Thread-safe for read (write race is benign — worst case fetches twice).
    """
    global _symbol_map
    if _symbol_map is not None:
        return _symbol_map

    # Try disk cache first (avoids network call on every restart)
    cached = _load_cache()
    if cached:
        _symbol_map = {**_FALLBACK_MAP, **cached}
        return _symbol_map

    # Fetch live from NSE
    live = _fetch_from_nse()
    if live:
        _save_cache(live)
        _symbol_map = {**_FALLBACK_MAP, **live}
        return _symbol_map

    # Nothing worked — use fallback
    logger.warning("Using hardcoded fallback NSE symbol map")
    _symbol_map = _FALLBACK_MAP.copy()
    return _symbol_map


def refresh_nse_symbols() -> int:
    """Force-refresh the NSE symbol map. Returns number of entries loaded."""
    global _symbol_map
    _symbol_map = None
    if os.path.exists(_CACHE_FILE):
        try:
            os.remove(_CACHE_FILE)
        except Exception:
            pass
    return len(get_nse_symbol_map())


def lookup_symbol(name_or_ticker: str) -> Optional[str]:
    """
    Look up a company name or NSE ticker, returns 'SYMBOL.NS' or None.
    Case-insensitive.
    """
    key = name_or_ticker.strip().upper()
    return get_nse_symbol_map().get(key)
