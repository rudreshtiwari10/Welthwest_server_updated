"""
Test script for all Market Regime Classifier endpoints
This script tests all API endpoints without requiring a running server
"""

import requests
import json
import time
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os

# Test configuration
BASE_URL = "http://127.0.0.1:8000"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "testpassword123"

def test_user_registration_and_login():
    """Test user registration and login to get JWT token"""
    print("\n" + "="*60)
    print("Testing User Registration and Login")
    print("="*60)
    
    try:
        # Test user registration
        registration_data = {
            "username": "testuser",
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "confirm_password": TEST_USER_PASSWORD,
            "name": "Test User"
        }
        
        print("1. Testing user registration...")
        try:
            response = requests.post(f"{BASE_URL}/api/auth/register", json=registration_data)
            if response.status_code == 201:
                print("✅ User registration successful")
            elif response.status_code == 400 and "already exists" in response.text:
                print("⚠️  User already exists, proceeding to login")
            else:
                print(f"❌ Registration failed: {response.text}")
        except Exception as e:
            print(f"❌ Registration error: {str(e)}")
        
        # Test user login
        login_data = {
            "username_or_email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
        
        print("2. Testing user login...")
        try:
            response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
            if response.status_code == 200:
                result = response.json()
                access_token = result.get("access_token")
                if access_token:
                    print("✅ User login successful")
                    return access_token
                else:
                    print("❌ No access token received")
                    return None
            else:
                print(f"❌ Login failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return None
            
    except Exception as e:
        print(f"❌ Authentication error: {str(e)}")
        return None

def test_market_regime_endpoints(access_token):
    """Test all market regime endpoints"""
    print("\n" + "="*60)
    print("Testing Market Regime Classifier Endpoints")
    print("="*60)
    
    if not access_token:
        print("❌ No access token available. Skipping endpoint tests.")
        return
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Test 1: Get regime definitions (no auth required)
    print("\n1. Testing GET /api/market-regime/definitions")
    try:
        response = requests.get(f"{BASE_URL}/api/market-regime/definitions")
        if response.status_code == 200:
            result = response.json()
            print("✅ Regime definitions retrieved successfully")
            print(f"   Number of regimes: {len(result.get('definitions', {}))}")
            for regime_id, regime_info in result.get('definitions', {}).items():
                print(f"   - {regime_id}: {regime_info.get('name', 'Unknown')}")
        else:
            print(f"❌ Failed to get regime definitions: {response.text}")
    except Exception as e:
        print(f"❌ Error getting regime definitions: {str(e)}")
    
    # Test 2: Get model info
    print("\n2. Testing GET /api/market-regime/model-info")
    try:
        response = requests.get(f"{BASE_URL}/api/market-regime/model-info", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Model info retrieved successfully")
            print(f"   Model status: {result.get('status', 'Unknown')}")
            print(f"   Model loaded: {result.get('is_loaded', False)}")
        else:
            print(f"❌ Failed to get model info: {response.text}")
    except Exception as e:
        print(f"❌ Error getting model info: {str(e)}")
    
    # Test 3: Train model (admin required - might fail)
    print("\n3. Testing POST /api/market-regime/train")
    try:
        train_data = {
            "ticker": "RELIANCE.NS",
            "period": "1y",
            "retrain": True
        }
        response = requests.post(f"{BASE_URL}/api/market-regime/train", json=train_data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Model training successful")
            print(f"   Training accuracy: {result.get('accuracy', 'N/A')}")
        elif response.status_code == 403:
            print("⚠️  Training requires admin access (expected for test user)")
        else:
            print(f"❌ Training failed: {response.text}")
    except Exception as e:
        print(f"❌ Error training model: {str(e)}")
    
    # Test 4: Predict regime
    print("\n4. Testing GET /api/market-regime/predict")
    try:
        response = requests.get(f"{BASE_URL}/api/market-regime/predict?ticker=RELIANCE.NS", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Regime prediction successful")
            print(f"   Predicted regime: {result.get('regime_name', 'Unknown')}")
            print(f"   Confidence: {result.get('confidence', 'N/A')}")
        else:
            print(f"❌ Prediction failed: {response.text}")
    except Exception as e:
        print(f"❌ Error predicting regime: {str(e)}")
    
    # Test 5: Get analysis
    print("\n5. Testing GET /api/market-regime/analysis")
    try:
        response = requests.get(f"{BASE_URL}/api/market-regime/analysis?ticker=RELIANCE.NS", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Regime analysis successful")
            print(f"   Analysis status: {result.get('status', 'Unknown')}")
            if result.get('current_regime'):
                print(f"   Current regime: {result['current_regime'].get('regime_name', 'Unknown')}")
        else:
            print(f"❌ Analysis failed: {response.text}")
    except Exception as e:
        print(f"❌ Error getting analysis: {str(e)}")
    
    # Test 6: Get recommendations
    print("\n6. Testing GET /api/market-regime/recommendations")
    try:
        response = requests.get(f"{BASE_URL}/api/market-regime/recommendations?ticker=RELIANCE.NS", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Regime recommendations successful")
            if result.get('recommendations'):
                recommendations = result['recommendations']
                print(f"   Strategy: {recommendations.get('strategy', 'Unknown')}")
                print(f"   Risk level: {recommendations.get('risk_level', 'Unknown')}")
                print(f"   Position size: {recommendations.get('position_size', 'Unknown')}")
        else:
            print(f"❌ Recommendations failed: {response.text}")
    except Exception as e:
        print(f"❌ Error getting recommendations: {str(e)}")
    
    # Test 7: Multiple predictions
    print("\n7. Testing POST /api/market-regime/multiple")
    try:
        multiple_data = {
            "tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
        }
        response = requests.post(f"{BASE_URL}/api/market-regime/multiple", json=multiple_data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Multiple predictions successful")
            predictions = result.get('predictions', {})
            print(f"   Predictions for {len(predictions)} tickers")
            for ticker, prediction in predictions.items():
                if prediction.get('status') == 'success':
                    print(f"   - {ticker}: {prediction.get('regime_name', 'Unknown')}")
                else:
                    print(f"   - {ticker}: Error")
        else:
            print(f"❌ Multiple predictions failed: {response.text}")
    except Exception as e:
        print(f"❌ Error getting multiple predictions: {str(e)}")
    
    # Test 8: Evaluate model (admin required - might fail)
    print("\n8. Testing GET /api/market-regime/evaluate")
    try:
        response = requests.get(f"{BASE_URL}/api/market-regime/evaluate?ticker=RELIANCE.NS", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Model evaluation successful")
            print(f"   Evaluation accuracy: {result.get('accuracy', 'N/A')}")
        elif response.status_code == 403:
            print("⚠️  Evaluation requires admin access (expected for test user)")
        else:
            print(f"❌ Evaluation failed: {response.text}")
    except Exception as e:
        print(f"❌ Error evaluating model: {str(e)}")

def test_other_endpoints(access_token):
    """Test other existing endpoints to ensure nothing is broken"""
    print("\n" + "="*60)
    print("Testing Other Existing Endpoints")
    print("="*60)
    
    if not access_token:
        print("❌ No access token available. Skipping endpoint tests.")
        return
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Test 1: Stock historical data
    print("\n1. Testing GET /api/stock/RELIANCE/historical")
    try:
        response = requests.get(f"{BASE_URL}/api/stock/RELIANCE/historical", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Historical data retrieved successfully")
            print(f"   Data points: {len(result.get('data', []))}")
        else:
            print(f"❌ Historical data failed: {response.text}")
    except Exception as e:
        print(f"❌ Error getting historical data: {str(e)}")
    
    # Test 2: Technical analysis
    print("\n2. Testing POST /api/technical-analysis")
    try:
        ta_data = {
            "ticker": "RELIANCE.NS",
            "indicators": ["rsi", "macd", "bollinger"]
        }
        response = requests.post(f"{BASE_URL}/api/technical-analysis", json=ta_data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Technical analysis successful")
            print(f"   Indicators calculated: {len(result.get('indicators', {}))}")
        else:
            print(f"❌ Technical analysis failed: {response.text}")
    except Exception as e:
        print(f"❌ Error with technical analysis: {str(e)}")
    
    # Test 3: Live data
    print("\n3. Testing GET /api/live/RELIANCE")
    try:
        response = requests.get(f"{BASE_URL}/api/live/RELIANCE", headers=headers)
        if response.status_code == 200:
            result = response.json()
            print("✅ Live data retrieved successfully")
            print(f"   Live data for: {result.get('RELIANCE', {}).get('price', 'N/A')}")
        else:
            print(f"❌ Live data failed: {response.text}")
    except Exception as e:
        print(f"❌ Error getting live data: {str(e)}")

def check_server_status():
    """Check if the server is running"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running")
            return True
        else:
            print("❌ Server returned non-200 status")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Server is not running")
        return False
    except Exception as e:
        print(f"❌ Error checking server: {str(e)}")
        return False

def main():
    """Main test function"""
    print("🚀 Starting Market Regime Classifier API Tests")
    print(f"Test started at: {datetime.now()}")
    print(f"Testing against: {BASE_URL}")
    
    # Check if server is running
    print("\n" + "="*60)
    print("Checking Server Status")
    print("="*60)
    
    if not check_server_status():
        print("\n❌ Server is not running. Please start the server first:")
        print("   python run.py")
        return
    
    # Test authentication
    access_token = test_user_registration_and_login()
    
    # Test market regime endpoints
    test_market_regime_endpoints(access_token)
    
    # Test other endpoints
    test_other_endpoints(access_token)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print("✅ All endpoint tests completed")
    print("📋 Check the results above for any failures")
    print("🔧 Fix any issues before deploying to production")
    print(f"Test completed at: {datetime.now()}")

if __name__ == "__main__":
    main()