"""
Market Article Model - AI-generated financial analysis articles
Separate from blogs — stored in market_articles collection
"""

import re
from datetime import datetime
from bson import ObjectId
from typing import List, Optional


class MarketArticle:
    """Market article data model"""

    def __init__(self, db):
        self.collection = db['market_articles']
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.collection.create_index([('slug', 1)], unique=True)
        self.collection.create_index([('status', 1), ('published_at', -1)])
        self.collection.create_index([('category', 1)])
        self.collection.create_index([('sector', 1)])
        self.collection.create_index([('tags', 1)])
        self.collection.create_index([('sentiment', 1)])

    @staticmethod
    def generate_slug(title: str) -> str:
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        # Add timestamp suffix for uniqueness
        ts = datetime.utcnow().strftime('%Y%m%d%H%M')
        return f"{slug[:80]}-{ts}"

    def create(self, data: dict) -> dict:
        """Create a new market article"""
        now = datetime.utcnow()
        is_published = data.get('status', 'published') == 'published'

        article = {
            'title': data['title'],
            'slug': data.get('slug') or self.generate_slug(data['title']),
            'content': data['content'],
            'summary': data.get('summary', ''),
            'key_takeaway': data.get('key_takeaway', ''),
            'sentiment': data.get('sentiment', 'Neutral'),
            'impact_score': data.get('impact_score', 'Medium'),
            'time_horizon': data.get('time_horizon', 'Short-term'),
            'affected_stocks': data.get('affected_stocks', []),
            'sector': data.get('sector', 'General'),
            'category': data.get('category', 'deep-analysis'),
            'tags': data.get('tags', []),
            'source_articles': data.get('source_articles', []),
            'meta_title': data.get('meta_title', data['title']),
            'meta_description': data.get('meta_description', data.get('summary', '')),
            'image_url': data.get('image_url', None),
            'status': 'published' if is_published else 'draft',
            'created_at': now,
            'published_at': now if is_published else None,
            'updated_at': now,
            'view_count': 0,
        }

        result = self.collection.insert_one(article)
        article['_id'] = result.inserted_id
        return article

    def get_by_slug(self, slug: str) -> Optional[dict]:
        return self.collection.find_one({'slug': slug, 'status': 'published'})

    def list_published(self, page: int = 1, limit: int = 12,
                       category: Optional[str] = None,
                       sector: Optional[str] = None,
                       sentiment: Optional[str] = None) -> dict:
        """List published articles with filters and pagination"""
        query = {'status': 'published'}
        if category:
            query['category'] = category
        if sector:
            query['sector'] = sector
        if sentiment:
            query['sentiment'] = sentiment

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        articles = list(
            self.collection.find(query)
            .sort('published_at', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'articles': articles,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def increment_views(self, slug: str) -> bool:
        try:
            result = self.collection.update_one(
                {'slug': slug},
                {'$inc': {'view_count': 1}}
            )
            return result.modified_count > 0
        except:
            return False

    def update(self, slug: str, update_data: dict) -> bool:
        try:
            update_data['updated_at'] = datetime.utcnow()
            if update_data.get('status') == 'published' and 'published_at' not in update_data:
                update_data['published_at'] = datetime.utcnow()
            result = self.collection.update_one(
                {'slug': slug},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except:
            return False

    def delete(self, slug: str) -> bool:
        try:
            result = self.collection.delete_one({'slug': slug})
            return result.deleted_count > 0
        except:
            return False

    def get_categories_with_counts(self) -> list:
        """Get categories with article counts"""
        pipeline = [
            {'$match': {'status': 'published'}},
            {'$group': {'_id': '$category', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        results = list(self.collection.aggregate(pipeline))
        return [{'id': r['_id'], 'count': r['count']} for r in results]

    def get_related(self, slug: str, limit: int = 3) -> List[dict]:
        """Get related articles by same sector/category"""
        article = self.collection.find_one({'slug': slug})
        if not article:
            return []

        query = {
            'status': 'published',
            'slug': {'$ne': slug},
            '$or': [
                {'sector': article.get('sector')},
                {'category': article.get('category')},
            ]
        }
        return list(
            self.collection.find(query)
            .sort('published_at', -1)
            .limit(limit)
        )

    @staticmethod
    def serialize(article: dict) -> dict:
        """Convert article for JSON response"""
        if not article:
            return article
        article['_id'] = str(article['_id'])
        for dt_field in ('created_at', 'published_at', 'updated_at'):
            if article.get(dt_field):
                article[dt_field] = article[dt_field].isoformat()
        # Convert ObjectId refs in source_articles
        article['source_articles'] = [
            str(s) if isinstance(s, ObjectId) else s
            for s in article.get('source_articles', [])
        ]
        return article
