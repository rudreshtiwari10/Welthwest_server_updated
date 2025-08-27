#!/usr/bin/env python3
"""
Test script to verify the stock data fetching fix
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.stock_service import format_indian_ticker, get_historical_data_yfinance
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_ticker_formatting():
    """Test the format_indian_ticker function"""
    print("\n=== Testing Ticker Formatting ===")
    
    test_cases = [
        "RELIANCE",
        "$RELIANCE", 
        "$RELIANCE.BO",
        "RELIANCE.NS",
        "TCS",
        "$TCS.NS",
        "NIFTY",
        "^NSEI"
    ]
    
    for ticker in test_cases:
        formatted = format_indian_ticker(ticker)
        print(f"'{ticker}' -> '{formatted}'")
    
def test_stock_data_fetching():
    """Test actual stock data fetching"""
    print("\n=== Testing Stock Data Fetching ===")
    
    test_tickers = ["RELIANCE", "TCS"]
    
    for ticker in test_tickers:
        try:
            print(f"\nTesting {ticker}...")
            data = get_historical_data_yfinance(ticker, period="5d", interval="1d")
            
            if not data.empty:
                print(f"[SUCCESS] {ticker}: {len(data)} rows fetched")
                print(f"   Latest close price: {data['Close'].iloc[-1]:.2f}")
                print(f"   Date range: {data.index.min()} to {data.index.max()}")
            else:
                print(f"[ERROR] No data found for {ticker}")
                
        except Exception as e:
            print(f"[ERROR] {ticker}: {str(e)}")

if __name__ == "__main__":
    print("Stock Data Fix Test Script")
    print("=" * 50)
    
    test_ticker_formatting()
    test_stock_data_fetching()
    
    print("\n" + "=" * 50)
    print("Test completed!")