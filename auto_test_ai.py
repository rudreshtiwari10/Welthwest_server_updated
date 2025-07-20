"""
Automatic AI Model Endpoint Tester
===================================

Automatically tests all AI model endpoints without requiring user input.
Perfect for automated testing and CI/CD pipelines.

Usage: python auto_test_ai.py
"""

import requests
import json
import time
from datetime import datetime

class AutoAITester:
    """Automatic AI model endpoint tester"""
    
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.access_token = None
        self.test_results = []
        
        # Test user credentials
        self.test_user = {
            "email": "dasd@dfsdf.ocm",
            "password": "123456",
            "name": "Auto AI Tester"
        }
    
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
            return None
    
    def authenticate(self):
        """Authenticate user"""
        print("\n" + "="*50)
        print("AUTHENTICATION TESTS")
        print("="*50)
        
        # Test user registration
        response = self.make_request('POST', '/api/auth/register', data=self.test_user, auth_required=False)
        
        if response and response.status_code in [201, 400]:
            self.log_result("User Registration", "PASS", "User registration endpoint working")
        else:
            self.log_result("User Registration", "FAIL", "User registration failed")
            return False
        
        # Test user login
        login_data = {
            "email": self.test_user["email"],
            "password": self.test_user["password"]
        }
        
        response = self.make_request('POST', '/api/auth/login', data=login_data, auth_required=False)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                self.access_token = result.get("access_token")
                
                if self.access_token:
                    self.log_result("User Login", "PASS", "Login successful, token received")
                    return True
                else:
                    self.log_result("User Login", "FAIL", "Login failed, no token received")
                    return False
            except:
                self.log_result("User Login", "FAIL", "Login failed, invalid response")
                return False
        else:
            self.log_result("User Login", "FAIL", "Login endpoint failed")
            return False
    
    def test_market_regime_endpoints(self):
        """Test all market regime endpoints"""
        print("\n" + "="*50)
        print("MARKET REGIME CLASSIFIER TESTS")
        print("="*50)
        
        # Test 1: Regime definitions (no auth)
        response = self.make_request('GET', '/api/market-regime/definitions', auth_required=False)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                definitions = result.get('definitions', {})
                if len(definitions) == 5:
                    self.log_result("Regime Definitions", "PASS", f"All 5 regimes defined: {list(definitions.keys())}")
                else:
                    self.log_result("Regime Definitions", "WARN", f"Expected 5 regimes, got {len(definitions)}")
            except:
                self.log_result("Regime Definitions", "FAIL", "Invalid response format")
        else:
            self.log_result("Regime Definitions", "FAIL", "Endpoint not accessible")
        
        # Test 2: Model info
        response = self.make_request('GET', '/api/market-regime/model-info')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                status = result.get('status', 'unknown')
                is_loaded = result.get('is_loaded', False)
                
                if status == 'trained' and is_loaded:
                    self.log_result("Model Info", "PASS", "Model is trained and loaded")
                else:
                    self.log_result("Model Info", "WARN", f"Model status: {status}, loaded: {is_loaded}")
            except:
                self.log_result("Model Info", "FAIL", "Invalid response format")
        else:
            self.log_result("Model Info", "FAIL", "Endpoint not accessible")
        
        # Test 3: Regime prediction
        response = self.make_request('GET', '/api/market-regime/predict?ticker=RELIANCE.NS')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                regime_name = result.get('regime_name')
                confidence = result.get('confidence')
                
                if regime_name and confidence:
                    self.log_result("Regime Prediction", "PASS", f"Predicted {regime_name} with {confidence:.2f} confidence")
                else:
                    self.log_result("Regime Prediction", "FAIL", "Missing regime name or confidence")
            except:
                self.log_result("Regime Prediction", "FAIL", "Invalid response format")
        else:
            self.log_result("Regime Prediction", "FAIL", "Endpoint not accessible")
        
        # Test 4: Analysis
        response = self.make_request('GET', '/api/market-regime/analysis?ticker=RELIANCE.NS')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                if result.get('status') == 'success':
                    self.log_result("Regime Analysis", "PASS", "Analysis completed successfully")
                else:
                    self.log_result("Regime Analysis", "FAIL", "Analysis failed")
            except:
                self.log_result("Regime Analysis", "FAIL", "Invalid response format")
        else:
            self.log_result("Regime Analysis", "FAIL", "Endpoint not accessible")
        
        # Test 5: Recommendations
        response = self.make_request('GET', '/api/market-regime/recommendations?ticker=RELIANCE.NS')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                recommendations = result.get('recommendations', {})
                strategy = recommendations.get('strategy')
                
                if strategy:
                    self.log_result("Trading Recommendations", "PASS", f"Strategy: {strategy}")
                else:
                    self.log_result("Trading Recommendations", "FAIL", "No strategy in recommendations")
            except:
                self.log_result("Trading Recommendations", "FAIL", "Invalid response format")
        else:
            self.log_result("Trading Recommendations", "FAIL", "Endpoint not accessible")
        
        # Test 6: Multiple predictions
        data = {"tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]}
        response = self.make_request('POST', '/api/market-regime/multiple', data=data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                predictions = result.get('predictions', {})
                
                if len(predictions) == 3:
                    successful = sum(1 for p in predictions.values() if p.get('status') == 'success')
                    self.log_result("Multiple Predictions", "PASS", f"Predicted {successful}/3 tickers successfully")
                else:
                    self.log_result("Multiple Predictions", "FAIL", f"Expected 3 predictions, got {len(predictions)}")
            except:
                self.log_result("Multiple Predictions", "FAIL", "Invalid response format")
        else:
            self.log_result("Multiple Predictions", "FAIL", "Endpoint not accessible")
        
        # Test 7: Model training (might fail for non-admin)
        data = {"ticker": "RELIANCE.NS", "period": "1y", "retrain": True}
        response = self.make_request('POST', '/api/market-regime/train', data=data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                if result.get('status') == 'success':
                    accuracy = result.get('accuracy', 0)
                    self.log_result("Model Training", "PASS", f"Training successful with {accuracy:.2f} accuracy")
                else:
                    self.log_result("Model Training", "FAIL", "Training failed")
            except:
                self.log_result("Model Training", "FAIL", "Invalid response format")
        elif response and response.status_code == 403:
            self.log_result("Model Training", "WARN", "Admin access required (expected for test user)")
        else:
            self.log_result("Model Training", "FAIL", "Endpoint not accessible")
        
        # Test 8: Model evaluation (might fail for non-admin)
        response = self.make_request('GET', '/api/market-regime/evaluate?ticker=RELIANCE.NS')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                if result.get('status') == 'success':
                    accuracy = result.get('accuracy', 0)
                    self.log_result("Model Evaluation", "PASS", f"Evaluation successful with {accuracy:.2f} accuracy")
                else:
                    self.log_result("Model Evaluation", "FAIL", "Evaluation failed")
            except:
                self.log_result("Model Evaluation", "FAIL", "Invalid response format")
        elif response and response.status_code == 403:
            self.log_result("Model Evaluation", "WARN", "Admin access required (expected for test user)")
        else:
            self.log_result("Model Evaluation", "FAIL", "Endpoint not accessible")
    
    def test_technical_analysis_endpoints(self):
        """Test technical analysis endpoints"""
        print("\n" + "="*50)
        print("TECHNICAL ANALYSIS TESTS")
        print("="*50)
        
        data = {
            "ticker": "RELIANCE.NS",
            "indicators": ["rsi", "macd", "bollinger"]
        }
        
        response = self.make_request('POST', '/api/technical-analysis', data=data)
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                indicators = result.get('indicators', {})
                
                if len(indicators) >= 3:
                    self.log_result("Technical Analysis", "PASS", f"Calculated {len(indicators)} indicators")
                else:
                    self.log_result("Technical Analysis", "WARN", f"Expected 3+ indicators, got {len(indicators)}")
            except:
                self.log_result("Technical Analysis", "FAIL", "Invalid response format")
        else:
            self.log_result("Technical Analysis", "FAIL", "Endpoint not accessible")
    
    def test_stock_data_endpoints(self):
        """Test stock data endpoints"""
        print("\n" + "="*50)
        print("STOCK DATA TESTS")
        print("="*50)
        
        # Test historical data
        response = self.make_request('GET', '/api/stock/RELIANCE/historical?period=1mo')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                data_points = len(result.get('data', []))
                
                if data_points > 0:
                    self.log_result("Historical Data", "PASS", f"Retrieved {data_points} data points")
                else:
                    self.log_result("Historical Data", "FAIL", "No historical data returned")
            except:
                self.log_result("Historical Data", "FAIL", "Invalid response format")
        else:
            self.log_result("Historical Data", "FAIL", "Endpoint not accessible")
        
        # Test live data
        response = self.make_request('GET', '/api/live/RELIANCE')
        
        if response and response.status_code == 200:
            try:
                result = response.json()
                ticker_data = result.get('RELIANCE', {})
                
                if 'price' in ticker_data:
                    self.log_result("Live Data", "PASS", f"Retrieved live price: {ticker_data['price']}")
                else:
                    self.log_result("Live Data", "FAIL", "No price data returned")
            except:
                self.log_result("Live Data", "FAIL", "Invalid response format")
        else:
            self.log_result("Live Data", "FAIL", "Endpoint not accessible")
    
    def check_server_status(self):
        """Check if server is running"""
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def run_all_tests(self):
        """Run all tests automatically"""
        print("="*60)
        print(" AUTOMATIC AI MODEL ENDPOINT TEST SUITE ".center(60))
        print("="*60)
        print(f"Testing server: {self.base_url}")
        print(f"Test started: {datetime.now()}")
        
        # Check server status
        if not self.check_server_status():
            print("\n[FATAL] Server is not running or not accessible!")
            print("Please start the server first: python run.py")
            return False
        
        print("\n[INFO] Server is running")
        
        # Run all tests
        try:
            # Authenticate first
            if not self.authenticate():
                print("\n[FATAL] Authentication failed - cannot test authenticated endpoints")
                return False
            
            # Test all endpoints
            self.test_market_regime_endpoints()
            self.test_technical_analysis_endpoints()
            self.test_stock_data_endpoints()
            
            # Generate summary
            self.generate_test_summary()
            return True
            
        except Exception as e:
            print(f"\n[FATAL] Test suite failed: {str(e)}")
            return False
    
    def generate_test_summary(self):
        """Generate test summary"""
        print("\n" + "="*60)
        print(" TEST SUMMARY ".center(60))
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['status'] == 'PASS')
        failed_tests = sum(1 for r in self.test_results if r['status'] == 'FAIL')
        warning_tests = sum(1 for r in self.test_results if r['status'] == 'WARN')
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Warnings: {warning_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print(f"\nFailed Tests:")
            for result in self.test_results:
                if result['status'] == 'FAIL':
                    print(f"  - {result['test_name']}: {result['message']}")
        
        if warning_tests > 0:
            print(f"\nWarnings:")
            for result in self.test_results:
                if result['status'] == 'WARN':
                    print(f"  - {result['test_name']}: {result['message']}")
        
        print(f"\nTest completed: {datetime.now()}")
        
        # Overall status
        if failed_tests == 0:
            print("\n[SUCCESS] ALL TESTS PASSED! AI Model endpoints are working correctly.")
        else:
            print(f"\n[WARNING] {failed_tests} tests failed. Please check the issues above.")

def main():
    """Main function"""
    import sys
    
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    
    tester = AutoAITester(server_url)
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()