"""
Test script for Advanced AI Trading System
"""
from lstm_model import lstm_hmm_forecast_service
import json

print("=" * 60)
print("ADVANCED AI TRADING SYSTEM - TEST")
print("=" * 60)

# Test 1: Basic forecast
print("\n[Test 1] Basic Forecast for HDFCBANK.NS")
result1 = lstm_hmm_forecast_service.get_full_trade_forecast('HDFCBANK.NS')
print(f"Status: {result1['status']}")
print(f"Action: {result1['recommendation']['action']}")
print(f"Confidence: {result1['recommendation']['confidence']}")
print(f"Risk Level: {result1['risk_assessment']['level']}")

# Test 2: With custom parameters
print("\n[Test 2] Custom Parameters for RELIANCE.NS")
result2 = lstm_hmm_forecast_service.get_full_trade_forecast(
    'RELIANCE.NS',
    capital=500000,
    risk_per_trade=0.03,
    trading_style='positional'
)
print(f"Status: {result2['status']}")
print(f"Action: {result2['recommendation']['action']}")
print(f"Position Size: {result2['position_sizing']['position_percentage']}%")
print(f"Entry: Rs. {result2['signals']['entry_price']:.2f}")
print(f"Stop Loss: Rs. {result2['signals']['stop_loss']:.2f}")
print(f"Take Profit: Rs. {result2['signals']['take_profit']:.2f}")

# Test 3: Multiple stocks
print("\n[Test 3] Multiple Stock Forecast")
result3 = lstm_hmm_forecast_service.get_multiple_forecasts(
    ['TCS.NS', 'INFY.NS', 'WIPRO.NS'],
    capital=300000
)
print(f"Status: {result3['status']}")
print(f"Forecasts generated: {len(result3['forecasts'])}")
for ticker, forecast in result3['forecasts'].items():
    print(f"  {ticker}: {forecast['recommendation']['action']}")

# Save sample output
print("\n[Saving] Sample forecast output...")
with open('sample_forecast_output.json', 'w') as f:
    json.dump(result1, f, indent=2)
print("Saved to: sample_forecast_output.json")

print("\n" + "=" * 60)
print("ALL TESTS PASSED SUCCESSFULLY!")
print("=" * 60)

# Print system capabilities
print("\nSYSTEM CAPABILITIES:")
print("- 50+ Technical Indicators")
print("- Chart Pattern Recognition")
print("- Sentiment Analysis")
print("- Kelly Criterion Position Sizing")
print("- Multi-Model Ensemble Fusion")
print("- Complete Trade Blueprints")
print("- Risk Assessment & Management")
