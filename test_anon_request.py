"""
Test script to simulate anonymous requests to the features
"""
import requests
import json

# Base URL - adjust if your server is running on a different port
BASE_URL = "http://localhost:8000"

def test_ai_market_analysis():
    """Test AI Market Analysis endpoint"""
    print("\n=== Testing AI Market Analysis ===")
    url = f"{BASE_URL}/api/ai-analysis/run"
    data = {
        "ticker": "AAPL",
        "period": "1y"
    }

    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Check for Set-Cookie header
        if 'Set-Cookie' in response.headers:
            print(f"Set-Cookie: {response.headers['Set-Cookie']}")
    except Exception as e:
        print(f"Error: {e}")

def test_backtest():
    """Test Backtest endpoint"""
    print("\n=== Testing Backtest ===")
    url = f"{BASE_URL}/api/backtest/run"
    data = {
        "stock_symbol": "AAPL",
        "selected_indicators": {
            "rsi": True,
            "macd": True,
            "bollinger_bands": True
        },
        "voting_threshold": 0.6,
        "period": "1y",
        "timeframe": "1d",
        "initial_capital": 100000,
        "position_size_pct": 0.1
    }

    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Check for Set-Cookie header
        if 'Set-Cookie' in response.headers:
            print(f"Set-Cookie: {response.headers['Set-Cookie']}")
    except Exception as e:
        print(f"Error: {e}")

def test_chat():
    """Test Chat endpoint"""
    print("\n=== Testing Chat ===")
    url = f"{BASE_URL}/api/chat"
    data = {
        "message": "What is the stock market?",
        "model": "openrouter"
    }

    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)[:500]}...")  # First 500 chars

        # Check for Set-Cookie header
        if 'Set-Cookie' in response.headers:
            print(f"Set-Cookie: {response.headers['Set-Cookie']}")
    except Exception as e:
        print(f"Error: {e}")

def test_anonymous_status():
    """Test anonymous status endpoint"""
    print("\n=== Testing Anonymous Status ===")
    url = f"{BASE_URL}/api/usage/anonymous-status?feature=welth-ai-assistant"

    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Starting anonymous request tests...")
    print("Make sure the Flask server is running on http://localhost:8000")

    # Test each endpoint
    test_anonymous_status()
    test_ai_market_analysis()
    test_backtest()
    test_chat()

    print("\n=== Tests Complete ===")
