#!/usr/bin/env python3
"""
Test script for the new stock fundamentals API endpoint
"""
import requests
import json
import sys

# API Base URL
API_URL = "http://localhost:5000/api"

def test_fundamentals_endpoint():
    """Test the stock fundamentals API endpoint"""
    print("Testing Stock Fundamentals API Endpoint")
    print("=" * 50)
    
    # Test with a popular Indian stock
    test_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY"]
    
    for symbol in test_symbols:
        print(f"\n🔍 Testing {symbol}")
        print("-" * 30)
        
        try:
            # Make API request
            url = f"{API_URL}/stock/fundamentals"
            params = {"ticker": symbol}
            
            print(f"Making request to: {url}")
            print(f"Parameters: {params}")
            
            response = requests.get(url, params=params, timeout=30)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                print("✅ Success! Fundamental data retrieved:")
                
                # Print key information
                if 'data' in data and data['data']:
                    fund_data = data['data']
                    
                    print(f"Company: {fund_data.get('company_name', 'N/A')}")
                    print(f"Sector: {fund_data.get('sector', 'N/A')}")
                    print(f"Current Price: ₹{fund_data.get('current_price', 'N/A')}")
                    
                    # Valuation ratios
                    if 'valuation_ratios' in fund_data:
                        val_ratios = fund_data['valuation_ratios']
                        print(f"P/E Ratio: {val_ratios.get('pe_ratio', 'N/A')}")
                        print(f"P/B Ratio: {val_ratios.get('pb_ratio', 'N/A')}")
                    
                    # Profitability ratios
                    if 'profitability_ratios' in fund_data:
                        prof_ratios = fund_data['profitability_ratios']
                        print(f"ROE: {prof_ratios.get('roe', 'N/A')}%")
                        print(f"ROA: {prof_ratios.get('roa', 'N/A')}%")
                    
                    # Balance sheet
                    if 'balance_sheet' in fund_data:
                        bs = fund_data['balance_sheet']
                        print(f"Total Assets: ₹{bs.get('total_assets', 'N/A')} Cr")
                        print(f"Shareholders Equity: ₹{bs.get('shareholders_equity', 'N/A')} Cr")
                    
                    print(f"Timestamp: {fund_data.get('timestamp', 'N/A')}")
                else:
                    print("⚠️ Warning: No fundamental data in response")
                    print(json.dumps(data, indent=2))
            else:
                print(f"❌ Error: HTTP {response.status_code}")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2))
                except:
                    print(response.text)
                
        except requests.RequestException as e:
            print(f"❌ Request failed: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    print("\n" + "=" * 50)
    print("Test completed!")

if __name__ == "__main__":
    print("Stock Fundamentals API Test")
    print("Make sure the Flask server is running on http://localhost:5000")
    print()
    
    try:
        test_fundamentals_endpoint()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)