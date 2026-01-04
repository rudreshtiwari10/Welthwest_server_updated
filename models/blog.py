"""
Blog Model - Internal Content Management
Blogs are stored in database and managed by developers/admins only
"""

from datetime import datetime
from bson import ObjectId
from typing import List, Optional

class Blog:
    """Blog data model"""

    def __init__(self, db):
        self.collection = db['blogs']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('slug', 1)], unique=True)
        self.collection.create_index([('status', 1)])
        self.collection.create_index([('category', 1)])
        self.collection.create_index([('publishedAt', -1)])
        self.collection.create_index([('tags', 1)])

    def create(self, blog_data: dict) -> dict:
        """Create a new blog post"""
        blog = {
            'title': blog_data['title'],
            'slug': blog_data['slug'],
            'content': blog_data['content'],
            'author': blog_data['author'],
            'category': blog_data.get('category', 'General'),
            'tags': blog_data.get('tags', []),
            'summary': blog_data.get('summary', ''),
            'imageUrl': blog_data.get('imageUrl'),
            'status': blog_data.get('status', 'draft'),  # draft | published
            'publishedAt': datetime.utcnow() if blog_data.get('status') == 'published' else None,
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow(),
            'viewCount': 0,
            'likeCount': 0,
            # SEO fields
            'metaTitle': blog_data.get('metaTitle', blog_data['title']),
            'metaDescription': blog_data.get('metaDescription', blog_data.get('summary', '')),
            'noIndex': blog_data.get('noIndex', False),
            # Approval workflow
            'approvalStatus': blog_data.get('approvalStatus', 'pending'),  # pending | approved | rejected
            'approver': None,
            'approvalComments': [],
            'submittedAt': None,
            # Analytics
            'readTime': self._calculate_read_time(blog_data['content']),
            'engagementRate': 0.0,
            'commentCount': 0
        }

        result = self.collection.insert_one(blog)
        blog['_id'] = result.inserted_id
        return blog

    def get_by_id(self, blog_id: str) -> Optional[dict]:
        """Get blog by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(blog_id)})
        except:
            return None

    def get_by_slug(self, slug: str) -> Optional[dict]:
        """Get blog by slug"""
        return self.collection.find_one({'slug': slug})

    def get_all(self, status: str = 'published', page: int = 1, limit: int = 10,
                category: Optional[str] = None, sort_by: str = 'publishedAt') -> dict:
        """Get all blogs with pagination"""
        query = {'status': status}

        if category:
            query['category'] = category

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        blogs = list(
            self.collection.find(query)
            .sort(sort_by, -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'blogs': blogs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def update(self, blog_id: str, update_data: dict) -> bool:
        """Update blog"""
        try:
            update_data['updatedAt'] = datetime.utcnow()

            # If status changed to published, set publishedAt
            if update_data.get('status') == 'published' and 'publishedAt' not in update_data:
                update_data['publishedAt'] = datetime.utcnow()

            result = self.collection.update_one(
                {'_id': ObjectId(blog_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except:
            return False

    def delete(self, blog_id: str) -> bool:
        """Delete blog"""
        try:
            result = self.collection.delete_one({'_id': ObjectId(blog_id)})
            return result.deleted_count > 0
        except:
            return False

    def search(self, query: str, page: int = 1, limit: int = 10) -> dict:
        """Search blogs by title, content, or tags"""
        search_query = {
            'status': 'published',
            '$or': [
                {'title': {'$regex': query, '$options': 'i'}},
                {'content': {'$regex': query, '$options': 'i'}},
                {'tags': {'$regex': query, '$options': 'i'}},
                {'summary': {'$regex': query, '$options': 'i'}}
            ]
        }

        total = self.collection.count_documents(search_query)
        skip = (page - 1) * limit

        blogs = list(
            self.collection.find(search_query)
            .sort('publishedAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'blogs': blogs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def increment_view(self, blog_id: str) -> bool:
        """Increment view count"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(blog_id)},
                {'$inc': {'viewCount': 1}}
            )
            return result.modified_count > 0
        except:
            return False

    def get_categories(self) -> List[str]:
        """Get all unique categories"""
        return self.collection.distinct('category', {'status': 'published'})

    def get_tags(self) -> List[str]:
        """Get all unique tags"""
        all_tags = self.collection.distinct('tags', {'status': 'published'})
        return all_tags

    def _calculate_read_time(self, content: str) -> int:
        """Calculate estimated read time in minutes (avg 200 words/min)"""
        word_count = len(content.split())
        return max(1, round(word_count / 200))

    def submit_for_approval(self, blog_id: str) -> bool:
        """Submit blog for approval"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(blog_id)},
                {
                    '$set': {
                        'approvalStatus': 'pending',
                        'submittedAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def approve_blog(self, blog_id: str, approver: str, comment: str = '') -> bool:
        """Approve a blog post"""
        try:
            approval_comment = {
                'user': approver,
                'action': 'approved',
                'comment': comment,
                'timestamp': datetime.utcnow()
            }

            result = self.collection.update_one(
                {'_id': ObjectId(blog_id)},
                {
                    '$set': {
                        'approvalStatus': 'approved',
                        'approver': approver,
                        'updatedAt': datetime.utcnow()
                    },
                    '$push': {'approvalComments': approval_comment}
                }
            )
            return result.modified_count > 0
        except:
            return False

    def reject_blog(self, blog_id: str, approver: str, comment: str) -> bool:
        """Reject a blog post"""
        try:
            approval_comment = {
                'user': approver,
                'action': 'rejected',
                'comment': comment,
                'timestamp': datetime.utcnow()
            }

            result = self.collection.update_one(
                {'_id': ObjectId(blog_id)},
                {
                    '$set': {
                        'approvalStatus': 'rejected',
                        'approver': approver,
                        'updatedAt': datetime.utcnow()
                    },
                    '$push': {'approvalComments': approval_comment}
                }
            )
            return result.modified_count > 0
        except:
            return False

    def add_approval_comment(self, blog_id: str, user: str, comment: str) -> bool:
        """Add internal comment to blog"""
        try:
            approval_comment = {
                'user': user,
                'action': 'comment',
                'comment': comment,
                'timestamp': datetime.utcnow()
            }

            result = self.collection.update_one(
                {'_id': ObjectId(blog_id)},
                {'$push': {'approvalComments': approval_comment}}
            )
            return result.modified_count > 0
        except:
            return False

    def get_analytics(self, blog_id: str) -> Optional[dict]:
        """Get blog analytics"""
        try:
            blog = self.collection.find_one({'_id': ObjectId(blog_id)})
            if not blog:
                return None

            return {
                'viewCount': blog.get('viewCount', 0),
                'readTime': blog.get('readTime', 0),
                'engagementRate': blog.get('engagementRate', 0),
                'likeCount': blog.get('likeCount', 0),
                'commentCount': blog.get('commentCount', 0)
            }
        except:
            return None
