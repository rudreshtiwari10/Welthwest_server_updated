#!/usr/bin/env python3
"""
Debug script to check OHLC data formatting issues
"""

import pandas as pd
import numpy as np
import yfinance as yf
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.stock_service import get_ohlc_data, format_indian_ticker
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_direct_yfinance():
    """Test direct yfinance data fetching"""
    print("=" * 60)
    print("TESTING DIRECT YFINANCE DATA")
    print("=" * 60)
    
    ticker = "RELIANCE.NS"
    start_date = "2023-01-01"
    end_date = "2023-01-10"  # Small range for testing
    
    try:
        # Direct yfinance call
        yf_ticker = yf.Ticker(ticker)
        yf_data = yf_ticker.history(start=start_date, end=end_date, interval="1d")
        
        print(f"Direct yfinance data for {ticker}:")
        print(f"Shape: {yf_data.shape}")
        print(f"Columns: {yf_data.columns.tolist()}")
        print(f"Index type: {type(yf_data.index)}")
        print(f"Date range: {yf_data.index.min()} to {yf_data.index.max()}")
        print("\nFirst few rows:")
        print(yf_data.head())
        print("\nData types:")
        print(yf_data.dtypes)
        
        return yf_data
        
    except Exception as e:
        print(f"Error in direct yfinance: {e}")
        return None

def test_service_data():
    """Test data from our stock service"""
    print("\n" + "=" * 60)
    print("TESTING STOCK SERVICE DATA")
    print("=" * 60)
    
    ticker = "RELIANCE"
    start_date = "2023-01-01"
    end_date = "2023-01-10"  # Small range for testing
    
    try:
        # Service call
        service_data = get_ohlc_data(ticker, start_date, end_date, "1d")
        
        print(f"Stock service data for {ticker}:")
        print(f"Shape: {service_data.shape}")
        print(f"Columns: {service_data.columns.tolist()}")
        print(f"Index type: {type(service_data.index)}")
        print(f"Date range: {service_data.index.min()} to {service_data.index.max()}")
        print("\nFirst few rows:")
        print(service_data.head())
        print("\nData types:")
        print(service_data.dtypes)
        
        return service_data
        
    except Exception as e:
        print(f"Error in service data: {e}")
        return None

def compare_data(yf_data, service_data):
    """Compare direct yfinance data with service data"""
    print("\n" + "=" * 60)
    print("COMPARING DATA")
    print("=" * 60)
    
    if yf_data is None or service_data is None:
        print("Cannot compare - one of the datasets is None")
        return
    
    print("=== COMPARISON RESULTS ===")
    print(f"YFinance shape: {yf_data.shape}")
    print(f"Service shape: {service_data.shape}")
    
    # Check if we have matching dates
    yf_dates = set(yf_data.index.strftime('%Y-%m-%d'))
    service_dates = set(pd.to_datetime(service_data.index).strftime('%Y-%m-%d'))
    
    print(f"YFinance dates: {sorted(yf_dates)}")
    print(f"Service dates: {sorted(service_dates)}")
    print(f"Date overlap: {yf_dates.intersection(service_dates)}")
    
    # Compare OHLC values for overlapping dates
    common_dates = yf_dates.intersection(service_dates)
    if common_dates:
        print("\n=== OHLC VALUE COMPARISON ===")
        for date_str in sorted(common_dates)[:3]:  # Check first 3 common dates
            # Find matching rows
            yf_row = yf_data[yf_data.index.strftime('%Y-%m-%d') == date_str].iloc[0]
            service_row = service_data[pd.to_datetime(service_data.index).strftime('%Y-%m-%d') == date_str].iloc[0]
            
            print(f"\nDate: {date_str}")
            print(f"YFinance - Open: {yf_row['Open']:.2f}, High: {yf_row['High']:.2f}, Low: {yf_row['Low']:.2f}, Close: {yf_row['Close']:.2f}")
            print(f"Service  - Open: {service_row['Open']:.2f}, High: {service_row['High']:.2f}, Low: {service_row['Low']:.2f}, Close: {service_row['Close']:.2f}")
            
            # Check if values match
            tolerances = ['Open', 'High', 'Low', 'Close']
            for col in tolerances:
                diff = abs(yf_row[col] - service_row[col])
                if diff > 0.01:  # More than 1 paisa difference
                    print(f"  [WARNING] {col} differs by {diff:.4f}")
                else:
                    print(f"  [OK] {col} matches")

def test_backtesting_price_data():
    """Test how price data is formatted in backtesting"""
    print("\n" + "=" * 60)
    print("TESTING BACKTESTING PRICE DATA FORMAT")
    print("=" * 60)
    
    try:
        from services.backtesting_service import BacktestingService
        
        bs = BacktestingService()
        
        # Get data like backtesting does
        ticker = "RELIANCE"
        start_date = "2023-01-01"
        end_date = "2023-01-10"
        
        df = get_ohlc_data(ticker, start_date, end_date, "1d")
        
        # Format dates like backtesting does
        try:
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            dates = df.index.strftime('%Y-%m-%d').tolist()
        except Exception as e:
            logger.warning(f"Error formatting dates: {str(e)}. Using string conversion.")
            dates = [str(d) for d in df.index.tolist()]
        
        # Create price data like backtesting does
        price_data = [{
            "Date": date,
            "Open": float(row.Open) if hasattr(row, 'Open') and not pd.isna(row.Open) else None,
            "High": float(row.High) if hasattr(row, 'High') and not pd.isna(row.High) else None,
            "Low": float(row.Low) if hasattr(row, 'Low') and not pd.isna(row.Low) else None,
            "Close": float(row.Close) if hasattr(row, 'Close') and not pd.isna(row.Close) else None,
            "Volume": float(row.Volume) if hasattr(row, 'Volume') and not pd.isna(row.Volume) else None
        } for date, row in zip(dates, df.itertuples())]
        
        print("Backtesting formatted price data:")
        print(f"Number of records: {len(price_data)}")
        print("\nFirst few records:")
        for i, record in enumerate(price_data[:3]):
            print(f"Record {i+1}: {record}")
        
        # Check for issues
        print("\n=== ISSUE DETECTION ===")
        for i, record in enumerate(price_data):
            if any(v is None for k, v in record.items() if k != 'Date'):
                print(f"[WARNING] Record {i+1} has None values: {record}")
            if record['Open'] == record['High'] == record['Low'] == record['Close']:
                print(f"[WARNING] Record {i+1} has all OHLC values the same: {record}")
        
        return price_data
        
    except Exception as e:
        print(f"Error in backtesting format test: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run all data format tests"""
    print("Starting data format debug tests...")
    
    # Test 1: Direct yfinance
    yf_data = test_direct_yfinance()
    
    # Test 2: Stock service
    service_data = test_service_data()
    
    # Test 3: Compare
    compare_data(yf_data, service_data)
    
    # Test 4: Backtesting format
    price_data = test_backtesting_price_data()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print("[OK] Direct yfinance data:", "OK" if yf_data is not None else "FAILED")
    print("[OK] Stock service data:", "OK" if service_data is not None else "FAILED")
    print("[OK] Backtesting format:", "OK" if price_data is not None else "FAILED")

if __name__ == "__main__":
    main()