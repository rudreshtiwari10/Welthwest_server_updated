#!/usr/bin/env python3
"""
Test script for HMM model endpoints
"""
import requests
import json
import sys
import time

# Configuration
BASE_URL = "http://localhost:5000"  # Adjust if your server runs on different port
TEST_TICKER = "RELIANCE.NS"

def test_hmm_predict_get():
    """Test HMM prediction via GET request"""
    print("Testing HMM prediction (GET)...")
    
    url = f"{BASE_URL}/api/hmm_model/predict"
    params = {"ticker": TEST_TICKER}
    
    try:
        response = requests.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_hmm_predict_post():
    """Test HMM prediction via POST request"""
    print("\nTesting HMM prediction (POST)...")
    
    url = f"{BASE_URL}/api/hmm_model/predict"
    data = {"ticker": TEST_TICKER}
    
    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_hmm_analysis():
    """Test HMM regime persistence analysis"""
    print("\nTesting HMM regime analysis...")
    
    url = f"{BASE_URL}/api/hmm_model/analysis"
    params = {"ticker": TEST_TICKER, "period": "6mo"}
    
    try:
        response = requests.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_hmm_model_info():
    """Test HMM model info (requires authentication)"""
    print("\nTesting HMM model info...")
    print("Note: This endpoint requires JWT authentication")
    
    url = f"{BASE_URL}/api/hmm_model/model-info"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        # 401 is expected without authentication
        return response.status_code in [200, 401]
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Run all HMM endpoint tests"""
    print("=== HMM Model Endpoint Tests ===")
    print(f"Testing against: {BASE_URL}")
    print(f"Test ticker: {TEST_TICKER}")
    print("=" * 40)
    
    results = []
    
    # Test basic prediction endpoints (no auth required)
    results.append(test_hmm_predict_get())
    results.append(test_hmm_predict_post())
    results.append(test_hmm_analysis())
    results.append(test_hmm_model_info())
    
    print("\n" + "=" * 40)
    print("Test Results Summary:")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("✅ All basic HMM endpoints are working!")
    else:
        print("❌ Some endpoints failed. Check server logs.")
    
    print("\nNote: Authentication-required endpoints (train, evaluate, multiple)")
    print("were not tested and require valid JWT tokens.")

if __name__ == "__main__":
    main()