"""
AI Model Endpoints Simulator
============================

Interactive Python simulator to test all AI model endpoints including:
- Authentication (login/register)
- Market Regime Classifier endpoints
- Technical Analysis endpoints
- Other AI model endpoints

Usage: python ai_model_simulator.py

Requirements:
- Server must be running (python run.py)
- pip install requests colorama
"""

import requests
import json
import time
import os
import sys
from datetime import datetime
from typing import Dict, Optional, List

# Try to import colorama for colored output
try:
    from colorama import init, Fore, Back, Style
    init()
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False
    # Fallback color constants
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Back:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""

class AIModelSimulator:
    """Interactive simulator for testing AI model endpoints"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.access_token = None
        self.user_info = None
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'AI-Model-Simulator/1.0'
        })
        
        # Test user credentials
        self.test_user = {
            "email": "test@aimodel.com",
            "password": "testpass123",
            "name": "AI Model Tester"
        }
        
        # Available tickers for testing
        self.test_tickers = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "SBIN.NS", "HINDUNILVR.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS"
        ]
    
    def print_header(self, title: str):
        """Print a formatted header"""
        print(f"\n{Style.BRIGHT}{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{Fore.CYAN}{title.center(60)}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    def print_success(self, message: str):
        """Print success message"""
        print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")
    
    def print_error(self, message: str):
        """Print error message"""
        print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")
    
    def print_warning(self, message: str):
        """Print warning message"""
        print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")
    
    def print_info(self, message: str):
        """Print info message"""
        print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")
    
    def check_server_status(self) -> bool:
        """Check if the server is running"""
        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                    params: Optional[Dict] = None, auth_required: bool = True) -> requests.Response:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        # Add authorization header if token exists and auth is required
        headers = {}
        if auth_required and self.access_token:
            headers['Authorization'] = f"Bearer {self.access_token}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data, headers=headers, timeout=30)
            elif method.upper() == 'PUT':
                response = self.session.put(url, json=data, headers=headers, timeout=30)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return response
        except requests.exceptions.RequestException as e:
            self.print_error(f"Request failed: {str(e)}")
            return None
    
    def register_user(self) -> bool:
        """Register a test user"""
        print(f"\n{Style.BRIGHT}Registering test user...{Style.RESET_ALL}")
        
        response = self.make_request('POST', '/api/auth/register', data=self.test_user, auth_required=False)
        
        if response and response.status_code == 201:
            self.print_success("User registered successfully")
            return True
        elif response and response.status_code == 400 and "already exists" in response.text:
            self.print_warning("User already exists, proceeding to login")
            return True
        else:
            self.print_error(f"Registration failed: {response.text if response else 'No response'}")
            return False
    
    def login_user(self) -> bool:
        """Login the test user"""
        print(f"\n{Style.BRIGHT}Logging in test user...{Style.RESET_ALL}")
        
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        response = self.make_request('POST', '/api/auth/login', data=login_data, auth_required=False)
        
        if response and response.status_code == 200:
            result = response.json()
            self.access_token = result.get("access_token")
            self.user_info = result.get("user")
            
            if self.access_token:
                self.print_success(f"Login successful! Welcome {self.user_info.get('name', 'User')}")
                return True
            else:
                self.print_error("Login failed: No access token received")
                return False
        else:
            self.print_error(f"Login failed: {response.text if response else 'No response'}")
            return False
    
    def authenticate(self) -> bool:
        """Handle user authentication"""
        self.print_header("AUTHENTICATION")
        
        if not self.register_user():
            return False
        
        if not self.login_user():
            return False
        
        return True
    
    def test_market_regime_endpoints(self):
        """Test all market regime classifier endpoints"""
        self.print_header("MARKET REGIME CLASSIFIER ENDPOINTS")
        
        # Test 1: Get regime definitions (no auth required)
        print(f"\n{Style.BRIGHT}1. GET /api/market-regime/definitions{Style.RESET_ALL}")
        response = self.make_request('GET', '/api/market-regime/definitions', auth_required=False)
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Regime definitions retrieved successfully")
            print(f"   Number of regimes: {len(result.get('definitions', {}))}")
            for regime_id, regime_info in result.get('definitions', {}).items():
                print(f"   - {regime_id}: {regime_info.get('name', 'Unknown')}")
        else:
            self.print_error(f"Failed to get regime definitions: {response.text if response else 'No response'}")
        
        # Test 2: Get model info
        print(f"\n{Style.BRIGHT}2. GET /api/market-regime/model-info{Style.RESET_ALL}")
        response = self.make_request('GET', '/api/market-regime/model-info')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Model info retrieved successfully")
            print(f"   Model status: {result.get('status', 'Unknown')}")
            print(f"   Model loaded: {result.get('is_loaded', False)}")
            print(f"   Supported tickers: {len(result.get('supported_tickers', []))}")
        else:
            self.print_error(f"Failed to get model info: {response.text if response else 'No response'}")
        
        # Test 3: Train model (admin required - might fail)
        print(f"\n{Style.BRIGHT}3. POST /api/market-regime/train{Style.RESET_ALL}")
        train_data = {
            "ticker": "RELIANCE.NS",
            "period": "1y",
            "retrain": True
        }
        response = self.make_request('POST', '/api/market-regime/train', data=train_data)
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Model training successful")
            print(f"   Training accuracy: {result.get('accuracy', 'N/A')}")
            print(f"   Training samples: {result.get('training_samples', 'N/A')}")
        elif response and response.status_code == 403:
            self.print_warning("Training requires admin access (expected for test user)")
        else:
            self.print_error(f"Training failed: {response.text if response else 'No response'}")
        
        # Test 4: Predict regime
        print(f"\n{Style.BRIGHT}4. GET /api/market-regime/predict{Style.RESET_ALL}")
        ticker = input(f"Enter ticker to predict (default: RELIANCE.NS): ").strip() or "RELIANCE.NS"
        
        response = self.make_request('GET', f'/api/market-regime/predict?ticker={ticker}')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Regime prediction successful")
            print(f"   Ticker: {ticker}")
            print(f"   Predicted regime: {result.get('regime_name', 'Unknown')}")
            print(f"   Confidence: {result.get('confidence', 'N/A')}")
            print(f"   Description: {result.get('regime_description', 'N/A')}")
        else:
            self.print_error(f"Prediction failed: {response.text if response else 'No response'}")
        
        # Test 5: Get analysis
        print(f"\n{Style.BRIGHT}5. GET /api/market-regime/analysis{Style.RESET_ALL}")
        response = self.make_request('GET', f'/api/market-regime/analysis?ticker={ticker}')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Regime analysis successful")
            print(f"   Analysis status: {result.get('status', 'Unknown')}")
            if result.get('current_regime'):
                print(f"   Current regime: {result['current_regime'].get('regime_name', 'Unknown')}")
            if result.get('historical_analysis'):
                hist = result['historical_analysis']
                print(f"   Historical periods analyzed: {hist.get('total_periods', 'N/A')}")
        else:
            self.print_error(f"Analysis failed: {response.text if response else 'No response'}")
        
        # Test 6: Get recommendations
        print(f"\n{Style.BRIGHT}6. GET /api/market-regime/recommendations{Style.RESET_ALL}")
        response = self.make_request('GET', f'/api/market-regime/recommendations?ticker={ticker}')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Regime recommendations successful")
            if result.get('recommendations'):
                recommendations = result['recommendations']
                print(f"   Strategy: {recommendations.get('strategy', 'Unknown')}")
                print(f"   Risk level: {recommendations.get('risk_level', 'Unknown')}")
                print(f"   Position size: {recommendations.get('position_size', 'Unknown')}")
                print(f"   Confidence level: {recommendations.get('confidence_level', 'Unknown')}")
        else:
            self.print_error(f"Recommendations failed: {response.text if response else 'No response'}")
        
        # Test 7: Multiple predictions
        print(f"\n{Style.BRIGHT}7. POST /api/market-regime/multiple{Style.RESET_ALL}")
        multiple_data = {
            "tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
        }
        response = self.make_request('POST', '/api/market-regime/multiple', data=multiple_data)
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Multiple predictions successful")
            predictions = result.get('predictions', {})
            print(f"   Predictions for {len(predictions)} tickers:")
            for ticker, prediction in predictions.items():
                if prediction.get('status') == 'success':
                    print(f"   - {ticker}: {prediction.get('regime_name', 'Unknown')} ({prediction.get('confidence', 0):.2f})")
                else:
                    print(f"   - {ticker}: Error - {prediction.get('message', 'Unknown error')}")
        else:
            self.print_error(f"Multiple predictions failed: {response.text if response else 'No response'}")
        
        # Test 8: Evaluate model (admin required - might fail)
        print(f"\n{Style.BRIGHT}8. GET /api/market-regime/evaluate{Style.RESET_ALL}")
        response = self.make_request('GET', f'/api/market-regime/evaluate?ticker={ticker}')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Model evaluation successful")
            print(f"   Evaluation accuracy: {result.get('accuracy', 'N/A')}")
            print(f"   Total samples: {result.get('total_samples', 'N/A')}")
        elif response and response.status_code == 403:
            self.print_warning("Evaluation requires admin access (expected for test user)")
        else:
            self.print_error(f"Evaluation failed: {response.text if response else 'No response'}")
    
    def test_technical_analysis_endpoints(self):
        """Test technical analysis endpoints"""
        self.print_header("TECHNICAL ANALYSIS ENDPOINTS")
        
        # Test 1: Technical analysis
        print(f"\n{Style.BRIGHT}1. POST /api/technical-analysis{Style.RESET_ALL}")
        ticker = input(f"Enter ticker for technical analysis (default: RELIANCE.NS): ").strip() or "RELIANCE.NS"
        
        ta_data = {
            "ticker": ticker,
            "indicators": ["rsi", "macd", "bollinger", "sma", "ema"]
        }
        response = self.make_request('POST', '/api/technical-analysis', data=ta_data)
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Technical analysis successful")
            indicators = result.get('indicators', {})
            print(f"   Indicators calculated: {len(indicators)}")
            for indicator, data in indicators.items():
                if 'current' in data:
                    print(f"   - {indicator.upper()}: {data['current']}")
                elif 'signal' in data:
                    print(f"   - {indicator.upper()}: {data['signal']}")
        else:
            self.print_error(f"Technical analysis failed: {response.text if response else 'No response'}")
    
    def test_stock_data_endpoints(self):
        """Test stock data endpoints"""
        self.print_header("STOCK DATA ENDPOINTS")
        
        # Test 1: Historical data
        print(f"\n{Style.BRIGHT}1. GET /api/stock/{{}}/historical{Style.RESET_ALL}")
        ticker = input(f"Enter ticker for historical data (default: RELIANCE): ").strip() or "RELIANCE"
        
        response = self.make_request('GET', f'/api/stock/{ticker}/historical')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Historical data retrieved successfully")
            data_points = len(result.get('data', []))
            print(f"   Data points: {data_points}")
            if data_points > 0:
                print(f"   Period: {result.get('period', 'N/A')}")
                print(f"   Interval: {result.get('interval', 'N/A')}")
        else:
            self.print_error(f"Historical data failed: {response.text if response else 'No response'}")
        
        # Test 2: Live data
        print(f"\n{Style.BRIGHT}2. GET /api/live/{{}}{Style.RESET_ALL}")
        response = self.make_request('GET', f'/api/live/{ticker}')
        
        if response and response.status_code == 200:
            result = response.json()
            self.print_success("Live data retrieved successfully")
            ticker_data = result.get(ticker, {})
            if 'price' in ticker_data:
                print(f"   Current price: {ticker_data['price']}")
                print(f"   Day high: {ticker_data.get('dayHigh', 'N/A')}")
                print(f"   Day low: {ticker_data.get('dayLow', 'N/A')}")
        else:
            self.print_error(f"Live data failed: {response.text if response else 'No response'}")
    
    def test_custom_endpoint(self):
        """Test a custom endpoint"""
        self.print_header("CUSTOM ENDPOINT TEST")
        
        print("Enter custom endpoint details:")
        method = input("HTTP method (GET/POST/PUT/DELETE): ").strip().upper() or "GET"
        endpoint = input("Endpoint path (e.g., /api/custom): ").strip()
        
        if not endpoint:
            self.print_error("Endpoint path is required")
            return
        
        data = None
        if method in ['POST', 'PUT']:
            json_data = input("JSON data (optional, press Enter to skip): ").strip()
            if json_data:
                try:
                    data = json.loads(json_data)
                except json.JSONDecodeError:
                    self.print_error("Invalid JSON data")
                    return
        
        response = self.make_request(method, endpoint, data=data)
        
        if response:
            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            try:
                result = response.json()
                print(f"Response Body: {json.dumps(result, indent=2)}")
            except:
                print(f"Response Body: {response.text}")
        else:
            self.print_error("Failed to make request")
    
    def interactive_menu(self):
        """Display interactive menu"""
        while True:
            self.print_header("AI MODEL ENDPOINT SIMULATOR")
            print(f"{Style.BRIGHT}Choose an option:{Style.RESET_ALL}")
            print("1. Test Market Regime Classifier Endpoints")
            print("2. Test Technical Analysis Endpoints")
            print("3. Test Stock Data Endpoints")
            print("4. Test Custom Endpoint")
            print("5. Re-authenticate")
            print("6. Show Current Session Info")
            print("7. Exit")
            
            choice = input(f"\n{Style.BRIGHT}Enter your choice (1-7): {Style.RESET_ALL}").strip()
            
            if choice == '1':
                self.test_market_regime_endpoints()
            elif choice == '2':
                self.test_technical_analysis_endpoints()
            elif choice == '3':
                self.test_stock_data_endpoints()
            elif choice == '4':
                self.test_custom_endpoint()
            elif choice == '5':
                self.authenticate()
            elif choice == '6':
                self.show_session_info()
            elif choice == '7':
                print(f"\n{Style.BRIGHT}Thank you for using AI Model Endpoint Simulator!{Style.RESET_ALL}")
                break
            else:
                self.print_error("Invalid choice. Please try again.")
            
            input(f"\n{Style.BRIGHT}Press Enter to continue...{Style.RESET_ALL}")
    
    def show_session_info(self):
        """Show current session information"""
        self.print_header("SESSION INFORMATION")
        
        print(f"{Style.BRIGHT}Server URL:{Style.RESET_ALL} {self.base_url}")
        print(f"{Style.BRIGHT}Authentication Status:{Style.RESET_ALL} {'✓ Authenticated' if self.access_token else '✗ Not authenticated'}")
        
        if self.user_info:
            print(f"{Style.BRIGHT}User Info:{Style.RESET_ALL}")
            print(f"   Name: {self.user_info.get('name', 'N/A')}")
            print(f"   Email: {self.user_info.get('email', 'N/A')}")
            print(f"   Role: {self.user_info.get('role', 'user')}")
        
        if self.access_token:
            print(f"{Style.BRIGHT}Access Token:{Style.RESET_ALL} {self.access_token[:20]}...")
        
        print(f"{Style.BRIGHT}Available Test Tickers:{Style.RESET_ALL}")
        for i, ticker in enumerate(self.test_tickers, 1):
            print(f"   {i}. {ticker}")
    
    def run(self):
        """Run the simulator"""
        print(f"{Style.BRIGHT}{Fore.MAGENTA}")
        print("╔════════════════════════════════════════════════════════════╗")
        print("║                 AI MODEL ENDPOINT SIMULATOR                 ║")
        print("║                                                            ║")
        print("║  Interactive testing tool for AI trading platform APIs    ║")
        print("╚════════════════════════════════════════════════════════════╝")
        print(f"{Style.RESET_ALL}")
        
        # Check server status
        print(f"\n{Style.BRIGHT}Checking server status...{Style.RESET_ALL}")
        if not self.check_server_status():
            self.print_error("Server is not running or not accessible")
            self.print_info("Please start the server first: python run.py")
            return
        
        self.print_success(f"Server is running at {self.base_url}")
        
        # Authenticate
        if not self.authenticate():
            self.print_error("Authentication failed. Cannot proceed with authenticated endpoints.")
            return
        
        # Start interactive menu
        self.interactive_menu()

def main():
    """Main function"""
    # Check if server URL is provided as argument
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    
    simulator = AIModelSimulator(server_url)
    simulator.run()

if __name__ == "__main__":
    main()