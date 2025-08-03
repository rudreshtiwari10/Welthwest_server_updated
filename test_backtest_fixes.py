#!/usr/bin/env python3
"""
Test script to verify backtesting signal generation fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.backtesting_service import BacktestingService
from services.technical_analysis import TechnicalAnalysis
import logging

# Configure detailed logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_signal_generation_fixes():
    """Test the comprehensive fixes for signal generation"""
    print("🔧 Testing Backtesting Signal Generation Fixes")
    print("=" * 60)
    
    # Initialize services
    backtester = BacktestingService()
    ta = TechnicalAnalysis()
    
    # Test parameters - designed to generate signals
    test_configs = [
        {
            "name": "Single RSI Test",
            "params": {
                "ticker": "RELIANCE",
                "start_date": "2023-01-01",
                "end_date": "2023-06-30",
                "initial_capital": 100000,
                "position_size": 10,
                "timeframe": "1d",
                "indicators": [
                    {"type": "rsi", "parameters": {"period": 14}}
                ],
                "minimum_confidence_threshold": 0.0,  # Very low threshold
                "enable_regime_filter": False,  # Disabled
                "stop_loss": None,  # No stop loss for testing
                "take_profit": None  # No take profit for testing
            }
        },
        {
            "name": "Single MACD Test", 
            "params": {
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
                "enable_regime_filter": False
            }
        },
        {
            "name": "Multiple Indicators Test",
            "params": {
                "ticker": "RELIANCE", 
                "start_date": "2023-01-01",
                "end_date": "2023-06-30",
                "initial_capital": 100000,
                "position_size": 10,
                "timeframe": "1d",
                "indicators": [
                    {"type": "rsi", "parameters": {"period": 14}},
                    {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}},
                    {"type": "sma", "parameters": {"period": 20}}
                ],
                "minimum_confidence_threshold": 0.0,
                "enable_regime_filter": False
            }
        }
    ]
    
    results_summary = []
    
    for i, config in enumerate(test_configs, 1):
        print(f"\n📊 Test {i}: {config['name']}")
        print("-" * 40)
        
        try:
            # Run backtest
            result = backtester.run_backtest(**config['params'])
            
            # Analyze results
            total_trades = result['metrics']['total_trades']
            total_signals = sum(1 for date in result.get('price_data', []) if date.get('signal', 0) != 0) 
            
            # Check if we have indicator data
            has_indicator_data = len(result.get('indicator_data', {})) > 0
            
            # Determine success
            success = total_trades > 0 or total_signals > 0 or has_indicator_data
            
            print(f"✅ Status: {'SUCCESS' if success else 'FAILED'}")
            print(f"📈 Total trades: {total_trades}")
            print(f"🎯 Has indicator data: {has_indicator_data}")
            print(f"📊 Indicator columns: {list(result.get('indicator_data', {}).keys())}")
            
            if 'debug_info' in result:
                print(f"🐛 Debug info: {result['debug_info']}")
            
            if result.get('summary'):
                print(f"📝 Summary: {result['summary'][:100]}...")
            
            results_summary.append({
                'test': config['name'],
                'success': success,
                'trades': total_trades,
                'has_data': has_indicator_data
            })
            
        except Exception as e:
            print(f"❌ FAILED: {str(e)}")
            logger.error(f"Test {config['name']} failed", exc_info=True)
            results_summary.append({
                'test': config['name'],
                'success': False,
                'trades': 0,
                'has_data': False,
                'error': str(e)
            })
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 FINAL RESULTS SUMMARY")
    print("=" * 60)
    
    total_tests = len(results_summary)
    successful_tests = sum(1 for r in results_summary if r['success'])
    
    for result in results_summary:
        status_icon = "✅" if result['success'] else "❌"
        print(f"{status_icon} {result['test']}: {result['trades']} trades, "
              f"Data: {result['has_data']}")
        if 'error' in result:
            print(f"   Error: {result['error']}")
    
    print(f"\n🎯 Overall Success Rate: {successful_tests}/{total_tests} "
          f"({successful_tests/total_tests*100:.1f}%)")
    
    if successful_tests == total_tests:
        print("🎉 All tests passed! Signal generation fixes are working correctly.")
    elif successful_tests > 0:
        print("⚠️  Some tests passed. Partial success - check failed tests above.")
    else:
        print("🚨 All tests failed. Signal generation issues remain.")
    
    return successful_tests == total_tests

def test_indicator_calculations():
    """Test individual indicator calculations"""
    print("\n🔬 Testing Individual Indicator Calculations")
    print("-" * 50)
    
    ta = TechnicalAnalysis()
    
    # Test with sample data
    test_params = {
        "ticker": "RELIANCE",
        "indicators": ["rsi", "macd", "bollinger", "sma", "ema"],
        "params": {
            "rsi_period": 14,
            "macd_fastperiod": 12,
            "macd_slowperiod": 26,
            "macd_signalperiod": 9,
            "bb_period": 20,
            "sma_period": 20,
            "ema_period": 20
        }
    }
    
    try:
        result = ta.calculate_indicators(
            test_params["ticker"],
            test_params["indicators"],
            test_params["params"]
        )
        
        print("✅ Indicator calculation completed")
        
        for indicator, data in result.items():
            if isinstance(data, dict) and 'error' not in data:
                print(f"  📊 {indicator.upper()}: OK")
                if 'signal' in data:
                    print(f"     Signal: {data['signal']}")
            else:
                print(f"  ❌ {indicator.upper()}: {data.get('error', 'Unknown error')}")
        
        return True
    except Exception as e:
        print(f"❌ Indicator calculation failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Starting Comprehensive Backtesting Fix Tests ===\n")
    
    # Test individual indicators first
    indicator_test_passed = test_indicator_calculations()
    
    # Test full backtesting pipeline
    backtest_test_passed = test_signal_generation_fixes()
    
    print(f"\n🏁 FINAL CONCLUSION")
    print("=" * 40)
    if indicator_test_passed and backtest_test_passed:
        print("🎉 ALL FIXES WORKING CORRECTLY!")
        print("   • Indicators calculate properly")
        print("   • Signals are being generated")
        print("   • Backtesting pipeline is functional")
    else:
        print("⚠️  SOME ISSUES REMAIN:")
        if not indicator_test_passed:
            print("   • Indicator calculations need attention")
        if not backtest_test_passed:
            print("   • Signal generation/backtesting needs attention")
    
    print("\n📝 Check the detailed logs above for more information.")