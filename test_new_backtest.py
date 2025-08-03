#!/usr/bin/env python3
"""
Test script for the new comprehensive backtesting endpoint
This script tests the /api/backtesting/newrun endpoint with sample data
"""

import requests
import json
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
BACKTEST_URL = f"{BASE_URL}/api/backtesting/newrun"

# Test credentials - you may need to adjust these
TEST_USER = {
    "email": "test@example.com",
    "password": "testpassword"
}

# Sample backtest parameters (replicating Colab structure)
BACKTEST_PARAMS = {
    "stock_symbol": "RELIANCE",
    "selected_indicators": {
        "RSI": {
            "period": 14,
            "oversold": 30,
            "overbought": 70
        },
        "MACD": {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9
        },
        "Bollinger_Bands": {
            "period": 20,
            "std_dev": 2
        },
        "Stochastic": {
            "k_period": 14,
            "d_period": 3,
            "oversold": 20,
            "overbought": 80
        },
        "SMA": {
            "periods": [20, 50]
        },
        "EMA": {
            "periods": [12, 26]
        }
    },
    "voting_threshold": 0.6,
    "period": "1y",
    "timeframe": "1d",
    "initial_capital": 100000,
    "position_size_pct": 0.1,
    "risk_reward_ratio": 2.0,
    "max_drawdown_pct": 0.05,
    "monte_carlo_simulations": 1000,
    "confidence_level": 0.95
}

def test_login():
    """Test user login and return JWT token"""
    try:
        response = requests.post(LOGIN_URL, json=TEST_USER)
        if response.status_code == 200:
            data = response.json()
            if 'access_token' in data:
                print("Login successful")
                return data['access_token']
            else:
                print("Login failed: No access token in response")
                return None
        else:
            print(f"Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Login error: {str(e)}")
        return None

def test_backtest(token):
    """Test the new backtesting endpoint"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        print("Starting backtest...")
        print(f"Parameters: {json.dumps(BACKTEST_PARAMS, indent=2)}")
        
        response = requests.post(BACKTEST_URL, json=BACKTEST_PARAMS, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("Backtest successful!")
            
            # Print summary
            if 'data' in data:
                result_data = data['data']
                
                # Metrics
                if 'metrics' in result_data:
                    metrics = result_data['metrics']
                    print("\n📈 Performance Metrics:")
                    print(f"  Total Return: ${metrics.get('Total_Return', 0):.2f}")
                    print(f"  Total Return %: {metrics.get('Total_Return_Pct', 0):.2f}%")
                    print(f"  Number of Trades: {metrics.get('Number_of_Trades', 0)}")
                    print(f"  Win Rate: {metrics.get('Win_Rate', 0):.2f}%")
                    print(f"  Max Drawdown: {metrics.get('Max_Drawdown', 0):.2f}%")
                    print(f"  Sharpe Ratio: {metrics.get('Sharpe_Ratio', 0):.3f}")
                    print(f"  Profit Factor: {metrics.get('Profit_Factor', 0):.2f}")
                
                # Trades
                if 'trades' in result_data:
                    trades = result_data['trades']
                    print(f"\n💼 Trades: {len(trades)} total trades")
                    if trades:
                        print("  First 3 trades:")
                        for i, trade in enumerate(trades[:3]):
                            print(f"    {i+1}. {trade.get('Direction', 'N/A')} - PnL: ${trade.get('PnL', 0):.2f} ({trade.get('Return_Pct', 0):.2f}%)")
                
                # Summary
                if 'summary' in result_data:
                    summary = result_data['summary']
                    print(f"\n📋 Summary:")
                    print(f"  Symbol: {summary.get('symbol', 'N/A')}")
                    print(f"  Period: {summary.get('backtest_period', {}).get('start_date', 'N/A')} to {summary.get('backtest_period', {}).get('end_date', 'N/A')}")
                    print(f"  Data Points: {summary.get('total_data_points', 0)}")
                    print(f"  Indicators: {', '.join(summary.get('indicators_used', []))}")
                    print(f"  Voting Threshold: {summary.get('voting_threshold', 0)}")
                
                # Monte Carlo
                if 'monte_carlo' in result_data:
                    mc = result_data['monte_carlo']['statistics']
                    print(f"\n🎲 Monte Carlo Analysis:")
                    print(f"  Mean Return: {mc.get('Mean_Return', 0):.2f}%")
                    print(f"  Std Return: {mc.get('Std_Return', 0):.2f}%")
                    print(f"  VaR (95%): {mc.get('VaR_95.0%', 0):.2f}%")
                    print(f"  Probability of Loss: {mc.get('Probability_of_Loss', 0):.2f}%")
                
                # Charts
                if 'charts' in result_data:
                    charts = result_data['charts']
                    print(f"\n📊 Charts Generated:")
                    print(f"  Candlestick Chart: {'✅' if 'candlestick' in charts else '❌'}")
                    print(f"  Equity Curve: {'✅' if 'equity_curve' in charts else '❌'}")
                    print(f"  Drawdown Chart: {'✅' if 'drawdown' in charts else '❌'}")
                
                print("\n✅ All test validations passed!")
                return True
            else:
                print("❌ No data in response")
                return False
                
        else:
            print(f"❌ Backtest failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Backtest error: {str(e)}")
        return False

def run_simple_test():
    """Run a simple test without authentication for basic functionality"""
    try:
        from services.backtesting_engine import IndianStockStrategyBuilder
        
        print("🧪 Running simple functionality test...")
        
        # Test data fetching
        builder = IndianStockStrategyBuilder()
        df = builder.fetch_stock_data("RELIANCE", "3mo", "1d")
        
        if df is not None and not df.empty:
            print(f"✅ Data fetch successful: {len(df)} rows")
            
            # Test indicator calculation
            indicators = {
                "RSI": {"period": 14},
                "SMA": {"periods": [20, 50]}
            }
            
            df = builder.calculate_indicators(df, indicators)
            print("✅ Indicators calculated successfully")
            
            # Test signal generation
            df = builder.generate_voting_signals(df, indicators, 0.6)
            print("✅ Signals generated successfully")
            
            # Test backtest
            trades_df, equity_df, metrics = builder.backtest_strategy(df, 100000, 0.1, 2.0, 0.05)
            print("✅ Backtest completed successfully")
            
            print(f"📊 Quick Results:")
            print(f"  Total Return: ${metrics.get('Total_Return', 0):.2f}")
            print(f"  Number of Trades: {metrics.get('Number_of_Trades', 0)}")
            print(f"  Win Rate: {metrics.get('Win_Rate', 0):.2f}%")
            
            return True
        else:
            print("❌ Data fetch failed")
            return False
            
    except Exception as e:
        print(f"❌ Simple test error: {str(e)}")
        return False

def main():
    """Main test function"""
    print("Starting Comprehensive Backtesting Tests")
    print("=" * 50)
    
    # Run simple test first
    print("\n1. Testing Basic Functionality (No Auth)")
    simple_success = run_simple_test()
    
    if simple_success:
        print("\n2. Testing API Endpoint (With Auth)")
        
        # Test login
        token = test_login()
        
        if token:
            # Test backtest endpoint
            backtest_success = test_backtest(token)
            
            if backtest_success:
                print("\n🎉 All tests completed successfully!")
                print("The new /api/backtesting/newrun endpoint is working correctly.")
            else:
                print("\n⚠️  API test failed, but basic functionality works.")
        else:
            print("\n⚠️  Could not authenticate. Please check credentials.")
            print("   You may need to create a test user or update credentials.")
    else:
        print("\n❌ Basic functionality test failed.")
        print("   Please check dependencies and fix any import errors.")

if __name__ == "__main__":
    main()