import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, time
import time
import logging
import numpy as np
import requests
import os
import random
import pytz
from services.cache_service import get_cached_data, set_cached_data
from services.upstox_service import (
    get_upstox_historical_data, 
    get_upstox_live_data, 
    get_upstox_market_indices,
    upstox_api
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Detect cloud environment (Render) for stricter anti-rate-limit behavior
IS_RENDER = str(os.getenv('RENDER', '')).lower() in ('true', '1', 'yes')

# Prefer a browser-impersonating session on Render if curl_cffi is available
_YF_SESSION = None
try:
    if IS_RENDER:
        from curl_cffi import requests as curl_requests  # type: ignore
        _sess = curl_requests.Session(impersonate="chrome")
        _sess.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        })
        _YF_SESSION = _sess
except Exception:
    _YF_SESSION = None

# Don't set a custom session - let yfinance handle its own session management
# This fixes the "Yahoo API requires curl_cffi session" error

def _sleep_before_yf_call():
    if IS_RENDER:
        time.sleep(random.uniform(3.0, 8.0))
    else:
        time.sleep(random.uniform(0.5, 2.0))

def filter_trading_days(df):
    """
    Filter DataFrame to include only market trading days (Monday-Friday, excluding Indian holidays)
    """
    try:
        if df.empty:
            return df
        
        # Ensure we have a datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        # Filter out weekends (Saturday=5, Sunday=6)
        df = df[df.index.weekday < 5]
        
        # Basic Indian market holidays (major ones)
        # Note: This is a simplified list. In production, you'd want a more comprehensive holiday calendar
        indian_holidays_2023 = [
            '2023-01-26',  # Republic Day
            '2023-03-07',  # Holi
            '2023-03-30',  # Ram Navami
            '2023-04-04',  # Mahavir Jayanti
            '2023-04-14',  # Good Friday
            '2023-04-22',  # Eid ul Fitr
            '2023-05-01',  # May Day
            '2023-06-29',  # Eid ul Adha
            '2023-08-15',  # Independence Day
            '2023-08-31',  # Ganesh Chaturthi
            '2023-10-02',  # Gandhi Jayanti
            '2023-10-24',  # Dussehra
            '2023-11-12',  # Diwali Laxmi Pujan
            '2023-11-13',  # Diwali Balipratipada
            '2023-11-27',  # Guru Nanak Jayanti
            '2023-12-25',  # Christmas
        ]
        
        indian_holidays_2024 = [
            '2024-01-22',  # Ram Mandir Pran Pratishtha
            '2024-01-26',  # Republic Day
            '2024-03-08',  # Holi
            '2024-03-25',  # Holi (second day)
            '2024-03-29',  # Good Friday
            '2024-04-11',  # Eid ul Fitr
            '2024-04-14',  # Ambedkar Jayanti
            '2024-04-17',  # Ram Navami
            '2024-05-01',  # May Day
            '2024-06-17',  # Eid ul Adha
            '2024-08-15',  # Independence Day
            '2024-08-26',  # Janmashtami
            '2024-09-16',  # Eid Milad Un Nabi
            '2024-10-02',  # Gandhi Jayanti
            '2024-10-12',  # Dussehra
            '2024-11-01',  # Diwali
            '2024-11-15',  # Guru Nanak Jayanti
            '2024-12-25',  # Christmas
        ]
        
        all_holidays = indian_holidays_2023 + indian_holidays_2024
        holiday_dates = pd.to_datetime(all_holidays)
        
        # Filter out holidays
        df = df[~df.index.normalize().isin(holiday_dates)]
        
        logger.info(f"Filtered to {len(df)} trading days")
        return df
        
    except Exception as e:
        logger.warning(f"Error filtering trading days: {str(e)}. Returning original data.")
        return df

def format_indian_ticker(ticker_symbol):
    """
    Format ticker symbol for Indian market
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol
    
    Returns:
    str: Formatted ticker symbol with .NS or .BO suffix
    """
    # Clean the ticker symbol - remove any unwanted characters
    ticker_symbol = str(ticker_symbol).strip().upper()
    
    # Remove any $ prefix that might have been added
    if ticker_symbol.startswith('$'):
        ticker_symbol = ticker_symbol[1:]
    
    # Remove any other unwanted prefixes or characters
    ticker_symbol = ''.join(c for c in ticker_symbol if c.isalnum() or c in ['.', '^'])
    
    # Handle index symbols
    if ticker_symbol.upper() == "NIFTY":
        return "^NSEI"
    if ticker_symbol.upper() == "BANKNIFTY":
        return "^NSEBANK"
    if ticker_symbol.upper() == "SENSEX":
        return "^BSESN"
    if ticker_symbol.startswith("^"):
        return ticker_symbol
        
    # Handle regular stocks
    if ticker_symbol.endswith('.NS') or ticker_symbol.endswith('.BO'):
        return ticker_symbol
    else:
        # Default to National Stock Exchange (NSE)
        return f"{ticker_symbol}.NS"

def get_historical_data(ticker_symbol, period="1y", interval="1d"):
    """
    Fetch historical stock data for Indian market with caching
    Primary: Upstox API, Fallback: Yahoo Finance
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol (e.g., 'RELIANCE', 'TCS')
    period (str): Time period to fetch (e.g., '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
    interval (str): Data interval (e.g., '1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
    
    Returns:
    DataFrame: Historical stock data
    """
    # Create a unique cache key
    cache_key = f"hist_{ticker_symbol}_{period}_{interval}"
    cache_ttl = 600  # 10 minutes
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        # Convert back to DataFrame with correct index
        df = pd.DataFrame.from_dict(cached_data)
        if 'date' in df:
            df.set_index('date', inplace=True)
        return df
    
    # Try Upstox API first (Primary)
    try:
        if upstox_api.access_token:
            logger.info(f"Attempting to fetch data from Upstox for {ticker_symbol}")
            # Convert interval format for Upstox
            upstox_interval = convert_interval_to_upstox(interval)
            upstox_data = get_upstox_historical_data(ticker_symbol, period, upstox_interval)
            
            if len(upstox_data) > 0:
                logger.info(f"Successfully fetched data from Upstox for {ticker_symbol}")
                return upstox_data
            else:
                logger.warning(f"No data from Upstox for {ticker_symbol}, falling back to Yahoo Finance")
        else:
            logger.warning("Upstox access token not available, using Yahoo Finance")
    except Exception as e:
        logger.error(f"Error fetching from Upstox: {str(e)}, falling back to Yahoo Finance")
    
    # Fallback to Yahoo Finance
    logger.info(f"Using Yahoo Finance as fallback for {ticker_symbol}")
    return get_historical_data_yfinance(ticker_symbol, period, interval)

def convert_interval_to_upstox(interval):
    """Convert yfinance interval format to Upstox format"""
    interval_mapping = {
        '1m': '1minute',
        '5m': '5minute',
        '15m': '15minute',
        '30m': '30minute',
        '1h': '1hour',
        '1d': '1day',
        '1wk': '1week',
        '1mo': '1month'
    }
    return interval_mapping.get(interval, '1day')

def get_historical_data_yfinance(ticker_symbol, period="1y", interval="1d"):
    """
    Fetch historical stock data using Yahoo Finance (Backup method)
    """
    # Create a unique cache key for yfinance
    cache_key = f"yf_hist_{ticker_symbol}_{period}_{interval}"
    cache_ttl = 600  # 10 minutes
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        # Convert back to DataFrame with correct index
        df = pd.DataFrame.from_dict(cached_data)
        if 'date' in df:
            df.set_index('date', inplace=True)
        return df
    
    # Format ticker for Indian market
    formatted_ticker = format_indian_ticker(ticker_symbol)
    
    max_retries = 5
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}: Calling yfinance for ticker: {formatted_ticker}")
            _sleep_before_yf_call()
            ticker = yf.Ticker(formatted_ticker)
            hist_data = ticker.history(period=period, interval=interval)
            
            if len(hist_data) > 0:
                logger.info(f"Successfully fetched data. Shape: {hist_data.shape}")
                logger.info(f"Columns: {hist_data.columns.tolist()}")
                logger.info(f"Date range: {hist_data.index.min()} to {hist_data.index.max()}")
                
                # Remove rows with NaN values for all essential columns for 1d interval
                if interval == "1d":
                    hist_data = hist_data.dropna(subset=['Open', 'High', 'Low', 'Close'])
                    logger.info(f"After removing NaN rows for 1d data: {hist_data.shape}")
                
                # Store original index as a column for caching
                hist_data_for_cache = hist_data.copy()
                hist_data_for_cache['date'] = hist_data_for_cache.index.strftime('%Y-%m-%d %H:%M:%S')
                
                # Cache the result with proper date formatting
                set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), cache_ttl)
                
                # Keep the original datetime index but normalize timezone
                hist_data.index = hist_data.index.tz_localize(None) if hist_data.index.tz is not None else hist_data.index
                hist_data.index.name = 'date'
                
                # Filter to trading days only
                hist_data = filter_trading_days(hist_data)
                
                return hist_data
            
            # If we got empty data, try BSE if NSE didn't work
            if formatted_ticker.endswith('.NS'):
                bse_ticker = ticker_symbol + '.BO'
                _sleep_before_yf_call()
                ticker = yf.Ticker(bse_ticker)
                hist_data = ticker.history(period=period, interval=interval)
                
                if len(hist_data) > 0:
                    logger.info(f"Successfully fetched BSE data. Shape: {hist_data.shape}")
                    
                    # Remove rows with NaN values for all essential columns for 1d interval
                    if interval == "1d":
                        hist_data = hist_data.dropna(subset=['Open', 'High', 'Low', 'Close'])
                        logger.info(f"After removing NaN rows for 1d BSE data: {hist_data.shape}")
                    
                    # Store original index as a column for caching
                    hist_data_for_cache = hist_data.copy()
                    hist_data_for_cache['date'] = hist_data_for_cache.index.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Cache the result with proper date formatting
                    set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), cache_ttl)
                    
                    # Keep the original datetime index but normalize timezone
                    hist_data.index = hist_data.index.tz_localize(None) if hist_data.index.tz is not None else hist_data.index
                    hist_data.index.name = 'date'
                    
                    return hist_data
            
            # If we got empty data, wait and retry
            logger.warning(f"Empty data for {formatted_ticker} on attempt {attempt + 1}, retrying...")
            time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Exception on attempt {attempt + 1} for {formatted_ticker}: {str(e)}")
            # If rate limited, back off longer
            msg = str(e).lower()
            if 'too many requests' in msg or 'rate limit' in msg or '429' in msg:
                logger.warning(f"Rate limited for {formatted_ticker}, backing off...")
                time.sleep(retry_delay * 5)
            elif 'possibly delisted' in msg or 'no price data' in msg:
                logger.warning(f"Delisted error for {formatted_ticker}, trying different approach...")
                # This is likely a ticker format issue, break early to try BSE
                break
            else:
                time.sleep(retry_delay)
            continue
    
    # If all retries failed, return empty DataFrame with expected columns
    return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_ohlc_data(ticker_symbol, start_date=None, end_date=None, interval="1d"):
    """
    Fetch OHLC (Open, High, Low, Close) data for a specific date range
    Primary: Upstox API, Fallback: Yahoo Finance
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol
    start_date (str): Start date in format YYYY-MM-DD
    end_date (str): End date in format YYYY-MM-DD
    interval (str): Data interval
    
    Returns:
    DataFrame: OHLC data
    """
    try:
        logger.info(f"Fetching OHLC data for {ticker_symbol} from {start_date} to {end_date} with interval {interval}")
        
        # Set default dates if not provided
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        if not start_date:
            # Default to 1 year ago if not specified
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        # Create cache key
        cache_key = f"ohlc_{ticker_symbol}_{start_date}_{end_date}_{interval}"
        cached_data = get_cached_data(cache_key)
        
        if cached_data is not None:
            logger.info(f"Using cached OHLC data for {ticker_symbol}")
            df = pd.DataFrame.from_dict(cached_data)
            if 'date' in df:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                df.index.name = 'date'
            logger.info(f"Cached data shape: {df.shape}")
            return df
        
        # Try Upstox API first (Primary)
        try:
            if upstox_api.access_token:
                logger.info(f"Attempting to fetch OHLC data from Upstox for {ticker_symbol}")
                # Convert interval format for Upstox
                upstox_interval = convert_interval_to_upstox(interval)
                
                # Calculate period from date range for Upstox
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                days_diff = (end_dt - start_dt).days
                
                if days_diff <= 1:
                    period = "1d"
                elif days_diff <= 30:
                    period = "1mo"
                else:
                    period = "1y"
                
                upstox_data = get_upstox_historical_data(ticker_symbol, period, upstox_interval)
                
                if len(upstox_data) > 0:
                    logger.info(f"Successfully fetched OHLC data from Upstox for {ticker_symbol}")
                    
                    # Store data for caching
                    upstox_data_for_cache = upstox_data.copy()
                    upstox_data_for_cache['date'] = upstox_data_for_cache.index
                    set_cached_data(cache_key, upstox_data_for_cache.to_dict('records'), 600)
                    
                    return upstox_data
                else:
                    logger.warning(f"No OHLC data from Upstox for {ticker_symbol}, falling back to Yahoo Finance")
            else:
                logger.warning("Upstox access token not available, using Yahoo Finance for OHLC")
        except Exception as e:
            logger.error(f"Error fetching OHLC from Upstox: {str(e)}, falling back to Yahoo Finance")
        
        # Fallback to Yahoo Finance
        logger.info(f"Using Yahoo Finance as fallback for OHLC data: {ticker_symbol}")
        return get_ohlc_data_yfinance(ticker_symbol, start_date, end_date, interval)
        
    except Exception as e:
        logger.error(f"Error in get_ohlc_data: {str(e)}")
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_ohlc_data_yfinance(ticker_symbol, start_date=None, end_date=None, interval="1d"):
    """
    Fetch OHLC data using Yahoo Finance (Backup method)
    """
    # Format ticker for Indian market
    formatted_ticker = format_indian_ticker(ticker_symbol)
    logger.info(f"Formatted ticker: {formatted_ticker}")
    
    # Create cache key for yfinance
    cache_key = f"yf_ohlc_{formatted_ticker}_{start_date}_{end_date}_{interval}"
    cached_data = get_cached_data(cache_key)
    
    if cached_data is not None:
        logger.info(f"Using cached yfinance data for {formatted_ticker}")
        df = pd.DataFrame.from_dict(cached_data)
        if 'date' in df:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.index.name = 'date'
        return df
    
    max_retries = 5
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} to fetch data from yfinance")
            _sleep_before_yf_call()
            ticker = yf.Ticker(formatted_ticker)
            hist_data = ticker.history(start=start_date, end=end_date, interval=interval)
            
            if len(hist_data) > 0:
                logger.info(f"Successfully fetched OHLC data. Shape: {hist_data.shape}")
                logger.info(f"Columns: {hist_data.columns.tolist()}")
                logger.info(f"Date range: {hist_data.index.min()} to {hist_data.index.max()}")
                
                # Remove rows with NaN values for all essential columns for 1d interval
                if interval == "1d":
                    hist_data = hist_data.dropna(subset=['Open', 'High', 'Low', 'Close'])
                    logger.info(f"After removing NaN rows for 1d OHLC data: {hist_data.shape}")
                
                # Store data for caching with proper date formatting
                hist_data_for_cache = hist_data.copy()
                hist_data_for_cache['date'] = hist_data_for_cache.index.strftime('%Y-%m-%d %H:%M:%S')
                set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), 3600)  # 1 hour cache
                
                # Keep the original datetime index but normalize timezone
                hist_data.index = hist_data.index.tz_localize(None) if hist_data.index.tz is not None else hist_data.index
                hist_data.index.name = 'date'
                
                # Filter to trading days only
                hist_data = filter_trading_days(hist_data)
                
                return hist_data
            
            # If we got empty data from NSE, try BSE
            if formatted_ticker.endswith('.NS'):
                logger.info("No data from NSE, trying BSE")
                bse_ticker = ticker_symbol + '.BO'
                _sleep_before_yf_call()
                ticker = yf.Ticker(bse_ticker)
                hist_data = ticker.history(start=start_date, end=end_date, interval=interval)
                
                if len(hist_data) > 0:
                    logger.info(f"Successfully fetched BSE OHLC data. Shape: {hist_data.shape}")
                    
                    # Remove rows with NaN values for all essential columns for 1d interval
                    if interval == "1d":
                        hist_data = hist_data.dropna(subset=['Open', 'High', 'Low', 'Close'])
                        logger.info(f"After removing NaN rows for 1d BSE OHLC data: {hist_data.shape}")
                    
                    # Store data for caching with proper date formatting
                    hist_data_for_cache = hist_data.copy()
                    hist_data_for_cache['date'] = hist_data_for_cache.index.strftime('%Y-%m-%d %H:%M:%S')
                    set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), 3600)
                    
                    # Keep the original datetime index but normalize timezone
                    hist_data.index = hist_data.index.tz_localize(None) if hist_data.index.tz is not None else hist_data.index
                    hist_data.index.name = 'date'
                    
                    return hist_data
            
            logger.warning(f"No data available for attempt {attempt + 1}")
            time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Error fetching data on attempt {attempt + 1}: {str(e)}")
            msg = str(e).lower()
            if 'too many requests' in msg or 'rate limit' in msg or '429' in msg:
                time.sleep(retry_delay * 5)
            else:
                time.sleep(retry_delay)
            continue
        
    logger.error("All attempts to fetch data failed")
    return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_live_data(ticker_symbols):
    """
    Fetch the most recent (live) stock data for Indian stocks with caching
    Primary: Upstox API, Fallback: Yahoo Finance
    
    Parameters:
    ticker_symbols (str or list): Single ticker or list of tickers
    
    Returns:
    DataFrame: Latest stock data
    """
    logger.info(f"Fetching live data for ticker(s): {ticker_symbols}")
    
    if isinstance(ticker_symbols, str):
        # For single ticker, check cache
        cache_key = f"live_{ticker_symbols}"
        cache_ttl = 60  # 1 minute (shorter for live data)
        
        cached_data = get_cached_data(cache_key)
        if cached_data is not None:
            logger.info(f"Using cached data for {ticker_symbols}")
            return pd.DataFrame.from_dict(cached_data, orient='index')
    else:
        # For multiple tickers, create a list of results
        tickers_list = ticker_symbols
        results = {}
        
        for symbol in tickers_list:
            # Check cache for each ticker
            cache_key = f"live_{symbol}"
            cached_data = get_cached_data(cache_key)
            
            if cached_data is not None:
                logger.info(f"Using cached data for {symbol}")
                # Handle both single symbol and dict format
                if isinstance(cached_data, dict):
                    if symbol in cached_data:
                        results[symbol] = cached_data[symbol]
                    else:
                        # If cached data doesn't have the symbol, try to get the first available data
                        first_key = next(iter(cached_data.keys()), None)
                        if first_key:
                            results[symbol] = cached_data[first_key]
                        else:
                            logger.warning(f"Cached data for {symbol} is empty")
                else:
                    results[symbol] = cached_data
            else:
                # Skip fetching fresh data to avoid recursion - will be handled in main flow
                logger.info(f"No cached data for {symbol}, will fetch with main flow")
                continue
        
        if results:
            return pd.DataFrame.from_dict(results, orient='index')
    
    # If no cached data or for single ticker, proceed with fetching fresh data
    if isinstance(ticker_symbols, str):
        ticker_symbols = [ticker_symbols]

    # Try Upstox API first (Primary)
    try:
        if upstox_api.access_token:
            logger.info(f"Attempting to fetch live data from Upstox for {ticker_symbols}")
            upstox_data = get_upstox_live_data(ticker_symbols)
            
            if upstox_data:
                logger.info(f"Successfully fetched live data from Upstox")
                # Convert to DataFrame format
                result_df = pd.DataFrame.from_dict(upstox_data, orient='index')
                
                # Cache the results
                for symbol in ticker_symbols:
                    if symbol in upstox_data:
                        cache_key = f"live_{symbol}"
                        set_cached_data(cache_key, {symbol: upstox_data[symbol]}, 60)
                
                return result_df
            else:
                logger.warning("No live data from Upstox, falling back to Yahoo Finance")
        else:
            logger.warning("Upstox access token not available, using Yahoo Finance for live data")
    except Exception as e:
        logger.error(f"Error fetching live data from Upstox: {str(e)}, falling back to Yahoo Finance")
    
    # Fallback to Yahoo Finance
    logger.info(f"Using Yahoo Finance as fallback for live data: {ticker_symbols}")
    return get_live_data_yfinance(ticker_symbols)

def get_live_data_yfinance(ticker_symbols):
    """
    Fetch live data using Yahoo Finance (Backup method)
    """
    # Format tickers for Indian market
    formatted_tickers = []
    for symbol in ticker_symbols:
        formatted_ticker = format_indian_ticker(symbol)
        logger.info(f"Formatted ticker {symbol} to {formatted_ticker}")
        formatted_tickers.append(formatted_ticker)

    live_data = {}
    for symbol in formatted_tickers:
        max_retries = 3
        retry_delay = 2  # increased from 1 to 2 seconds
        success = False
        error_msg = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1} for {symbol}")
                _sleep_before_yf_call()
                ticker = yf.Ticker(symbol)
                
                # First try to get info
                try:
                    info = ticker.info
                except Exception as e:
                    logger.warning(f"Failed to get info for {symbol}: {str(e)}")
                    info = {}

                # Then try to get latest price separately
                try:
                    hist = ticker.history(period='1d')
                    if not hist.empty:
                        latest_price = hist['Close'].iloc[-1]
                    else:
                        raise Exception("No price data available")
                except Exception as e:
                    logger.warning(f"Failed to get price for {symbol}: {str(e)}")
                    raise

                live_data[symbol] = {
                    'price': latest_price,
                    'marketCap': info.get('marketCap', 'N/A'),
                    'volume': info.get('volume', 'N/A'),
                    'dayHigh': info.get('dayHigh', 'N/A'),
                    'dayLow': info.get('dayLow', 'N/A'),
                    'open': info.get('open', 'N/A'),
                    'previousClose': info.get('previousClose', 'N/A'),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                success = True
                logger.info(f"Successfully fetched data for {symbol}")
                break
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error fetching data for {symbol} (attempt {attempt + 1}): {error_msg}")
                
                # If there was an exception and it's NSE, try BSE
                if symbol.endswith('.NS') and attempt == 0:
                    try:
                        logger.info(f"Trying BSE fallback for {symbol}")
                        bse_symbol = symbol.replace('.NS', '.BO')
                        _sleep_before_yf_call()
                        ticker = yf.Ticker(bse_symbol)
                        
                        # Get info
                        try:
                            info = ticker.info
                        except Exception as e:
                            logger.warning(f"Failed to get BSE info for {bse_symbol}: {str(e)}")
                            info = {}

                        # Get latest price
                        hist = ticker.history(period='1d')
                        if not hist.empty:
                            latest_price = hist['Close'].iloc[-1]
                        else:
                            raise Exception("No BSE price data available")
                        
                        live_data[symbol] = {
                            'price': latest_price,
                            'marketCap': info.get('marketCap', 'N/A'),
                            'volume': info.get('volume', 'N/A'),
                            'dayHigh': info.get('dayHigh', 'N/A'),
                            'dayLow': info.get('dayLow', 'N/A'),
                            'open': info.get('open', 'N/A'),
                            'previousClose': info.get('previousClose', 'N/A'),
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source': 'BSE'  # Indicate data is from BSE
                        }
                        success = True
                        logger.info(f"Successfully fetched BSE data for {symbol}")
                        break
                    except Exception as bse_error:
                        logger.error(f"BSE fallback failed for {symbol}: {str(bse_error)}")
                        error_msg = f"NSE Error: {error_msg}, BSE Error: {str(bse_error)}"
                
                # Wait before retrying
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
                
        if not success:
            live_data[symbol] = {
                'error': f"Failed to retrieve data after {max_retries} attempts: {error_msg}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    # Create a mapping from original symbols to formatted symbols
    original_to_formatted = {}
    for i, original in enumerate(ticker_symbols):
        if i < len(formatted_tickers):
            original_to_formatted[original] = formatted_tickers[i]
    
    # Rebuild the live_data dict with original symbol names
    original_live_data = {}
    for original_symbol, formatted_symbol in original_to_formatted.items():
        if formatted_symbol in live_data:
            original_live_data[original_symbol] = live_data[formatted_symbol]
            # Cache data with original symbol names
            cache_key = f"live_{original_symbol}"
            set_cached_data(cache_key, {original_symbol: live_data[formatted_symbol]}, 60)  # 1 minute cache
            logger.info(f"Cached data for {original_symbol}")
        else:
            # If no data found for formatted symbol, create error entry
            logger.warning(f"No data found for {original_symbol} (formatted as {formatted_symbol})")
            original_live_data[original_symbol] = {
                'error': f"No data available for {original_symbol}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    # Ensure we have data for all requested symbols
    for original_symbol in ticker_symbols:
        if original_symbol not in original_live_data:
            logger.warning(f"Missing data for {original_symbol}, adding error entry")
            original_live_data[original_symbol] = {
                'error': f"Failed to fetch data for {original_symbol}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    result_df = pd.DataFrame.from_dict(original_live_data, orient='index')
    return result_df

def is_market_hours():
    """
    Check if it's currently Indian market hours (9:15 AM - 3:30 PM IST, Monday-Friday)
    """
    try:
        # Get current time in IST
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        # Check if it's a weekday (Monday=0, Sunday=6)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check if it's within market hours (9:15 AM - 3:30 PM IST)
        market_start = time(9, 15)
        market_end = time(15, 30)
        
        return market_start <= now.time() <= market_end
        
    except Exception as e:
        logger.warning(f"Error checking market hours: {str(e)}")
        # Default to True if we can't determine
        return True

def warm_market_indices_cache():
    """
    Pre-fetch market indices data to warm the cache during low-traffic periods
    This function can be called by a scheduler or during app startup
    """
    try:
        logger.info("Starting market indices cache warming")
        
        # Check if cache is already warm
        cache_key = "market_indices"
        cached_data = get_cached_data(cache_key)
        
        if cached_data:
            logger.info("Market indices cache is already warm")
            return True
        
        # Pre-fetch data
        logger.info("Pre-fetching market indices data for cache warming")
        indices_data = get_market_indices_yfinance_optimized()
        
        if indices_data and len(indices_data) > 0:
            # Cache with longer TTL for pre-fetched data
            cache_ttl = 3600  # 1 hour for pre-fetched data
            set_cached_data(cache_key, indices_data, cache_ttl)
            logger.info(f"Successfully warmed market indices cache with {len(indices_data)} indices")
            return True
        else:
            logger.warning("Failed to warm market indices cache - no data received")
            return False
            
    except Exception as e:
        logger.error(f"Error warming market indices cache: {str(e)}")
        return False

def get_market_indices():
    """
    Get major Indian market indices data with smart caching and circuit breaker
    Primary: Upstox API, Fallback: Yahoo Finance
    
    Returns:
    dict: Market indices data
    """
    cache_key = "market_indices"
    
    # Smart cache TTL based on market hours
    if is_market_hours():
        cache_ttl = 300  # 5 minutes during market hours (more frequent updates)
    else:
        cache_ttl = 1800  # 30 minutes outside market hours (less frequent updates)
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data:
        logger.info("Returning cached market indices data")
        return cached_data
    
    # Circuit breaker: Check if Upstox has failed recently
    upstox_failure_key = "upstox_market_indices_failure"
    upstox_failure_data = get_cached_data(upstox_failure_key)
    
    # Try Upstox API first (Primary) - unless it failed recently
    if not upstox_failure_data:
        try:
            if upstox_api.access_token:
                logger.info("Attempting to fetch market indices from Upstox")
                upstox_indices = get_upstox_market_indices()
                
                if upstox_indices and len(upstox_indices) > 0:
                    logger.info("Successfully fetched market indices from Upstox")
                    # Cache the result
                    set_cached_data(cache_key, upstox_indices, cache_ttl)
                    return upstox_indices
                else:
                    logger.warning("No market indices data from Upstox, falling back to Yahoo Finance")
            else:
                logger.warning("Upstox access token not available, using Yahoo Finance for market indices")
        except Exception as e:
            logger.error(f"Error fetching market indices from Upstox: {str(e)}, falling back to Yahoo Finance")
            # Mark Upstox as failed for 15 minutes
            set_cached_data(upstox_failure_key, {"failed_at": datetime.now().isoformat()}, 900)
    else:
        logger.info("Skipping Upstox due to recent failures, using Yahoo Finance")
    
    # Fallback to Yahoo Finance - optimized version
    logger.info("Using Yahoo Finance for market indices")
    return get_market_indices_yfinance_optimized()

def get_market_indices_yfinance_optimized():
    """
    Get market indices data using Yahoo Finance with optimized bulk data fetching
    No unnecessary delays, optimized period, and better error handling
    """
    # Define the indices to fetch - expanded list for better horizontal scrolling
    indices = [
        "^NSEI",      # NIFTY 50
        "^BSESN",     # BSE SENSEX
        "^NSEBANK",   # NIFTY BANK
        "^CNXIT",     # NIFTY IT
        "^CNXFMCG",   # NIFTY FMCG
        "^CNXPHARMA", # NIFTY PHARMA
        "^CNXAUTO",   # NIFTY AUTO
        "^CNXMETAL",  # NIFTY METAL
        "^CNXREALTY", # NIFTY REALTY
        "^CNXENERGY"  # NIFTY ENERGY
    ]

    # Define index names mapping
    index_names = {
        "^NSEI": "NIFTY 50",
        "^BSESN": "BSE SENSEX",
        "^NSEBANK": "NIFTY BANK",
        "^CNXIT": "NIFTY IT",
        "^CNXFMCG": "NIFTY FMCG",
        "^CNXPHARMA": "NIFTY PHARMA",
        "^CNXAUTO": "NIFTY AUTO",
        "^CNXMETAL": "NIFTY METAL",
        "^CNXREALTY": "NIFTY REALTY",
        "^CNXENERGY": "NIFTY ENERGY"
    }
    
    result = {}
    start_time = time.time()
    
    try:
        logger.info(f"Fetching data for {len(indices)} market indices in optimized bulk call")
        
        # Use yfinance's download function to get data for all indices in a single call
        # Fetch 7 days of data to provide chart history
        data = yf.download(
            tickers=indices,
            period="7d",  # 7 days for chart data
            group_by="ticker",
            auto_adjust=True,
            progress=False
        )
        
        end_time = time.time()
        logger.info(f"Bulk indices data fetch completed in {end_time - start_time:.2f} seconds")
        
        # If bulk response is empty, fall back to individual calls
        try:
            is_empty_bulk = not isinstance(data, dict) or all((k not in data or data[k].empty) for k in indices)
        except Exception:
            is_empty_bulk = True
        if is_empty_bulk:
            logger.warning("Bulk indices download returned empty; using optimized individual fallback")
            return get_market_indices_individual_optimized()

        # Process the bulk data for each index
        for index_symbol in indices:
            try:
                if index_symbol in data and not data[index_symbol].empty:
                    # Get the Close prices and drop NaN values
                    close_prices = data[index_symbol]['Close'].dropna()

                    if len(close_prices) >= 2:
                        # Use the last valid price and second-to-last valid price
                        latest_price = close_prices.iloc[-1]
                        prev_close = close_prices.iloc[-2]

                        # Calculate change and percent change
                        change = latest_price - prev_close
                        pct_change = (change / prev_close * 100) if prev_close and prev_close != 0 else 0

                        # Prepare chart data (dates and prices)
                        chart_data = {
                            'dates': [d.strftime('%Y-%m-%d') for d in close_prices.index],
                            'prices': [round(float(p), 2) for p in close_prices.values]
                        }

                        result[index_symbol] = {
                            'name': index_names.get(index_symbol, index_symbol),
                            'price': round(latest_price, 2),
                            'change': round(change, 2),
                            'percentChange': round(pct_change, 2),
                            'chartData': chart_data,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source': 'Yahoo Finance (Bulk)'
                        }
                        logger.info(f"Processed index {index_symbol}: {round(pct_change, 2)}%")
                    elif len(close_prices) == 1:
                        # If we only have 1 valid day, use it as is without change data
                        latest_price = close_prices.iloc[-1]
                        result[index_symbol] = {
                            'name': index_names.get(index_symbol, index_symbol),
                            'price': round(latest_price, 2),
                            'change': 0,
                            'percentChange': 0,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'note': 'Insufficient data for change calculation',
                            'source': 'Yahoo Finance (Bulk)'
                        }
                        logger.warning(f"Only one valid price found for index {index_symbol}")
                    else:
                        # No valid prices found
                        result[index_symbol] = {
                            'name': index_names.get(index_symbol, index_symbol),
                            'error': 'No valid price data available',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source': 'Yahoo Finance (Bulk)'
                        }
                        logger.warning(f"No valid price data found for index {index_symbol}")
                else:
                    result[index_symbol] = {
                        'name': index_names.get(index_symbol, index_symbol),
                        'error': 'No data available',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source': 'Yahoo Finance (Bulk)'
                    }
                    logger.warning(f"No data available for index {index_symbol}")
            except Exception as e:
                result[index_symbol] = {
                    'name': index_names.get(index_symbol, index_symbol),
                    'error': str(e),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'Yahoo Finance (Bulk)'
                }
                logger.error(f"Error processing index {index_symbol}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error in bulk indices fetch: {str(e)}")
        # If bulk fetch fails, try optimized individual fetches as fallback
        return get_market_indices_individual_optimized()
    
    # Log metadata but don't include it in the response
    fetch_time_seconds = round(time.time() - start_time, 2)
    logger.info(f"Successfully fetched market indices data in {fetch_time_seconds} seconds")
    logger.info(f"Source: Yahoo Finance (Optimized Bulk), Indices count: {len(indices)}")
    
    # Cache before returning
    cache_key = "market_indices"
    set_cached_data(cache_key, result, 1800)  # 30 minutes cache
    return result

def get_market_indices_individual_fallback():
    """
    Fallback method to get market indices data using individual API calls
    Used when the bulk fetch fails
    """
    logger.warning("Using individual API calls as fallback for market indices")
    indices = ["^NSEI", "^BSESN", "^CNXIT", "^NSEBANK"]  # NIFTY 50, SENSEX, NIFTY IT, NIFTY BANK
    
    # Define index names mapping
    index_names = {
        "^NSEI": "NIFTY 50",
        "^BSESN": "BSE SENSEX",
        "^CNXIT": "NIFTY IT",
        "^NSEBANK": "NIFTY BANK"
    }
    
    start_time = time.time()
    result = {}
    
    for index_symbol in indices:
        try:
            _sleep_before_yf_call()
            index = yf.Ticker(index_symbol, session=_YF_SESSION)
            hist = index.history(period="1d")
            if len(hist) > 0:
                latest_price = hist['Close'].iloc[-1]
                
                # Try to get previous close from info or estimate it
                try:
                    prev_close = index.info.get('previousClose')
                    if not prev_close and len(hist) > 1:
                        prev_close = hist['Close'].iloc[-2]
                    elif not prev_close:
                        prev_close = latest_price * 0.99  # Estimate as 99% of current price
                except:
                    prev_close = latest_price * 0.99  # Fallback estimate
                
                # Calculate change and percent change
                change = latest_price - prev_close if prev_close else 0
                pct_change = (change / prev_close * 100) if prev_close else 0
                
                result[index_symbol] = {
                    'name': index_names.get(index_symbol, index_symbol),
                    'price': round(latest_price, 2),
                    'change': round(change, 2),
                    'percentChange': round(pct_change, 2),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                result[index_symbol] = {
                    'name': index_names.get(index_symbol, index_symbol),
                    'error': 'No data available',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        except Exception as e:
            result[index_symbol] = {
                'name': index_names.get(index_symbol, index_symbol),
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    # Log metadata but don't include it in the response
    fetch_time_seconds = round(time.time() - start_time, 2)
    logger.info(f"Successfully fetched market indices data in {fetch_time_seconds} seconds (individual fallback)")
    logger.info(f"Source: Yahoo Finance (Individual Fallback), Indices count: {len(indices)}")
    
    # Cache before returning
    cache_key = "market_indices"
    set_cached_data(cache_key, result, 300)  # 5 minutes cache
    return result

def get_market_indices_individual_optimized():
    """
    Optimized fallback method to get market indices data using individual API calls
    No unnecessary delays and improved data accuracy
    """
    logger.warning("Using optimized individual API calls as fallback for market indices")
    # Define the indices to fetch - expanded list for better horizontal scrolling
    indices = [
        "^NSEI",      # NIFTY 50
        "^BSESN",     # BSE SENSEX
        "^NSEBANK",   # NIFTY BANK
        "^CNXIT",     # NIFTY IT
        "^CNXFMCG",   # NIFTY FMCG
        "^CNXPHARMA", # NIFTY PHARMA
        "^CNXAUTO",   # NIFTY AUTO
        "^CNXMETAL",  # NIFTY METAL
        "^CNXREALTY", # NIFTY REALTY
        "^CNXENERGY"  # NIFTY ENERGY
    ]

    # Define index names mapping
    index_names = {
        "^NSEI": "NIFTY 50",
        "^BSESN": "BSE SENSEX",
        "^NSEBANK": "NIFTY BANK",
        "^CNXIT": "NIFTY IT",
        "^CNXFMCG": "NIFTY FMCG",
        "^CNXPHARMA": "NIFTY PHARMA",
        "^CNXAUTO": "NIFTY AUTO",
        "^CNXMETAL": "NIFTY METAL",
        "^CNXREALTY": "NIFTY REALTY",
        "^CNXENERGY": "NIFTY ENERGY"
    }
    
    start_time = time.time()
    result = {}
    
    for index_symbol in indices:
        try:
            # No sleep delay for market indices - they're less rate-limited
            # Don't pass custom session - let yfinance handle its own session
            index = yf.Ticker(index_symbol)

            # Get 7 days of data for chart
            hist = index.history(period="7d")

            if len(hist) > 0:
                close_prices = hist['Close'].dropna()
                latest_price = close_prices.iloc[-1]

                # Always try to get real previous close data
                prev_close = None
                if len(close_prices) >= 2:
                    # Use actual previous day's close if available
                    prev_close = close_prices.iloc[-2]
                else:
                    # Try to get from ticker info
                    try:
                        prev_close = index.info.get('previousClose')
                    except:
                        pass

                # Prepare chart data
                chart_data = {
                    'dates': [d.strftime('%Y-%m-%d') for d in close_prices.index],
                    'prices': [round(float(p), 2) for p in close_prices.values]
                }

                # Only calculate change if we have real previous close data
                if prev_close and prev_close > 0:
                    change = latest_price - prev_close
                    pct_change = (change / prev_close * 100)

                    result[index_symbol] = {
                        'name': index_names.get(index_symbol, index_symbol),
                        'price': round(latest_price, 2),
                        'change': round(change, 2),
                        'percentChange': round(pct_change, 2),
                        'chartData': chart_data,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source': 'Yahoo Finance (Individual)'
                    }
                    logger.info(f"Processed index {index_symbol}: {round(pct_change, 2)}%")
                else:
                    # No valid previous close data
                    result[index_symbol] = {
                        'name': index_names.get(index_symbol, index_symbol),
                        'price': round(latest_price, 2),
                        'change': 0,
                        'percentChange': 0,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'note': 'Previous close data unavailable',
                        'source': 'Yahoo Finance (Individual)'
                    }
                    logger.warning(f"No valid previous close data for index {index_symbol}")
            else:
                result[index_symbol] = {
                    'name': index_names.get(index_symbol, index_symbol),
                    'error': 'No data available',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'Yahoo Finance (Individual)'
                }
        except Exception as e:
            result[index_symbol] = {
                'name': index_names.get(index_symbol, index_symbol),
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'Yahoo Finance (Individual)'
            }
            logger.error(f"Error processing index {index_symbol}: {str(e)}")
    
    # Log metadata but don't include it in the response
    fetch_time_seconds = round(time.time() - start_time, 2)
    logger.info(f"Successfully fetched market indices data in {fetch_time_seconds} seconds (individual optimized fallback)")
    logger.info(f"Source: Yahoo Finance (Individual Optimized Fallback), Indices count: {len(indices)}")
    
    # Cache before returning
    cache_key = "market_indices"
    set_cached_data(cache_key, result, 1800)  # 30 minutes cache
    return result

def validate_ticker(ticker_symbol):
    """
    Check if a ticker symbol is valid for Indian market
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol to validate
    
    Returns:
    bool: True if valid, False otherwise
    """
    # Remove any existing suffixes
    if ticker_symbol.endswith('.NS') or ticker_symbol.endswith('.BO'):
        base_ticker = ticker_symbol.split('.')[0]
    else:
        base_ticker = ticker_symbol
    
    # Well-known Indian tickers
    well_known_tickers = [
        'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'HINDUNILVR',
        'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT', 'AXISBANK', 'MARUTI', 'ASIANPAINT',
        'TATAMOTORS', 'WIPRO', 'BAJFINANCE', 'HCLTECH', 'SUNPHARMA', 'ULTRACEMCO'
    ]
    
    # Check if it's a well-known ticker
    if base_ticker in well_known_tickers:
        return True
    
    # Try with NSE suffix
    nse_ticker = f"{base_ticker}.NS"
    
    max_retries = 2
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            _sleep_before_yf_call()
            ticker = yf.Ticker(nse_ticker)
            
            # First check: Try to get history data
            hist = ticker.history(period="1d")
            if len(hist) > 0:
                return True
                
            # Second check: Try to access info
            info = ticker.info
            if info and len(info) > 0:
                # Check for common fields that should exist
                return any(key in info for key in ['regularMarketPrice', 'currentPrice', 'symbol', 'shortName'])
                
            # If we got here but didn't return True, try BSE
            bse_ticker = f"{base_ticker}.BO"
            _sleep_before_yf_call()
            ticker = yf.Ticker(bse_ticker)
            
            hist = ticker.history(period="1d")
            if len(hist) > 0:
                return True
                
            info = ticker.info
            if info and len(info) > 0:
                return any(key in info for key in ['regularMarketPrice', 'currentPrice', 'symbol', 'shortName'])
                
            # If we still didn't return True, wait and retry
            time.sleep(retry_delay)
            
        except Exception as e:
            # If there was an exception, wait and retry
            time.sleep(retry_delay)
            continue
    
    return False

def get_top_gainers_losers():
    """
    Get top gainers and losers in the Indian market for the day with caching
    Uses Yahoo Finance's bulk data fetching to get data for multiple stocks in a single call
    
    Returns:
    dict: Top gainers and losers data
    """
    cache_key = "gainers_losers"
    cache_ttl = 900  # 15 minutes (as per requirement)
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data:
        logger.info("Returning cached top gainers and losers data")
        return cached_data
    
    # Use a curated list of key Indian stocks
    key_stocks = [
        'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS', 
        'SBIN.NS', 'HINDUNILVR.NS', 'BHARTIARTL.NS', 'ITC.NS', 'LT.NS', 
        'AXISBANK.NS', 'MARUTI.NS', 'ASIANPAINT.NS', 'TATAMOTORS.NS',
        'WIPRO.NS', 'BAJFINANCE.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 
        'TITAN.NS', 'NTPC.NS', 'ONGC.NS', 'ADANIENT.NS'
    ]
    
    try:
        logger.info(f"Fetching data for {len(key_stocks)} stocks in a single bulk call")
        start_time = time.time()
        
        # Use yfinance's download function to get data for all stocks in a single call
        # This is much more efficient than making individual calls for each stock
        _sleep_before_yf_call()
        data = yf.download(
            tickers=key_stocks,
            period="5d",  # Get 5 days to ensure we have valid data for 1d interval
            group_by="ticker",
            auto_adjust=True,
            progress=False
        )
        
        end_time = time.time()
        logger.info(f"Bulk data fetch completed in {end_time - start_time:.2f} seconds")
        
        stock_changes = []
        
        # Process the bulk data
        for stock in key_stocks:
            try:
                if stock in data and not data[stock].empty:
                    # Get the Close prices and drop NaN values
                    close_prices = data[stock]['Close'].dropna()
                    
                    if len(close_prices) >= 2:
                        # Use the last valid price and second-to-last valid price
                        current_price = close_prices.iloc[-1]
                        prev_close = close_prices.iloc[-2]
                        
                        # Calculate actual change and percent change
                        change = current_price - prev_close
                        pct_change = (change / prev_close * 100) if prev_close != 0 else 0
                    elif len(close_prices) == 1:
                        # If we only have 1 valid price, use 0 change
                        current_price = close_prices.iloc[-1]
                        change = 0
                        pct_change = 0
                    else:
                        # No valid prices found, skip this stock
                        logger.warning(f"No valid price data for {stock}")
                        continue
                    
                    # Use simple name extraction
                    company_name = stock.replace('.NS', '')
                    
                    stock_changes.append({
                        'symbol': company_name,
                        'name': company_name,
                        'price': round(current_price, 2),
                        'change': round(change, 2),
                        'percentChange': round(pct_change, 2)
                    })
                    logger.info(f"Processed {stock}: {round(pct_change, 2)}%")
                else:
                    logger.warning(f"Insufficient data for {stock}")
            except Exception as e:
                logger.warning(f"Error processing {stock}: {str(e)}")
                continue
        
        if len(stock_changes) >= 5:  # We need at least 5 stocks for meaningful results
            # Sort by percent change for gainers (descending)
            gainers_list = sorted(stock_changes, key=lambda x: x['percentChange'], reverse=True)
            
            # Sort by percent change for losers (ascending)
            losers_list = sorted(stock_changes, key=lambda x: x['percentChange'])
            
            # Get top 5 gainers and losers
            gainers = gainers_list[:5] if len(gainers_list) >= 5 else gainers_list
            losers = losers_list[:5] if len(losers_list) >= 5 else losers_list
            
            result = {
                'gainers': gainers,
                'losers': losers,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'Yahoo Finance (Bulk Data)',
                'total_stocks_analyzed': len(stock_changes),
                'fetch_time_seconds': round(end_time - start_time, 2)
            }
            
            # Cache before returning
            set_cached_data(cache_key, result, cache_ttl)
            logger.info(f"Successfully cached top gainers and losers data from {len(stock_changes)} stocks")
            return result
        else:
            logger.error(f"Insufficient data: only {len(stock_changes)} stocks could be analyzed")
            # Fall back to the backup method with a different set of stocks
            return get_top_gainers_losers_backup()
            
    except Exception as e:
        logger.error(f"Error in primary method for top gainers/losers: {str(e)}")
        # Fall back to the backup method
        return get_top_gainers_losers_backup()

def get_top_gainers_losers_backup():
    """
    Backup method to get top gainers and losers using Yahoo Finance
    Uses a different set of stocks as a fallback with bulk data fetching
    
    Returns:
    dict: Top gainers and losers data
    """
    logger.info("Using backup method for top gainers and losers with bulk data fetching")
    
    # Alternative list of stocks to try
    backup_stocks = [
        'HDFC.NS', 'ONGC.NS', 'POWERGRID.NS', 'NTPC.NS', 'ULTRACEMCO.NS',
        'BAJAJFINSV.NS', 'TECHM.NS', 'DRREDDY.NS', 'NESTLEIND.NS', 'COALINDIA.NS',
        'ADANIPORTS.NS', 'GRASIM.NS', 'HEROMOTOCO.NS', 'TATACONSUM.NS', 'BPCL.NS'
    ]
    
    try:
        logger.info(f"Fetching backup data for {len(backup_stocks)} stocks in a single bulk call")
        start_time = time.time()
        
        # Use yfinance's download function for bulk fetching
        _sleep_before_yf_call()
        data = yf.download(
            tickers=backup_stocks,
            period="5d",  # Get 5 days to ensure we have valid data for 1d interval
            group_by="ticker",
            auto_adjust=True,
            progress=False
        )
        
        end_time = time.time()
        logger.info(f"Backup bulk data fetch completed in {end_time - start_time:.2f} seconds")
        
        stock_changes = []
        
        # Process the bulk data
        for stock in backup_stocks:
            try:
                if stock in data and not data[stock].empty:
                    # Get the Close prices and drop NaN values
                    close_prices = data[stock]['Close'].dropna()
                    
                    if len(close_prices) >= 2:
                        # Use actual price data and calculate proper change
                        current_price = close_prices.iloc[-1]
                        prev_close = close_prices.iloc[-2]
                        change = current_price - prev_close
                        pct_change = (change / prev_close * 100) if prev_close != 0 else 0
                    elif len(close_prices) == 1:
                        # If we only have 1 valid price, use 0 change
                        current_price = close_prices.iloc[-1]
                        change = 0
                        pct_change = 0
                    else:
                        # No valid prices found, skip this stock
                        logger.warning(f"No valid price data for backup stock {stock}")
                        continue
                    
                    stock_changes.append({
                        'symbol': stock.replace('.NS', ''),
                        'name': stock.replace('.NS', ''),
                        'price': round(current_price, 2),
                        'change': round(change, 2),
                        'percentChange': round(pct_change, 2)
                    })
                    logger.info(f"Processed backup stock {stock}: {round(pct_change, 2)}%")
                else:
                    logger.warning(f"No data for backup stock {stock}")
            except Exception as e:
                logger.warning(f"Error processing backup stock {stock}: {str(e)}")
                continue
    
        # If we still don't have enough data, generate some mock data
        if len(stock_changes) < 5:
            logger.warning("Insufficient real data, adding mock data")
            mock_stocks = [
                {'symbol': 'MOCKREL', 'name': 'Mock Reliance', 'price': 2500.0, 'change': 25.0, 'percentChange': 1.0},
                {'symbol': 'MOCKTCS', 'name': 'Mock TCS', 'price': 3500.0, 'change': -35.0, 'percentChange': -1.0},
                {'symbol': 'MOCKHDFC', 'name': 'Mock HDFC', 'price': 1500.0, 'change': 15.0, 'percentChange': 1.0},
                {'symbol': 'MOCKINFY', 'name': 'Mock Infosys', 'price': 1400.0, 'change': -14.0, 'percentChange': -1.0},
                {'symbol': 'MOCKICICI', 'name': 'Mock ICICI', 'price': 900.0, 'change': 9.0, 'percentChange': 1.0},
                {'symbol': 'MOCKSBIN', 'name': 'Mock SBI', 'price': 600.0, 'change': -6.0, 'percentChange': -1.0},
                {'symbol': 'MOCKHUL', 'name': 'Mock HUL', 'price': 2200.0, 'change': 22.0, 'percentChange': 1.0},
                {'symbol': 'MOCKBAJAJ', 'name': 'Mock Bajaj', 'price': 7000.0, 'change': -70.0, 'percentChange': -1.0},
                {'symbol': 'MOCKITC', 'name': 'Mock ITC', 'price': 400.0, 'change': 4.0, 'percentChange': 1.0},
                {'symbol': 'MOCKLNT', 'name': 'Mock L&T', 'price': 2000.0, 'change': -20.0, 'percentChange': -1.0}
            ]
            stock_changes.extend(mock_stocks)
        
        # Sort by percent change for gainers (descending)
        gainers_list = sorted(stock_changes, key=lambda x: x['percentChange'], reverse=True)
        
        # Sort by percent change for losers (ascending)
        losers_list = sorted(stock_changes, key=lambda x: x['percentChange'])
        
        # Get top 5 gainers and losers
        gainers = gainers_list[:5] if len(gainers_list) >= 5 else gainers_list
        losers = losers_list[:5] if len(losers_list) >= 5 else losers_list
        
        result = {
            'gainers': gainers,
            'losers': losers,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'Yahoo Finance (Backup - Bulk Data)',
            'total_stocks_analyzed': len(stock_changes),
            'contains_mock_data': len(stock_changes) < 5,
            'fetch_time_seconds': round(end_time - start_time, 2)
        }
        
        # Cache for a shorter time when using backup
        set_cached_data("gainers_losers", result, 600)  # 10 minutes
        logger.info(f"Backup method completed with {len(stock_changes)} stocks")
        return result
        
    except Exception as e:
        logger.error(f"Error in backup method for top gainers/losers: {str(e)}")
        # Return mock data as last resort
        return get_mock_gainers_losers()

def get_mock_gainers_losers():
    """
    Generate mock data for gainers and losers as a last resort
    when all other methods fail
    
    Returns:
    dict: Mock gainers and losers data
    """
    logger.warning("Generating mock data for gainers and losers")
    
    mock_gainers = [
        {'symbol': 'MOCKREL', 'name': 'Mock Reliance', 'price': 2500.0, 'change': 25.0, 'percentChange': 1.0},
        {'symbol': 'MOCKHDFC', 'name': 'Mock HDFC', 'price': 1500.0, 'change': 15.0, 'percentChange': 1.0},
        {'symbol': 'MOCKICICI', 'name': 'Mock ICICI', 'price': 900.0, 'change': 9.0, 'percentChange': 1.0},
        {'symbol': 'MOCKHUL', 'name': 'Mock HUL', 'price': 2200.0, 'change': 22.0, 'percentChange': 1.0},
        {'symbol': 'MOCKITC', 'name': 'Mock ITC', 'price': 400.0, 'change': 4.0, 'percentChange': 1.0}
    ]
    
    mock_losers = [
        {'symbol': 'MOCKTCS', 'name': 'Mock TCS', 'price': 3500.0, 'change': -35.0, 'percentChange': -1.0},
        {'symbol': 'MOCKINFY', 'name': 'Mock Infosys', 'price': 1400.0, 'change': -14.0, 'percentChange': -1.0},
        {'symbol': 'MOCKSBIN', 'name': 'Mock SBI', 'price': 600.0, 'change': -6.0, 'percentChange': -1.0},
        {'symbol': 'MOCKBAJAJ', 'name': 'Mock Bajaj', 'price': 7000.0, 'change': -70.0, 'percentChange': -1.0},
        {'symbol': 'MOCKLNT', 'name': 'Mock L&T', 'price': 2000.0, 'change': -20.0, 'percentChange': -1.0}
    ]
    
    result = {
        'gainers': mock_gainers,
        'losers': mock_losers,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'Mock Data (Last Resort)',
        'total_stocks_analyzed': 10,
        'contains_mock_data': True
    }
    
    # Cache for a very short time
    set_cached_data("gainers_losers", result, 300)  # 5 minutes
    return result 

def get_stock_fundamentals(ticker_symbol):
    """
    Fetch fundamental data including balance sheet and financial ratios for Indian stocks
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol (e.g., 'RELIANCE', 'TCS')
    
    Returns:
    dict: Comprehensive fundamental data including ratios and balance sheet
    """
    cache_key = f"fundamentals_{ticker_symbol}"
    cache_ttl = 3600  # 1 hour cache for fundamentals data
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data:
        logger.info(f"Returning cached fundamentals data for {ticker_symbol}")
        return cached_data
    
    # Format ticker for Indian market
    formatted_ticker = format_indian_ticker(ticker_symbol)
    logger.info(f"Fetching fundamentals for {formatted_ticker}")
    
    try:
        _sleep_before_yf_call()
        ticker = yf.Ticker(formatted_ticker)
        
        # Get company info
        info = ticker.info
        
        # Get financial statements
        try:
            balance_sheet = ticker.balance_sheet
            income_stmt = ticker.income_stmt
            cash_flow = ticker.cash_flow
            
            # Convert to dict and handle NaN values
            balance_sheet_dict = balance_sheet.fillna(0).to_dict() if not balance_sheet.empty else {}
            income_stmt_dict = income_stmt.fillna(0).to_dict() if not income_stmt.empty else {}
            cash_flow_dict = cash_flow.fillna(0).to_dict() if not cash_flow.empty else {}
            
        except Exception as e:
            logger.warning(f"Could not fetch financial statements for {ticker_symbol}: {str(e)}")
            balance_sheet_dict = {}
            income_stmt_dict = {}
            cash_flow_dict = {}
        
        # Extract key metrics with fallbacks
        def safe_get(dictionary, key, default=0):
            value = dictionary.get(key, default) if dictionary else default
            # Handle NaN values
            if value is None or (isinstance(value, float) and (value != value or value == float('inf') or value == float('-inf'))):
                return default
            return value
        
        # Current stock metrics
        current_price = safe_get(info, 'currentPrice', safe_get(info, 'regularMarketPrice', 0))
        market_cap = safe_get(info, 'marketCap', 0)
        
        # Valuation ratios
        pe_ratio = safe_get(info, 'trailingPE', safe_get(info, 'forwardPE', 0))
        pb_ratio = safe_get(info, 'priceToBook', 0)
        ps_ratio = safe_get(info, 'priceToSalesTrailing12Months', 0)
        ev_ebitda = safe_get(info, 'enterpriseToEbitda', 0)
        
        # Balance sheet data (using most recent year) - Extract first before calculations
        latest_bs_date = None
        total_assets = 0
        total_liabilities = 0
        shareholders_equity = 0
        current_assets = 0
        current_liabilities = 0
        cash_and_equivalents = 0
        total_debt = 0
        
        if balance_sheet_dict:
            # Get the most recent date (first column)
            latest_bs_date = next(iter(balance_sheet_dict.keys()), None)
            if latest_bs_date:
                bs_data = balance_sheet_dict[latest_bs_date]
                total_assets = bs_data.get('Total Assets', 0)
                current_assets = bs_data.get('Current Assets', 0)
                current_liabilities = bs_data.get('Current Liabilities', 0)
                shareholders_equity = bs_data.get('Stockholders Equity', bs_data.get('Total Stockholder Equity', 0))
                cash_and_equivalents = bs_data.get('Cash And Cash Equivalents', 0)
                total_debt = bs_data.get('Total Debt', bs_data.get('Net Debt', 0))
                total_liabilities = total_assets - shareholders_equity if total_assets and shareholders_equity else 0

        # Profitability ratios
        roe = safe_get(info, 'returnOnEquity', 0) * 100 if safe_get(info, 'returnOnEquity') else 0
        roa = safe_get(info, 'returnOnAssets', 0) * 100 if safe_get(info, 'returnOnAssets') else 0
        
        # Calculate ROE and ROA manually if not available from info
        if not roe and income_stmt_dict:
            # ROE = Net Income / Shareholders Equity
            latest_income_date = next(iter(income_stmt_dict.keys()), None)
            if latest_income_date and shareholders_equity and shareholders_equity != 0:
                net_income = income_stmt_dict[latest_income_date].get('Net Income', 0)
                if net_income:
                    roe = (net_income / shareholders_equity) * 100
        
        if not roa and income_stmt_dict:
            # ROA = Net Income / Total Assets
            latest_income_date = next(iter(income_stmt_dict.keys()), None)
            if latest_income_date and total_assets and total_assets != 0:
                net_income = income_stmt_dict[latest_income_date].get('Net Income', 0)
                if net_income:
                    roa = (net_income / total_assets) * 100
        profit_margin = safe_get(info, 'profitMargins', 0) * 100 if safe_get(info, 'profitMargins') else 0
        gross_margin = safe_get(info, 'grossMargins', 0) * 100 if safe_get(info, 'grossMargins') else 0
        
        # Financial health ratios - calculate manually if not available from info
        current_ratio = safe_get(info, 'currentRatio', 0)
        if not current_ratio and current_assets and current_liabilities and current_liabilities != 0:
            current_ratio = current_assets / current_liabilities
        
        quick_ratio = safe_get(info, 'quickRatio', 0)
        if not quick_ratio and current_assets and current_liabilities and current_liabilities != 0:
            # Quick ratio = (Current Assets - Inventory) / Current Liabilities
            # Approximating by using 80% of current assets (assuming 20% is inventory)
            quick_ratio = (current_assets * 0.8) / current_liabilities
        
        debt_to_equity = safe_get(info, 'debtToEquity', 0)
        if not debt_to_equity and total_debt and shareholders_equity and shareholders_equity != 0:
            debt_to_equity = (total_debt / shareholders_equity) * 100
        
        # Calculate interest coverage ratio manually if not available
        interest_coverage = safe_get(info, 'interestCoverage', 0)
        if not interest_coverage and income_stmt_dict:
            latest_income_date = next(iter(income_stmt_dict.keys()), None)
            if latest_income_date:
                ebit = income_stmt_dict[latest_income_date].get('EBIT', 0)
                interest_expense = income_stmt_dict[latest_income_date].get('Interest Expense', 0)
                if ebit and interest_expense and interest_expense != 0:
                    interest_coverage = ebit / abs(interest_expense)  # Interest expense is usually negative
        
        # Market performance
        fifty_two_week_high = safe_get(info, 'fiftyTwoWeekHigh', current_price * 1.2)
        fifty_two_week_low = safe_get(info, 'fiftyTwoWeekLow', current_price * 0.8)
        dividend_yield = safe_get(info, 'dividendYield', 0) * 100 if safe_get(info, 'dividendYield') else 0
        
        # Calculate derived metrics
        working_capital = current_assets - current_liabilities
        book_value_per_share = shareholders_equity / safe_get(info, 'sharesOutstanding', 1) if shareholders_equity and safe_get(info, 'sharesOutstanding') else 0
        
        # Build the comprehensive response
        result = {
            'symbol': ticker_symbol,
            'company_name': safe_get(info, 'longName', ticker_symbol),
            'sector': safe_get(info, 'sector', 'N/A'),
            'industry': safe_get(info, 'industry', 'N/A'),
            'current_price': current_price,
            'market_cap': market_cap,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            
            # Valuation ratios
            'valuation_ratios': {
                'pe_ratio': pe_ratio,
                'pb_ratio': pb_ratio,
                'ps_ratio': ps_ratio,
                'ev_ebitda': ev_ebitda
            },
            
            # Profitability ratios
            'profitability_ratios': {
                'roe': roe,
                'roa': roa,
                'roic': roe * 0.85,  # Estimated ROIC
                'gross_margin': gross_margin,
                'profit_margin': profit_margin
            },
            
            # Financial health ratios
            'financial_health': {
                'current_ratio': current_ratio,
                'quick_ratio': quick_ratio,
                'debt_to_equity': debt_to_equity,
                'interest_coverage': interest_coverage
            },
            
            # Market performance
            'market_performance': {
                'fifty_two_week_high': fifty_two_week_high,
                'fifty_two_week_low': fifty_two_week_low,
                'dividend_yield': dividend_yield,
                'beta': safe_get(info, 'beta', 1.0)
            },
            
            # Balance sheet summary (amounts in crores for Indian stocks)
            'balance_sheet': {
                'total_assets': total_assets / 10000000 if total_assets else 0,  # Convert to crores
                'current_assets': current_assets / 10000000 if current_assets else 0,
                'cash_and_equivalents': cash_and_equivalents / 10000000 if cash_and_equivalents else 0,
                'fixed_assets': (total_assets - current_assets) / 10000000 if total_assets and current_assets else 0,
                'total_liabilities': total_liabilities / 10000000 if total_liabilities else 0,
                'current_liabilities': current_liabilities / 10000000 if current_liabilities else 0,
                'long_term_debt': (total_debt - (current_liabilities * 0.3)) / 10000000 if total_debt and current_liabilities else 0,
                'shareholders_equity': shareholders_equity / 10000000 if shareholders_equity else 0,
                'working_capital': working_capital / 10000000 if working_capital else 0,
                'book_value_per_share': book_value_per_share
            },
            
            # Additional metrics
            'key_metrics': {
                'revenue_ttm': safe_get(info, 'totalRevenue', 0) / 10000000,  # In crores
                'net_income_ttm': safe_get(info, 'netIncomeToCommon', 0) / 10000000,  # In crores
                'earnings_per_share': safe_get(info, 'trailingEps', 0),
                'dividend_per_share': safe_get(info, 'dividendRate', 0),
                'shares_outstanding': safe_get(info, 'sharesOutstanding', 0) / 10000000,  # In crores
                'float_shares': safe_get(info, 'floatShares', 0) / 10000000,  # In crores
                'employees': safe_get(info, 'fullTimeEmployees', 0)
            }
        }
        
        # Cache the result
        set_cached_data(cache_key, result, cache_ttl)
        logger.info(f"Successfully fetched and cached fundamentals for {ticker_symbol}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {ticker_symbol}: {str(e)}")
        # Return a basic error response
        return {
            'symbol': ticker_symbol,
            'error': f"Unable to fetch fundamental data: {str(e)}",
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'valuation_ratios': {'pe_ratio': 0, 'pb_ratio': 0, 'ps_ratio': 0, 'ev_ebitda': 0},
            'profitability_ratios': {'roe': 0, 'roa': 0, 'roic': 0, 'gross_margin': 0, 'profit_margin': 0},
            'financial_health': {'current_ratio': 0, 'quick_ratio': 0, 'debt_to_equity': 0, 'interest_coverage': 0},
            'market_performance': {'fifty_two_week_high': 0, 'fifty_two_week_low': 0, 'dividend_yield': 0, 'beta': 1.0},
            'balance_sheet': {
                'total_assets': 0, 'current_assets': 0, 'cash_and_equivalents': 0, 'fixed_assets': 0,
                'total_liabilities': 0, 'current_liabilities': 0, 'long_term_debt': 0, 'shareholders_equity': 0,
                'working_capital': 0, 'book_value_per_share': 0
            },
            'key_metrics': {
                'revenue_ttm': 0, 'net_income_ttm': 0, 'earnings_per_share': 0, 'dividend_per_share': 0,
                'shares_outstanding': 0, 'float_shares': 0, 'employees': 0
            }
        }