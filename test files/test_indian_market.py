import requests
import json

BASE_URL = "http://localhost:5000"

def test_indian_stock_validation():
    print("\nTesting Indian stock validation...")
    
    # Test with a few popular Indian stocks
    indian_stocks = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN"]
    
    for stock in indian_stocks:
        response = requests.get(f"{BASE_URL}/api/validate?ticker={stock}")
        data = response.json()
        print(f"{stock}: {data['valid']}")

def test_indian_historical_data():
    print("\nTesting historical data for Indian stocks...")
    
    # Test with a popular Indian stock
    ticker = "RELIANCE"
    response = requests.get(f"{BASE_URL}/api/historical?ticker={ticker}&period=1mo&interval=1d")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Retrieved {len(data['data'])} data points for {ticker}")
        if len(data['data']) > 0:
            print("First data point:")
            print(json.dumps(data['data'][0], indent=2))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

def test_indian_ohlc_data():
    print("\nTesting OHLC data for Indian stocks...")
    
    # Test with a popular Indian stock
    ticker = "TCS"
    response = requests.get(f"{BASE_URL}/api/ohlc?ticker={ticker}&start_date=2023-01-01&end_date=2023-02-01&interval=1d")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Retrieved {len(data['data'])} OHLC data points for {ticker}")
        if len(data['data']) > 0:
            print("First data point:")
            print(json.dumps(data['data'][0], indent=2))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

def test_indian_market_indices():
    print("\nTesting Indian market indices...")
    
    response = requests.get(f"{BASE_URL}/api/market-indices")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Retrieved {len(data['indices'])} Indian market indices")
        for index, details in data['indices'].items():
            print(f"{index}: {details.get('name', 'Unknown')}")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

def test_top_gainers_losers():
    print("\nTesting top gainers and losers...")
    
    response = requests.get(f"{BASE_URL}/api/top-gainers-losers")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Retrieved {len(data['gainers'])} gainers and {len(data['losers'])} losers")
        
        if len(data['gainers']) > 0:
            print("\nTop gainers:")
            for stock in data['gainers']:
                print(f"{stock['symbol']}: {stock['percentChange']:.2f}%")
        
        if len(data['losers']) > 0:
            print("\nTop losers:")
            for stock in data['losers']:
                print(f"{stock['symbol']}: {stock['percentChange']:.2f}%")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

def test_stock_comparison():
    print("\nTesting stock comparison...")
    
    response = requests.get(f"{BASE_URL}/api/compare?tickers=RELIANCE,TCS&period=1mo&interval=1d")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Comparing {', '.join(data['valid_tickers'])}")
        print(f"Period: {data['period']}, Interval: {data['interval']}")
        
        for ticker in data['valid_tickers']:
            raw_data = data['raw_data'].get(ticker, [])
            norm_data = data['normalized_data'].get(ticker, [])
            print(f"{ticker}: {len(raw_data)} data points, {len(norm_data)} normalized points")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    print("Starting Indian market API tests...")
    test_indian_stock_validation()
    test_indian_historical_data()
    test_indian_ohlc_data()
    test_indian_market_indices()
    test_top_gainers_losers()
    test_stock_comparison()
    print("\nTests completed.") 