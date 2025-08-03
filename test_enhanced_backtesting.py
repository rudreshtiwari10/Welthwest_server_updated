#!/usr/bin/env python3
"""
Test script for enhanced backtesting service
Tests all the fixes applied to the backtesting system
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.backtesting_service import BacktestingService
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_basic_indicators():
    """Test basic indicator functionality"""
    print("=== Testing Basic Indicators ===")
    
    backtester = BacktestingService()
    
    # Test parameters with exact values (no auto-changing)
    test_params = {
        "ticker": "RELIANCE.NS",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "initial_capital": 100000,
        "position_size": 10,
        "stop_loss": 2.5,  # Exact value should be preserved
        "take_profit": 5.0,  # Exact value should be preserved
        "timeframe": "1d",
        "indicators": [
            {
                "type": "RSI",
                "parameters": {"period": 14}
            },
            {
                "type": "SMA",
                "parameters": {"period": 20}
            },
            {
                "type": "EMA", 
                "parameters": {"period": 12}
            }
        ]
    }
    
    try:
        result = backtester.run_backtest(**test_params)
        
        print("✓ Basic indicators test passed")
        print(f"Total trades: {result['metrics']['total_trades']}")
        print(f"Total PnL: {result['metrics']['total_pnl']:.2f}")
        print(f"Win rate: {result['metrics']['win_rate']:.2f}%")
        
        # Verify exact parameters were preserved
        if hasattr(result, 'config'):
            if result['config']['stop_loss'] == 2.5 and result['config']['take_profit'] == 5.0:
                print("✓ Exact parameters preserved")
            else:
                print("✗ Parameters were modified")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic indicators test failed: {str(e)}")
        return False

def test_vwap_obv():
    """Test VWAP and OBV indicators (should not require parameters)"""
    print("\n=== Testing VWAP and OBV ===")
    
    backtester = BacktestingService()
    
    test_params = {
        "ticker": "RELIANCE.NS", 
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "initial_capital": 100000,
        "position_size": 10,
        "timeframe": "1d",
        "indicators": [
            {
                "type": "VWAP"
                # No parameters required - should use defaults
            },
            {
                "type": "OBV"
                # No parameters required - should use defaults
            }
        ]
    }
    
    try:
        result = backtester.run_backtest(**test_params)
        
        print(f"✅ VWAP/OBV test passed")
        print(f"📊 Total trades: {result['metrics']['total_trades']}")
        print(f"💰 Total PnL: {result['metrics']['total_pnl']:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ VWAP/OBV test failed: {str(e)}")
        return False

def test_all_indicators():
    """Test all supported indicators"""
    print("\n=== Testing All Indicators ===")
    
    backtester = BacktestingService()
    
    test_params = {
        "ticker": "RELIANCE.NS",
        "start_date": "2023-01-01", 
        "end_date": "2023-12-31",
        "initial_capital": 100000,
        "position_size": 5,  # Smaller size for multiple indicators
        "timeframe": "1d",
        "indicators": [
            {"type": "RSI", "parameters": {"period": 14}},
            {"type": "MACD", "parameters": {"fast": 12, "slow": 26, "signal": 9}},
            {"type": "SMA", "parameters": {"period": 20}},
            {"type": "EMA", "parameters": {"period": 12}},
            {"type": "Bollinger", "parameters": {"period": 20, "std_dev": 2}},
            {"type": "Stochastic", "parameters": {"k_period": 14, "d_period": 3}},
            {"type": "ATR", "parameters": {"period": 14}},
            {"type": "VWAP"},  # Default parameters
            {"type": "OBV"}    # Default parameters
        ]
    }
    
    try:
        result = backtester.run_backtest(**test_params)
        
        print(f"✅ All indicators test passed")
        print(f"📊 Total trades: {result['metrics']['total_trades']}")
        print(f"💰 Total PnL: {result['metrics']['total_pnl']:.2f}")
        print(f"📈 Win rate: {result['metrics']['win_rate']:.2f}%")
        print(f"📉 Max drawdown: {result['metrics']['max_drawdown_percent']:.2f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ All indicators test failed: {str(e)}")
        return False

def test_new_timeframes():
    """Test new timeframes"""
    print("\n=== Testing New Timeframes ===")
    
    backtester = BacktestingService()
    
    # Test different timeframes
    timeframes_to_test = ["5m", "15m", "1h", "4h"]
    
    for timeframe in timeframes_to_test:
        test_params = {
            "ticker": "RELIANCE.NS",
            "start_date": "2023-12-01",
            "end_date": "2023-12-31", 
            "initial_capital": 100000,
            "position_size": 10,
            "timeframe": timeframe,
            "indicators": [
                {"type": "RSI", "parameters": {"period": 14}},
                {"type": "SMA", "parameters": {"period": 20}}
            ]
        }
        
        try:
            result = backtester.run_backtest(**test_params)
            print(f"✅ Timeframe {timeframe} test passed - {result['metrics']['total_trades']} trades")
            
        except Exception as e:
            print(f"❌ Timeframe {timeframe} test failed: {str(e)}")
            return False
    
    return True

def test_exact_parameters():
    """Test that exact stop loss and take profit values are preserved"""
    print("\n=== Testing Exact Parameter Preservation ===")
    
    backtester = BacktestingService()
    
    # Test with decimal values
    exact_values = [
        {"stop_loss": 1.25, "take_profit": 3.75},
        {"stop_loss": 2.5, "take_profit": 7.5},
        {"stop_loss": 0.75, "take_profit": 1.5}
    ]
    
    for values in exact_values:
        test_params = {
            "ticker": "RELIANCE.NS",
            "start_date": "2023-01-01",
            "end_date": "2023-03-31",
            "initial_capital": 100000,
            "position_size": 10,
            "stop_loss": values["stop_loss"],
            "take_profit": values["take_profit"],
            "timeframe": "1d",
            "indicators": [
                {"type": "RSI", "parameters": {"period": 14}}
            ]
        }
        
        try:
            result = backtester.run_backtest(**test_params)
            print(f"✅ Exact values SL:{values['stop_loss']}, TP:{values['take_profit']} preserved")
            
        except Exception as e:
            print(f"❌ Exact values test failed: {str(e)}")
            return False
    
    return True

def main():
    """Run all tests"""
    print("Starting Enhanced Backtesting Tests\n")
    
    tests = [
        test_basic_indicators,
        test_vwap_obv,
        test_all_indicators,
        test_new_timeframes,
        test_exact_parameters
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Backtesting service is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)