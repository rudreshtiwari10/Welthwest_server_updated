"""
Risk Calculator Phase 5 Routes: Trade Journal with AI Insights
"""

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.risk_calculator_phase5_service import risk_phase5_service
from middleware.feature_limit import feature_limit
from datetime import datetime
import io

risk_phase5_bp = Blueprint('risk_phase5', __name__, url_prefix='/api/risk-calculator/phase5')


@risk_phase5_bp.route('/update-journal-entry', methods=['PUT'])
@jwt_required()
@feature_limit('risk-calculator')
def update_journal_entry():
    """Update trade journal entry with tags, notes, lessons"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()

        if 'trade_id' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing trade_id'
            }), 400

        journal_entry = risk_phase5_service.update_trade_journal_entry(
            user_id=user_id,
            trade_id=data['trade_id'],
            journal_data=data
        )

        # Convert ObjectId to string
        journal_entry['_id'] = str(journal_entry['_id'])
        if 'trade_id' in journal_entry:
            journal_entry['trade_id'] = str(journal_entry['trade_id'])

        return jsonify({
            'success': True,
            'message': 'Journal entry updated successfully',
            'journal_entry': journal_entry
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase5_bp.route('/journal-entries', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_journal_entries():
    """Get filtered trade journal entries"""
    try:
        user_id = get_jwt_identity()

        # Get filter parameters
        filters = {}
        if request.args.get('strategy_tag'):
            filters['strategy_tag'] = request.args.get('strategy_tag')
        if request.args.get('emotion_tag'):
            filters['emotion_tag'] = request.args.get('emotion_tag')
        if request.args.get('start_date'):
            filters['start_date'] = datetime.fromisoformat(request.args.get('start_date'))
        if request.args.get('end_date'):
            filters['end_date'] = datetime.fromisoformat(request.args.get('end_date'))
        if request.args.get('min_pnl'):
            filters['min_pnl'] = float(request.args.get('min_pnl'))
        if request.args.get('max_pnl'):
            filters['max_pnl'] = float(request.args.get('max_pnl'))

        limit = request.args.get('limit', 50, type=int)
        skip = request.args.get('skip', 0, type=int)

        entries = risk_phase5_service.get_journal_entries(
            user_id=user_id,
            filters=filters,
            limit=limit,
            skip=skip
        )

        # Convert ObjectIds to strings
        for entry in entries:
            entry['_id'] = str(entry['_id'])
            if 'trade_id' in entry:
                entry['trade_id'] = str(entry['trade_id'])

        return jsonify({
            'success': True,
            'entries': entries,
            'count': len(entries)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase5_bp.route('/generate-insights', methods=['POST'])
@jwt_required()
@feature_limit('risk-calculator')
def generate_insights():
    """Generate AI insights from trade journal"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}

        period_days = data.get('period_days', 30)

        if period_days < 1 or period_days > 365:
            return jsonify({
                'success': False,
                'error': 'period_days must be between 1 and 365'
            }), 400

        insights = risk_phase5_service.generate_ai_insights(user_id, period_days)

        # Convert ObjectId to string
        if '_id' in insights:
            insights['_id'] = str(insights['_id'])

        return jsonify({
            'success': True,
            'message': 'AI insights generated successfully',
            'insights': insights
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase5_bp.route('/insights', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def get_cached_insights():
    """Get cached AI insights"""
    try:
        user_id = get_jwt_identity()
        days = request.args.get('days', 30, type=int)

        # Get most recent insights for this period
        from database import db
        insights = db['risk_calculator_ai_insights'].find_one(
            {'user_id': user_id},
            sort=[('generated_at', -1)]
        )

        if insights:
            insights['_id'] = str(insights['_id'])
            return jsonify({
                'success': True,
                'insights': insights
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'No insights found. Generate insights first.'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase5_bp.route('/export-csv', methods=['GET'])
@jwt_required()
@feature_limit('risk-calculator')
def export_csv():
    """Export trade journal to CSV"""
    try:
        user_id = get_jwt_identity()

        # Get filter parameters
        filters = {}
        if request.args.get('start_date'):
            filters['start_date'] = datetime.fromisoformat(request.args.get('start_date'))
        if request.args.get('end_date'):
            filters['end_date'] = datetime.fromisoformat(request.args.get('end_date'))

        csv_content = risk_phase5_service.export_journal_csv(user_id, filters)

        # Create file-like object
        output = io.BytesIO()
        output.write(csv_content.encode('utf-8'))
        output.seek(0)

        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'trade_journal_{datetime.now().strftime("%Y%m%d")}.csv'
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@risk_phase5_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'risk_calculator_phase5',
        'status': 'healthy'
    }), 200
