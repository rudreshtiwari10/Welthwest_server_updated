import requests
import json

BASE_URL = "http://localhost:5000"

def test_validate_endpoint():
    print("Testing /api/validate endpoint...")
    
    # Test with a valid ticker
    response = requests.get(f"{BASE_URL}/api/validate?ticker=AAPL")
    print(f"AAPL validation response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    # Test with another valid ticker
    response = requests.get(f"{BASE_URL}/api/validate?ticker=MSFT")
    print(f"MSFT validation response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    # Test with an invalid ticker
    response = requests.get(f"{BASE_URL}/api/validate?ticker=INVALID_TICKER_XYZ")
    print(f"Invalid ticker validation response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_health_endpoint():
    print("\nTesting /health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Health check response: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_historical_endpoint():
    print("\nTesting /api/historical endpoint...")
    
    # Test with a valid ticker and short period
    response = requests.get(f"{BASE_URL}/api/historical?ticker=AAPL&period=5d&interval=1d")
    print(f"Historical data response: {response.status_code}")
    data = response.json()
    print(f"Ticker: {data['ticker']}, Period: {data['period']}, Interval: {data['interval']}")
    print(f"Number of data points: {len(data['data'])}")
    if len(data['data']) > 0:
        print("First data point:")
        print(json.dumps(data['data'][0], indent=2))

def test_live_endpoint():
    print("\nTesting /api/live endpoint...")
    
    # Test with multiple tickers
    response = requests.get(f"{BASE_URL}/api/live?tickers=AAPL,MSFT,GOOGL")
    print(f"Live data response: {response.status_code}")
    data = response.json()
    print(f"Valid tickers: {data['valid_tickers']}")
    print(f"Number of data points: {len(data['data'])}")
    if len(data['data']) > 0:
        print("First data point:")
        print(json.dumps(data['data'][0], indent=2))

if __name__ == "__main__":
    print("Starting API tests...")
    test_health_endpoint()
    test_validate_endpoint()
    test_historical_endpoint()
    test_live_endpoint()
    print("\nTests completed.") 