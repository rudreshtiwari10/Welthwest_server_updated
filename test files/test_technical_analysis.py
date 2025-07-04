#!/usr/bin/env python3
"""
Test script for technical analysis with all new indicators
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.technical_analysis import TechnicalAnalysis
import json

def test_technical_analysis():
    """Test all technical indicators"""
    print("Testing Technical Analysis with all indicators...")
    
    # Initialize technical analysis service
    ta = TechnicalAnalysis()
    
    # Test stock ticker
    ticker = "RELIANCE.NS"
    
    # Test all indicators
    indicators = [
        'rsi', 'macd', 'bollinger', 'sma', 'ema', 
        'stochastic', 'atr', 'obv', 'vwap', 'pivot', 'fibonacci'
    ]
    
    print(f"\nTesting indicators for {ticker}:")
    print("-" * 50)
    
    try:
        # Test individual indicators
        results = ta.calculate_indicators(ticker, indicators)
        
        for indicator, data in results.items():
            if "error" in data:
                print(f"❌ {indicator.upper()}: {data['error']}")
            else:
                print(f"✅ {indicator.upper()}: OK")
                if isinstance(data, dict) and 'signal' in data:
                    print(f"   Signal: {data['signal']}")
                    
        print("\n" + "=" * 50)
        
        # Test comprehensive trading signals
        print("Testing comprehensive trading signals...")
        signals = ta.get_trading_signals(ticker)
        
        if "error" in signals:
            print(f"❌ Trading Signals: {signals['error']}")
        else:
            print("✅ Trading Signals: OK")
            if 'overall' in signals:
                overall = signals['overall']
                print(f"   Overall Signal: {overall.get('signal', 'N/A')}")
                print(f"   Signal Strength: {overall.get('strength', 'N/A')}")
                print(f"   Consensus Ratio: {overall.get('consensus_ratio', 'N/A'):.2f}")
                print(f"   Total Indicators: {overall.get('total_indicators', 'N/A')}")
        
        print("\n" + "=" * 50)
        print("All tests completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_technical_analysis() 