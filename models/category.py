"""
Category Model
Organize blog content logically with categories
"""

from datetime import datetime
from bson import ObjectId
from typing import List, Optional

class Category:
    """Category data model for content organization"""

    def __init__(self, db):
        self.collection = db['categories']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('slug', 1)], unique=True)
        self.collection.create_index([('name', 1)])
        self.collection.create_index([('createdAt', -1)])

    def create(self, category_data: dict) -> dict:
        """Create a new category"""
        import re

        # Generate slug from name if not provided
        if not category_data.get('slug'):
            slug = re.sub(r'[^a-z0-9]+', '-', category_data['name'].lower()).strip('-')
            category_data['slug'] = slug

        category = {
            'name': category_data['name'],
            'slug': category_data['slug'],
            'description': category_data.get('description', ''),
            'icon': category_data.get('icon', 'folder'),
            'color': category_data.get('color', '#6B7280'),
            'postCount': 0,
            'createdBy': category_data['createdBy'],
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        }

        result = self.collection.insert_one(category)
        category['_id'] = result.inserted_id
        return category

    def get_by_id(self, category_id: str) -> Optional[dict]:
        """Get category by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(category_id)})
        except:
            return None

    def get_by_slug(self, slug: str) -> Optional[dict]:
        """Get category by slug"""
        return self.collection.find_one({'slug': slug})

    def get_all(self, page: int = 1, limit: int = 50) -> dict:
        """Get all categories with pagination"""
        total = self.collection.count_documents({})
        skip = (page - 1) * limit

        categories = list(
            self.collection.find({})
            .sort('name', 1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'categories': categories,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def update(self, category_id: str, update_data: dict) -> bool:
        """Update category"""
        try:
            update_data['updatedAt'] = datetime.utcnow()

            result = self.collection.update_one(
                {'_id': ObjectId(category_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except:
            return False

    def delete(self, category_id: str) -> bool:
        """Delete category"""
        try:
            result = self.collection.delete_one({'_id': ObjectId(category_id)})
            return result.deleted_count > 0
        except:
            return False

    def increment_post_count(self, category_name: str) -> bool:
        """Increment post count for category"""
        try:
            result = self.collection.update_one(
                {'name': category_name},
                {'$inc': {'postCount': 1}}
            )
            return result.modified_count > 0
        except:
            return False

    def decrement_post_count(self, category_name: str) -> bool:
        """Decrement post count for category"""
        try:
            result = self.collection.update_one(
                {'name': category_name},
                {'$inc': {'postCount': -1}}
            )
            return result.modified_count > 0
        except:
            return False

    def get_popular_categories(self, limit: int = 10) -> List[dict]:
        """Get most popular categories by post count"""
        return list(
            self.collection.find({})
            .sort('postCount', -1)
            .limit(limit)
        )
