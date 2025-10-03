#!/usr/bin/env python3
"""
Test script to call the AI analysis endpoint directly
"""
import requests
import json

# Test data
payload = {
    "ticker": "RELIANCE",
    "period": "6mo"
}

# Test the endpoint
url = "http://localhost:8000/api/ai-analysis/run"
headers = {"Content-Type": "application/json"}

print("Testing AI analysis endpoint...")
print(f"URL: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("\nSending request...")

try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"\nStatus Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print("\n✅ SUCCESS!")
        print(f"\nResponse keys: {list(data.keys())}")

        if 'prediction' in data:
            print(f"\nPrediction keys: {list(data['prediction'].keys())}")
            print(f"Regime: {data['prediction'].get('regime_name')}")

        if 'analysis' in data:
            print(f"\n✅ Analysis present!")
            print(f"Analysis keys: {list(data['analysis'].keys())}")
            if 'historical_analysis' in data['analysis']:
                print(f"Historical analysis keys: {list(data['analysis']['historical_analysis'].keys())}")
        else:
            print(f"\n❌ No analysis data!")

        if 'usage' in data:
            print(f"\nUsage info: {data['usage']}")

    else:
        print(f"\n❌ ERROR {response.status_code}")
        print(f"Response: {response.text}")

except requests.exceptions.ConnectionError:
    print("\n❌ Could not connect to server. Is it running on http://localhost:8000?")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
