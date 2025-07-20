"""
Simple AI Model Tester
======================

Lightweight testing tool for AI model endpoints without external dependencies.
Tests all Market Regime Classifier and other AI endpoints.

Usage: python simple_ai_tester.py

Requirements: Only built-in Python libraries (requests)
"""

import requests
import json
import time
import sys
from datetime import datetime

class SimpleAITester:
    """Simple AI model endpoint tester"""
    
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.access_token = None
        self.user_info = None
        
        # Test user credentials
        self.test_user = {
            "email": "tester@aimodel.com",
            "password": "testpass123",
            "name": "AI Model Tester"
        }
    
    def print_separator(self):
        """Print separator line"""
        print("-" * 60)
    
    def print_header(self, title):
        """Print header"""
        print("\n" + "=" * 60)
        print(f" {title} ".center(60))
        print("=" * 60)
    
    def make_request(self, method, endpoint, data=None, auth_required=True):
        """Make HTTP request"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.access_token:
            headers['Authorization'] = f"Bearer {self.access_token}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            else:
                print(f"[ERROR] Unsupported method: {method}")
                return None
            
            return response
        except Exception as e:
            print(f"[ERROR] Request failed: {str(e)}")
            return None
    
    def authenticate(self):
        """Authenticate user"""
        print("\n[INFO] Authenticating user...")
        
        # Register user
        print("  - Registering user...")
        response = self.make_request('POST', '/api/auth/register', data=self.test_user, auth_required=False)
        
        if response and response.status_code == 201:
            print("  - User registered successfully")
        elif response and response.status_code == 400:
            print("  - User already exists, proceeding to login")
        else:
            print(f"  - Registration failed: {response.text if response else 'No response'}")
        
        # Login user
        print("  - Logging in user...")
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        response = self.make_request('POST', '/api/auth/login', data=login_data, auth_required=False)
        
        if response and response.status_code == 200:
            result = response.json()
            self.access_token = result.get("access_token")
            self.user_info = result.get("user")
            print(f"  - Login successful! Welcome {self.user_info.get('name', 'User')}")
            return True
        else:
            print(f"  - Login failed: {response.text if response else 'No response'}")
            return False
    
    def test_market_regime_endpoints(self):
        """Test all market regime endpoints"""
        self.print_header("MARKET REGIME CLASSIFIER ENDPOINTS")
        
        endpoints = [
            {
                "name": "Regime Definitions",
                "method": "GET",
                "endpoint": "/api/market-regime/definitions",
                "auth_required": False,
                "description": "Get all market regime definitions"
            },
            {
                "name": "Model Info",
                "method": "GET",
                "endpoint": "/api/market-regime/model-info",
                "auth_required": True,
                "description": "Get model information and status"
            },
            {
                "name": "Regime Prediction",
                "method": "GET",
                "endpoint": "/api/market-regime/predict?ticker=RELIANCE.NS",
                "auth_required": True,
                "description": "Predict market regime for RELIANCE.NS"
            },
            {
                "name": "Regime Analysis",
                "method": "GET",
                "endpoint": "/api/market-regime/analysis?ticker=RELIANCE.NS",
                "auth_required": True,
                "description": "Get comprehensive regime analysis"
            },
            {
                "name": "Trading Recommendations",
                "method": "GET",
                "endpoint": "/api/market-regime/recommendations?ticker=RELIANCE.NS",
                "auth_required": True,
                "description": "Get trading recommendations based on regime"
            },
            {
                "name": "Multiple Predictions",
                "method": "POST",
                "endpoint": "/api/market-regime/multiple",
                "auth_required": True,
                "description": "Get regime predictions for multiple tickers",
                "data": {"tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]}
            },
            {
                "name": "Model Training",
                "method": "POST",
                "endpoint": "/api/market-regime/train",
                "auth_required": True,
                "description": "Train the model (admin only)",
                "data": {"ticker": "RELIANCE.NS", "period": "1y", "retrain": True}
            },
            {
                "name": "Model Evaluation",
                "method": "GET",
                "endpoint": "/api/market-regime/evaluate?ticker=RELIANCE.NS",
                "auth_required": True,
                "description": "Evaluate model performance (admin only)"
            }
        ]
        
        for i, endpoint_info in enumerate(endpoints, 1):
            print(f"\n{i}. {endpoint_info['name']}")
            print(f"   {endpoint_info['description']}")
            print(f"   {endpoint_info['method']} {endpoint_info['endpoint']}")
            
            response = self.make_request(
                endpoint_info['method'],
                endpoint_info['endpoint'],
                data=endpoint_info.get('data'),
                auth_required=endpoint_info['auth_required']
            )
            
            if response:
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        # Pretty print specific fields based on endpoint
                        if "definitions" in endpoint_info['endpoint']:
                            definitions = result.get('definitions', {})
                            print(f"   Regimes: {len(definitions)}")
                            for regime_id, info in definitions.items():
                                print(f"     {regime_id}: {info.get('name', 'Unknown')}")
                        
                        elif "model-info" in endpoint_info['endpoint']:
                            print(f"   Model Status: {result.get('status', 'Unknown')}")
                            print(f"   Model Loaded: {result.get('is_loaded', False)}")
                        
                        elif "predict" in endpoint_info['endpoint']:
                            print(f"   Regime: {result.get('regime_name', 'Unknown')}")
                            print(f"   Confidence: {result.get('confidence', 'N/A')}")
                        
                        elif "recommendations" in endpoint_info['endpoint']:
                            recommendations = result.get('recommendations', {})
                            print(f"   Strategy: {recommendations.get('strategy', 'Unknown')}")
                            print(f"   Risk Level: {recommendations.get('risk_level', 'Unknown')}")
                        
                        elif "multiple" in endpoint_info['endpoint']:
                            predictions = result.get('predictions', {})
                            print(f"   Predictions: {len(predictions)}")
                            for ticker, pred in predictions.items():
                                if pred.get('status') == 'success':
                                    print(f"     {ticker}: {pred.get('regime_name', 'Unknown')}")
                        
                        elif "train" in endpoint_info['endpoint']:
                            print(f"   Training Status: {result.get('status', 'Unknown')}")
                            if result.get('accuracy'):
                                print(f"   Accuracy: {result['accuracy']:.4f}")
                        
                        elif "evaluate" in endpoint_info['endpoint']:
                            print(f"   Evaluation Status: {result.get('status', 'Unknown')}")
                            if result.get('accuracy'):
                                print(f"   Accuracy: {result['accuracy']:.4f}")
                        
                        else:
                            print(f"   Response: {json.dumps(result, indent=2)[:200]}...")
                    
                    except json.JSONDecodeError:
                        print(f"   Response: {response.text[:200]}...")
                
                elif response.status_code == 401:
                    print("   [WARNING] Authentication required")
                elif response.status_code == 403:
                    print("   [WARNING] Admin access required")
                else:
                    print(f"   [ERROR] {response.text[:200]}...")
            else:
                print("   [ERROR] No response received")
    
    def test_technical_analysis_endpoints(self):
        """Test technical analysis endpoints"""
        self.print_header("TECHNICAL ANALYSIS ENDPOINTS")
        
        print("\n1. Technical Analysis")
        print("   Calculate technical indicators for a stock")
        print("   POST /api/technical-analysis")
        
        ta_data = {
            "ticker": "RELIANCE.NS",
            "indicators": ["rsi", "macd", "bollinger", "sma", "ema"],
            "parameters": {
                "rsi_period": 14,
                "macd_fastperiod": 12,
                "macd_slowperiod": 26,
                "sma_period": 20,
                "ema_period": 20
            }
        }
        
        response = self.make_request('POST', '/api/technical-analysis', data=ta_data)
        
        if response:
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    indicators = result.get('indicators', {})
                    print(f"   Indicators calculated: {len(indicators)}")
                    
                    for indicator, data in indicators.items():
                        if isinstance(data, dict):
                            if 'current' in data:
                                print(f"     {indicator.upper()}: {data['current']}")
                            elif 'signal' in data:
                                print(f"     {indicator.upper()}: {data['signal']}")
                except json.JSONDecodeError:
                    print(f"   Response: {response.text[:200]}...")
            else:
                print(f"   [ERROR] {response.text[:200]}...")
    
    def test_stock_data_endpoints(self):
        """Test stock data endpoints"""
        self.print_header("STOCK DATA ENDPOINTS")
        
        endpoints = [
            {
                "name": "Historical Data",
                "method": "GET",
                "endpoint": "/api/stock/RELIANCE/historical?period=1mo",
                "description": "Get historical stock data"
            },
            {
                "name": "Live Data",
                "method": "GET",
                "endpoint": "/api/live/RELIANCE",
                "description": "Get live stock data"
            },
            {
                "name": "Market Indices",
                "method": "GET",
                "endpoint": "/api/market-indices",
                "description": "Get market indices data"
            }
        ]
        
        for i, endpoint_info in enumerate(endpoints, 1):
            print(f"\n{i}. {endpoint_info['name']}")
            print(f"   {endpoint_info['description']}")
            print(f"   {endpoint_info['method']} {endpoint_info['endpoint']}")
            
            response = self.make_request(endpoint_info['method'], endpoint_info['endpoint'])
            
            if response:
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        
                        if "historical" in endpoint_info['endpoint']:
                            data_points = len(result.get('data', []))
                            print(f"   Data Points: {data_points}")
                        
                        elif "live" in endpoint_info['endpoint']:
                            ticker_data = result.get('RELIANCE', {})
                            if 'price' in ticker_data:
                                print(f"   Price: {ticker_data['price']}")
                        
                        elif "indices" in endpoint_info['endpoint']:
                            indices = result.get('indices', {})
                            print(f"   Indices: {len(indices)}")
                        
                    except json.JSONDecodeError:
                        print(f"   Response: {response.text[:200]}...")
                else:
                    print(f"   [ERROR] {response.text[:200]}...")
    
    def run_comprehensive_test(self):
        """Run comprehensive test of all endpoints"""
        print("=" * 60)
        print(" AI MODEL ENDPOINT COMPREHENSIVE TEST ".center(60))
        print("=" * 60)
        print(f"Testing server at: {self.base_url}")
        print(f"Test started at: {datetime.now()}")
        
        # Check server status
        print(f"\n[INFO] Checking server status...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                print("[SUCCESS] Server is running")
            else:
                print(f"[ERROR] Server returned status {response.status_code}")
                return
        except Exception as e:
            print(f"[ERROR] Cannot connect to server: {str(e)}")
            print("Please make sure the server is running: python run.py")
            return
        
        # Authenticate
        if not self.authenticate():
            print("[ERROR] Authentication failed")
            return
        
        # Test all endpoints
        try:
            self.test_market_regime_endpoints()
            self.test_technical_analysis_endpoints()
            self.test_stock_data_endpoints()
        except Exception as e:
            print(f"[ERROR] Test failed: {str(e)}")
        
        print(f"\n[INFO] Test completed at: {datetime.now()}")
    
    def interactive_test(self):
        """Interactive test mode"""
        print("=" * 60)
        print(" AI MODEL ENDPOINT INTERACTIVE TESTER ".center(60))
        print("=" * 60)
        
        # Check server and authenticate
        if not self.authenticate():
            return
        
        while True:
            print("\nChoose test category:")
            print("1. Market Regime Classifier Endpoints")
            print("2. Technical Analysis Endpoints")
            print("3. Stock Data Endpoints")
            print("4. Run All Tests")
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            
            if choice == '1':
                self.test_market_regime_endpoints()
            elif choice == '2':
                self.test_technical_analysis_endpoints()
            elif choice == '3':
                self.test_stock_data_endpoints()
            elif choice == '4':
                self.run_comprehensive_test()
            elif choice == '5':
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")
            
            input("\nPress Enter to continue...")

def main():
    """Main function"""
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    
    tester = SimpleAITester(server_url)
    
    print("Choose testing mode:")
    print("1. Comprehensive Test (run all tests)")
    print("2. Interactive Test (choose what to test)")
    
    choice = input("\nEnter your choice (1-2): ").strip()
    
    if choice == '1':
        tester.run_comprehensive_test()
    elif choice == '2':
        tester.interactive_test()
    else:
        print("Invalid choice. Running comprehensive test...")
        tester.run_comprehensive_test()

if __name__ == "__main__":
    main()