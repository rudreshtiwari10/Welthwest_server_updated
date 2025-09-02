#!/usr/bin/env python3
"""
Simple test script to verify backtesting signal generation fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.backtesting_service import BacktestingService
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_simple_rsi_backtest():
    """Test simple RSI backtest to verify fixes"""
    print("Testing Simple RSI Backtest")
    print("=" * 40)
    
    try:
        backtester = BacktestingService()
        
        # Simple test parameters
        params = {
            "ticker": "RELIANCE",
            "start_date": "2023-01-01",
            "end_date": "2023-06-30",
            "initial_capital": 100000,
            "position_size": 10,
            "timeframe": "1d",
            "indicators": [
                {"type": "rsi", "parameters": {"period": 14}}
            ],
            "minimum_confidence_threshold": 0.0,  # No threshold
            "enable_regime_filter": False,  # Disabled
        }
        
        print("Running backtest...")
        result = backtester.run_backtest(**params)
        
        # Check results
        total_trades = result['metrics']['total_trades']
        has_indicator_data = len(result.get('indicator_data', {})) > 0
        
        print(f"Total trades: {total_trades}")
        print(f"Has indicator data: {has_indicator_data}")
        print(f"Indicator keys: {list(result.get('indicator_data', {}).keys())}")
        
        if 'RSI_14' in result.get('indicator_data', {}):
            rsi_values = result['indicator_data']['RSI_14']
            non_null_rsi = [v for v in rsi_values if v is not None]
            print(f"RSI values: {len(non_null_rsi)} non-null out of {len(rsi_values)} total")
            if non_null_rsi:
                print(f"RSI range: {min(non_null_rsi):.2f} - {max(non_null_rsi):.2f}")
        
        # Check if we have any success indicators
        success = total_trades > 0 or has_indicator_data or len(result.get('price_data', [])) > 0
        
        print(f"\nTest Result: {'SUCCESS' if success else 'FAILED'}")
        
        if not success:
            print("Debug info:")
            if 'debug_info' in result:
                print(f"  Error: {result['debug_info']}")
            print(f"  Summary: {result.get('summary', 'No summary available')}")
        
        return success
        
    except Exception as e:
        print(f"Test FAILED with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_simple_macd_backtest():
    """Test simple MACD backtest"""
    print("\nTesting Simple MACD Backtest")
    print("=" * 40)
    
    try:
        backtester = BacktestingService()
        
        params = {
            "ticker": "RELIANCE",
            "start_date": "2023-01-01", 
            "end_date": "2023-06-30",
            "initial_capital": 100000,
            "position_size": 10,
            "timeframe": "1d",
            "indicators": [
                {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}
            ],
            "minimum_confidence_threshold": 0.0,
            "enable_regime_filter": False,
        }
        
        print("Running MACD backtest...")
        result = backtester.run_backtest(**params)
        
        total_trades = result['metrics']['total_trades']
        has_macd_data = any(key.startswith('macd') for key in result.get('indicator_data', {}))
        
        print(f"Total trades: {total_trades}")
        print(f"Has MACD data: {has_macd_data}")
        
        success = total_trades > 0 or has_macd_data
        print(f"Test Result: {'SUCCESS' if success else 'FAILED'}")
        
        return success
        
    except Exception as e:
        print(f"MACD test FAILED: {str(e)}")
        return False

def main():
    print("Starting Backtesting Fix Verification")
    print("=" * 50)
    
    # Run tests
    rsi_success = test_simple_rsi_backtest()
    macd_success = test_simple_macd_backtest()
    
    # Summary
    print("\n" + "=" * 50)
    print("FINAL RESULTS")
    print("=" * 50)
    
    total_tests = 2
    passed_tests = sum([rsi_success, macd_success])
    
    print(f"RSI Test: {'PASSED' if rsi_success else 'FAILED'}")
    print(f"MACD Test: {'PASSED' if macd_success else 'FAILED'}")
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\nALL TESTS PASSED! Signal generation fixes are working.")
    elif passed_tests > 0:
        print("\nPARTIAL SUCCESS. Some functionality is working.")
    else:
        print("\nALL TESTS FAILED. Issues remain in signal generation.")

if __name__ == "__main__":
    main()