"""
Finance AI Routes - API endpoints for Welth AI Assistant

Endpoints:
- POST /api/finance-ai/query - Main query endpoint
- GET /api/finance-ai/indicators/<symbol> - Get technical indicators
- POST /api/finance-ai/screener - Run stock screener
- POST /api/finance-ai/backtest - Run strategy backtest
- GET /api/finance-ai/screens - Get available predefined screens
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import logging
from datetime import datetime

# Import middleware
from middleware.anon_limit import anon_or_auth_feature_limit

# Heavy service imports deferred into route functions to avoid slow startup
# services.finance_orchestrator, indicators_service, screener_service,
# simple_backtest_service, chart_service all import yfinance/pandas/numpy
# and are only needed when the user accesses these specific features.

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
finance_ai_bp = Blueprint('finance_ai', __name__, url_prefix='/api/finance-ai')


def validate_json_request(f):
    """Decorator to validate JSON requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            return jsonify({'error': 'Content-Type must be application/json'}), 400
        return f(*args, **kwargs)
    return decorated_function


@finance_ai_bp.route('/query', methods=['POST'])
@validate_json_request
@anon_or_auth_feature_limit('welth-ai-assistant')
def enhanced_query():
    """
    Main enhanced query endpoint - processes any finance question with conversation context

    Body:
    {
        "query": "Analyze RELIANCE stock with RSI",
        "conversation_history": [
            {"role": "user", "content": "What is Reliance?"},
            {"role": "assistant", "content": "Reliance Industries is..."}
        ]
    }

    Response:
    {
        "query": "Analyze RELIANCE stock with RSI",
        "category": "technical_analysis",
        "ai_response": "Based on the technical analysis...",
        "data": {...},
        "chart_base64": "...",
        "timestamp": "2024-01-01T12:00:00",
        "usage": {...}  // For anonymous users
    }
    """
    try:
        from flask import g

        data = request.get_json()
        query = data.get('query', '').strip()
        conversation_history = data.get('conversation_history', [])

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Process query through orchestrator with conversation context
        from services.finance_orchestrator import process_finance_query
        result = process_finance_query(query, conversation_history)

        # Add usage info for anonymous users (set by middleware)
        if hasattr(g, '_anon_feature_usage'):
            result['usage'] = {
                'remaining': g._anon_feature_usage['remaining'],
                'limit': g._anon_feature_usage['limit'],
                'used': g._anon_feature_usage['used']
            }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in enhanced_query: {e}")
        return jsonify({
            'error': 'query_failed',
            'message': 'An error occurred processing your query. Please try again.'
        }), 500


@finance_ai_bp.route('/indicators/<symbol>', methods=['GET'])
def get_stock_indicators(symbol):
    """
    Get technical indicators for a stock

    Query params:
    - period: Data period (1mo, 3mo, 6mo, 1y, 2y) - default: 6mo

    Response:
    {
        "symbol": "RELIANCE.NS",
        "current_price": 2500.50,
        "indicators": {
            "moving_averages": {...},
            "rsi": {...},
            "macd": {...},
            "bollinger_bands": {...}
        },
        "raw_data": {...}
    }
    """
    try:
        period = request.args.get('period', '6mo')

        # Get indicators
        from services.indicators_service import get_indicators
        result = get_indicators(symbol, period)

        if 'error' in result:
            return jsonify(result), 404

        # Generate chart
        from services.chart_service import generate_chart
        chart_base64 = generate_chart(
            result['raw_data'],
            chart_type='comprehensive',
            symbol=symbol
        )

        result['chart_base64'] = chart_base64

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in get_stock_indicators: {e}")
        return jsonify({'error': 'Unable to fetch indicators. Please check the symbol and try again.'}), 500


@finance_ai_bp.route('/screener', methods=['POST'])
@validate_json_request
def run_screener():
    """
    Run stock screener with custom or predefined rules

    Body (predefined screen):
    {
        "screen_name": "oversold_bounce",
        "universe": "NIFTY50",
        "top_n": 10
    }

    Body (custom rules):
    {
        "rules": {
            "rsi_oversold": true,
            "uptrend": true
        },
        "universe": "NIFTY50",
        "top_n": 10
    }

    Response:
    {
        "screen_name": "Oversold Bounce Candidates",
        "universe": "NIFTY50",
        "total_matches": 5,
        "results": [...]
    }
    """
    try:
        data = request.get_json()

        # Check if using predefined screen
        if 'screen_name' in data:
            screen_name = data.get('screen_name')
            universe = data.get('universe', 'NIFTY50')
            top_n = data.get('top_n', 10)

            from services.screener_service import run_screen, screen_stocks, get_available_screens
            result = run_screen(screen_name, universe, top_n)
        else:
            # Custom rules
            rules = data.get('rules', {})
            universe = data.get('universe', 'NIFTY50')
            top_n = data.get('top_n', 10)

            from services.screener_service import screen_stocks
            results = screen_stocks(universe, rules, top_n)
            result = {
                'universe': universe,
                'rules': rules,
                'total_matches': len(results),
                'results': results
            }

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in run_screener: {e}")
        return jsonify({'error': 'Screener encountered an error. Please try again.'}), 500


@finance_ai_bp.route('/screens', methods=['GET'])
def list_available_screens():
    """
    Get list of available predefined screens

    Response:
    {
        "oversold_bounce": {
            "name": "Oversold Bounce Candidates",
            "description": "...",
            "rules": {...}
        },
        ...
    }
    """
    try:
        from services.screener_service import get_available_screens
        screens = get_available_screens()
        return jsonify(screens), 200

    except Exception as e:
        logger.error(f"Error in list_available_screens: {e}")
        return jsonify({'error': 'Unable to load available screens.'}), 500


@finance_ai_bp.route('/backtest', methods=['POST'])
@validate_json_request
def run_strategy_backtest():
    """
    Run a strategy backtest

    Body:
    {
        "strategy": "sma_crossover",
        "symbol": "AAPL",
        "start_date": "2023-01-01",
        "end_date": "2024-01-01",
        "parameters": {
            "fast_period": 20,
            "slow_period": 50
        },
        "initial_capital": 100000
    }

    Response:
    {
        "strategy": "SMA Crossover",
        "symbol": "AAPL",
        "metrics": {...},
        "equity_curve": {...},
        "trades": [...],
        "chart_base64": "..."
    }
    """
    try:
        data = request.get_json()

        strategy = data.get('strategy', 'sma_crossover')
        symbol = data.get('symbol')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        initial_capital = data.get('initial_capital', 100000)
        parameters = data.get('parameters', {})

        if not symbol or not start_date or not end_date:
            return jsonify({
                'error': 'symbol, start_date, and end_date are required'
            }), 400

        # Run backtest
        from services.simple_backtest_service import run_backtest
        result = run_backtest(
            strategy=strategy,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            **parameters
        )

        if 'error' in result:
            return jsonify(result), 400

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in run_strategy_backtest: {e}")
        return jsonify({'error': 'Backtest failed. Please check your parameters and try again.'}), 500


@finance_ai_bp.route('/status', methods=['GET'])
def service_status():
    """Get status of all finance AI services"""
    try:
        status = {
            'orchestrator': 'active',
            'indicators': 'active',
            'screener': 'active',
            'backtest': 'active',
            'charts': 'active',
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(status), 200

    except Exception as e:
        logger.error(f"Error in service_status: {e}")
        return jsonify({'error': 'Service status check failed'}), 500


# Helper to register blueprint with app
def register_finance_ai_routes(app):
    """Register finance AI routes with Flask app"""
    app.register_blueprint(finance_ai_bp)
    logger.info("Finance AI routes registered")
