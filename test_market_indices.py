"""
Test script for the market indices API implementation with bulk data fetching
"""
import time
import yfinance as yf
from services.stock_service import get_market_indices, get_market_indices_yfinance

def test_yahoo_finance_bulk_indices_api():
    """Test Yahoo Finance bulk data API for market indices"""
    print("Testing Yahoo Finance bulk data API for market indices...")
    
    # Define the indices to test
    indices = ["^NSEI", "^BSESN", "^CNXIT", "^NSEBANK"]  # NIFTY 50, SENSEX, NIFTY IT, NIFTY BANK
    
    try:
        start_time = time.time()
        
        # Use yfinance's download function to get data for all indices in a single call
        data = yf.download(
            tickers=indices,
            period="1d",  # Use 1d as requested
            group_by="ticker",
            auto_adjust=True,
            progress=False
        )
        
        end_time = time.time()
        print(f"Bulk indices data fetch completed in {end_time - start_time:.2f} seconds")
        
        successful_fetches = 0
        for index_symbol in indices:
            try:
                if index_symbol in data and not data[index_symbol].empty:
                    latest_price = data[index_symbol]['Close'].iloc[-1]
                    print(f"Index: {index_symbol} - Current price: {latest_price:.2f}")
                    successful_fetches += 1
                else:
                    print(f"No data found for {index_symbol}")
            except Exception as e:
                print(f"Error processing {index_symbol}: {str(e)}")
        
        success_rate = (successful_fetches / len(indices)) * 100
        print(f"Successfully fetched {successful_fetches}/{len(indices)} indices ({success_rate:.1f}%)")
        
        return successful_fetches > 0
    except Exception as e:
        print(f"Error testing Yahoo Finance bulk indices API: {str(e)}")
        return False

def test_get_market_indices_function():
    """Test the get_market_indices function"""
    print("\nTesting get_market_indices function...")
    
    try:
        start_time = time.time()
        result = get_market_indices()
        end_time = time.time()
        
        print(f"Function execution time: {end_time - start_time:.2f} seconds")
        
        if result:
            # Metadata has been removed as requested
            print(f"Function returned data for {len([k for k in result.keys()])} indices")
            
            # Print the indices data
            print("\nIndices data:")
            for symbol, data in result.items():
                if symbol != '_meta':  # Skip metadata
                    if 'error' in data:
                        print(f"{symbol} - ERROR: {data['error']}")
                    else:
                        print(f"{symbol} ({data.get('name', 'Unknown')}): {data.get('price', 'N/A')} ({data.get('percentChange', 'N/A')}%)")
            
            return True
        else:
            print("Error: Function returned no data")
            return False
    except Exception as e:
        print(f"Error calling get_market_indices: {str(e)}")
        return False

def test_direct_function():
    """Test the direct Yahoo Finance function"""
    print("\nTesting get_market_indices_yfinance function directly...")
    
    try:
        start_time = time.time()
        result = get_market_indices_yfinance()
        end_time = time.time()
        
        print(f"Direct function execution time: {end_time - start_time:.2f} seconds")
        
        if result:
            print(f"Function returned data for {len(result.keys())} indices")
            # Print first index data as example
            if len(result) > 0:
                first_index = next(iter(result))
                print(f"Sample index data: {first_index} - {result[first_index]}")
            return True
        else:
            print("Error: Function returned no data")
            return False
    except Exception as e:
        print(f"Error calling direct function: {str(e)}")
        return False

def test_api_endpoint():
    """Test the API endpoint"""
    print("\nTesting API endpoint...")
    
    try:
        import requests
        response = requests.get("http://localhost:5000/api/market-indices")
        
        if response.status_code == 200:
            data = response.json()
            print(f"API returned data successfully")
            
            # Metadata has been removed as requested
            print(f"API returned data for {len(data.keys())} indices")
            # Print first index as example
            if len(data) > 0:
                first_index = next(iter(data))
                print(f"Sample index data: {first_index} - {data[first_index]}")
            
            return True
        else:
            print(f"Error: API returned status code {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"Error calling API endpoint: {str(e)}")
        return False

if __name__ == "__main__":
    print("===== Testing Market Indices Implementation (Bulk Data) =====\n")
    
    # Test Yahoo Finance bulk API access
    yahoo_api_works = test_yahoo_finance_bulk_indices_api()
    
    # Test the direct function
    direct_function_works = test_direct_function()
    
    # Test the main function
    function_works = test_get_market_indices_function()
    
    # Test the API endpoint (only if server is running)
    try:
        api_works = test_api_endpoint()
    except Exception as e:
        print(f"\nAPI endpoint test skipped - server may not be running: {str(e)}")
        api_works = None
    
    # Print summary
    print("\n===== Test Summary =====")
    print(f"Yahoo Finance Bulk Indices API: {'✓ PASS' if yahoo_api_works else '✗ FAIL'}")
    print(f"Direct Yahoo Finance Function: {'✓ PASS' if direct_function_works else '✗ FAIL'}")
    print(f"get_market_indices Function: {'✓ PASS' if function_works else '✗ FAIL'}")
    if api_works is not None:
        print(f"API Endpoint: {'✓ PASS' if api_works else '✗ FAIL'}")
    else:
        print(f"API Endpoint: SKIPPED")