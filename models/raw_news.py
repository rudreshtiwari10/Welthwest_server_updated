"""
Raw News Model - Stores fetched news for AI processing pipeline
"""

import hashlib
from datetime import datetime
from typing import List, Optional


class RawNews:
    """Raw news data model for the intelligence pipeline"""

    def __init__(self, db):
        self.collection = db['raw_news']
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.collection.create_index([('content_hash', 1)], unique=True)
        self.collection.create_index([('processed', 1)])
        self.collection.create_index([('fetched_at', -1)])
        self.collection.create_index([('cluster_id', 1)])

    @staticmethod
    def hash_title(title: str) -> str:
        return hashlib.sha256(title.strip().lower().encode()).hexdigest()

    def save_if_new(self, news_item: dict) -> Optional[dict]:
        """Save news item only if not already stored (dedupe by title hash)"""
        title = news_item.get('title', '').strip()
        if not title:
            return None

        content_hash = self.hash_title(title)

        doc = {
            'title': title,
            'description': news_item.get('summary', news_item.get('description', '')),
            'source_name': news_item.get('sourceName', news_item.get('source_name', '')),
            'source_url': news_item.get('sourceUrl', news_item.get('source_url', '')),
            'published_at': news_item.get('publishedAt', news_item.get('published_at', '')),
            'category': news_item.get('category', 'general'),
            'image_url': news_item.get('imageUrl', news_item.get('image_url', None)),
            'content_hash': content_hash,
            'fetched_at': datetime.utcnow(),
            'cluster_id': None,
            'processed': False,
        }

        try:
            result = self.collection.insert_one(doc)
            doc['_id'] = result.inserted_id
            return doc
        except Exception:
            # Duplicate hash — already exists
            return None

    def save_batch(self, news_items: list) -> int:
        """Save multiple news items, returns count of new items saved"""
        saved = 0
        for item in news_items:
            if self.save_if_new(item):
                saved += 1
        return saved

    def get_unprocessed(self, limit: int = 100) -> List[dict]:
        """Get unprocessed news items ordered by fetched_at"""
        return list(
            self.collection.find({'processed': False})
            .sort('fetched_at', -1)
            .limit(limit)
        )

    def mark_processed(self, ids: list, cluster_id: Optional[str] = None):
        """Mark news items as processed"""
        from bson import ObjectId
        object_ids = [ObjectId(i) if not isinstance(i, ObjectId) else i for i in ids]
        update = {'$set': {'processed': True}}
        if cluster_id:
            update['$set']['cluster_id'] = cluster_id
        self.collection.update_many(
            {'_id': {'$in': object_ids}},
            update
        )

    def cleanup_old(self, days: int = 7):
        """Remove raw news older than N days"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        self.collection.delete_many({'fetched_at': {'$lt': cutoff}})
