"""
Quick Test Script for Finance AI Upgrade

Run this script to test all new services locally
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_indicators():
    """Test indicators service"""
    print("\n" + "="*60)
    print("TEST 1: Indicators Service")
    print("="*60)

    try:
        from services.indicators_service import get_indicators, get_signal_summary

        # Test with AAPL
        print("Testing with AAPL...")
        result = get_indicators('AAPL', '3mo')

        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return False

        print(f"✅ Current Price: ${result['current_price']}")
        print(f"✅ RSI: {result['indicators']['rsi']['value']} ({result['indicators']['rsi']['signal']})")
        print(f"✅ MACD Trend: {result['indicators']['macd']['trend']}")
        print(f"✅ Overall Trend: {result['indicators']['trend_analysis']['overall_trend']}")

        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_screener():
    """Test screener service"""
    print("\n" + "="*60)
    print("TEST 2: Screener Service")
    print("="*60)

    try:
        from services.screener_service import run_screen, get_available_screens

        # Get available screens
        screens = get_available_screens()
        print(f"✅ Available screens: {len(screens)}")
        for name, config in screens.items():
            print(f"   - {name}: {config['description']}")

        # Run oversold bounce screen
        print("\nRunning 'oversold_bounce' screen on NIFTY50...")
        result = run_screen('oversold_bounce', 'NIFTY50', top_n=5)

        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return False

        print(f"✅ Found {result['total_matches']} matching stocks")
        if result['results']:
            print("Top matches:")
            for stock in result['results'][:3]:
                print(f"   - {stock['symbol']}: Score {stock['score']}, RSI {stock.get('rsi', 'N/A')}")

        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backtest():
    """Test backtest service"""
    print("\n" + "="*60)
    print("TEST 3: Backtest Service")
    print("="*60)

    try:
        from services.simple_backtest_service import run_backtest
        from datetime import datetime, timedelta

        # Test with AAPL last 6 months
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

        print(f"Testing SMA crossover on AAPL ({start_date} to {end_date})...")
        result = run_backtest(
            strategy='sma_crossover',
            symbol='AAPL',
            start_date=start_date,
            end_date=end_date,
            fast_period=20,
            slow_period=50,
            initial_capital=100000
        )

        if 'error' in result:
            print(f"❌ Error: {result['error']}")
            return False

        metrics = result['metrics']
        print(f"✅ Total Return: {metrics['total_return_pct']}%")
        print(f"✅ Number of Trades: {metrics['num_trades']}")
        print(f"✅ Win Rate: {metrics['win_rate_pct']}%")
        print(f"✅ Max Drawdown: {metrics['max_drawdown_pct']}%")
        print(f"✅ Sharpe Ratio: {metrics['sharpe_ratio']}")

        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_charts():
    """Test chart service"""
    print("\n" + "="*60)
    print("TEST 4: Chart Service")
    print("="*60)

    try:
        from services.chart_service import generate_chart
        from services.indicators_service import get_indicators

        print("Generating comprehensive chart for AAPL...")
        indicators = get_indicators('AAPL', '3mo')

        if 'error' in indicators:
            print(f"❌ Error getting data: {indicators['error']}")
            return False

        chart_base64 = generate_chart(
            indicators['raw_data'],
            chart_type='comprehensive',
            symbol='AAPL'
        )

        if chart_base64:
            print(f"✅ Chart generated successfully ({len(chart_base64)} characters)")
            print(f"✅ Chart can be embedded as: data:image/png;base64,{chart_base64[:50]}...")
            return True
        else:
            print("❌ Chart generation failed")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_orchestrator():
    """Test orchestrator service"""
    print("\n" + "="*60)
    print("TEST 5: Orchestrator Service")
    print("="*60)

    try:
        from services.finance_orchestrator import process_finance_query

        test_queries = [
            "What is the price of AAPL?",
            "Analyze TCS with RSI",
            "Find oversold stocks",
        ]

        for query in test_queries:
            print(f"\nQuery: '{query}'")
            result = process_finance_query(query)

            print(f"  Category: {result.get('category')}")
            print(f"  Response: {result.get('ai_response', 'N/A')[:100]}...")

            if 'error' in result:
                print(f"  ❌ Error: {result['error']}")
            else:
                print(f"  ✅ Success")

        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag():
    """Test RAG service (optional)"""
    print("\n" + "="*60)
    print("TEST 6: RAG Service (Optional)")
    print("="*60)

    try:
        from services.rag_service import rag_service

        if not rag_service.is_available():
            print("⚠️  RAG service not available (optional dependencies not installed)")
            print("   To enable: pip install PyPDF2 sentence-transformers chromadb")
            return True  # Not a failure, it's optional

        print("✅ RAG service is available and ready")
        print(f"✅ Collection: {rag_service.collection.name if rag_service.collection else 'N/A'}")

        summary = rag_service.get_document_summary()
        print(f"✅ Total document chunks: {summary.get('total_chunks', 0)}")

        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "🚀"*30)
    print("Finance AI Upgrade - Test Suite")
    print("🚀"*30)

    # Check environment
    print("\nEnvironment Check:")
    print(f"Python: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")

    # Check .env
    from dotenv import load_dotenv
    load_dotenv()

    gemini_key = os.getenv('GEMINI_API_KEY', '')
    if gemini_key:
        print(f"✅ GEMINI_API_KEY found ({gemini_key[:10]}...)")
    else:
        print("⚠️  GEMINI_API_KEY not found in .env")

    # Run tests
    results = {
        'Indicators': test_indicators(),
        'Screener': test_screener(),
        'Backtest': test_backtest(),
        'Charts': test_charts(),
        'Orchestrator': test_orchestrator(),
        'RAG': test_rag()
    }

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20s} {status}")

    total = len(results)
    passed = sum(results.values())

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Finance AI upgrade is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check the errors above.")

    return passed == total


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
