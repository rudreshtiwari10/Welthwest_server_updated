"""
Finance AI Routes - Enhanced API endpoints for upgraded Wealth AI Assistant

New Enhanced Endpoints:
- POST /api/finance-ai/query - Main query endpoint (replaces basic chat)
- GET /api/finance-ai/indicators/<symbol> - Get technical indicators
- POST /api/finance-ai/screener - Run stock screener
- POST /api/finance-ai/backtest - Run strategy backtest
- POST /api/finance-ai/upload-pdf - Upload PDF for RAG analysis
- POST /api/finance-ai/doc-query - Query uploaded documents
- GET /api/finance-ai/screens - Get available predefined screens
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import logging
import os
from werkzeug.utils import secure_filename

# Import middleware
from middleware.anon_limit import anon_or_auth_feature_limit

# Import services
from services.finance_orchestrator import process_finance_query
from services.indicators_service import get_indicators, get_signal_summary
from services.screener_service import screen_stocks, run_screen, get_available_screens
from services.simple_backtest_service import run_backtest
# RAG service disabled - PDF document analysis not currently used
# from services.rag_service import ingest_pdf, search_documents, rag_service
class _DisabledRAG:
    def is_available(self): return False
rag_service = _DisabledRAG()
def ingest_pdf(*a, **kw): return None
def search_documents(*a, **kw): return []
from services.chart_service import generate_chart

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
finance_ai_bp = Blueprint('finance_ai', __name__, url_prefix='/api/finance-ai')

# Configuration
UPLOAD_FOLDER = './uploaded_pdfs'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
            'error': str(e),
            'message': 'An error occurred processing your query'
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
        result = get_indicators(symbol, period)

        if 'error' in result:
            return jsonify(result), 404

        # Generate chart
        chart_base64 = generate_chart(
            result['raw_data'],
            chart_type='comprehensive',
            symbol=symbol
        )

        result['chart_base64'] = chart_base64

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in get_stock_indicators: {e}")
        return jsonify({'error': str(e)}), 500


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

            result = run_screen(screen_name, universe, top_n)
        else:
            # Custom rules
            rules = data.get('rules', {})
            universe = data.get('universe', 'NIFTY50')
            top_n = data.get('top_n', 10)

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
        return jsonify({'error': str(e)}), 500


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
        screens = get_available_screens()
        return jsonify(screens), 200

    except Exception as e:
        logger.error(f"Error in list_available_screens: {e}")
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


@finance_ai_bp.route('/upload-pdf', methods=['POST'])
def upload_pdf():
    """
    Upload a PDF for RAG analysis

    Form data:
    - file: PDF file
    - company: Company name (optional)
    - report_type: Type of report (optional)
    - report_date: Report date (optional)

    Response:
    {
        "success": true,
        "doc_id": "abc123",
        "num_chunks": 45,
        "metadata": {...}
    }
    """
    try:
        # Check if RAG service is available
        if not rag_service.is_available():
            return jsonify({
                'error': 'RAG service not available',
                'message': 'Please install required dependencies: PyPDF2, sentence-transformers, chromadb',
                'install_command': 'pip install PyPDF2 sentence-transformers chromadb'
            }), 503

        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        # Save file
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Prepare metadata
        metadata = {
            'company': request.form.get('company', ''),
            'report_type': request.form.get('report_type', ''),
            'report_date': request.form.get('report_date', '')
        }

        # Ingest document
        result = ingest_pdf(filepath, metadata)

        # Clean up file
        os.remove(filepath)

        if 'error' in result:
            return jsonify(result), 500

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in upload_pdf: {e}")
        return jsonify({'error': str(e)}), 500


@finance_ai_bp.route('/doc-query', methods=['POST'])
@validate_json_request
def query_documents():
    """
    Query uploaded documents

    Body:
    {
        "query": "What was the revenue growth?",
        "top_k": 5,
        "filter": {
            "company": "Tesla"
        }
    }

    Response:
    {
        "query": "What was the revenue growth?",
        "results": [
            {
                "text": "...",
                "metadata": {...},
                "distance": 0.23
            }
        ]
    }
    """
    try:
        if not rag_service.is_available():
            return jsonify({
                'error': 'RAG service not available',
                'message': 'Please install required dependencies'
            }), 503

        data = request.get_json()
        query = data.get('query', '').strip()
        top_k = data.get('top_k', 5)
        filter_metadata = data.get('filter', None)

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        # Search documents
        results = search_documents(query, top_k)

        return jsonify({
            'query': query,
            'num_results': len(results),
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Error in query_documents: {e}")
        return jsonify({'error': str(e)}), 500


@finance_ai_bp.route('/status', methods=['GET'])
def service_status():
    """
    Get status of all finance AI services

    Response:
    {
        "orchestrator": "active",
        "indicators": "active",
        "screener": "active",
        "backtest": "active",
        "rag": "active" | "unavailable",
        "charts": "active"
    }
    """
    try:
        status = {
            'orchestrator': 'active',
            'indicators': 'active',
            'screener': 'active',
            'backtest': 'active',
            'rag': 'active' if rag_service.is_available() else 'unavailable',
            'charts': 'active',
            'timestamp': pd.Timestamp.now().isoformat()
        }

        if not rag_service.is_available():
            status['rag_missing_dependencies'] = {
                'pdf': not rag_service.is_available(),
                'install_command': 'pip install PyPDF2 sentence-transformers chromadb'
            }

        return jsonify(status), 200

    except Exception as e:
        logger.error(f"Error in service_status: {e}")
        return jsonify({'error': str(e)}), 500


# Helper to register blueprint with app
def register_finance_ai_routes(app):
    """Register finance AI routes with Flask app"""
    app.register_blueprint(finance_ai_bp)
    logger.info("Finance AI routes registered")
