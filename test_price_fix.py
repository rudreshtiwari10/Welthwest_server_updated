"""
Quick test to verify LSTM model outputs correct prices for TCS stock
"""
import yfinance as yf
import sys
import os

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lstm_model.lstm_hmm_forecast_service import lstm_hmm_forecast_service

def test_price_accuracy():
    """Test that predicted prices are in realistic range"""
    print("=" * 80)
    print("TESTING LSTM PRICE ACCURACY FIX")
    print("=" * 80)

    ticker = "TCS.NS"

    # Get real current price from Yahoo Finance
    print(f"\n1. Fetching REAL market price for {ticker}...")
    stock = yf.Ticker(ticker)
    real_data = stock.history(period='1d')
    real_price = real_data['Close'].iloc[-1]
    print(f"   ✓ Real TCS current price: ₹{real_price:.2f}")

    # Get prediction from our service
    print(f"\n2. Getting AI forecast from our LSTM service...")
    result = lstm_hmm_forecast_service.get_full_trade_forecast(
        ticker=ticker,
        capital=100000,
        risk_per_trade=0.02,
        trading_style='swing'
    )

    if result['status'] == 'success':
        predicted_price = result['price_analysis']['current_price']
        print(f"   ✓ Our model's current price: ₹{predicted_price:.2f}")

        # Calculate error
        error_percent = abs(predicted_price - real_price) / real_price * 100
        print(f"\n3. ACCURACY CHECK:")
        print(f"   Real price:      ₹{real_price:.2f}")
        print(f"   Predicted price: ₹{predicted_price:.2f}")
        print(f"   Error:           {error_percent:.2f}%")

        # Check if price is in realistic range (within 5% of real price)
        if error_percent < 5:
            print(f"\n   ✅ SUCCESS! Price is accurate (error < 5%)")
            print(f"   The data pipeline fix is working correctly!")
        else:
            print(f"\n   ⚠️  WARNING: Price error is {error_percent:.2f}%")
            print(f"   This might indicate the mock data fallback is being used.")

        # Show forecast
        print(f"\n4. 5-DAY PRICE FORECAST:")
        for day in result['price_analysis']['forecast']:
            print(f"   Day {day['day']}: ₹{day['predicted_price']:.2f} ({day['price_change']:+.2f}%)")

        # Show recommendation
        print(f"\n5. AI RECOMMENDATION:")
        rec = result['recommendation']
        print(f"   Action:     {rec['action']}")
        print(f"   Confidence: {rec['confidence']}")
        print(f"   Reasoning:  {rec['reasoning']}")

    else:
        print(f"   ❌ ERROR: {result.get('message', 'Unknown error')}")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_price_accuracy()
