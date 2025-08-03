#!/usr/bin/env python3
"""
Simple test for backtesting service fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.backtesting_service import BacktestingService
import logging

# Configure logging
logging.basicConfig(level=logging.WARNING)

def test_vwap_obv():
    """Test VWAP and OBV without required parameters"""
    print("Testing VWAP and OBV (no parameters required)...")
    
    backtester = BacktestingService()
    
    test_params = {
        "ticker": "RELIANCE.NS",
        "start_date": "2023-01-01",
        "end_date": "2023-03-31",
        "initial_capital": 100000,
        "position_size": 10,
        "timeframe": "1d",
        "indicators": [
            {"type": "VWAP"},  # No parameters - should work now
            {"type": "OBV"}    # No parameters - should work now
        ]
    }
    
    try:
        result = backtester.run_backtest(**test_params)
        print(f"SUCCESS: VWAP/OBV test passed")
        print(f"Total trades: {result['metrics']['total_trades']}")
        return True
    except Exception as e:
        print(f"FAILED: {str(e)}")
        return False

def test_exact_parameters():
    """Test exact parameter preservation"""
    print("\nTesting exact parameter preservation...")
    
    backtester = BacktestingService()
    
    test_params = {
        "ticker": "RELIANCE.NS",
        "start_date": "2023-01-01",
        "end_date": "2023-03-31",
        "initial_capital": 100000,
        "position_size": 10,
        "stop_loss": 2.75,    # Exact decimal value
        "take_profit": 5.25,  # Exact decimal value
        "timeframe": "1d",
        "indicators": [
            {"type": "RSI", "parameters": {"period": 14}}
        ]
    }
    
    try:
        print(f"Input SL: {test_params['stop_loss']}, TP: {test_params['take_profit']}")
        result = backtester.run_backtest(**test_params)
        print("SUCCESS: Exact parameters test passed")
        return True
    except Exception as e:
        print(f"FAILED: {str(e)}")
        return False

def test_new_timeframes():
    """Test new timeframes"""
    print("\nTesting new timeframes...")
    
    backtester = BacktestingService()
    
    timeframes = ["5m", "15m", "1h"]
    
    for tf in timeframes:
        test_params = {
            "ticker": "RELIANCE.NS",
            "start_date": "2023-12-01",
            "end_date": "2023-12-07",
            "initial_capital": 100000,
            "position_size": 10,
            "timeframe": tf,
            "indicators": [
                {"type": "RSI", "parameters": {"period": 14}}
            ]
        }
        
        try:
            result = backtester.run_backtest(**test_params)
            print(f"SUCCESS: Timeframe {tf} works")
        except Exception as e:
            print(f"FAILED {tf}: {str(e)}")
            return False
    
    return True

def main():
    print("=== Backtesting Service Fix Tests ===\n")
    
    tests = [
        test_vwap_obv,
        test_exact_parameters,
        test_new_timeframes
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nResults: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("All fixes working correctly!")
    else:
        print("Some issues remain.")

if __name__ == "__main__":
    main()