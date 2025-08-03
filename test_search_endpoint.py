#!/usr/bin/env python3
"""
Test script for the yahoo-suggest endpoint
"""
import requests
import json

def test_search_endpoint():
    base_url = "http://localhost:8000"
    
    test_queries = [
        "REL",      # Should match RELIANCE
        "TCS",      # Should match TCS
        "HDFC",     # Should match HDFC stocks
        "INFOSYS",  # Should match in name
        "NIFTY",    # Should match NIFTY index
        "ABC"       # Should return no matches
    ]
    
    print("Testing yahoo-suggest endpoint...")
    print("=" * 50)
    
    for query in test_queries:
        try:
            url = f"{base_url}/api/yahoo-suggest?q={query}"
            print(f"Testing query: '{query}'")
            print(f"URL: {url}")
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                quotes = data.get('quotes', [])
                print(f"✅ Success! Found {len(quotes)} matches")
                
                for i, quote in enumerate(quotes[:3]):  # Show first 3 matches
                    print(f"  {i+1}. {quote['symbol']} - {quote['name']} ({quote['exchange']})")
                
                if len(quotes) > 3:
                    print(f"  ... and {len(quotes) - 3} more")
                    
            else:
                print(f"❌ Error: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"❌ Connection Error: Server not running at {base_url}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            
        print("-" * 30)

if __name__ == "__main__":
    test_search_endpoint()