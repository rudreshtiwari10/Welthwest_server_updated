"""
Pattern Analysis Routes
Endpoints for 3-model AI pattern analysis
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.pattern_analysis_service import pattern_analysis_service
from database import db
from bson import ObjectId
from datetime import datetime, timedelta

pattern_analysis_bp = Blueprint('pattern_analysis', __name__, url_prefix='/api/pattern-analysis')


@pattern_analysis_bp.route('/analyze', methods=['POST'])
def analyze_patterns():
    """
    Run 3-model AI pattern analysis on a stock

    Request Body:
    {
        "symbol": "RELIANCE",
        "timeframe": "1d",
        "lookback_days": 90
    }

    Response:
    {
        "success": true,
        "analysis": {...},
        "analysis_id": "..."
    }
    """
    try:
        data = request.get_json()

        symbol = data.get('symbol')
        timeframe = data.get('timeframe', '1d')
        lookback_days = data.get('lookback_days', 90)

        if not symbol:
            return jsonify({'success': False, 'error': 'Symbol is required'}), 400

        # Run analysis
        analysis = pattern_analysis_service.analyze_stock(symbol, timeframe, lookback_days)

        # Save to database
        analysis_doc = {
            'symbol': symbol,
            'timeframe': timeframe,
            'lookback_days': lookback_days,
            **analysis,
            'created_at': datetime.now()
        }

        result = db.pattern_analysis.insert_one(analysis_doc)
        analysis_id = str(result.inserted_id)

        return jsonify({
            'success': True,
            'analysis': analysis,
            'analysis_id': analysis_id
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@pattern_analysis_bp.route('/history/<symbol>', methods=['GET'])
@jwt_required()
def get_pattern_history(symbol):
    """
    Get historical pattern analysis for a symbol

    Query Params:
        days: Number of days to look back (default: 30)

    Response:
    {
        "success": true,
        "symbol": "RELIANCE",
        "analyses": [...]
    }
    """
    try:
        days = request.args.get('days', 30, type=int)

        from_date = datetime.now() - timedelta(days=days)

        analyses = list(db.pattern_analysis.find({
            'symbol': symbol,
            'created_at': {'$gte': from_date}
        }).sort('created_at', -1))

        # Convert ObjectId to string
        for analysis in analyses:
            analysis['_id'] = str(analysis['_id'])

        return jsonify({
            'success': True,
            'symbol': symbol,
            'analyses': analyses
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@pattern_analysis_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'pattern_analysis',
        'status': 'healthy'
    }), 200
