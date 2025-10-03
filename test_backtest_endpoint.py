#!/usr/bin/env python3
"""
Test script to call the backtest endpoint directly
"""
import requests
import json

# Test data
payload = {
    "stock_symbol": "RELIANCE",
    "selected_indicators": {
        "RSI": {
            "period": 14,
            "oversold": 30,
            "overbought": 70
        }
    },
    "voting_threshold": 0.6,
    "period": "6mo",
    "timeframe": "1d",
    "initial_capital": 100000,
    "position_size_pct": 0.1,
    "risk_reward_ratio": 2.0,
    "max_drawdown_pct": 0.05,
    "monte_carlo_simulations": 10,
    "confidence_level": 0.95
}

# Test the endpoint
url = "http://localhost:8000/api/backtest/run"
headers = {"Content-Type": "application/json"}

print("Testing backtest endpoint...")
print(f"URL: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("\nSending request...")

try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")

    if response.status_code == 200:
        data = response.json()
        print("\n✅ SUCCESS!")
        if 'data' in data:
            print(f"Number of trades: {len(data['data'].get('trades', []))}")
            print(f"Metrics: {list(data['data'].get('metrics', {}).keys())}")
        if 'usage' in data:
            print(f"Usage info: {data['usage']}")
    else:
        print(f"\n❌ ERROR {response.status_code}")
        print(f"Response: {response.text}")
        try:
            error_data = response.json()
            print(f"\nError details: {json.dumps(error_data, indent=2)}")
        except:
            pass

except requests.exceptions.ConnectionError:
    print("\n❌ Could not connect to server. Is it running on http://localhost:8000?")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
