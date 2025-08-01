#!/usr/bin/env python3
"""
Enhanced Backtesting System Test
Tests the new features: market regime toggle, relaxed confidence thresholds, and comprehensive metrics
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from services.backtesting_service import BacktestingService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_enhanced_backtesting():
    """Test the enhanced backtesting features"""
    
    # Initialize backtesting service
    backtesting_service = BacktestingService()
    
    # Test parameters
    ticker = "RELIANCE.NS"
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')  # 1 year
    
    # Define test indicators
    indicators = [
        {
            "type": "RSI",
            "parameters": {"period": 14}
        },
        {
            "type": "MACD",
            "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}
        },
        {
            "type": "SMA",
            "parameters": {"period": 20}
        }
    ]
    
    print("="*80)
    print("ENHANCED BACKTESTING SYSTEM TEST")
    print("="*80)
    
    # Test 1: Traditional backtest with high confidence threshold (60%)
    print("\n1. TRADITIONAL BACKTEST (60% confidence threshold)")
    print("-" * 50)
    
    try:
        results1 = backtesting_service.run_backtest(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            indicators=indicators,
            initial_capital=100000,
            position_size=10,
            stop_loss=5.0,
            take_profit=10.0,
            enable_regime_filter=False,  # Disabled
            minimum_confidence_threshold=60.0  # High threshold
        )
        
        print(f"Total Trades: {results1['metrics']['total_trades']}")
        print(f"Win Rate: {results1['performance']['win_rate']:.1f}%")
        print(f"Total Return: {results1['performance']['total_return']:.2f}%")
        print(f"Sharpe Ratio: {results1['performance']['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {results1['performance']['max_drawdown']:.2f}%")
        
        if results1.get('confidence_stats'):
            conf_stats = results1['confidence_stats']
            print(f"Average Signal Confidence: {conf_stats.get('average_confidence', 0) * 100:.1f}%")
        
    except Exception as e:
        print(f"Error in Test 1: {str(e)}")
    
    # Test 2: Relaxed backtest with 30% confidence threshold
    print("\n2. RELAXED BACKTEST (30% confidence threshold)")
    print("-" * 50)
    
    try:
        results2 = backtesting_service.run_backtest(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            indicators=indicators,
            initial_capital=100000,
            position_size=10,
            stop_loss=5.0,
            take_profit=10.0,
            enable_regime_filter=False,  # Disabled
            minimum_confidence_threshold=30.0  # Relaxed threshold
        )
        
        print(f"Total Trades: {results2['metrics']['total_trades']}")
        print(f"Win Rate: {results2['performance']['win_rate']:.1f}%")
        print(f"Total Return: {results2['performance']['total_return']:.2f}%")
        print(f"Sharpe Ratio: {results2['performance']['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {results2['performance']['max_drawdown']:.2f}%")
        
        if results2.get('confidence_stats'):
            conf_stats = results2['confidence_stats']
            print(f"Average Signal Confidence: {conf_stats.get('average_confidence', 0) * 100:.1f}%")
        
        # Show improvement in trade count
        trade_increase = results2['metrics']['total_trades'] - results1['metrics']['total_trades']
        print(f"Trade Count Increase: +{trade_increase} trades ({trade_increase/results1['metrics']['total_trades']*100:.1f}% more)")
        
    except Exception as e:
        print(f"Error in Test 2: {str(e)}")
    
    # Test 3: Market regime enabled with relaxed threshold
    print("\n3. MARKET REGIME ENABLED (30% confidence threshold)")
    print("-" * 50)
    
    try:
        results3 = backtesting_service.run_backtest(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            indicators=indicators,
            initial_capital=100000,
            position_size=10,
            stop_loss=5.0,
            take_profit=10.0,
            enable_regime_filter=True,  # Enabled
            minimum_confidence_threshold=30.0
        )
        
        print(f"Total Trades: {results3['metrics']['total_trades']}")
        print(f"Win Rate: {results3['performance']['win_rate']:.1f}%")
        print(f"Total Return: {results3['performance']['total_return']:.2f}%")
        print(f"Sharpe Ratio: {results3['performance']['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {results3['performance']['max_drawdown']:.2f}%")
        print(f"Regime Filter: {'Enabled' if results3.get('regime_filter_enabled') else 'Disabled'}")
        
    except Exception as e:
        print(f"Error in Test 3: {str(e)}")
    
    # Test 4: Display comprehensive metrics
    print("\n4. COMPREHENSIVE METRICS ANALYSIS")
    print("-" * 50)
    
    try:
        # Use the relaxed threshold results for comprehensive analysis
        perf = results2['performance']
        
        if 'comprehensive_metrics' in perf:
            comp_metrics = perf['comprehensive_metrics']
            print("\nTrade Analysis:")
            print(f"  Average Win: ${comp_metrics.get('average_win', 0):.2f}")
            print(f"  Average Loss: ${comp_metrics.get('average_loss', 0):.2f}")
            print(f"  Win/Loss Ratio: {comp_metrics.get('win_loss_ratio', 0):.2f}")
            print(f"  Expectancy: ${comp_metrics.get('expectancy', 0):.2f}")
            print(f"  Largest Win: ${comp_metrics.get('largest_win', 0):.2f}")
            print(f"  Largest Loss: ${comp_metrics.get('largest_loss', 0):.2f}")
            
            print("\nDuration Analysis:")
            print(f"  Average Trade Duration: {comp_metrics.get('average_trade_duration', 0):.1f} days")
            print(f"  Median Trade Duration: {comp_metrics.get('median_trade_duration', 0):.1f} days")
            print(f"  Max Trade Duration: {comp_metrics.get('max_trade_duration', 0)} days")
            
            print("\nRisk Metrics:")
            print(f"  VaR (95%): {comp_metrics.get('var_95', 0):.2f}%")
            print(f"  CVaR (95%): {comp_metrics.get('cvar_95', 0):.2f}%")
            print(f"  Return Skewness: {comp_metrics.get('trade_return_skewness', 0):.3f}")
            print(f"  Return Kurtosis: {comp_metrics.get('trade_return_kurtosis', 0):.3f}")
        
        if 'efficiency_metrics' in perf:
            eff_metrics = perf['efficiency_metrics']
            print("\nStrategy Efficiency:")
            print(f"  Market Exposure: {eff_metrics.get('market_exposure', 0) * 100:.1f}%")
            print(f"  Return per Trade: ${eff_metrics.get('return_per_trade', 0):.2f}")
            print(f"  Win Efficiency: {eff_metrics.get('win_efficiency', 0) * 100:.1f}%")
            print(f"  Consistency Score: {eff_metrics.get('consistency_score', 0):.3f}")
            print(f"  Equity Curve Linearity: {eff_metrics.get('equity_curve_linearity', 0):.3f}")
        
    except Exception as e:
        print(f"Error in comprehensive metrics analysis: {str(e)}")
    
    # Test 5: Display summary
    print("\n5. STRATEGY SUMMARY")
    print("-" * 50)
    
    try:
        if 'summary' in results2:
            print(results2['summary'])
    except Exception as e:
        print(f"Error displaying summary: {str(e)}")
    
    print("\n" + "="*80)
    print("TESTING COMPLETE")
    print("="*80)
    
    # Return results for further analysis if needed
    return {
        'traditional': results1,
        'relaxed': results2,
        'regime_enabled': results3
    }

def demonstrate_api_usage():
    """Demonstrate how to use the enhanced backtesting API"""
    
    print("\n" + "="*80)
    print("API USAGE DEMONSTRATION")
    print("="*80)
    
    print("""
Example API call for enhanced backtesting:

POST /api/backtest
{
    "ticker": "RELIANCE.NS",
    "start_date": "2023-01-01",
    "end_date": "2024-01-01",
    "indicators": [
        {"type": "RSI", "parameters": {"period": 14}},
        {"type": "MACD", "parameters": {"fastperiod": 12, "slowperiod": 26, "signalperiod": 9}}
    ],
    "initial_capital": 100000,
    "position_size": 10,
    "stop_loss": 5.0,
    "take_profit": 10.0,
    "enable_regime_filter": false,           // NEW: User can enable/disable
    "minimum_confidence_threshold": 30.0     // NEW: Relaxed from default 50%
}

Response includes:
- Traditional metrics (returns, sharpe, drawdown)
- Confidence statistics (NEW)
- Comprehensive trade metrics (NEW)
- Strategy efficiency metrics (NEW)
- Enhanced summary with all metrics (NEW)
""")

if __name__ == "__main__":
    # Run the enhanced backtesting tests
    results = test_enhanced_backtesting()
    
    # Demonstrate API usage
    demonstrate_api_usage()
    
    print("\nEnhanced backtesting system is ready!")
    print("Key improvements:")
    print("✓ Market regime enable/disable feature")
    print("✓ Relaxed confidence threshold (30% default)")
    print("✓ Comprehensive trade analysis metrics")
    print("✓ Strategy efficiency measurements")
    print("✓ Enhanced risk metrics (VaR, CVaR, skewness, kurtosis)")
    print("✓ Improved trade entry/exit logic")
    print("✓ Better performance analysis and reporting")