"""
Custom User AI Model Tester
============================

Allows you to specify your own credentials for testing AI model endpoints.
You can either modify the credentials in this file or provide them as input.

Usage: python custom_user_tester.py
"""

import requests
import json
import time
from datetime import datetime

class CustomUserTester:
    """AI model tester with custom user credentials"""
    
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.access_token = None
        self.test_results = []
        
        # You can modify these credentials or the script will ask for them
        self.test_user = {
            "email": "dasd@dfsdf.ocm",      # Your email
            "password": "123456",            # Your password
            "name": "Custom User"            # Your name
        }
    
    def get_user_credentials(self):
        """Get user credentials from input or use defaults"""
        print("=== Authentication Setup ===")
        print("Current credentials:")
        print(f"Email: {self.test_user['email']}")
        print(f"Password: {self.test_user['password']}")
        print(f"Name: {self.test_user['name']}")
        
        use_default = input("\nUse these credentials? (y/n): ").strip().lower()
        
        if use_default != 'y':
            print("\nEnter your credentials:")
            email = input("Email: ").strip()
            password = input("Password: ").strip()
            name = input("Name: ").strip()
            
            if email and password and name:
                self.test_user = {
                    "email": email,
                    "password": password,
                    "name": name
                }
                print("\nCredentials updated!")
            else:
                print("Invalid input. Using default credentials.")
    
    def log_result(self, test_name, status, message, details=None):
        """Log test result"""
        result = {
            "test_name": test_name,
            "status": status,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status_symbol = "+" if status == "PASS" else "-" if status == "FAIL" else "!"
        print(f"[{status}] {status_symbol} {test_name}: {message}")
    
    def make_request(self, method, endpoint, data=None, auth_required=True):
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if auth_required and self.access_token:
            headers['Authorization'] = f"Bearer {self.access_token}"
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            else:
                return None
            
            return response
        except Exception as e:
            print(f"Request error: {str(e)}")
            return None
    
    def authenticate(self):
        """Authenticate user with custom credentials"""
        print(f"\n{'='*50}")
        print("AUTHENTICATION")
        print(f"{'='*50}")
        
        print(f"Authenticating user: {self.test_user['email']}")
        
        # Try to register user first
        print("Attempting user registration...")
        response = self.make_request('POST', '/api/auth/register', data=self.test_user, auth_required=False)
        
        if response:
            if response.status_code == 201:
                print("+ User registered successfully")
            elif response.status_code == 400 and "already exists" in response.text:
                print("! User already exists, proceeding to login")
            else:
                print(f"- Registration failed: {response.text}")
        else:
            print("- Registration request failed")
        
        # Login user
        print("Attempting user login...")
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
                    print(f"+ Login successful!")
                    print(f"  Welcome: {user_info.get('name', 'User')}")
                    print(f"  Email: {user_info.get('email', 'Unknown')}")
                    print(f"  Role: {user_info.get('role', 'user')}")
                    return True
                else:
                    print("- Login failed: No access token received")
                    return False
            except:
                print("- Login failed: Invalid response format")
                return False
        else:
            print(f"- Login failed: {response.text if response else 'No response'}")
            return False
    
    def test_market_regime_endpoints(self):
        """Test all market regime endpoints"""
        print(f"\n{'='*50}")
        print("MARKET REGIME CLASSIFIER ENDPOINTS")
        print(f"{'='*50}")
        
        print("\n1. Testing Regime Definitions (no auth required)")
        response = self.make_request('GET', '/api/market-regime/definitions', auth_required=False)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                definitions = result.get('definitions', {})
                print(f"+ Found {len(definitions)} market regimes:")
                for regime_id, info in definitions.items():
                    print(f"  {regime_id}: {info.get('name', 'Unknown')}")
            except:
                print("- Invalid response format")
        else:
            print("- Failed to get regime definitions")
        
        print("\n2. Testing Model Information")
        response = self.make_request('GET', '/api/market-regime/model-info')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(f"+ Model Status: {result.get('status', 'Unknown')}")
                print(f"+ Model Loaded: {result.get('is_loaded', False)}")
                print(f"+ Supported Tickers: {len(result.get('supported_tickers', []))}")
            except:
                print("- Invalid response format")
        else:
            print("- Failed to get model info")
        
        print("\n3. Testing Regime Prediction")
        ticker = "RELIANCE.NS"
        response = self.make_request('GET', f'/api/market-regime/predict?ticker={ticker}')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                regime_name = result.get('regime_name', 'Unknown')
                confidence = result.get('confidence', 0)
                print(f"+ Prediction for {ticker}:")
                print(f"  Regime: {regime_name}")
                print(f"  Confidence: {confidence:.2f}")
                print(f"  Description: {result.get('regime_description', 'N/A')}")
            except:
                print("- Invalid response format")
        else:
            print("- Failed to get regime prediction")
        
        print("\n4. Testing Trading Recommendations")
        response = self.make_request('GET', f'/api/market-regime/recommendations?ticker={ticker}')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                recommendations = result.get('recommendations', {})
                print(f"+ Trading Recommendations for {ticker}:")
                print(f"  Strategy: {recommendations.get('strategy', 'Unknown')}")
                print(f"  Risk Level: {recommendations.get('risk_level', 'Unknown')}")
                print(f"  Position Size: {recommendations.get('position_size', 'Unknown')}")
                print(f"  Notes: {recommendations.get('notes', 'N/A')}")
            except:
                print("- Invalid response format")
        else:
            print("- Failed to get recommendations")
        
        print("\n5. Testing Multiple Predictions")
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
        data = {"tickers": tickers}
        response = self.make_request('POST', '/api/market-regime/multiple', data=data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                predictions = result.get('predictions', {})
                print(f"+ Multiple Predictions Results:")
                for ticker, pred in predictions.items():
                    if pred.get('status') == 'success':
                        print(f"  {ticker}: {pred.get('regime_name', 'Unknown')} ({pred.get('confidence', 0):.2f})")
                    else:
                        print(f"  {ticker}: Error - {pred.get('message', 'Unknown')}")
            except:
                print("- Invalid response format")
        else:
            print("- Failed to get multiple predictions")
        
        print("\n6. Testing Model Training (Admin Only)")
        train_data = {"ticker": "RELIANCE.NS", "period": "1y", "retrain": True}
        response = self.make_request('POST', '/api/market-regime/train', data=train_data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                print(f"+ Training Status: {result.get('status', 'Unknown')}")
                if result.get('accuracy'):
                    print(f"+ Training Accuracy: {result['accuracy']:.4f}")
                    print(f"+ Training Samples: {result.get('training_samples', 'N/A')}")
            except:
                print("- Invalid response format")
        elif response and response.status_code == 403:
            print("! Training requires admin access (expected for regular users)")
        else:
            print("- Training failed")
    
    def test_other_endpoints(self):
        """Test other important endpoints"""
        print(f"\n{'='*50}")
        print("OTHER ENDPOINTS")
        print(f"{'='*50}")
        
        print("\n1. Testing Technical Analysis")
        ta_data = {
            "ticker": "RELIANCE.NS",
            "indicators": ["rsi", "macd", "bollinger"]
        }
        response = self.make_request('POST', '/api/technical-analysis', data=ta_data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                indicators = result.get('indicators', {})
                print(f"+ Technical Analysis Results:")
                for indicator, data in indicators.items():
                    if isinstance(data, dict) and 'current' in data:
                        print(f"  {indicator.upper()}: {data['current']}")
            except:
                print("- Invalid response format")
        else:
            print("- Technical analysis failed")
        
        print("\n2. Testing Historical Data")
        response = self.make_request('GET', '/api/stock/RELIANCE/historical?period=1mo')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                data_points = len(result.get('data', []))
                print(f"+ Historical Data: {data_points} data points retrieved")
            except:
                print("- Invalid response format")
        else:
            print("- Historical data failed")
        
        print("\n3. Testing Live Data")
        response = self.make_request('GET', '/api/live/RELIANCE')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                ticker_data = result.get('RELIANCE', {})
                if 'price' in ticker_data:
                    print(f"+ Live Data: Price = {ticker_data['price']}")
                else:
                    print("- No price data in response")
            except:
                print("- Invalid response format")
        else:
            print("- Live data failed")
    
    def check_server_status(self):
        """Check if server is running"""
        print("Checking server status...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                print("+ Server is running")
                return True
            else:
                print(f"- Server returned status {response.status_code}")
                return False
        except Exception as e:
            print(f"- Cannot connect to server: {str(e)}")
            return False
    
    def run_tests(self):
        """Run all tests with custom user"""
        print("="*60)
        print(" CUSTOM USER AI MODEL ENDPOINT TESTER ".center(60))
        print("="*60)
        print(f"Testing server: {self.base_url}")
        print(f"Started: {datetime.now()}")
        
        # Check server
        if not self.check_server_status():
            print("\n[ERROR] Server is not running!")
            print("Please start the server first: python run.py")
            return
        
        # Get user credentials
        self.get_user_credentials()
        
        # Authenticate
        if not self.authenticate():
            print("\n[ERROR] Authentication failed!")
            return
        
        # Run tests
        try:
            self.test_market_regime_endpoints()
            self.test_other_endpoints()
            
            print(f"\n{'='*60}")
            print(" TEST COMPLETED ".center(60))
            print(f"{'='*60}")
            print(f"Completed: {datetime.now()}")
            print("\n[SUCCESS] All tests completed successfully!")
            
        except Exception as e:
            print(f"\n[ERROR] Test failed: {str(e)}")

def main():
    """Main function"""
    tester = CustomUserTester()
    tester.run_tests()

if __name__ == "__main__":
    main()