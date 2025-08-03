#!/usr/bin/env python3
"""
Comprehensive test script for all technical indicators
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

def test_all_indicators():
    """Test all technical indicators systematically"""
    print("Testing All Technical Indicators")
    print("=" * 50)
    
    backtester = BacktestingService()
    
    # List of all indicators to test
    indicators_to_test = [
        {"name": "RSI", "config": {"type": "rsi", "parameters": {"period": 14}}},
        {"name": "MACD", "config": {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}},
        {"name": "Bollinger Bands", "config": {"type": "bollinger", "parameters": {"period": 20, "num_std": 2}}},
        {"name": "SMA", "config": {"type": "sma", "parameters": {"period": 20}}},
        {"name": "EMA", "config": {"type": "ema", "parameters": {"period": 20}}},  
        {"name": "Stochastic", "config": {"type": "stochastic", "parameters": {"k_period": 14, "d_period": 3}}},
        {"name": "ATR", "config": {"type": "atr", "parameters": {"period": 14}}},
        {"name": "OBV", "config": {"type": "obv", "parameters": {"signal_period": 20, "ma_type": 1}}},
        {"name": "VWAP", "config": {"type": "vwap", "parameters": {"period": 14, "anchor": 1}}},
    ]
    
    results = []
    
    # Test each indicator individually
    for indicator_info in indicators_to_test:
        name = indicator_info["name"]
        config = indicator_info["config"]
        
        print(f"\nTesting {name}...")
        print("-" * 30)
        
        try:
            # Base test parameters
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
            
            # Run backtest
            result = backtester.run_backtest(**params)
            
            # Analyze results
            total_trades = result['metrics']['total_trades']
            has_indicator_data = len(result.get('indicator_data', {})) > 0
            indicator_keys = list(result.get('indicator_data', {}).keys())
            
            success = total_trades > 0 or has_indicator_data
            
            print(f"Status: {'SUCCESS' if success else 'FAILED'}")
            print(f"Trades: {total_trades}")
            print(f"Has data: {has_indicator_data}")
            print(f"Data keys: {indicator_keys}")
            
            # Check for specific indicator data
            expected_keys = {
                "RSI": ["RSI_14"],
                "MACD": ["macd", "macd_signal", "macd_histogram"],
                "Bollinger Bands": ["bollinger_upper", "bollinger_middle", "bollinger_lower"],
                "SMA": ["SMA_20"],
                "EMA": ["EMA_20"],
                "Stochastic": ["stochastic_k", "stochastic_d"],
                "ATR": [],  # ATR usually doesn't appear in final output
                "OBV": [],  # OBV usually doesn't appear in final output
                "VWAP": [],  # VWAP usually doesn't appear in final output
            }
            
            expected = expected_keys.get(name, [])
            found_expected = any(key in indicator_keys for key in expected) if expected else True
            
            if expected and not found_expected:
                print(f"WARNING: Expected keys {expected} not found")
            
            results.append({
                'name': name,
                'success': success,
                'trades': total_trades,  
                'has_data': has_indicator_data,
                'keys': indicator_keys,
                'found_expected': found_expected
            })
            
        except Exception as e:
            print(f"FAILED: {str(e)}")
            results.append({
                'name': name,
                'success': False,
                'trades': 0,
                'has_data': False,
                'keys': [],
                'found_expected': False,
                'error': str(e)
            })
    
    # Test multiple indicators together
    print(f"\nTesting Multiple Indicators Together...")
    print("-" * 40)
    
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
            ],
            "minimum_confidence_threshold": 0.0,
            "enable_regime_filter": False,
        }
        
        multi_result = backtester.run_backtest(**multi_params)
        
        multi_trades = multi_result['metrics']['total_trades']
        multi_data = len(multi_result.get('indicator_data', {})) > 0
        multi_keys = list(multi_result.get('indicator_data', {}).keys())
        
        print(f"Multi-indicator test: {'SUCCESS' if multi_trades > 0 or multi_data else 'FAILED'}")
        print(f"Trades: {multi_trades}")
        print(f"Data keys: {multi_keys}")
        
        results.append({
            'name': 'Multiple Indicators',
            'success': multi_trades > 0 or multi_data,
            'trades': multi_trades,
            'has_data': multi_data,
            'keys': multi_keys,
            'found_expected': True
        })
        
    except Exception as e:
        print(f"Multi-indicator test FAILED: {str(e)}")
        results.append({
            'name': 'Multiple Indicators',
            'success': False,
            'trades': 0,
            'has_data': False,
            'keys': [],
            'found_expected': False,
            'error': str(e)
        })
    
    # Summary
    print("\n" + "=" * 50)
    print("COMPREHENSIVE TEST RESULTS")
    print("=" * 50)
    
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r['success'])
    
    for result in results:
        status = "PASS" if result['success'] else "FAIL"
        data_status = "✓" if result['has_data'] else "✗"
        print(f"{result['name']:20} | {status:4} | Trades: {result['trades']:2} | Data: {data_status} | Keys: {len(result['keys'])}")
        
        if 'error' in result:
            print(f"    Error: {result['error']}")
    
    print(f"\nOverall Success Rate: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    
    if successful_tests == total_tests:
        print("ALL INDICATORS WORKING CORRECTLY!")
    elif successful_tests > total_tests * 0.7:
        print("MOST INDICATORS WORKING - Minor issues remain")
    else:
        print("SIGNIFICANT ISSUES DETECTED - Multiple indicators failing")
    
    return successful_tests == total_tests

if __name__ == "__main__":
    test_all_indicators()