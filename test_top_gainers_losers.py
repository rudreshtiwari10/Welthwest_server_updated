"""
Test script for the top gainers and losers API implementation
"""
import requests
import json
import time
import yfinance as yf
from services.stock_service import get_top_gainers_losers

def test_yahoo_finance_bulk_api():
    """Test Yahoo Finance bulk data API access"""
    print("Testing Yahoo Finance bulk data API...")
    
    # Test with just 3 key stocks to keep the test fast
    test_stocks = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS']
    
    try:
        start_time = time.time()
        
        # Use yfinance's download function to get data for all stocks in a single call
        data = yf.download(
            tickers=test_stocks,
            period="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False
        )
        
        end_time = time.time()
        print(f"Bulk data fetch completed in {end_time - start_time:.2f} seconds")
        
        successful_fetches = 0
        for stock in test_stocks:
            try:
                if stock in data and not data[stock].empty:
                    current_price = data[stock]['Close'].iloc[-1]
                    print(f"Sample stock: {stock} - Current price: {current_price:.2f}")
                    successful_fetches += 1
                else:
                    print(f"No data found for {stock}")
            except Exception as e:
                print(f"Error processing {stock}: {str(e)}")
        
        success_rate = (successful_fetches / len(test_stocks)) * 100
        print(f"Successfully fetched {successful_fetches}/{len(test_stocks)} stocks ({success_rate:.1f}%)")
        
        return successful_fetches > 0
    except Exception as e:
        print(f"Error testing Yahoo Finance bulk API: {str(e)}")
        return False

def test_get_top_gainers_losers():
    """Test the get_top_gainers_losers function"""
    print("\nTesting get_top_gainers_losers function...")
    
    try:
        start_time = time.time()
        result = get_top_gainers_losers()
        end_time = time.time()
        
        print(f"Function execution time: {end_time - start_time:.2f} seconds")
        
        if result:
            print(f"Source: {result.get('source', 'Unknown')}")
            print(f"Timestamp: {result.get('timestamp', 'N/A')}")
            
            print("\nTop Gainers:")
            for i, gainer in enumerate(result.get('gainers', []), 1):
                print(f"{i}. {gainer.get('symbol')} - {gainer.get('price')} ({gainer.get('percentChange')}%)")
            
            print("\nTop Losers:")
            for i, loser in enumerate(result.get('losers', []), 1):
                print(f"{i}. {loser.get('symbol')} - {loser.get('price')} ({loser.get('percentChange')}%)")
            
            return True
        else:
            print("Error: Function returned no data")
            return False
    except Exception as e:
        print(f"Error calling get_top_gainers_losers: {str(e)}")
        return False

def test_api_endpoint():
    """Test the API endpoint"""
    print("\nTesting API endpoint...")
    
    try:
        response = requests.get("http://localhost:5000/api/top-gainers-losers")
        
        if response.status_code == 200:
            data = response.json()
            print(f"API returned data successfully")
            print(f"Source: {data.get('source', 'Unknown')}")
            
            print(f"Number of gainers: {len(data.get('gainers', []))}")
            print(f"Number of losers: {len(data.get('losers', []))}")
            
            return True
        else:
            print(f"Error: API returned status code {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"Error calling API endpoint: {str(e)}")
        return False

if __name__ == "__main__":
    print("===== Testing Top Gainers and Losers Implementation (Bulk Data) =====\n")
    
    # Test Yahoo Finance bulk API access
    yahoo_api_works = test_yahoo_finance_bulk_api()
    
    # Test the function
    start_time = time.time()
    function_works = test_get_top_gainers_losers()
    total_time = time.time() - start_time
    
    # Test the API endpoint (only if server is running)
    try:
        api_works = test_api_endpoint()
    except Exception as e:
        print(f"\nAPI endpoint test skipped - server may not be running: {str(e)}")
        api_works = None
    
    # Print summary
    print("\n===== Test Summary =====")
    print(f"Yahoo Finance Bulk API Access: {'✓ PASS' if yahoo_api_works else '✗ FAIL'}")
    print(f"get_top_gainers_losers Function: {'✓ PASS' if function_works else '✗ FAIL'}")
    print(f"Total function execution time: {total_time:.2f} seconds")
    if api_works is not None:
        print(f"API Endpoint: {'✓ PASS' if api_works else '✗ FAIL'}")
    else:
        print(f"API Endpoint: SKIPPED")