"""
Multi-Timeframe Stock Screener API Routes

Endpoints:
- GET /api/mtf-screener/regime-strip - NIFTY 50 regime probabilities
- GET /api/mtf-screener/screen/<timeframe> - Top 5 stocks for timeframe
- GET /api/mtf-screener/stock/<ticker>/<timeframe> - Detailed stock analysis
- GET /api/mtf-screener/sector-heatmap/<timeframe> - Sector heatmap
- GET /api/mtf-screener/all-timeframes - All timeframe results
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from middleware.feature_limit import feature_limit
from services.mtf_screener_service import get_mtf_screener_service
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """
    Recursively convert numpy types to Python native types for JSON serialization.
    Handles numpy.bool_, numpy.int64, numpy.float64, numpy.ndarray, etc.
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.str_, np.bytes_)):
        return str(obj)
    elif obj is np.nan or (isinstance(obj, float) and np.isnan(obj)):
        return None
    else:
        return obj

# Create Blueprint
mtf_screener_bp = Blueprint('mtf_screener', __name__, url_prefix='/api/mtf-screener')

# Valid timeframes
VALID_TIMEFRAMES = ['5m', '15m', '1h', '1d']


@mtf_screener_bp.route('/regime-strip', methods=['GET'])
@feature_limit('mtf-screener')
def get_regime_strip():
    """
    Get NIFTY 50 regime probabilities for dashboard header

    Returns:
        JSON with current regime and probabilities for all 4 states
    """
    try:
        service = get_mtf_screener_service()
        result = service.get_nifty_regime_strip()
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in regime-strip endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@mtf_screener_bp.route('/screen/<timeframe>', methods=['GET'])
@feature_limit('mtf-screener')
def screen_stocks(timeframe: str):
    """
    Get top 5 screened stocks for a specific timeframe

    Args:
        timeframe: One of '5m', '15m', '1h', '1d'

    Returns:
        JSON with top stocks, regime info, and screening summary
    """
    try:
        # Validate timeframe
        if timeframe not in VALID_TIMEFRAMES:
            return jsonify({
                "status": "error",
                "message": f"Invalid timeframe. Use one of: {', '.join(VALID_TIMEFRAMES)}"
            }), 400

        service = get_mtf_screener_service()
        result = service.screen_all_stocks(timeframe)
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in screen endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timeframe": timeframe
        }), 500


@mtf_screener_bp.route('/stock/<ticker>/<timeframe>', methods=['GET'])
@feature_limit('mtf-screener')
def get_stock_detail(ticker: str, timeframe: str):
    """
    Get detailed analysis for a specific stock

    Args:
        ticker: Stock ticker symbol (e.g., 'RELIANCE.NS' or 'RELIANCE')
        timeframe: One of '5m', '15m', '1h', '1d'

    Returns:
        JSON with complete stock analysis including score breakdown
    """
    try:
        # Validate timeframe
        if timeframe not in VALID_TIMEFRAMES:
            return jsonify({
                "status": "error",
                "message": f"Invalid timeframe. Use one of: {', '.join(VALID_TIMEFRAMES)}"
            }), 400

        # Add .NS suffix if not present
        if not ticker.endswith('.NS'):
            ticker = f"{ticker}.NS"

        service = get_mtf_screener_service()
        result = service.screen_single_stock(ticker, timeframe)
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in stock detail endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "ticker": ticker,
            "timeframe": timeframe
        }), 500


@mtf_screener_bp.route('/sector-heatmap/<timeframe>', methods=['GET'])
@feature_limit('mtf-screener')
def get_sector_heatmap(timeframe: str):
    """
    Get sector performance heatmap

    Args:
        timeframe: One of '5m', '15m', '1h', '1d'

    Returns:
        JSON with sector-wise performance data
    """
    try:
        # Validate timeframe
        if timeframe not in VALID_TIMEFRAMES:
            return jsonify({
                "status": "error",
                "message": f"Invalid timeframe. Use one of: {', '.join(VALID_TIMEFRAMES)}"
            }), 400

        service = get_mtf_screener_service()
        result = service.get_sector_heatmap(timeframe)
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in sector heatmap endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timeframe": timeframe
        }), 500


@mtf_screener_bp.route('/all-timeframes', methods=['GET'])
@feature_limit('mtf-screener')
def get_all_timeframes():
    """
    Get screening results for all 4 timeframes at once

    Returns:
        JSON with results for 5m, 15m, 1h, and 1d timeframes
    """
    try:
        service = get_mtf_screener_service()
        result = service.get_all_timeframe_results()
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in all-timeframes endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@mtf_screener_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for MTF Screener service

    Returns:
        JSON with service status
    """
    try:
        service = get_mtf_screener_service()

        return jsonify({
            "status": "healthy",
            "service": "mtf-screener",
            "supported_timeframes": VALID_TIMEFRAMES,
            "stock_universe_size": len(service.stock_universe),
            "cache_ttl_seconds": service.cache_ttl,
            "features": ["LONG", "SHORT", "dual_scoring"]
        }), 200

    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


# ==========================================
# SHORT/SELLING SCREENER ENDPOINTS
# ==========================================

@mtf_screener_bp.route('/shorts/<timeframe>', methods=['GET'])
@feature_limit('mtf-screener')
def screen_shorts(timeframe: str):
    """
    Get top SHORT opportunities for a specific timeframe

    This endpoint returns stocks with highest SHORT scores,
    focusing on selling opportunities.

    Args:
        timeframe: One of '5m', '15m', '1h', '1d'

    Returns:
        JSON with top SHORT stocks, sorted by short_score
    """
    try:
        # Validate timeframe
        if timeframe not in VALID_TIMEFRAMES:
            return jsonify({
                "status": "error",
                "message": f"Invalid timeframe. Use one of: {', '.join(VALID_TIMEFRAMES)}"
            }), 400

        service = get_mtf_screener_service()
        result = service.screen_all_stocks(timeframe)

        if result.get('status') != 'success':
            return jsonify(result), 500

        # Filter and sort by SHORT score
        all_stocks = result.get('top_stocks', [])

        # Re-sort by short_score (descending)
        shorts_sorted = sorted(
            all_stocks,
            key=lambda x: x.get('short_score', 0),
            reverse=True
        )

        # Filter to stocks with meaningful short scores
        top_shorts = [s for s in shorts_sorted if s.get('short_score', 0) >= 50][:10]

        # Update ranks
        for i, stock in enumerate(top_shorts, 1):
            stock['short_rank'] = i

        result = convert_numpy_types({
            "status": "success",
            "timeframe": timeframe,
            "mode": "SHORTS",
            "description": "Top SHORT opportunities - stocks ready to sell",
            "regime_strip": result.get('regime_strip', {}),
            "top_shorts": top_shorts,
            "total_screened": result.get('total_screened', 0),
            "shorts_found": len(top_shorts),
            "timestamp": result.get('timestamp')
        })

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in shorts endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timeframe": timeframe
        }), 500


@mtf_screener_bp.route('/shorts/stock/<ticker>/<timeframe>', methods=['GET'])
@feature_limit('mtf-screener')
def get_short_stock_detail(ticker: str, timeframe: str):
    """
    Get detailed SHORT analysis for a specific stock

    Args:
        ticker: Stock ticker symbol (e.g., 'RELIANCE.NS' or 'RELIANCE')
        timeframe: One of '5m', '15m', '1h', '1d'

    Returns:
        JSON with complete SHORT analysis including breakdown signals
    """
    try:
        # Validate timeframe
        if timeframe not in VALID_TIMEFRAMES:
            return jsonify({
                "status": "error",
                "message": f"Invalid timeframe. Use one of: {', '.join(VALID_TIMEFRAMES)}"
            }), 400

        # Add .NS suffix if not present
        if not ticker.endswith('.NS'):
            ticker = f"{ticker}.NS"

        service = get_mtf_screener_service()
        result = service.screen_single_stock(ticker, timeframe)

        if result.get('status') != 'success':
            return jsonify(result), 500

        # Add SHORT-specific analysis
        short_analysis = {
            "short_score": result.get('short_score', 30),
            "short_eligible": result.get('short_score', 30) >= 65,
            "short_breakdown": result.get('short_breakdown', {}),
            "short_signals": result.get('short_signals', []),
            "short_trade_setup": result.get('short_trade_setup', {}),
            "direction_recommendation": result.get('direction', 'HOLD'),
            "short_strength": "STRONG" if result.get('short_score', 0) >= 80 else
                             "MODERATE" if result.get('short_score', 0) >= 65 else
                             "WEAK" if result.get('short_score', 0) >= 50 else "NONE"
        }

        result['short_analysis'] = short_analysis
        result = convert_numpy_types(result)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in short stock detail endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "ticker": ticker,
            "timeframe": timeframe
        }), 500


@mtf_screener_bp.route('/dual/<timeframe>', methods=['GET'])
@feature_limit('mtf-screener')
def screen_dual(timeframe: str):
    """
    Get dual scoring results (LONG and SHORT) for all stocks

    This endpoint returns both LONG and SHORT scores for comparison,
    showing which direction is stronger for each stock.

    Args:
        timeframe: One of '5m', '15m', '1h', '1d'

    Returns:
        JSON with stocks showing both LONG and SHORT scores
    """
    try:
        # Validate timeframe
        if timeframe not in VALID_TIMEFRAMES:
            return jsonify({
                "status": "error",
                "message": f"Invalid timeframe. Use one of: {', '.join(VALID_TIMEFRAMES)}"
            }), 400

        service = get_mtf_screener_service()
        result = service.screen_all_stocks(timeframe)

        if result.get('status') != 'success':
            return jsonify(result), 500

        # Format stocks with dual scoring emphasis
        all_stocks = result.get('top_stocks', [])

        dual_results = {
            "status": "success",
            "timeframe": timeframe,
            "mode": "DUAL",
            "description": "Dual scoring - compare LONG vs SHORT opportunities",
            "regime_strip": result.get('regime_strip', {}),
            "stocks": all_stocks,
            "summary": {
                "total_screened": result.get('total_screened', 0),
                "longs": len([s for s in all_stocks if s.get('direction') == 'LONG']),
                "shorts": len([s for s in all_stocks if s.get('direction') == 'SHORT']),
                "holds": len([s for s in all_stocks if s.get('direction') == 'HOLD'])
            },
            "timestamp": result.get('timestamp')
        }

        dual_results = convert_numpy_types(dual_results)
        return jsonify(dual_results), 200

    except Exception as e:
        logger.error(f"Error in dual endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timeframe": timeframe
        }), 500


@mtf_screener_bp.route('/regime-strip-short', methods=['GET'])
@feature_limit('mtf-screener')
def get_regime_strip_short():
    """
    Get NIFTY 50 regime with SHORT interpretation

    Returns:
        JSON with regime probabilities and SHORT trading guidance
    """
    try:
        from screener_model.mtf_regime_detector import get_regime_detector

        detector = get_regime_detector()
        result = detector.get_nifty_regime_strip_with_short()
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in regime-strip-short endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ==========================================
# MACRO DASHBOARD ENDPOINTS
# ==========================================

@mtf_screener_bp.route('/macro/dashboard', methods=['GET'])
@feature_limit('mtf-screener')
def get_macro_dashboard():
    """
    Get full macro dashboard with all indicators

    Returns:
        JSON with all macro sections and SHORT bias score
    """
    try:
        from services.macro_dashboard_service import get_macro_dashboard_service

        service = get_macro_dashboard_service()
        result = service.get_full_dashboard()
        result = convert_numpy_types(result)

        return jsonify(result), 200 if result.get('status') == 'success' else 500

    except Exception as e:
        logger.error(f"Error in macro dashboard endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@mtf_screener_bp.route('/macro/bias-score', methods=['GET'])
@feature_limit('mtf-screener')
def get_macro_bias_score():
    """
    Get calculated SHORT bias score

    Returns:
        JSON with score (0-20), breakdown, and recommendation
    """
    try:
        from services.macro_dashboard_service import get_macro_dashboard_service

        service = get_macro_dashboard_service()
        result = service.calculate_short_bias_score()
        result = convert_numpy_types(result)

        return jsonify({
            "status": "success",
            **result
        }), 200

    except Exception as e:
        logger.error(f"Error in macro bias score endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@mtf_screener_bp.route('/macro/section/<section_name>', methods=['GET'])
@feature_limit('mtf-screener')
def get_macro_section(section_name: str):
    """
    Get specific macro section data

    Args:
        section_name: One of 'interest_rates', 'currency_flows', 'growth_inflation',
                     'volatility_sentiment', 'oil_commodities', 'us_macro', 'market_breadth'

    Returns:
        JSON with section-specific indicators
    """
    try:
        from services.macro_dashboard_service import get_macro_dashboard_service

        service = get_macro_dashboard_service()

        section_methods = {
            'interest_rates': service.get_interest_rates_section,
            'currency_flows': service.get_currency_flows_section,
            'growth_inflation': service.get_growth_inflation_section,
            'volatility_sentiment': service.get_volatility_sentiment_section,
            'oil_commodities': service.get_oil_commodities_section,
            'us_macro': service.get_us_macro_section,
            'market_breadth': service.get_market_breadth_section
        }

        if section_name not in section_methods:
            return jsonify({
                "status": "error",
                "message": f"Invalid section. Use one of: {', '.join(section_methods.keys())}"
            }), 400

        result = section_methods[section_name]()
        result = convert_numpy_types(result)

        return jsonify({
            "status": "success",
            "section": section_name,
            "data": result
        }), 200

    except Exception as e:
        logger.error(f"Error in macro section endpoint: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "section": section_name
        }), 500


# Error handlers
@mtf_screener_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Endpoint not found"
    }), 404


@mtf_screener_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Internal server error"
    }), 500
