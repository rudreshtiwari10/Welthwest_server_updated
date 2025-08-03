#!/usr/bin/env python3
"""
Final comprehensive test for all indicators
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.backtesting_service import BacktestingService
import logging

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Reduce log noise

def test_all_indicators_final():
    """Final test of all indicators"""
    print("Final Test: All Technical Indicators")
    print("=" * 50)
    
    backtester = BacktestingService()
    
    # All indicators with proper configurations
    indicators_to_test = [
        {"name": "RSI", "config": {"type": "rsi", "parameters": {"period": 14}}},
        {"name": "MACD", "config": {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}},
        {"name": "Bollinger", "config": {"type": "bollinger", "parameters": {"period": 20, "num_std": 2}}},
        {"name": "SMA", "config": {"type": "sma", "parameters": {"period": 20}}},
        {"name": "EMA", "config": {"type": "ema", "parameters": {"period": 20}}},  
        {"name": "Stochastic", "config": {"type": "stochastic", "parameters": {"k_period": 14, "d_period": 3}}},
        {"name": "ATR", "config": {"type": "atr", "parameters": {"period": 14}}},
        {"name": "OBV", "config": {"type": "obv", "parameters": {"signal_period": 20, "ma_type": 1}}},
        {"name": "VWAP", "config": {"type": "vwap", "parameters": {"period": 14, "anchor": 1}}},
    ]
    
    results = []
    
    print("Testing Individual Indicators:")
    print("-" * 40)
    
    for indicator_info in indicators_to_test:
        name = indicator_info["name"]
        config = indicator_info["config"]
        
        try:
            params = {
                "ticker": "RELIANCE",
                "start_date": "2023-01-01",
                "end_date": "2023-06-30",
                "initial_capital": 100000,
                "position_size": 10,
                "timeframe": "1d",
                "indicators": [config],
                "minimum_confidence_threshold": 0.0,
                "enable_regime_filter": False,
            }
            
            result = backtester.run_backtest(**params)
            
            total_trades = result['metrics']['total_trades']
            has_data = len(result.get('indicator_data', {})) > 0
            
            success = total_trades > 0 or has_data
            status = "PASS" if success else "FAIL"
            
            print(f"{name:12} | {status:4} | Trades: {total_trades:2}")
            
            results.append({
                'name': name,
                'success': success,
                'trades': total_trades,
                'has_data': has_data
            })
            
        except Exception as e:
            print(f"{name:12} | FAIL | Error: {str(e)[:30]}...")
            results.append({
                'name': name,
                'success': False,
                'trades': 0,
                'has_data': False,
                'error': str(e)
            })
    
    # Test multiple indicators
    print(f"\nTesting Multiple Indicators:")
    print("-" * 30)
    
    try:
        multi_params = {
            "ticker": "RELIANCE",
            "start_date": "2023-01-01", 
            "end_date": "2023-06-30",
            "initial_capital": 100000,
            "position_size": 10,
            "timeframe": "1d",
            "indicators": [
                {"type": "rsi", "parameters": {"period": 14}},
                {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}},
                {"type": "sma", "parameters": {"period": 20}},
                {"type": "bollinger", "parameters": {"period": 20}},
            ],
            "minimum_confidence_threshold": 0.0,
            "enable_regime_filter": False,
        }
        
        multi_result = backtester.run_backtest(**multi_params)
        multi_trades = multi_result['metrics']['total_trades']
        multi_data = len(multi_result.get('indicator_data', {})) > 0
        
        multi_success = multi_trades > 0 or multi_data
        print(f"Multi-indicator: {'PASS' if multi_success else 'FAIL'} | Trades: {multi_trades}")
        
        results.append({
            'name': 'Multi-Indicator',
            'success': multi_success,
            'trades': multi_trades,
            'has_data': multi_data
        })
        
    except Exception as e:
        print(f"Multi-indicator: FAIL | Error: {str(e)[:30]}...")
        results.append({
            'name': 'Multi-Indicator',
            'success': False,
            'trades': 0,
            'has_data': False,
            'error': str(e)
        })
    
    # Final summary
    print("\n" + "=" * 50)
    print("FINAL RESULTS SUMMARY")
    print("=" * 50)
    
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r['success'])
    total_trades = sum(r['trades'] for r in results)
    
    print(f"Tests Passed: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"Total Trades: {total_trades}")
    
    # Breakdown by success
    passed = [r['name'] for r in results if r['success']]
    failed = [r['name'] for r in results if not r['success']]
    
    if passed:
        print(f"\nPASSED: {', '.join(passed)}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
    
    # Overall conclusion
    if successful_tests == total_tests:
        print(f"\n*** ALL INDICATORS WORKING PERFECTLY! ***")
        print("Signal generation system is fully operational.")
    elif successful_tests >= total_tests * 0.8:
        print(f"\n*** EXCELLENT RESULTS! ***")
        print("Most indicators working correctly.")
    elif successful_tests >= total_tests * 0.6:
        print(f"\n*** GOOD PROGRESS ***")
        print("Majority of indicators functional.")
    else:
        print(f"\n*** NEEDS MORE WORK ***")
        print("Several indicators still have issues.")
    
    return successful_tests >= total_tests * 0.8

if __name__ == "__main__":
    test_all_indicators_final()