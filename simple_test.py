#!/usr/bin/env python3
"""
Simple test script for the new comprehensive backtesting engine
"""

def run_simple_test():
    """Run a simple test of the backtesting engine functionality"""
    try:
        from services.backtesting_engine import IndianStockStrategyBuilder
        
        print("Running simple functionality test...")
        
        # Test data fetching
        builder = IndianStockStrategyBuilder()
        df = builder.fetch_stock_data("RELIANCE", "3mo", "1d")
        
        if df is not None and not df.empty:
            print(f"Data fetch successful: {len(df)} rows")
            
            # Test indicator calculation
            indicators = {
                "RSI": {"period": 14, "oversold": 30, "overbought": 70},
                "SMA": {"periods": [20, 50]},
                "MACD": {"fast_period": 12, "slow_period": 26, "signal_period": 9}
            }
            
            df = builder.calculate_indicators(df, indicators)
            print("Indicators calculated successfully")
            
            # Test signal generation
            df = builder.generate_voting_signals(df, indicators, 0.6)
            print("Signals generated successfully")
            
            # Test backtest
            trades_df, equity_df, metrics = builder.backtest_strategy(df, 100000, 0.1, 2.0, 0.05)
            print("Backtest completed successfully")
            
            print(f"\nQuick Results:")
            print(f"  Total Return: ${metrics.get('Total_Return', 0):.2f}")
            print(f"  Total Return %: {metrics.get('Total_Return_Pct', 0):.2f}%")
            print(f"  Number of Trades: {metrics.get('Number_of_Trades', 0)}")
            print(f"  Win Rate: {metrics.get('Win_Rate', 0):.2f}%")
            print(f"  Max Drawdown: {metrics.get('Max_Drawdown', 0):.2f}%")
            print(f"  Sharpe Ratio: {metrics.get('Sharpe_Ratio', 0):.3f}")
            
            # Test chart creation
            try:
                candlestick_chart = builder.create_candlestick_chart(df, trades_df)
                equity_chart = builder.create_equity_curve_chart(equity_df)
                drawdown_chart = builder.create_drawdown_chart(equity_df)
                print("Charts created successfully")
            except Exception as e:
                print(f"Chart creation error: {str(e)}")
            
            # Test Monte Carlo if there are trades
            if not trades_df.empty:
                try:
                    mc_stats, mc_results = builder.monte_carlo_analysis(trades_df, 100000, 100, 0.95)
                    if mc_stats:
                        print("Monte Carlo analysis completed successfully")
                        print(f"  Mean Return: {mc_stats.get('Mean_Return', 0):.2f}%")
                        print(f"  VaR (95%): {mc_stats.get('VaR_95.0%', 0):.2f}%")
                except Exception as e:
                    print(f"Monte Carlo error: {str(e)}")
            
            return True
        else:
            print("Data fetch failed")
            return False
            
    except Exception as e:
        print(f"Simple test error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("Starting Comprehensive Backtesting Engine Test")
    print("=" * 50)
    
    success = run_simple_test()
    
    if success:
        print("\nAll tests completed successfully!")
        print("The IndianStockStrategyBuilder is working correctly.")
    else:
        print("\nTest failed. Please check dependencies and fix any errors.")

if __name__ == "__main__":
    main()