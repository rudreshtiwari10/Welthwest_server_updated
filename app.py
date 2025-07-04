from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from services.stock_service import (
    get_historical_data, get_live_data, validate_ticker,
    get_ohlc_data, get_market_indices, get_top_gainers_losers
)
from services.utils import normalize_data, calculate_statistics
from services.user_service import UserService
import os
import requests
import logging
import uuid
import pandas as pd
from typing import Dict, Any, Optional
from config import get_config
from datetime import timedelta
from services.technical_analysis import TechnicalAnalysis
from services.portfolio_service import PortfolioService
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
import json
from functools import wraps
import re
from services.backtesting_service import BacktestingService

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configure Werkzeug logger to only show errors
logging.getLogger('werkzeug').setLevel(logging.ERROR)

def is_binary_content(data):
    """Check if the request content appears to be binary data"""
    # Check for common TLS/SSL handshake patterns
    ssl_patterns = [
        rb'\x16\x03[\x00-\x03]',    # TLS record layer
        rb'\xc0[\x2b\x2f\x2c\x30]', # Common cipher suites (À+À/À,À0)
        rb'\x01\x00',               # Client Hello
        rb'\x03[\x00-\x03]',        # SSL/TLS versions
    ]
    
    if not data:
        return False
        
    # Convert to bytes if string
    if isinstance(data, str):
        data = data.encode('utf-8', errors='ignore')
        
    # Check for binary patterns
    for pattern in ssl_patterns:
        if re.search(pattern, data):
            return True
            
    # Check if data contains high proportion of non-printable characters
    printable = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
    return (printable / len(data)) < 0.75

def validate_json_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        try:
            # Check for binary content
            raw_data = request.get_data()
            if is_binary_content(raw_data):
                logger.warning(f"Rejected binary request from {request.remote_addr}")
                return jsonify({"error": "Binary/malformed request rejected"}), 400
                
            # Attempt to parse JSON
            if raw_data:
                json.loads(raw_data)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON format"}), 400
        except UnicodeDecodeError:
            logger.warning(f"Unicode decode error in request from {request.remote_addr}")
            return jsonify({"error": "Invalid request encoding"}), 400
        return f(*args, **kwargs)
    return decorated_function

# Initialize app with configuration
def create_app():
    app = Flask(__name__)
    config = get_config()
    app.config.from_object(config)
    
    # Set maximum content length (10MB)
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    
    # Configure JWT
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
    
    # Configure CORS with specific origins
    frontend_url = os.environ.get("FRONTEND_URL", "*")
    allowed_origins = [frontend_url]
    
    CORS(app, resources={
        r"/api/*": {"origins": allowed_origins},
        r"/": {"origins": allowed_origins}
    })

    # Error handlers
    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(e):
        return jsonify({"error": "Request entity too large. Maximum size is 10MB"}), 413

    @app.errorhandler(BadRequest)
    def handle_bad_request(e):
        return jsonify({"error": "Bad request format"}), 400
        
    @app.errorhandler(UnicodeDecodeError)
    def handle_unicode_error(e):
        return jsonify({"error": "Invalid request encoding"}), 400

    @app.before_request
    def validate_request():
        # Skip validation for GET requests and health checks
        if request.method == 'GET' or request.path in ['/', '/health']:
            return
            
        # Check for binary content early
        raw_data = request.get_data()
        if is_binary_content(raw_data):
            logger.warning(f"Rejected binary request from {request.remote_addr} to {request.path}")
            return jsonify({"error": "Binary/malformed request rejected"}), 400
            
        # Log request info for non-binary requests
        logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")
        if request.content_length:
            logger.info(f"Content Length: {request.content_length}")
    
    return app

app = create_app()
jwt = JWTManager(app)
user_service = UserService()

# Initialize services
technical_analysis = TechnicalAnalysis()
portfolio_service = PortfolioService()

# Initialize backtesting service
backtesting_service = BacktestingService()

# Root route for health checks
@app.route('/', methods=['GET', 'HEAD'])
def root():
    """Root endpoint for health checks"""
    return jsonify({"status": "healthy", "message": "Indian Stock Market API is running"}), 200

# Authentication routes
@app.route('/api/auth/register', methods=['POST'])
@validate_json_request
def register():
    """Register a new user"""
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['email', 'username', 'password', 'confirm_password']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Validate password match
    if data['password'] != data['confirm_password']:
        return jsonify({"error": "Passwords do not match"}), 400
    
    # Register user
    success, message, user_data = user_service.register_user(
        email=data['email'],
        username=data['username'],
        password=data['password']
    )
    
    if not success:
        return jsonify({"error": message}), 400
    
    # Generate tokens
    access_token = create_access_token(identity=str(user_data['id']))
    refresh_token = create_refresh_token(identity=str(user_data['id']))
    
    # Store refresh token
    user_service.store_refresh_token(user_data['id'], refresh_token)
    
    return jsonify({
        "message": "Registration successful",
        "user": user_data,
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 201

@app.route('/api/auth/login', methods=['POST'])
@validate_json_request
def login():
    """Login user"""
    data = request.get_json()
    
    # Validate required fields
    if 'username_or_email' not in data or 'password' not in data:
        return jsonify({"error": "Username/email and password are required"}), 400
    
    # Authenticate user
    success, message, user_data = user_service.login_user(
        username_or_email=data['username_or_email'],
        password=data['password']
    )
    
    if not success:
        return jsonify({"error": message}), 401
    
    # Generate tokens
    access_token = create_access_token(identity=str(user_data['id']))
    refresh_token = create_refresh_token(identity=str(user_data['id']))
    
    # Store refresh token
    user_service.store_refresh_token(user_data['id'], refresh_token)
    
    return jsonify({
        "message": "Login successful",
        "user": user_data,
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 200

@app.route('/api/auth/refresh', methods=['POST'])
@validate_json_request
def refresh():
    """Refresh access token"""
    data = request.get_json()
    
    if 'refresh_token' not in data:
        return jsonify({"error": "Refresh token is required"}), 400
    
    # Validate refresh token
    user_id = user_service.validate_refresh_token(data['refresh_token'])
    
    if not user_id:
        return jsonify({"error": "Invalid or expired refresh token"}), 401
    
    # Get user data
    user_data = user_service.get_user_by_id(user_id)
    
    if not user_data:
        return jsonify({"error": "User not found"}), 404
    
    # Generate new access token
    access_token = create_access_token(identity=user_id)
    
    return jsonify({
        "access_token": access_token,
        "user": user_data
    }), 200

@app.route('/api/auth/logout', methods=['POST'])
@validate_json_request
def logout():
    """Logout user"""
    data = request.get_json()
    
    if 'refresh_token' not in data:
        return jsonify({"error": "Refresh token is required"}), 400
    
    # Invalidate refresh token
    success = user_service.invalidate_refresh_token(data['refresh_token'])
    
    if success:
        return jsonify({"message": "Logout successful"}), 200
    else:
        return jsonify({"error": "Invalid refresh token"}), 400

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user data"""
    user_id = get_jwt_identity()
    user_data = user_service.get_user_by_id(user_id)
    
    if not user_data:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({"user": user_data}), 200

@app.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
@validate_json_request
def update_profile():
    """Update user profile"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    success, message, user_data = user_service.update_user_profile(user_id, data)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({
        "message": "Profile updated successfully",
        "user": user_data
    }), 200

# AI Chat Service Implementation
class AIModelService:
    """Service for handling interactions with various AI models"""
    
    def __init__(self):
        # Load API keys from environment variables
        self.openai_api_key = os.environ.get('OPENAI_API_KEY', '')
        self.openrouter_api_key = os.environ.get('OPENROUTER_API_KEY', '')
        self.claude_api_key = os.environ.get('CLAUDE_API_KEY', '')
        
        # Default system prompt for financial context
        self.default_system_prompt = """
        You are a helpful AI assistant for a financial platform called WelthWest. 
        Your primary role is to provide accurate information and insights about stocks, 
        market trends, investment strategies, and financial concepts.
        
        When discussing stocks:
        - Provide balanced perspectives on potential investments
        - Explain market concepts clearly without jargon
        - Never make specific buy/sell recommendations
        - Always remind users that all investments carry risk
        - Clarify that you're providing information, not financial advice
        
        If asked about specific stocks, provide general information about the company, 
        its sector, and recent market performance if available.
        """
    
    def extract_stock_symbols(self, query: str) -> list:
        """
        Extract potential stock symbols from the query
        This is a simple implementation - in production, you'd want a more robust approach
        """
        # Common Indian stock symbols to look for
        common_symbols = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
            'SBIN', 'HINDUNILVR', 'BHARTIARTL', 'ITC', 'KOTAKBANK',
            'NIFTY', 'SENSEX', 'BANKNIFTY'
        ]
        
        # Convert query to uppercase for case-insensitive matching
        upper_query = query.upper()
        
        # Check for common symbols in the query
        found_symbols = []
        for symbol in common_symbols:
            if symbol in upper_query.split():
                # For indices, handle special formatting
                if symbol == 'NIFTY':
                    found_symbols.append('^NSEI')
                elif symbol == 'SENSEX':
                    found_symbols.append('^BSESN')
                elif symbol == 'BANKNIFTY':
                    found_symbols.append('^NSEBANK')
                else:
                    # For regular stocks, add .NS suffix for NSE
                    found_symbols.append(f"{symbol}.NS")
        
        return found_symbols
    
    def get_stock_data_for_query(self, query: str) -> Dict[str, Any]:
        """
        Extract stock symbols from query and fetch their data
        """
        symbols = self.extract_stock_symbols(query)
        stock_data = {}
        
        if symbols:
            try:
                # Get live data for the symbols
                live_data = get_live_data(symbols)
                
                # Process the data into a more usable format
                for symbol in symbols:
                    if symbol in live_data.index:
                        data = live_data.loc[symbol]
                        stock_data[symbol] = {
                            'current_price': data.get('price'),
                            'change': {
                                'value': data.get('previousClose', 0) - data.get('price', 0),
                                'percent': ((data.get('price', 0) / data.get('previousClose', 0)) - 1) * 100 if data.get('previousClose', 0) else 0
                            },
                            'volume': data.get('volume'),
                            'market_cap': data.get('marketCap'),
                            'day_range': {
                                'low': data.get('dayLow'),
                                'high': data.get('dayHigh')
                            }
                        }
            except Exception as e:
                logger.error(f"Error fetching stock data: {str(e)}")
        
        return stock_data
    
    def chat_with_llama(self, query: str) -> Dict[str, Any]:
        """
        Simulate a response from a local Llama model
        In production, you would connect to an actual Llama model API or local instance
        """
        # This is a mock implementation
        response = {
            "analysis": f"Based on your query about {query}, I can provide some general information. "
                       f"This is a simulated response as if from a Llama model. "
                       f"In a real implementation, this would connect to an actual Llama model API or local instance. "
                       f"For specific financial advice, please consult with a financial advisor.",
            "model": "llama-simulated"
        }
        
        return response
    
    def chat_with_openai(self, query: str) -> Dict[str, Any]:
        """
        Send query to OpenAI API and get response
        """
        if not self.openai_api_key:
            return {"analysis": "OpenAI API key not configured. Please contact support.", "model": "openai-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": "gpt-3.5-turbo"
                }
            else:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from OpenAI. Status code: {response.status_code}", "model": "openai-error"}
                
        except Exception as e:
            logger.error(f"Exception in OpenAI chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "openai-error"}
    
    def chat_with_openrouter(self, query: str) -> Dict[str, Any]:
        """
        Send query to OpenRouter API and get response
        """
        if not self.openrouter_api_key:
            return {"analysis": "OpenRouter API key not configured. Please contact support.", "model": "openrouter-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "https://welthwest.com"  # Replace with your actual domain
            }
            
            payload = {
                "model": "anthropic/claude-3-opus",  # You can change this to any model supported by OpenRouter
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                used_model = result.get("model", "unknown")
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": used_model
                }
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from OpenRouter. Status code: {response.status_code}", "model": "openrouter-error"}
                
        except Exception as e:
            logger.error(f"Exception in OpenRouter chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "openrouter-error"}
    
    def chat_with_claude(self, query: str) -> Dict[str, Any]:
        """
        Send query to Anthropic's Claude API and get response
        """
        if not self.claude_api_key:
            return {"analysis": "Claude API key not configured. Please contact support.", "model": "claude-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.claude_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": "claude-3-opus-20240229",
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "analysis": result["content"][0]["text"],
                    "model": "claude-3-opus"
                }
            else:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from Claude. Status code: {response.status_code}", "model": "claude-error"}
                
        except Exception as e:
            logger.error(f"Exception in Claude chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "claude-error"}
    
    def process_chat_query(self, query: str, model: str = "llama", user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a chat query using the specified model
        """
        # Get any relevant stock data
        stock_data = self.get_stock_data_for_query(query)
        
        # Select the appropriate model handler
        if model == "openai":
            response = self.chat_with_openai(query)
        elif model == "openrouter":
            response = self.chat_with_openrouter(query)
        elif model == "claude":
            response = self.chat_with_claude(query)
        else:
            # Default to llama
            response = self.chat_with_llama(query)
        
        # Add stock data to the response
        response["stock_data"] = stock_data
        
        # In a production system, you might want to log this interaction
        if user_id:
            # Log the interaction for the user
            logger.info(f"Chat query from user {user_id}: {query}")
        
        return response

# Initialize the AI model service
ai_service = AIModelService()

@app.route('/api/historical', methods=['GET'])
def historical_data():
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()
    period = request.args.get('period', default='1y', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    # Validate the ticker
    if not validate_ticker(ticker):
        return jsonify({"error": f"Invalid ticker symbol: {ticker}"}), 400
    
    try:
        data = get_historical_data(ticker, period, interval)
        # Convert DataFrame to dictionary for JSON serialization
        result = data.reset_index().to_dict(orient='records')
        return jsonify({
            "data": result, 
            "ticker": ticker, 
            "period": period, 
            "interval": interval
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ohlc', methods=['GET'])
def ohlc_data():
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()
    start_date = request.args.get('start_date', default=None, type=str)
    end_date = request.args.get('end_date', default=None, type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    # Validate the ticker
    if not validate_ticker(ticker):
        return jsonify({"error": f"Invalid ticker symbol: {ticker}"}), 400
    
    try:
        data = get_ohlc_data(ticker, start_date, end_date, interval)
        # Convert DataFrame to dictionary for JSON serialization
        result = data.reset_index().to_dict(orient='records')
        return jsonify({
            "data": result, 
            "ticker": ticker, 
            "start_date": start_date,
            "end_date": end_date,
            "interval": interval
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/live', methods=['GET'])
def live_data():
    ticker_input = request.args.get('tickers', default='RELIANCE', type=str).upper()
    ticker_list = [t.strip() for t in ticker_input.split(',')]
    
    # Validate tickers
    valid_tickers = []
    invalid_tickers = []
    for ticker in ticker_list:
        if validate_ticker(ticker):
            valid_tickers.append(ticker)
        else:
            invalid_tickers.append(ticker)
    
    if not valid_tickers:
        return jsonify({"error": "No valid ticker symbols provided"}), 400
    
    try:
        data = get_live_data(valid_tickers)
        # Convert DataFrame to dictionary for JSON serialization
        result = data.reset_index().to_dict(orient='records')
        response = {
            "data": result,
            "valid_tickers": valid_tickers
        }
        
        if invalid_tickers:
            response["invalid_tickers"] = invalid_tickers
            
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/validate', methods=['GET'])
def validate():
    ticker = request.args.get('ticker', type=str)
    
    if not ticker:
        return jsonify({"error": "No ticker symbol provided"}), 400
        
    is_valid = validate_ticker(ticker.upper())
    return jsonify({
        "ticker": ticker.upper(), 
        "valid": is_valid
    })

@app.route('/api/compare', methods=['GET'])
def compare_stocks():
    ticker_input = request.args.get('tickers', default='RELIANCE,TCS', type=str).upper()
    period = request.args.get('period', default='1y', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    ticker_list = [t.strip() for t in ticker_input.split(',')]
    
    # Validate tickers
    valid_tickers = []
    invalid_tickers = []
    for ticker in ticker_list:
        if validate_ticker(ticker):
            valid_tickers.append(ticker)
        else:
            invalid_tickers.append(ticker)
    
    if not valid_tickers:
        return jsonify({"error": "No valid ticker symbols provided"}), 400
    
    try:
        comparison_data = {}
        normalized_data = {}
        
        for ticker in valid_tickers:
            data = get_historical_data(ticker, period, interval)
            comparison_data[ticker] = data.reset_index().to_dict(orient='records')
            
            # Normalize data for better comparison
            norm_data = normalize_data(data, 'Close')
            normalized_data[ticker] = norm_data.reset_index().to_dict(orient='records')
        
        response = {
            "raw_data": comparison_data,
            "normalized_data": normalized_data,
            "valid_tickers": valid_tickers,
            "period": period,
            "interval": interval
        }
        
        if invalid_tickers:
            response["invalid_tickers"] = invalid_tickers
            
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()
    period = request.args.get('period', default='1y', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    # Validate the ticker
    if not validate_ticker(ticker):
        return jsonify({"error": f"Invalid ticker symbol: {ticker}"}), 400
    
    try:
        data = get_historical_data(ticker, period, interval)
        stats = calculate_statistics(data)
        
        return jsonify({
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "statistics": stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-indices', methods=['GET'])
def market_indices():
    try:
        indices_data = get_market_indices()
        return jsonify({
            "indices": indices_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/top-gainers-losers', methods=['GET'])
def top_gainers_losers():
    try:
        data = get_top_gainers_losers()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# AI Chat endpoint
@app.route('/api/market/chat', methods=['POST'])
@validate_json_request
def chat_with_ai():
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({"error": "No query provided"}), 400
            
        query = data['query']
        model = data.get('model', 'llama')
        user_id = data.get('user_id')
        
        # Process the chat query
        response = ai_service.process_chat_query(query, model, user_id)
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({"error": str(e), "analysis": "Sorry, I encountered an error processing your request."}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Indian Stock Market API is running"}), 200

# Technical Analysis Endpoints
@app.route('/api/indicators', methods=['GET'])
@jwt_required()
def get_indicators():
    """Get technical indicators for a stock"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        # Parse indicators from query string
        indicators = request.args.get('indicators', '').split(',')
        if not indicators or not indicators[0]:
            return jsonify({"error": "At least one indicator is required"}), 400
            
        # Parse parameters for indicators
        params = {}
        for key, value in request.args.items():
            if key not in ['ticker', 'indicators']:
                try:
                    params[key] = int(value)
                except ValueError:
                    params[key] = value
                    
        results = technical_analysis.calculate_indicators(ticker, indicators, params)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/screener', methods=['GET'])
@jwt_required()
def screen_stocks():
    """Screen stocks based on technical criteria"""
    try:
        criteria_str = request.args.get('criteria', '')
        if not criteria_str:
            return jsonify({"error": "Screening criteria are required"}), 400
            
        # Parse criteria string (e.g., "rsi<30,volume>1000000")
        criteria = {}
        try:
            for criterion in criteria_str.split(','):
                if '<' in criterion:
                    indicator, value = criterion.split('<')
                    criteria[indicator.strip()] = {"below": float(value)}
                elif '>' in criterion:
                    indicator, value = criterion.split('>')
                    criteria[indicator.strip()] = {"above": float(value)}
        except Exception as e:
            return jsonify({"error": f"Invalid criteria format: {str(e)}"}), 400
            
        results = technical_analysis.screen_stocks(criteria)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/intraday', methods=['GET'])
@jwt_required()
def get_intraday_data():
    """Get intraday data for a stock"""
    try:
        ticker = request.args.get('ticker')
        interval = request.args.get('interval', '5m')
        
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        valid_intervals = ['1m', '5m', '15m', '30m', '1h']
        if interval not in valid_intervals:
            return jsonify({"error": f"Invalid interval. Must be one of {valid_intervals}"}), 400
            
        df = get_historical_data(ticker, period="1d", interval=interval)
        if df.empty:
            return jsonify({"error": "No data available"}), 404
            
        # Convert DataFrame to list of dictionaries with datetime index as string
        data = []
        for idx, row in df.iterrows():
            entry = {
                "timestamp": idx.strftime('%Y-%m-%d %H:%M:%S'),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": float(row['Volume'])
            }
            data.append(entry)
            
        return jsonify({"data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/signals', methods=['GET'])
@jwt_required()
def get_trading_signals():
    """Get trading signals for a stock"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        signals = technical_analysis.get_trading_signals(ticker)
        return jsonify(signals)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/technical-analysis', methods=['GET'])
@jwt_required()
def get_comprehensive_technical_analysis():
    """Get comprehensive technical analysis for a stock with all indicators"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        # Get all indicators
        all_indicators = ['rsi', 'macd', 'bollinger', 'sma', 'ema', 'stochastic', 'atr', 'obv', 'vwap', 'pivot', 'fibonacci']
        
        # Get indicator data
        indicator_data = technical_analysis.calculate_indicators(ticker, all_indicators)
        
        # Get trading signals
        signals = technical_analysis.get_trading_signals(ticker)
        
        # Combine everything
        result = {
            "ticker": ticker,
            "timestamp": pd.Timestamp.now().isoformat(),
            "indicators": indicator_data,
            "signals": signals,
            "summary": {
                "overall_signal": signals.get("overall", {}).get("signal", "neutral"),
                "signal_strength": signals.get("overall", {}).get("strength", "weak"),
                "consensus_ratio": signals.get("overall", {}).get("consensus_ratio", 0),
                "total_indicators": signals.get("overall", {}).get("total_indicators", 0)
            }
        }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/levels', methods=['GET'])
@jwt_required()
def get_support_resistance():
    """Get support and resistance levels"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        levels = technical_analysis.get_support_resistance(ticker)
        return jsonify(levels)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/patterns', methods=['GET'])
@jwt_required()
def get_patterns():
    """Get chart patterns"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        patterns = technical_analysis.identify_patterns(ticker)
        return jsonify(patterns)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Portfolio Management Endpoints
@app.route('/api/portfolio/performance', methods=['GET'])
@jwt_required()
def get_portfolio_performance():
    """Get portfolio performance metrics"""
    try:
        user_id = get_jwt_identity()
        user_data = user_service.get_user_by_id(user_id)
        
        if not user_data:
            return jsonify({"error": "User not found"}), 404
            
        if 'portfolio' not in user_data or not user_data['portfolio']:
            return jsonify({"error": "No portfolio found"}), 404
            
        performance = portfolio_service.calculate_portfolio_performance(user_data['portfolio'])
        return jsonify(performance)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/portfolio/add', methods=['POST'])
@jwt_required()
@validate_json_request
def add_to_portfolio():
    """Add stock to portfolio"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        required_fields = ['ticker', 'quantity', 'buy_price']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Validate ticker
        if not validate_ticker(data['ticker']):
            return jsonify({"error": "Invalid ticker symbol"}), 400
            
        # Validate numeric fields
        try:
            data['quantity'] = int(data['quantity'])
            data['buy_price'] = float(data['buy_price'])
        except ValueError:
            return jsonify({"error": "Invalid quantity or buy price"}), 400
            
        # Add to portfolio
        success = user_service.add_to_portfolio(user_id, data)
        if not success:
            return jsonify({"error": "Failed to add to portfolio"}), 400
            
        return jsonify({"message": "Successfully added to portfolio"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/risk-calculator', methods=['POST'])
@jwt_required()
@validate_json_request
def calculate_risk():
    """Calculate position size and risk metrics"""
    try:
        data = request.get_json()
        required_fields = ['ticker', 'risk_per_trade', 'account_size', 'stop_loss_pct']
        
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Validate numeric fields
        try:
            risk_per_trade = float(data['risk_per_trade'])
            account_size = float(data['account_size'])
            stop_loss_pct = float(data['stop_loss_pct'])
        except ValueError:
            return jsonify({"error": "Invalid numeric values"}), 400
            
        # Validate ranges
        if not (0 < risk_per_trade <= 100 and account_size > 0 and 0 < stop_loss_pct <= 100):
            return jsonify({"error": "Invalid parameter ranges"}), 400
            
        risk_metrics = portfolio_service.calculate_position_size(
            data['ticker'],
            risk_per_trade,
            account_size,
            stop_loss_pct
        )
        
        return jsonify(risk_metrics)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/correlation', methods=['GET'])
@jwt_required()
def get_correlation():
    """Get correlation matrix for multiple stocks"""
    try:
        tickers = request.args.get('tickers', '').split(',')
        if not tickers or len(tickers) < 2:
            return jsonify({"error": "At least two tickers are required"}), 400
            
        # Validate tickers
        invalid_tickers = [ticker for ticker in tickers if not validate_ticker(ticker)]
        if invalid_tickers:
            return jsonify({"error": f"Invalid ticker symbols: {', '.join(invalid_tickers)}"}), 400
            
        correlation = portfolio_service.calculate_correlation_matrix(tickers)
        return jsonify(correlation)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Market Intelligence Endpoints
@app.route('/api/market-breadth', methods=['GET'])
@jwt_required()
def get_market_breadth():
    """Get market breadth indicators"""
    try:
        # Get Nifty 500 stocks for market breadth calculation
        nifty500_stocks = technical_analysis._get_default_stock_list()  # Implement this to return Nifty 500 stocks
        
        advances = 0
        declines = 0
        new_highs = 0
        new_lows = 0
        
        for ticker in nifty500_stocks[:50]:  # Limit to 50 stocks for performance
            try:
                df = get_historical_data(ticker, period="5d", interval="1d")
                if not df.empty:
                    # Count advances/declines
                    if df['Close'].iloc[-1] > df['Close'].iloc[-2]:
                        advances += 1
                    else:
                        declines += 1
                        
                    # Check for new highs/lows (52-week)
                    year_data = get_historical_data(ticker, period="1y")
                    if not year_data.empty:
                        if df['Close'].iloc[-1] >= year_data['High'].max():
                            new_highs += 1
                        if df['Close'].iloc[-1] <= year_data['Low'].min():
                            new_lows += 1
            except Exception:
                continue
        
        return jsonify({
            "advance_decline_ratio": advances / declines if declines > 0 else float('inf'),
            "advances": advances,
            "declines": declines,
            "new_highs": new_highs,
            "new_lows": new_lows,
            "total_stocks_analyzed": len(nifty500_stocks[:50])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/backtesting/generate-signals', methods=['POST'])
@jwt_required()
@validate_json_request
def generate_backtesting_signals():
    """Generate backtesting signals based on technical indicators"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['instrument', 'timeframe', 'start_date', 'end_date', 'indicators', 'combination_logic']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate timeframe format
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '1d']
        if data['timeframe'] not in valid_timeframes:
            return jsonify({"error": f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes)}"}), 400
            
        # Validate date formats
        try:
            pd.to_datetime(data['start_date'])
            pd.to_datetime(data['end_date'])
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
            
        # Validate combination logic
        if data['combination_logic'] not in ['AND', 'OR']:
            return jsonify({"error": "combination_logic must be either 'AND' or 'OR'"}), 400
            
        # Validate indicators array
        if not isinstance(data['indicators'], list) or len(data['indicators']) == 0:
            return jsonify({"error": "indicators must be a non-empty array"}), 400
            
        for indicator in data['indicators']:
            if not all(k in indicator for k in ['type', 'parameters', 'signal_condition', 'signal_type']):
                return jsonify({"error": "Each indicator must have type, parameters, signal_condition, and signal_type"}), 400
                
        # Get historical data
        df = get_ohlc_data(data['instrument'], data['timeframe'], data['start_date'], data['end_date'])
        if df.empty:
            return jsonify({"error": "No data available for the specified period"}), 404
            
        # Calculate indicator values and generate signals
        signals = []
        indicator_results = {}
        
        for indicator in data['indicators']:
            try:
                # Calculate indicator values
                indicator_type = indicator['type'].lower()
                params = indicator['parameters']
                
                if indicator_type == 'rsi':
                    values = technical_analysis._calculate_rsi(df, params.get('period', 14))
                    indicator_results[indicator_type] = values
                elif indicator_type == 'macd':
                    macd_data = technical_analysis._calculate_macd(
                        df,
                        params.get('fastperiod', 12),
                        params.get('slowperiod', 26),
                        params.get('signalperiod', 9)
                    )
                    indicator_results[indicator_type] = macd_data
                elif indicator_type == 'bollinger':
                    bb_data = technical_analysis._calculate_bollinger_bands(df, params.get('period', 20))
                    indicator_results[indicator_type] = bb_data
                else:
                    return jsonify({"error": f"Unsupported indicator type: {indicator_type}"}), 400
                    
            except Exception as e:
                return jsonify({"error": f"Error calculating {indicator_type}: {str(e)}"}), 500
                
        # Generate signals based on indicator conditions
        for idx, row in df.iterrows():
            signal = None
            conditions_met = []
            
            for indicator in data['indicators']:
                indicator_type = indicator['type'].lower()
                condition = indicator['signal_condition']
                signal_type = indicator['signal_type']
                
                # Check conditions for each indicator
                condition_met = False
                
                if indicator_type == 'rsi':
                    rsi_value = indicator_results[indicator_type][idx]
                    if condition == 'oversold' and rsi_value < 30:
                        condition_met = signal_type == 'buy'
                    elif condition == 'overbought' and rsi_value > 70:
                        condition_met = signal_type == 'sell'
                        
                elif indicator_type == 'macd':
                    macd = indicator_results[indicator_type]['macd'][idx]
                    signal_line = indicator_results[indicator_type]['signal'][idx]
                    if condition == 'crossover' and macd > signal_line:
                        condition_met = signal_type == 'buy'
                    elif condition == 'crossunder' and macd < signal_line:
                        condition_met = signal_type == 'sell'
                        
                elif indicator_type == 'bollinger':
                    price = row['Close']
                    lower = indicator_results[indicator_type]['lower'][idx]
                    upper = indicator_results[indicator_type]['upper'][idx]
                    if condition == 'lower_band' and price <= lower:
                        condition_met = signal_type == 'buy'
                    elif condition == 'upper_band' and price >= upper:
                        condition_met = signal_type == 'sell'
                        
                conditions_met.append(condition_met)
                
            # Combine conditions based on logic
            if data['combination_logic'] == 'AND' and all(conditions_met):
                signal = {
                    'timestamp': idx.isoformat(),
                    'price': float(row['Close']),
                    'type': data['indicators'][0]['signal_type']  # Use first indicator's signal type
                }
            elif data['combination_logic'] == 'OR' and any(conditions_met):
                # For OR logic, use the signal type of the first condition that was met
                signal_type = next(ind['signal_type'] for i, ind in enumerate(data['indicators']) if conditions_met[i])
                signal = {
                    'timestamp': idx.isoformat(),
                    'price': float(row['Close']),
                    'type': signal_type
                }
                
            if signal:
                signals.append(signal)
                
        # Calculate performance metrics
        metrics = calculate_performance_metrics(signals, df)
        
        return jsonify({
            "signals": signals,
            "metrics": metrics,
            "summary": {
                "total_signals": len(signals),
                "period_start": data['start_date'],
                "period_end": data['end_date'],
                "instrument": data['instrument']
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def calculate_performance_metrics(signals, df):
    """Calculate performance metrics for the backtesting signals"""
    if not signals:
        return {
            "win_rate": 0,
            "total_trades": 0,
            "profit_loss": 0,
            "max_drawdown": 0
        }
        
    trades = []
    current_position = None
    total_profit_loss = 0
    max_drawdown = 0
    peak_value = 0
    
    for signal in signals:
        price = signal['price']
        
        if not current_position and signal['type'] == 'buy':
            current_position = {
                'entry_price': price,
                'entry_time': signal['timestamp']
            }
        elif current_position and signal['type'] == 'sell':
            profit_loss = price - current_position['entry_price']
            trades.append({
                'entry_price': current_position['entry_price'],
                'exit_price': price,
                'profit_loss': profit_loss,
                'entry_time': current_position['entry_time'],
                'exit_time': signal['timestamp']
            })
            total_profit_loss += profit_loss
            
            # Update peak value and drawdown
            if total_profit_loss > peak_value:
                peak_value = total_profit_loss
            else:
                drawdown = peak_value - total_profit_loss
                max_drawdown = max(max_drawdown, drawdown)
                
            current_position = None
            
    winning_trades = len([t for t in trades if t['profit_loss'] > 0])
    total_trades = len(trades)
    
    return {
        "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
        "total_trades": total_trades,
        "profit_loss": total_profit_loss,
        "max_drawdown": max_drawdown,
        "trades": trades
    }

@app.route('/api/backtesting/run', methods=['POST'])
@jwt_required()
@validate_json_request
def run_backtest():
    """Run a backtest with the specified parameters"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['ticker', 'start_date', 'end_date', 'indicators', 'position_size']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Get optional parameters
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')
        timeframe = data.get('timeframe', '1d')
        
        # Validate indicators format
        if not isinstance(data['indicators'], list):
            return jsonify({"error": "Indicators must be a list"}), 400
            
        for indicator in data['indicators']:
            if not isinstance(indicator, dict):
                return jsonify({"error": "Each indicator must be an object"}), 400
            if 'type' not in indicator:
                return jsonify({"error": "Each indicator must have a type"}), 400
            if 'parameters' not in indicator and 'params' not in indicator:
                return jsonify({"error": f"Parameters must be specified for indicator {indicator['type']}"}), 400
        
        # Initialize backtesting service if not already initialized
        if not hasattr(app, 'backtesting_service'):
            from services.backtesting_service import BacktestingService
            app.backtesting_service = BacktestingService()
        
        # Run backtest
        results = app.backtesting_service.run_backtest(
            ticker=data['ticker'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            indicators=data['indicators'],
            position_size=float(data['position_size']),
            stop_loss=float(stop_loss) if stop_loss is not None else None,
            take_profit=float(take_profit) if take_profit is not None else None,
            timeframe=timeframe
        )
        
        return jsonify(results), 200
        
    except ValueError as e:
        logger.warning(f"Validation error in backtest: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while running the backtest"}), 500 