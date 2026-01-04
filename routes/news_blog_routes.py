"""
News & Blogs API Routes
- News: External aggregation only (NO database storage)
- Blogs: Internal content management (database storage, admin-only CRUD)
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from services.news_aggregator import NewsAggregator
from models.blog import Blog
import re

# Create blueprint
news_blog_bp = Blueprint('news_blog', __name__)

def get_blog_model():
    """Get Blog model instance (import here to avoid circular dependency)"""
    from app import mongo
    return Blog(mongo.db)

def admin_required(f):
    """Decorator to require admin/developer role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Import here to avoid circular dependency
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

        try:
            verify_jwt_in_request()
            current_user_id = get_jwt_identity()

            # Check if user is admin/developer
            from app import mongo
            user = mongo.db.users.find_one({'_id': current_user_id})

            if not user or user.get('role') not in ['admin', 'developer']:
                return jsonify({
                    'success': False,
                    'error': 'Admin access required'
                }), 403

        except Exception as e:
            return jsonify({
                'success': False,
                'error': 'Authentication required'
            }), 401

        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# NEWS ROUTES (External, No DB Storage)
# ============================================================================

@news_blog_bp.route('/api/news', methods=['GET'])
def get_news():
    """
    Get news from external sources
    Query params:
    - category: all|indian_markets|global_markets|nse|bse|ipos|economy|banking|corporate
    - region: indian|global
    - limit: number of articles
    """
    try:
        category = request.args.get('category', 'all')
        region = request.args.get('region', 'indian')
        limit = int(request.args.get('limit', 50))

        result = NewsAggregator.get_news(category=category, region=region, limit=limit)

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/news/search', methods=['GET'])
def search_news():
    """
    Search news articles
    Query params:
    - q: search query
    - category: filter by category
    - limit: number of results
    """
    try:
        query = request.args.get('q', '')
        category = request.args.get('category', 'all')
        limit = int(request.args.get('limit', 20))

        if not query:
            return jsonify({
                'success': False,
                'error': 'Search query required'
            }), 400

        result = NewsAggregator.search_news(query=query, category=category, limit=limit)

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/news/categories', methods=['GET'])
def get_news_categories():
    """Get available news categories"""
    categories = [
        {'id': 'all', 'name': 'All News', 'icon': 'newspaper'},
        {'id': 'indian_markets', 'name': 'Indian Markets', 'icon': 'chart-bar'},
        {'id': 'global_markets', 'name': 'Global Markets', 'icon': 'globe'},
        {'id': 'nse', 'name': 'NSE', 'icon': 'building'},
        {'id': 'bse', 'name': 'BSE', 'icon': 'building'},
        {'id': 'ipos', 'name': 'IPOs', 'icon': 'rocket'},
        {'id': 'economy', 'name': 'Economy', 'icon': 'currency-rupee'},
        {'id': 'banking', 'name': 'Banking & Finance', 'icon': 'bank'},
        {'id': 'corporate', 'name': 'Corporate Results', 'icon': 'document-text'}
    ]

    return jsonify({
        'success': True,
        'categories': categories
    }), 200


# ============================================================================
# BLOG ROUTES (Internal, Database Storage, Admin-Only CRUD)
# ============================================================================

@news_blog_bp.route('/api/blogs', methods=['GET'])
def get_blogs():
    """
    Get published blogs
    Query params:
    - page: page number
    - limit: items per page
    - category: filter by category
    """
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        category = request.args.get('category')

        blog_model = get_blog_model()
        result = blog_model.get_all(status='published', page=page, limit=limit, category=category)

        # Convert ObjectId to string
        for blog in result['blogs']:
            blog['_id'] = str(blog['_id'])
            if blog.get('publishedAt'):
                blog['publishedAt'] = blog['publishedAt'].isoformat()
            if blog.get('createdAt'):
                blog['createdAt'] = blog['createdAt'].isoformat()
            if blog.get('updatedAt'):
                blog['updatedAt'] = blog['updatedAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/blogs/<slug>', methods=['GET'])
def get_blog_by_slug(slug):
    """Get blog by slug and increment view count"""
    try:
        blog_model = get_blog_model()
        blog = blog_model.get_by_slug(slug)

        if not blog:
            return jsonify({
                'success': False,
                'error': 'Blog not found'
            }), 404

        # Only show published blogs to public
        if blog.get('status') != 'published':
            return jsonify({
                'success': False,
                'error': 'Blog not found'
            }), 404

        # Increment view count
        blog_model.increment_view(str(blog['_id']))

        # Convert ObjectId to string
        blog['_id'] = str(blog['_id'])
        if blog.get('publishedAt'):
            blog['publishedAt'] = blog['publishedAt'].isoformat()
        if blog.get('createdAt'):
            blog['createdAt'] = blog['createdAt'].isoformat()
        if blog.get('updatedAt'):
            blog['updatedAt'] = blog['updatedAt'].isoformat()

        return jsonify({
            'success': True,
            'blog': blog
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/blogs/search', methods=['GET'])
def search_blogs():
    """Search published blogs"""
    try:
        query = request.args.get('q', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))

        if not query:
            return jsonify({
                'success': False,
                'error': 'Search query required'
            }), 400

        blog_model = get_blog_model()
        result = blog_model.search(query=query, page=page, limit=limit)

        # Convert ObjectId to string
        for blog in result['blogs']:
            blog['_id'] = str(blog['_id'])
            if blog.get('publishedAt'):
                blog['publishedAt'] = blog['publishedAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/blogs/categories', methods=['GET'])
def get_blog_categories():
    """Get all blog categories"""
    try:
        blog_model = get_blog_model()
        categories = blog_model.get_categories()

        return jsonify({
            'success': True,
            'categories': categories
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# ADMIN BLOG ROUTES (Create, Update, Delete)
# ============================================================================

@news_blog_bp.route('/api/admin/blogs', methods=['POST'])
@admin_required
def create_blog():
    """Create new blog (admin only)"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('title') or not data.get('content'):
            return jsonify({
                'success': False,
                'error': 'Title and content are required'
            }), 400

        # Generate slug from title if not provided
        if not data.get('slug'):
            slug = re.sub(r'[^a-z0-9]+', '-', data['title'].lower()).strip('-')
            data['slug'] = slug

        # Get current user as author
        from flask_jwt_extended import get_jwt_identity
        from app import mongo

        user_id = get_jwt_identity()
        user = mongo.db.users.find_one({'_id': user_id})
        data['author'] = user.get('username', 'Admin')

        blog_model = get_blog_model()
        blog = blog_model.create(data)

        # Convert ObjectId to string
        blog['_id'] = str(blog['_id'])
        if blog.get('publishedAt'):
            blog['publishedAt'] = blog['publishedAt'].isoformat()
        if blog.get('createdAt'):
            blog['createdAt'] = blog['createdAt'].isoformat()

        return jsonify({
            'success': True,
            'blog': blog,
            'message': 'Blog created successfully'
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/admin/blogs/<blog_id>', methods=['PUT'])
@admin_required
def update_blog(blog_id):
    """Update blog (admin only)"""
    try:
        data = request.get_json()

        blog_model = get_blog_model()
        success = blog_model.update(blog_id, data)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Blog not found or update failed'
            }), 404

        return jsonify({
            'success': True,
            'message': 'Blog updated successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/admin/blogs/<blog_id>', methods=['DELETE'])
@admin_required
def delete_blog(blog_id):
    """Delete blog (admin only)"""
    try:
        blog_model = get_blog_model()
        success = blog_model.delete(blog_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Blog not found or delete failed'
            }), 404

        return jsonify({
            'success': True,
            'message': 'Blog deleted successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/admin/blogs/<blog_id>', methods=['GET'])
@admin_required
def get_blog_admin(blog_id):
    """Get blog by ID (admin - can view drafts)"""
    try:
        blog_model = get_blog_model()
        blog = blog_model.get_by_id(blog_id)

        if not blog:
            return jsonify({
                'success': False,
                'error': 'Blog not found'
            }), 404

        # Convert ObjectId to string
        blog['_id'] = str(blog['_id'])
        if blog.get('publishedAt'):
            blog['publishedAt'] = blog['publishedAt'].isoformat()
        if blog.get('createdAt'):
            blog['createdAt'] = blog['createdAt'].isoformat()
        if blog.get('updatedAt'):
            blog['updatedAt'] = blog['updatedAt'].isoformat()

        return jsonify({
            'success': True,
            'blog': blog
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@news_blog_bp.route('/api/admin/blogs', methods=['GET'])
@admin_required
def get_all_blogs_admin():
    """Get all blogs including drafts (admin only)"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        status = request.args.get('status', 'all')  # all, published, draft

        blog_model = get_blog_model()

        if status == 'all':
            # Get both published and draft
            result = blog_model.get_all(status='published', page=1, limit=1000)
            drafts = blog_model.get_all(status='draft', page=1, limit=1000)
            all_blogs = result['blogs'] + drafts['blogs']
            all_blogs.sort(key=lambda x: x.get('updatedAt', x.get('createdAt')), reverse=True)

            # Paginate
            start = (page - 1) * limit
            end = start + limit
            paginated = all_blogs[start:end]

            result = {
                'blogs': paginated,
                'total': len(all_blogs),
                'page': page,
                'limit': limit,
                'totalPages': (len(all_blogs) + limit - 1) // limit
            }
        else:
            result = blog_model.get_all(status=status, page=page, limit=limit)

        # Convert ObjectId to string
        for blog in result['blogs']:
            blog['_id'] = str(blog['_id'])
            if blog.get('publishedAt'):
                blog['publishedAt'] = blog['publishedAt'].isoformat()
            if blog.get('createdAt'):
                blog['createdAt'] = blog['createdAt'].isoformat()
            if blog.get('updatedAt'):
                blog['updatedAt'] = blog['updatedAt'].isoformat()

        return jsonify({
            'success': True,
            **result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
