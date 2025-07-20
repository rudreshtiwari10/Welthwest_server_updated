"""
Configuration-Based AI Model Tester
====================================

Reads user credentials and settings from test_config.json file.
Easy to modify credentials without changing code.

Usage: python config_based_tester.py

Configuration: Edit test_config.json to change credentials and settings
"""

import requests
import json
import time
import os
from datetime import datetime

class ConfigBasedTester:
    """AI model tester using configuration file"""
    
    def __init__(self, config_file="test_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.access_token = None
        
        # Load from config
        self.base_url = self.config.get("server_url", "http://127.0.0.1:8000")
        self.test_user = self.config.get("test_user", {})
        self.test_settings = self.config.get("test_settings", {})
        
        print(f"Configuration loaded from: {config_file}")
        print(f"Server URL: {self.base_url}")
        print(f"Test User: {self.test_user.get('email', 'Unknown')}")
    
    def load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                print(f"Config file {self.config_file} not found. Using defaults.")
                return self.get_default_config()
        except Exception as e:
            print(f"Error loading config: {str(e)}. Using defaults.")
            return self.get_default_config()
    
    def get_default_config(self):
        """Get default configuration"""
        return {
            "server_url": "http://127.0.0.1:8000",
            "test_user": {
                "email": "test@example.com",
                "password": "testpass123",
                "name": "Test User"
            },
            "test_settings": {
                "default_ticker": "RELIANCE.NS",
                "test_tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"],
                "timeout": 30,
                "retry_attempts": 3
            }
        }
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"Configuration saved to: {self.config_file}")
        except Exception as e:
            print(f"Error saving config: {str(e)}")
    
    def make_request(self, method, endpoint, data=None, auth_required=True):
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.access_token:
            headers['Authorization'] = f"Bearer {self.access_token}"
        
        timeout = self.test_settings.get('timeout', 30)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            else:
                return None
            
            return response
        except Exception as e:
            print(f"Request error: {str(e)}")
            return None
    
    def authenticate(self):
        """Authenticate user using config credentials"""
        print(f"\n{'='*50}")
        print("AUTHENTICATION")
        print(f"{'='*50}")
        
        if not self.test_user.get('email') or not self.test_user.get('password'):
            print("ERROR: Missing email or password in configuration")
            return False
        
        print(f"Authenticating: {self.test_user['email']}")
        
        # Register user
        print("Registering user...")
        response = self.make_request('POST', '/api/auth/register', data=self.test_user, auth_required=False)
        
        if response:
            if response.status_code == 201:
                print("✓ User registered successfully")
            elif response.status_code == 400:
                print("ℹ User already exists")
            else:
                print(f"✗ Registration failed: {response.status_code}")
        
        # Login user
        print("Logging in...")
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        response = self.make_request('POST', '/api/auth/login', data=login_data, auth_required=False)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                self.access_token = result.get("access_token")
                user_info = result.get("user", {})
                
                if self.access_token:
                    print("✓ Login successful!")
                    print(f"  Name: {user_info.get('name', 'Unknown')}")
                    print(f"  Email: {user_info.get('email', 'Unknown')}")
                    print(f"  Role: {user_info.get('role', 'user')}")
                    print(f"  Token: {self.access_token[:20]}...")
                    return True
                else:
                    print("✗ Login failed: No access token")
                    return False
            except:
                print("✗ Login failed: Invalid response")
                return False
        else:
            print(f"✗ Login failed: {response.status_code if response else 'No response'}")
            return False
    
    def test_market_regime_endpoints(self):
        """Test market regime endpoints"""
        print(f"\n{'='*50}")
        print("MARKET REGIME CLASSIFIER TESTS")
        print(f"{'='*50}")
        
        default_ticker = self.test_settings.get('default_ticker', 'RELIANCE.NS')
        test_tickers = self.test_settings.get('test_tickers', ['RELIANCE.NS', 'TCS.NS'])
        
        # Test 1: Regime definitions
        print("\n1. Testing Regime Definitions")
        response = self.make_request('GET', '/api/market-regime/definitions', auth_required=False)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                definitions = result.get('definitions', {})
                print(f"✓ Found {len(definitions)} regimes:")
                for regime_id, info in definitions.items():
                    print(f"   {regime_id}: {info.get('name', 'Unknown')}")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Failed to get regime definitions")
        
        # Test 2: Model info
        print("\n2. Testing Model Info")
        response = self.make_request('GET', '/api/market-regime/model-info')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(f"✓ Model Status: {result.get('status', 'Unknown')}")
                print(f"✓ Model Loaded: {result.get('is_loaded', False)}")
                print(f"✓ Supported Tickers: {len(result.get('supported_tickers', []))}")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Failed to get model info")
        
        # Test 3: Single prediction
        print(f"\n3. Testing Single Prediction ({default_ticker})")
        response = self.make_request('GET', f'/api/market-regime/predict?ticker={default_ticker}')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(f"✓ Regime: {result.get('regime_name', 'Unknown')}")
                print(f"✓ Confidence: {result.get('confidence', 0):.2f}")
                print(f"✓ Description: {result.get('regime_description', 'N/A')}")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Failed to get prediction")
        
        # Test 4: Multiple predictions
        print(f"\n4. Testing Multiple Predictions")
        data = {"tickers": test_tickers}
        response = self.make_request('POST', '/api/market-regime/multiple', data=data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                predictions = result.get('predictions', {})
                print(f"✓ Predictions for {len(predictions)} tickers:")
                for ticker, pred in predictions.items():
                    if pred.get('status') == 'success':
                        print(f"   {ticker}: {pred.get('regime_name', 'Unknown')} ({pred.get('confidence', 0):.2f})")
                    else:
                        print(f"   {ticker}: Error")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Failed to get multiple predictions")
        
        # Test 5: Recommendations
        print(f"\n5. Testing Recommendations ({default_ticker})")
        response = self.make_request('GET', f'/api/market-regime/recommendations?ticker={default_ticker}')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                recommendations = result.get('recommendations', {})
                print(f"✓ Strategy: {recommendations.get('strategy', 'Unknown')}")
                print(f"✓ Risk Level: {recommendations.get('risk_level', 'Unknown')}")
                print(f"✓ Position Size: {recommendations.get('position_size', 'Unknown')}")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Failed to get recommendations")
        
        # Test 6: Analysis
        print(f"\n6. Testing Analysis ({default_ticker})")
        response = self.make_request('GET', f'/api/market-regime/analysis?ticker={default_ticker}')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                if result.get('status') == 'success':
                    print("✓ Analysis completed successfully")
                    if result.get('historical_analysis'):
                        hist = result['historical_analysis']
                        print(f"   Historical periods: {hist.get('total_periods', 'N/A')}")
                else:
                    print("✗ Analysis failed")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Failed to get analysis")
        
        # Test 7: Training (admin only)
        print(f"\n7. Testing Training ({default_ticker})")
        train_data = {"ticker": default_ticker, "period": "1y", "retrain": True}
        response = self.make_request('POST', '/api/market-regime/train', data=train_data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(f"✓ Training Status: {result.get('status', 'Unknown')}")
                if result.get('accuracy'):
                    print(f"✓ Accuracy: {result['accuracy']:.4f}")
            except:
                print("✗ Invalid response format")
        elif response and response.status_code == 403:
            print("ℹ Admin access required (expected)")
        else:
            print("✗ Training failed")
    
    def test_other_endpoints(self):
        """Test other endpoints"""
        print(f"\n{'='*50}")
        print("OTHER ENDPOINT TESTS")
        print(f"{'='*50}")
        
        default_ticker = self.test_settings.get('default_ticker', 'RELIANCE.NS')
        ticker_symbol = default_ticker.replace('.NS', '').replace('.BO', '')
        
        # Test technical analysis
        print("\n1. Testing Technical Analysis")
        ta_data = {
            "ticker": default_ticker,
            "indicators": ["rsi", "macd", "bollinger"]
        }
        response = self.make_request('POST', '/api/technical-analysis', data=ta_data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                indicators = result.get('indicators', {})
                print(f"✓ Calculated {len(indicators)} indicators")
                for indicator, data in indicators.items():
                    if isinstance(data, dict) and 'current' in data:
                        print(f"   {indicator.upper()}: {data['current']}")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Technical analysis failed")
        
        # Test historical data
        print("\n2. Testing Historical Data")
        response = self.make_request('GET', f'/api/stock/{ticker_symbol}/historical?period=1mo')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                data_points = len(result.get('data', []))
                print(f"✓ Retrieved {data_points} data points")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Historical data failed")
        
        # Test live data
        print("\n3. Testing Live Data")
        response = self.make_request('GET', f'/api/live/{ticker_symbol}')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                ticker_data = result.get(ticker_symbol, {})
                if 'price' in ticker_data:
                    print(f"✓ Live price: {ticker_data['price']}")
                else:
                    print("✗ No price data")
            except:
                print("✗ Invalid response format")
        else:
            print("✗ Live data failed")
    
    def run_comprehensive_test(self):
        """Run comprehensive test suite"""
        print("="*60)
        print(" CONFIGURATION-BASED AI MODEL TESTER ".center(60))
        print("="*60)
        print(f"Started: {datetime.now()}")
        
        # Check server
        print("\nChecking server connection...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                print("✓ Server is running")
            else:
                print(f"✗ Server returned status {response.status_code}")
                return
        except Exception as e:
            print(f"✗ Cannot connect to server: {str(e)}")
            print("Please start the server: python run.py")
            return
        
        # Authenticate
        if not self.authenticate():
            print("\nAuthentication failed. Cannot continue.")
            return
        
        # Run tests
        try:
            self.test_market_regime_endpoints()
            self.test_other_endpoints()
            
            print(f"\n{'='*60}")
            print(" TEST COMPLETED SUCCESSFULLY ".center(60))
            print(f"{'='*60}")
            print(f"Completed: {datetime.now()}")
            
        except Exception as e:
            print(f"\n✗ Test suite failed: {str(e)}")

def main():
    """Main function"""
    print("Configuration-Based AI Model Tester")
    print("====================================")
    
    config_file = "test_config.json"
    
    if not os.path.exists(config_file):
        print(f"\nConfig file '{config_file}' not found.")
        print("Creating default configuration...")
        
        # Create default config
        tester = ConfigBasedTester(config_file)
        tester.save_config()
        
        print(f"\nPlease edit '{config_file}' to set your credentials:")
        print("- email: Your email address")
        print("- password: Your password")
        print("- name: Your name")
        print("\nThen run this script again.")
        return
    
    # Run tests
    tester = ConfigBasedTester(config_file)
    tester.run_comprehensive_test()

if __name__ == "__main__":
    main()