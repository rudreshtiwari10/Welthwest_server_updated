#!/usr/bin/env python3
"""
Debug script to test backtesting functionality step by step
"""

import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.stock_service import get_ohlc_data, format_indian_ticker
from services.backtesting_service import BacktestingService
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_data_fetching():
    """Test if data fetching is working correctly"""
    print("=" * 50)
    print("TESTING DATA FETCHING")
    print("=" * 50)
    
    ticker = "RELIANCE"
    start_date = "2023-01-01"
    end_date = "2024-01-01"
    
    # Test data fetching
    print(f"Fetching data for {ticker} from {start_date} to {end_date}")
    try:
        df = get_ohlc_data(ticker, start_date, end_date, "1d")
        print(f"Data shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        print(f"Data types: {df.dtypes.to_dict()}")
        
        # Check for NaN values
        nan_counts = df.isnull().sum()
        print(f"NaN counts: {nan_counts.to_dict()}")
        
        if df.empty:
            print("ERROR: No data fetched!")
            return False
        
        # Show first and last few rows
        print("\nFirst 5 rows:")
        print(df.head())
        print("\nLast 5 rows:")
        print(df.tail())
        
        return True
        
    except Exception as e:
        print(f"ERROR fetching data: {str(e)}")
        return False

def test_indicator_calculation():
    """Test if technical indicators are calculated correctly"""
    print("\n" + "=" * 50)
    print("TESTING INDICATOR CALCULATION")
    print("=" * 50)
    
    ticker = "RELIANCE"
    start_date = "2023-01-01"
    end_date = "2024-01-01"
    
    try:
        # Get data
        df = get_ohlc_data(ticker, start_date, end_date, "1d")
        if df.empty:
            print("ERROR: No data for indicator calculation")
            return False
        
        # Initialize backtesting service
        bs = BacktestingService()
        
        # Test indicator calculation
        indicators = [
            {"type": "rsi", "parameters": {"period": 14}},
            {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}
        ]
        
        print("Calculating indicators...")
        df_with_indicators = bs._get_data_with_indicators(ticker, start_date, end_date, "1d", indicators)
        
        print(f"Data with indicators shape: {df_with_indicators.shape}")
        print(f"Columns: {df_with_indicators.columns.tolist()}")
        
        # Check for NaN values in indicators
        indicator_cols = [col for col in df_with_indicators.columns if col not in ['Open', 'High', 'Low', 'Close', 'Volume']]
        print(f"Indicator columns: {indicator_cols}")
        
        for col in indicator_cols:
            nan_count = df_with_indicators[col].isnull().sum()
            total_count = len(df_with_indicators[col])
            print(f"{col}: {nan_count}/{total_count} NaN values ({nan_count/total_count*100:.1f}%)")
        
        # Show sample of indicator values
        print("\nSample indicator values (last 10 rows):")
        print(df_with_indicators[indicator_cols].tail(10))
        
        return True
        
    except Exception as e:
        print(f"ERROR in indicator calculation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_signal_generation():
    """Test if trading signals are generated correctly"""
    print("\n" + "=" * 50)
    print("TESTING SIGNAL GENERATION")
    print("=" * 50)
    
    ticker = "RELIANCE"
    start_date = "2023-01-01"
    end_date = "2024-01-01"
    
    try:
        # Initialize backtesting service
        bs = BacktestingService()
        
        # Get data with indicators
        indicators = [
            {"type": "rsi", "parameters": {"period": 14}},
            {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}
        ]
        
        df = bs._get_data_with_indicators(ticker, start_date, end_date, "1d", indicators)
        
        if df.empty:
            print("ERROR: No data for signal generation")
            return False
        
        # Generate signals
        print("Generating signals...")
        signals = bs._generate_signals(df, indicators)
        
        print(f"Signals shape: {signals.shape}")
        print(f"Signal value counts: {signals.value_counts().to_dict()}")
        
        # Show signal occurrences
        buy_signals = (signals == 1).sum()
        sell_signals = (signals == -1).sum()
        neutral_signals = (signals == 0).sum()
        
        print(f"Buy signals: {buy_signals}")
        print(f"Sell signals: {sell_signals}")
        print(f"Neutral signals: {neutral_signals}")
        
        if buy_signals + sell_signals == 0:
            print("WARNING: No trading signals generated!")
        
        # Show dates where signals occurred
        signal_dates = df.index[signals != 0]
        print(f"Signal dates: {signal_dates.tolist()[:10]}...")  # Show first 10
        
        return True
        
    except Exception as e:
        print(f"ERROR in signal generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_full_backtest():
    """Test full backtesting process"""
    print("\n" + "=" * 50)
    print("TESTING FULL BACKTEST")
    print("=" * 50)
    
    try:
        # Initialize backtesting service
        bs = BacktestingService()
        
        # Test parameters
        params = {
            'ticker': 'RELIANCE',
            'start_date': '2023-01-01',
            'end_date': '2024-01-01',
            'indicators': [
                {"type": "rsi", "parameters": {"period": 14}},
                {"type": "macd", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}
            ],
            'initial_capital': 100000.0,
            'position_size': 10.0,
            'timeframe': '1d',
            'enable_regime_filter': False  # Disabled as per request
        }
        
        print("Running backtest with parameters:")
        for key, value in params.items():
            print(f"  {key}: {value}")
        
        # Run backtest
        results = bs.run_backtest(**params)
        
        print("\nBacktest completed!")
        print(f"Results keys: {list(results.keys())}")
        
        # Check metrics
        if 'metrics' in results:
            metrics = results['metrics']
            print(f"Total trades: {metrics.get('total_trades', 'N/A')}")
            print(f"Winning trades: {metrics.get('winning_trades', 'N/A')}")
            print(f"Losing trades: {metrics.get('losing_trades', 'N/A')}")
            print(f"Total P&L: {metrics.get('total_pnl', 'N/A')}")
        
        # Check performance
        if 'performance' in results:
            performance = results['performance']
            print(f"Total return: {performance.get('total_return', 'N/A')}%")
            print(f"Sharpe ratio: {performance.get('sharpe_ratio', 'N/A')}")
            print(f"Max drawdown: {performance.get('max_drawdown', 'N/A')}%")
            print(f"Win rate: {performance.get('win_rate', 'N/A')}%")
        
        # Check for NaN values in results
        def check_for_nans(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    check_for_nans(value, f"{path}.{key}" if path else key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_for_nans(item, f"{path}[{i}]")
            elif isinstance(obj, (int, float)) and pd.isna(obj):
                print(f"NaN found at: {path}")
        
        print("\nChecking for NaN values in results...")
        check_for_nans(results)
        
        return True
        
    except Exception as e:
        print(f"ERROR in full backtest: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("Starting backtesting debug tests...")
    
    tests = [
        ("Data Fetching", test_data_fetching),
        ("Indicator Calculation", test_indicator_calculation),
        ("Signal Generation", test_signal_generation),
        ("Full Backtest", test_full_backtest)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            success = test_func()
            results.append((test_name, success))
            print(f"[OK] {test_name}: {'PASSED' if success else 'FAILED'}")
        except Exception as e:
            print(f"[ERROR] {test_name}: FAILED with exception - {str(e)}")
            results.append((test_name, False))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for test_name, success in results:
        status = "[OK] PASSED" if success else "[ERROR] FAILED"
        print(f"{test_name}: {status}")

if __name__ == "__main__":
    main()