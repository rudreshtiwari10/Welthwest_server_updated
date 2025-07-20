import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from services.cache_service import get_cached_data, set_cached_data
from services.upstox_service import (
    get_upstox_historical_data, 
    get_upstox_live_data, 
    get_upstox_market_indices,
    upstox_api
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_indian_ticker(ticker_symbol):
    """
    Format ticker symbol for Indian market
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol
    
    Returns:
    str: Formatted ticker symbol with .NS or .BO suffix
    """
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
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(formatted_ticker)
            hist_data = ticker.history(period=period, interval=interval)
            
            if len(hist_data) > 0:
                # Store original index as a column for caching
                hist_data_for_cache = hist_data.copy()
                hist_data_for_cache['date'] = hist_data_for_cache.index
                
                # Cache the result
                set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), cache_ttl)
                
                # Convert dates to string format for JSON serialization
                hist_data.index = hist_data.index.strftime('%Y-%m-%d %H:%M:%S')
                return hist_data
            
            # If we got empty data, try BSE if NSE didn't work
            if formatted_ticker.endswith('.NS'):
                bse_ticker = ticker_symbol + '.BO'
                ticker = yf.Ticker(bse_ticker)
                hist_data = ticker.history(period=period, interval=interval)
                
                if len(hist_data) > 0:
                    # Store original index as a column for caching
                    hist_data_for_cache = hist_data.copy()
                    hist_data_for_cache['date'] = hist_data_for_cache.index
                    
                    # Cache the result
                    set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), cache_ttl)
                    
                    # Convert dates to string format for JSON serialization
                    hist_data.index = hist_data.index.strftime('%Y-%m-%d %H:%M:%S')
                    return hist_data
            
            # If we got empty data, wait and retry
            time.sleep(retry_delay)
        except Exception as e:
            # If there was an exception, wait and retry
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
            logger.info(f"Using cached data for {ticker_symbol}")
            df = pd.DataFrame.from_dict(cached_data)
            if 'date' in df:
                df.set_index('date', inplace=True)
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
            df.set_index('date', inplace=True)
        return df
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} to fetch data from yfinance")
            ticker = yf.Ticker(formatted_ticker)
            hist_data = ticker.history(start=start_date, end=end_date, interval=interval)
            
            if len(hist_data) > 0:
                logger.info(f"Successfully fetched data. Shape: {hist_data.shape}")
                logger.info(f"Columns: {hist_data.columns.tolist()}")
                logger.info(f"Date range: {hist_data.index.min()} to {hist_data.index.max()}")
                
                # Store data for caching
                hist_data_for_cache = hist_data.copy()
                hist_data_for_cache['date'] = hist_data_for_cache.index
                set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), 600)  # 10 minutes cache
                
                # Convert dates to string format for JSON serialization
                hist_data.index = hist_data.index.strftime('%Y-%m-%d %H:%M:%S')
                return hist_data
            
            # If we got empty data from NSE, try BSE
            if formatted_ticker.endswith('.NS'):
                logger.info("No data from NSE, trying BSE")
                bse_ticker = ticker_symbol + '.BO'
                ticker = yf.Ticker(bse_ticker)
                hist_data = ticker.history(start=start_date, end=end_date, interval=interval)
                
                if len(hist_data) > 0:
                    logger.info(f"Successfully fetched BSE data. Shape: {hist_data.shape}")
                    
                    # Store data for caching
                    hist_data_for_cache = hist_data.copy()
                    hist_data_for_cache['date'] = hist_data_for_cache.index
                    set_cached_data(cache_key, hist_data_for_cache.to_dict('records'), 600)
                    
                    # Convert dates to string format for JSON serialization
                    hist_data.index = hist_data.index.strftime('%Y-%m-%d %H:%M:%S')
                    return hist_data
            
            logger.warning(f"No data available for attempt {attempt + 1}")
            time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Error fetching data on attempt {attempt + 1}: {str(e)}")
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

def get_market_indices():
    """
    Get major Indian market indices data with caching
    Primary: Upstox API, Fallback: Yahoo Finance
    
    Returns:
    dict: Market indices data
    """
    cache_key = "market_indices"
    cache_ttl = 300  # 5 minutes
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data:
        return cached_data
    
    # Try Upstox API first (Primary)
    try:
        if upstox_api.access_token:
            logger.info("Attempting to fetch market indices from Upstox")
            upstox_indices = get_upstox_market_indices()
            
            if upstox_indices:
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
    
    # Fallback to Yahoo Finance
    logger.info("Using Yahoo Finance as fallback for market indices")
    return get_market_indices_yfinance()

def get_market_indices_yfinance():
    """
    Get market indices data using Yahoo Finance (Backup method)
    """
    indices = ["^NSEI", "^BSESN", "^CNXIT", "^NSEBANK"]  # NIFTY 50, SENSEX, NIFTY IT, NIFTY BANK
    
    result = {}
    for index_symbol in indices:
        try:
            index = yf.Ticker(index_symbol)
            hist = index.history(period="1d")
            if len(hist) > 0:
                latest_price = hist['Close'].iloc[-1]
                prev_close = index.info.get('previousClose', hist['Close'].iloc[-2] if len(hist) > 1 else None)
                
                # Calculate change and percent change
                change = latest_price - prev_close if prev_close else 0
                pct_change = (change / prev_close * 100) if prev_close else 0
                
                result[index_symbol] = {
                    'name': index.info.get('shortName', index_symbol),
                    'price': latest_price,
                    'change': change,
                    'percentChange': pct_change,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        except Exception as e:
            result[index_symbol] = {
                'name': index_symbol,
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
    
    # Cache before returning
    cache_key = "market_indices"
    set_cached_data(cache_key, result, 300)
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
    
    Returns:
    dict: Top gainers and losers data
    """
    cache_key = "gainers_losers"
    cache_ttl = 300  # 5 minutes
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data:
        return cached_data
    
    # List of major Indian stocks to check
    major_stocks = [
        'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS', 
        'SBIN.NS', 'HINDUNILVR.NS', 'BHARTIARTL.NS', 'ITC.NS', 'KOTAKBANK.NS',
        'LT.NS', 'AXISBANK.NS', 'MARUTI.NS', 'ASIANPAINT.NS', 'TATAMOTORS.NS',
        'WIPRO.NS', 'BAJFINANCE.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 'ULTRACEMCO.NS',
        'TITAN.NS', 'BAJAJFINSV.NS', 'NTPC.NS', 'POWERGRID.NS', 'ONGC.NS',
        'GRASIM.NS', 'ADANIPORTS.NS', 'JSWSTEEL.NS', 'TECHM.NS', 'DRREDDY.NS'
    ]
    
    stock_changes = []
    
    for stock in major_stocks:
        try:
            ticker = yf.Ticker(stock)
            hist = ticker.history(period="2d")
            
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current_price = hist['Close'].iloc[-1]
                change = current_price - prev_close
                pct_change = (change / prev_close * 100)
                
                stock_changes.append({
                    'symbol': stock,
                    'name': ticker.info.get('shortName', stock),
                    'price': current_price,
                    'change': change,
                    'percentChange': pct_change
                })
        except Exception:
            # Skip stocks with errors
            continue
    
    # Sort by percent change
    stock_changes.sort(key=lambda x: x['percentChange'], reverse=True)
    
    # Get top 5 gainers and losers
    gainers = stock_changes[:5] if len(stock_changes) >= 5 else stock_changes
    
    # Sort in reverse for losers
    stock_changes.sort(key=lambda x: x['percentChange'])
    losers = stock_changes[:5] if len(stock_changes) >= 5 else stock_changes
    
    result = {
        'gainers': gainers,
        'losers': losers,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Cache before returning
    set_cached_data(cache_key, result, cache_ttl)
    return result 