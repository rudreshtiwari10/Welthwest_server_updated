#!/usr/bin/env python3
"""
Test the actual backtesting API endpoint
"""

import requests
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_backtest_api():
    """Test the /api/backtesting/run endpoint"""
    
    # API endpoint (assuming Flask app is running on localhost:5000)
    url = "http://localhost:5000/api/backtesting/run"
    
    # Test payload
    payload = {
        "ticker": "RELIANCE",
        "start_date": "2023-01-01",
        "end_date": "2024-01-01",
        "indicators": [
            {
                "type": "rsi",
                "parameters": {
                    "period": 14
                }
            },
            {
                "type": "macd",
                "parameters": {
                    "fastperiod": 12,
                    "slowperiod": 26,
                    "signalperiod": 9
                }
            }
        ],
        "initial_capital": 100000,
        "position_size": 10,
        "timeframe": "1d"
    }
    
    headers = {
        "Content-Type": "application/json"
        # Note: In a real scenario, you'd need to add JWT token here
        # "Authorization": "Bearer your_jwt_token_here"
    }
    
    try:
        print("Testing backtesting API endpoint...")
        print(f"URL: {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                print("✅ API call successful!")
                print(f"Response keys: {list(result.keys())}")
                
                # Check for NaN values in response
                response_str = json.dumps(result)
                if 'NaN' in response_str or 'null' in response_str:
                    print("⚠️ Found NaN or null values in response")
                    # Count occurrences
                    nan_count = response_str.count('NaN')
                    null_count = response_str.count('null')
                    print(f"NaN occurrences: {nan_count}")
                    print(f"null occurrences: {null_count}")
                else:
                    print("✅ No NaN or null values found in response")
                
                # Check metrics
                if 'metrics' in result:
                    metrics = result['metrics']
                    print(f"Total trades: {metrics.get('total_trades', 'N/A')}")
                    print(f"Total P&L: {metrics.get('total_pnl', 'N/A')}")
                
                # Check performance
                if 'performance' in result:
                    performance = result['performance']
                    print(f"Total return: {performance.get('total_return', 'N/A')}%")
                    print(f"Sharpe ratio: {performance.get('sharpe_ratio', 'N/A')}")
                
                return True
                
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON response: {e}")
                print(f"Raw response: {response.text[:500]}...")
                return False
        else:
            print(f"❌ API call failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - Flask app might not be running")
        print("To test the API, start the Flask app first:")
        print("python app.py")
        return False
    except Exception as e:
        print(f"❌ Error testing API: {e}")
        return False

def test_simple_calculation():
    """Test a simple calculation to see if basic math works"""
    print("\n" + "="*50)
    print("TESTING SIMPLE CALCULATIONS")
    print("="*50)
    
    import numpy as np
    import pandas as pd
    
    # Test basic numpy operations
    data = [1, 2, 3, 4, 5]
    arr = np.array(data)
    
    print(f"Array: {arr}")
    print(f"Mean: {np.mean(arr)}")
    print(f"Std: {np.std(arr)}")
    print(f"Any NaN: {np.isnan(arr).any()}")
    
    # Test with NaN
    data_with_nan = [1, 2, np.nan, 4, 5]
    arr_with_nan = np.array(data_with_nan)
    
    print(f"Array with NaN: {arr_with_nan}")
    print(f"Mean: {np.nanmean(arr_with_nan)}")
    print(f"Std: {np.nanstd(arr_with_nan)}")
    print(f"Any NaN: {np.isnan(arr_with_nan).any()}")
    
    # Test pandas operations
    df = pd.DataFrame({
        'A': [1, 2, 3, 4, 5],
        'B': [10, 20, 30, 40, 50]
    })
    
    print(f"DataFrame:\n{df}")
    print(f"DataFrame mean:\n{df.mean()}")
    print(f"Any NaN: {df.isnull().any().any()}")

if __name__ == "__main__":
    print("Testing API and calculations...")
    
    # Test simple calculations first
    test_simple_calculation()
    
    # Test API endpoint
    print("\n" + "="*50)
    print("TESTING API ENDPOINT")
    print("="*50)
    api_success = test_backtest_api()
    
    if not api_success:
        print("\n⚠️ API test failed - this might be because:")
        print("1. Flask app is not running")
        print("2. JWT authentication is required")
        print("3. Port or URL is different")
        print("\nTo start the Flask app, run: python app.py")