import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
from services.cache_service import get_cached_data, set_cached_data

def format_indian_ticker(ticker_symbol):
    """
    Format ticker symbol for Indian market
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol
    
    Returns:
    str: Formatted ticker symbol with .NS or .BO suffix
    """
    if ticker_symbol.endswith('.NS') or ticker_symbol.endswith('.BO'):
        return ticker_symbol
    else:
        # Default to National Stock Exchange (NSE)
        return f"{ticker_symbol}.NS"

def get_historical_data(ticker_symbol, period="1y", interval="1d"):
    """
    Fetch historical stock data for Indian market with caching
    
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
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol
    start_date (str): Start date in format YYYY-MM-DD
    end_date (str): End date in format YYYY-MM-DD
    interval (str): Data interval
    
    Returns:
    DataFrame: OHLC data
    """
    # Format ticker for Indian market
    formatted_ticker = format_indian_ticker(ticker_symbol)
    
    # Set default dates if not provided
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    if not start_date:
        # Default to 1 year ago if not specified
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(formatted_ticker)
            hist_data = ticker.history(start=start_date, end=end_date, interval=interval)
            
            if len(hist_data) > 0:
                # Convert dates to string format for JSON serialization
                hist_data.index = hist_data.index.strftime('%Y-%m-%d %H:%M:%S')
                return hist_data
            
            # If we got empty data from NSE, try BSE
            if formatted_ticker.endswith('.NS'):
                bse_ticker = ticker_symbol + '.BO'
                ticker = yf.Ticker(bse_ticker)
                hist_data = ticker.history(start=start_date, end=end_date, interval=interval)
                
                if len(hist_data) > 0:
                    # Convert dates to string format for JSON serialization
                    hist_data.index = hist_data.index.strftime('%Y-%m-%d %H:%M:%S')
                    return hist_data
            
            # If we still got empty data, wait and retry
            time.sleep(retry_delay)
        except Exception as e:
            # If there was an exception, wait and retry
            time.sleep(retry_delay)
            continue
    
    # If all retries failed, return empty DataFrame with expected columns
    return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_live_data(ticker_symbols):
    """
    Fetch the most recent (live) stock data for Indian stocks with caching
    
    Parameters:
    ticker_symbols (str or list): Single ticker or list of tickers
    
    Returns:
    DataFrame: Latest stock data
    """
    if isinstance(ticker_symbols, str):
        # For single ticker, check cache
        cache_key = f"live_{ticker_symbols}"
        cache_ttl = 60  # 1 minute (shorter for live data)
        
        cached_data = get_cached_data(cache_key)
        if cached_data is not None:
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
                # Use cached data
                results[symbol] = cached_data[symbol]
            else:
                # Fetch fresh data for this ticker
                fresh_data = get_live_data(symbol)
                if not fresh_data.empty:
                    results[symbol] = fresh_data.loc[symbol].to_dict()
        
        if results:
            return pd.DataFrame.from_dict(results, orient='index')
    
    # If no cached data or for single ticker, proceed with fetching fresh data
    if isinstance(ticker_symbols, str):
        ticker_symbols = [ticker_symbols]

    # Format tickers for Indian market
    formatted_tickers = []
    for symbol in ticker_symbols:
        formatted_tickers.append(format_indian_ticker(symbol))

    live_data = {}
    for symbol in formatted_tickers:
        max_retries = 3
        retry_delay = 1  # seconds
        success = False
        
        for attempt in range(max_retries):
            try:
                ticker = yf.Ticker(symbol)
                # Get the latest info
                info = ticker.info
                # Get the latest price
                latest_price = ticker.history(period='1d')['Close'].iloc[-1]

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
                break
            except Exception as e:
                # If there was an exception and it's NSE, try BSE
                if symbol.endswith('.NS') and attempt == 0:
                    try:
                        bse_symbol = symbol.replace('.NS', '.BO')
                        ticker = yf.Ticker(bse_symbol)
                        info = ticker.info
                        latest_price = ticker.history(period='1d')['Close'].iloc[-1]
                        
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
                        break
                    except:
                        pass
                
                # If still not successful, wait and retry
                time.sleep(retry_delay)
                continue
                
        if not success:
            live_data[symbol] = {
                'error': "Failed to retrieve data after multiple attempts",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

    result_df = pd.DataFrame.from_dict(live_data, orient='index')
    
    # Before returning, cache the result for single ticker
    if isinstance(ticker_symbols, str) and ticker_symbols in live_data:
        ticker_symbol = ticker_symbols
        cache_key = f"live_{ticker_symbol}"
        set_cached_data(cache_key, live_data, cache_ttl)
    
    return result_df

def get_market_indices():
    """
    Get major Indian market indices data with caching
    
    Returns:
    dict: Market indices data
    """
    cache_key = "market_indices"
    cache_ttl = 300  # 5 minutes
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data:
        return cached_data
    
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
    set_cached_data(cache_key, result, cache_ttl)
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