import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_config
from services.cache_service import get_cached_data, set_cached_data
from services.auto_auth_service import UpstoxAutoAuth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UpstoxAPI:
    def __init__(self):
        self.config = get_config()
        self.api_key = self.config.UPSTOX_API_KEY
        self.api_secret = self.config.UPSTOX_API_SECRET
        self.redirect_uri = self.config.UPSTOX_REDIRECT_URI
        self.base_url = "https://api.upstox.com/v2"
        self.access_token = None
        self.token_file = "upstox_token.txt"
        self.auto_auth = UpstoxAutoAuth(self)
        
        # Try to load existing token
        self._load_token()
        
    def _load_token(self):
        """Load access token from file if it exists"""
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, 'r') as f:
                    token = f.read().strip()
                    if token:
                        self.access_token = token
                        logger.info("Loaded existing Upstox access token")
        except Exception as e:
            logger.error(f"Error loading token: {str(e)}")
    
    def _save_token(self):
        """Save access token to file"""
        try:
            if self.access_token:
                with open(self.token_file, 'w') as f:
                    f.write(self.access_token)
                logger.info("Saved Upstox access token")
        except Exception as e:
            logger.error(f"Error saving token: {str(e)}")
            
    def save_credentials(self, username, password, pin):
        """Save user credentials for automated login"""
        return self.auto_auth.save_credentials(username, password, pin)
        
    def get_login_url(self):
        """Generate login URL for Upstox OAuth"""
        login_url = f"https://api.upstox.com/v2/login/authorization/dialog"
        params = {
            'response_type': 'code',
            'client_id': self.api_key,
            'redirect_uri': self.redirect_uri,
            'state': 'sample_state'
        }
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{login_url}?{query_string}"
    
    def get_access_token(self, authorization_code):
        """Exchange authorization code for access token"""
        url = f"{self.base_url}/login/authorization/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        data = {
            'code': authorization_code,
            'client_id': self.api_key,
            'client_secret': self.api_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            if self.access_token:
                self._save_token()
                logger.info("Successfully obtained and saved Upstox access token")
            return token_data
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            return None
    
    def set_access_token(self, token):
        """Set access token manually"""
        self.access_token = token
        self._save_token()
    
    def _make_request(self, endpoint, params=None):
        """Make authenticated request to Upstox API"""
        if not self.access_token:
            # Try automated login if no token
            if not self.auto_auth.ensure_valid_token():
                logger.error("Failed to obtain access token automatically")
                raise Exception("Access token not set and automated login failed")
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout making request to {endpoint}")
            raise Exception(f"Request timeout for {endpoint}")
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.warning("Token expired, attempting automated login")
                if self.auto_auth.ensure_valid_token():
                    # Retry request with new token
                    return self._make_request(endpoint, params)
                else:
                    logger.error("Failed to refresh token automatically")
                    raise Exception("Authentication failed and automated refresh failed")
            else:
                logger.error(f"HTTP error making request to {endpoint}: {str(e)}")
                raise Exception(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error(f"Error making request to {endpoint}: {str(e)}")
            raise
    
    def get_historical_data(self, instrument_key, interval, from_date, to_date):
        """
        Fetch historical data from Upstox
        
        Parameters:
        instrument_key (str): Upstox instrument key (e.g., 'NSE_EQ|INE002A01018')
        interval (str): Data interval ('1minute', '30minute', '1day', etc.)
        from_date (str): Start date in YYYY-MM-DD format
        to_date (str): End date in YYYY-MM-DD format
        
        Returns:
        DataFrame: Historical data with OHLCV columns
        """
        endpoint = f"/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        
        try:
            response = self._make_request(endpoint)
            
            if response.get('status') == 'success' and response.get('data'):
                candles = response['data']['candles']
                
                # Convert to DataFrame
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                
                # Convert timestamp to datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                
                # Rename columns to match yfinance format
                df.rename(columns={
                    'open': 'Open',
                    'high': 'High',
                    'low': 'Low',
                    'close': 'Close',
                    'volume': 'Volume'
                }, inplace=True)
                
                # Drop OI column as it's not needed for stocks
                df.drop('oi', axis=1, inplace=True, errors='ignore')
                
                return df
            else:
                logger.warning(f"No data received for {instrument_key}")
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
                
        except Exception as e:
            logger.error(f"Error fetching historical data: {str(e)}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    
    def get_live_data(self, instrument_keys):
        """
        Fetch live market data for multiple instruments
        
        Parameters:
        instrument_keys (list): List of instrument keys
        
        Returns:
        dict: Live market data
        """
        endpoint = "/market-quote/quotes"
        params = {
            'instrument_key': ','.join(instrument_keys)
        }
        
        try:
            response = self._make_request(endpoint, params)
            
            if response.get('status') == 'success':
                return response.get('data', {})
            else:
                logger.warning("No live data received")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching live data: {str(e)}")
            return {}
    
    def search_instruments(self, query):
        """
        Search for instruments by name or symbol
        
        Parameters:
        query (str): Search query
        
        Returns:
        list: List of matching instruments
        """
        endpoint = "/search/instruments"
        params = {'query': query}
        
        try:
            response = self._make_request(endpoint, params)
            
            if response.get('status') == 'success':
                return response.get('data', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error searching instruments: {str(e)}")
            return []
    
    def get_market_indices(self):
        """
        Fetch market indices data
        
        Returns:
        dict: Market indices data
        """
        # Common Indian market indices instrument keys
        indices_keys = [
            'NSE_INDEX|Nifty 50',
            'NSE_INDEX|Nifty Bank',
            'BSE_INDEX|SENSEX'
        ]
        
        return self.get_live_data(indices_keys)

# Global instance
upstox_api = UpstoxAPI()

def format_upstox_ticker(ticker_symbol):
    """
    Convert ticker symbol to Upstox instrument key format
    This is a simplified mapping - in production, you'd use the search API
    """
    # Handle index symbols
    if ticker_symbol.upper() == "NIFTY":
        return "NSE_INDEX|Nifty 50"
    if ticker_symbol.upper() == "BANKNIFTY":
        return "NSE_INDEX|Nifty Bank"
    if ticker_symbol.upper() == "SENSEX":
        return "BSE_INDEX|SENSEX"
    
    # For regular stocks, we'll need to search or maintain a mapping
    # This is a simplified approach - you should implement proper instrument search
    return f"NSE_EQ|{ticker_symbol}"

def get_upstox_historical_data(ticker_symbol, period="1y", interval="1day"):
    """
    Fetch historical data using Upstox API with caching
    
    Parameters:
    ticker_symbol (str): Stock ticker symbol
    period (str): Time period ('1d', '1mo', '1y', etc.)
    interval (str): Data interval ('1minute', '1day', etc.)
    
    Returns:
    DataFrame: Historical stock data
    """
    # Create cache key
    cache_key = f"upstox_hist_{ticker_symbol}_{period}_{interval}"
    cache_ttl = 600  # 10 minutes
    
    # Try to get from cache first
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        df = pd.DataFrame.from_dict(cached_data)
        if 'date' in df:
            df.set_index('date', inplace=True)
        return df
    
    try:
        # Convert period to date range
        end_date = datetime.now()
        if period == "1d":
            start_date = end_date - timedelta(days=1)
        elif period == "1mo":
            start_date = end_date - timedelta(days=30)
        elif period == "1y":
            start_date = end_date - timedelta(days=365)
        else:
            start_date = end_date - timedelta(days=365)  # Default to 1 year
        
        # Format dates
        from_date = start_date.strftime('%Y-%m-%d')
        to_date = end_date.strftime('%Y-%m-%d')
        
        # Convert ticker to instrument key
        instrument_key = format_upstox_ticker(ticker_symbol)
        
        # Fetch data
        df = upstox_api.get_historical_data(instrument_key, interval, from_date, to_date)
        
        if len(df) > 0:
            # Store data for caching
            df_for_cache = df.copy()
            df_for_cache['date'] = df_for_cache.index
            set_cached_data(cache_key, df_for_cache.to_dict('records'), cache_ttl)
            
            # Convert dates to string format for JSON serialization
            df.index = df.index.strftime('%Y-%m-%d %H:%M:%S')
        
        return df
        
    except Exception as e:
        logger.error(f"Error fetching Upstox historical data: {str(e)}")
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_upstox_live_data(ticker_symbols):
    """
    Fetch live market data using Upstox API
    
    Parameters:
    ticker_symbols (list): List of ticker symbols
    
    Returns:
    dict: Live market data mapped to original ticker symbols
    """
    try:
        # Convert tickers to instrument keys and maintain mapping
        symbol_to_instrument = {}
        instrument_keys = []
        
        for symbol in ticker_symbols:
            instrument_key = format_upstox_ticker(symbol)
            symbol_to_instrument[instrument_key] = symbol
            instrument_keys.append(instrument_key)
        
        logger.info(f"Fetching Upstox data for instruments: {instrument_keys}")
        
        # Fetch live data
        live_data = upstox_api.get_live_data(instrument_keys)
        
        if not live_data:
            logger.warning("No data returned from Upstox API")
            return {}
        
        # Convert to format similar to yfinance with original symbol names
        formatted_data = {}
        for instrument_key, data in live_data.items():
            original_symbol = symbol_to_instrument.get(instrument_key)
            if original_symbol and data:
                formatted_data[original_symbol] = {
                    'price': data.get('last_price', 0),
                    'change': data.get('net_change', 0),
                    'change_percent': data.get('percent_change', 0),
                    'volume': data.get('volume', 0),
                    'dayHigh': data.get('ohlc', {}).get('high', 0),
                    'dayLow': data.get('ohlc', {}).get('low', 0),
                    'open': data.get('ohlc', {}).get('open', 0),
                    'previousClose': data.get('ohlc', {}).get('close', 0),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'Upstox'
                }
                logger.info(f"Formatted data for {original_symbol}: {formatted_data[original_symbol]}")
        
        logger.info(f"Successfully formatted {len(formatted_data)} symbols from Upstox")
        return formatted_data
        
    except Exception as e:
        logger.error(f"Error fetching Upstox live data: {str(e)}")
        return {}

def get_upstox_market_indices():
    """
    Fetch market indices data using Upstox API
    
    Returns:
    dict: Market indices data
    """
    try:
        indices_data = upstox_api.get_market_indices()
        
        # Format data similar to yfinance
        formatted_indices = {}
        for key, data in indices_data.items():
            if data:
                formatted_indices[key] = {
                    'price': data.get('last_price', 0),
                    'change': data.get('net_change', 0),
                    'change_percent': data.get('percent_change', 0)
                }
        
        return formatted_indices
        
    except Exception as e:
        logger.error(f"Error fetching Upstox market indices: {str(e)}")
        return {} 