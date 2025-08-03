#!/usr/bin/env python3
"""
Test RSI specifically to verify the fix
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.backtesting_service import BacktestingService
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_rsi_fix():
    """Test RSI specifically"""
    print("Testing RSI Fix")
    print("=" * 30)
    
    backtester = BacktestingService()
    
    # Test RSI with explicit parameters
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
        "minimum_confidence_threshold": 0.0,
        "enable_regime_filter": False,
    }
    
    try:
        result = backtester.run_backtest(**params)
        
        total_trades = result['metrics']['total_trades']
        has_rsi_data = 'RSI_14' in result.get('indicator_data', {})
        
        print(f"Total trades: {total_trades}")
        print(f"Has RSI data: {has_rsi_data}")
        print(f"Indicator keys: {list(result.get('indicator_data', {}).keys())}")
        
        if has_rsi_data:
            rsi_data = result['indicator_data']['RSI_14']
            non_null_rsi = [v for v in rsi_data if v is not None]
            print(f"RSI values: {len(non_null_rsi)} non-null out of {len(rsi_data)} total")
            if non_null_rsi:
                print(f"RSI range: {min(non_null_rsi):.2f} - {max(non_null_rsi):.2f}")
        
        success = total_trades > 0 or has_rsi_data
        print(f"\nRSI Test Result: {'SUCCESS' if success else 'FAILED'}")
        
        return success
        
    except Exception as e:
        print(f"RSI Test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_rsi_fix()