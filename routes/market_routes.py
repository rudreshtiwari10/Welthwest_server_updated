"""
Market Intelligence API Routes
Public: list/view AI-generated market articles
Admin: trigger pipeline, delete/update articles
"""

from flask import Blueprint, request, jsonify
from functools import wraps

market_bp = Blueprint('market', __name__)


def get_models():
    """Lazy import to avoid circular dependency"""
    from app import mongo
    from models.market_article import MarketArticle
    return MarketArticle(mongo.db)


def admin_required(f):
    """Require admin/developer role"""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        try:
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            from app import mongo
            user = mongo.db.users.find_one({'_id': user_id})
            if not user or user.get('role') not in ['admin', 'developer']:
                return jsonify({'success': False, 'error': 'Admin access required'}), 403
        except Exception:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


# ── Public Routes ──────────────────────────────────────────────

@market_bp.route('/api/markets/articles', methods=['GET'])
def list_articles():
    """List published market articles with pagination and filters"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 12))
        category = request.args.get('category')
        sector = request.args.get('sector')
        sentiment = request.args.get('sentiment')

        model = get_models()
        result = model.list_published(
            page=page, limit=limit,
            category=category, sector=sector, sentiment=sentiment,
        )

        from models.market_article import MarketArticle
        for article in result['articles']:
            MarketArticle.serialize(article)

        return jsonify({'success': True, **result}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@market_bp.route('/api/markets/articles/<slug>', methods=['GET'])
def get_article(slug):
    """Get single article by slug and increment views"""
    try:
        model = get_models()
        article = model.get_by_slug(slug)

        if not article:
            return jsonify({'success': False, 'error': 'Article not found'}), 404

        model.increment_views(slug)

        # Get related articles
        from models.market_article import MarketArticle
        related = model.get_related(slug, limit=3)
        for r in related:
            MarketArticle.serialize(r)

        MarketArticle.serialize(article)

        return jsonify({
            'success': True,
            'article': article,
            'related': related,
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@market_bp.route('/api/markets/categories', methods=['GET'])
def get_categories():
    """Get article categories with counts"""
    try:
        model = get_models()
        categories = model.get_categories_with_counts()

        # Add labels
        labels = {
            'market-pulse': 'Market Pulse',
            'deep-analysis': 'Deep Analysis',
            'stock-signals': 'Stock Signals',
            'global-impact': 'Global Impact',
        }
        for cat in categories:
            cat['label'] = labels.get(cat['id'], cat['id'].replace('-', ' ').title())

        return jsonify({'success': True, 'categories': categories}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Admin Routes ───────────────────────────────────────────────

@market_bp.route('/api/markets/trigger-pipeline', methods=['POST'])
@admin_required
def trigger_pipeline():
    """Manually trigger the news intelligence pipeline"""
    try:
        max_articles = int(request.args.get('max', 10))

        from app import mongo
        from services.news_intelligence import NewsIntelligence
        pipeline = NewsIntelligence(mongo.db)
        results = pipeline.run_pipeline(max_articles=max_articles)

        return jsonify({'success': True, 'results': results}), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@market_bp.route('/api/markets/articles/<slug>', methods=['DELETE'])
@admin_required
def delete_article(slug):
    """Delete a market article"""
    try:
        model = get_models()
        success = model.delete(slug)
        if not success:
            return jsonify({'success': False, 'error': 'Article not found'}), 404
        return jsonify({'success': True, 'message': 'Article deleted'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@market_bp.route('/api/markets/articles/<slug>', methods=['PATCH'])
@admin_required
def update_article(slug):
    """Update a market article"""
    try:
        data = request.get_json()
        model = get_models()
        success = model.update(slug, data)
        if not success:
            return jsonify({'success': False, 'error': 'Article not found or update failed'}), 404
        return jsonify({'success': True, 'message': 'Article updated'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
