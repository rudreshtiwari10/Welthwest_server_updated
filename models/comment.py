"""
Comments Model
User-generated comments on blogs with moderation
"""

from datetime import datetime
from bson import ObjectId
from typing import List, Optional

class Comment:
    """Comment data model for blog posts"""

    def __init__(self, db):
        self.collection = db['comments']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('blogId', 1)])
        self.collection.create_index([('userId', 1)])
        self.collection.create_index([('status', 1)])
        self.collection.create_index([('createdAt', -1)])

    def create(self, comment_data: dict) -> dict:
        """Create a new comment"""
        comment = {
            'blogId': comment_data['blogId'],
            'userId': comment_data['userId'],
            'username': comment_data['username'],
            'content': comment_data['content'],
            'status': comment_data.get('status', 'pending'),  # pending | approved | rejected | flagged
            'flagReason': None,
            'moderatedBy': None,
            'moderatedAt': None,
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow(),
            'likeCount': 0,
            'isEdited': False
        }

        result = self.collection.insert_one(comment)
        comment['_id'] = result.inserted_id
        return comment

    def get_by_id(self, comment_id: str) -> Optional[dict]:
        """Get comment by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(comment_id)})
        except:
            return None

    def get_by_blog(self, blog_id: str, status: str = 'approved', page: int = 1, limit: int = 50) -> dict:
        """Get comments for a specific blog"""
        query = {'blogId': blog_id, 'status': status}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        comments = list(
            self.collection.find(query)
            .sort('createdAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'comments': comments,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_all_pending(self, page: int = 1, limit: int = 20) -> dict:
        """Get all pending comments for moderation"""
        query = {'status': 'pending'}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        comments = list(
            self.collection.find(query)
            .sort('createdAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'comments': comments,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_by_user(self, user_id: str, page: int = 1, limit: int = 20) -> dict:
        """Get all comments by a specific user"""
        query = {'userId': user_id}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        comments = list(
            self.collection.find(query)
            .sort('createdAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'comments': comments,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def approve(self, comment_id: str, moderator: str) -> bool:
        """Approve a comment"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(comment_id)},
                {
                    '$set': {
                        'status': 'approved',
                        'moderatedBy': moderator,
                        'moderatedAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def reject(self, comment_id: str, moderator: str, reason: str = '') -> bool:
        """Reject a comment"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(comment_id)},
                {
                    '$set': {
                        'status': 'rejected',
                        'flagReason': reason,
                        'moderatedBy': moderator,
                        'moderatedAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def flag(self, comment_id: str, moderator: str, reason: str) -> bool:
        """Flag a comment as abusive"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(comment_id)},
                {
                    '$set': {
                        'status': 'flagged',
                        'flagReason': reason,
                        'moderatedBy': moderator,
                        'moderatedAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def delete(self, comment_id: str) -> bool:
        """Delete a comment"""
        try:
            result = self.collection.delete_one({'_id': ObjectId(comment_id)})
            return result.deleted_count > 0
        except:
            return False

    def update(self, comment_id: str, content: str) -> bool:
        """Update comment content (user edit)"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(comment_id)},
                {
                    '$set': {
                        'content': content,
                        'isEdited': True,
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def get_flagged_users(self) -> List[dict]:
        """Get users with multiple flagged comments (repeat offenders)"""
        pipeline = [
            {'$match': {'status': 'flagged'}},
            {
                '$group': {
                    '_id': '$userId',
                    'username': {'$first': '$username'},
                    'flaggedCount': {'$sum': 1},
                    'lastFlagged': {'$max': '$moderatedAt'}
                }
            },
            {'$match': {'flaggedCount': {'$gte': 2}}},
            {'$sort': {'flaggedCount': -1}}
        ]

        return list(self.collection.aggregate(pipeline))

    def get_comment_stats(self, blog_id: str) -> dict:
        """Get comment statistics for a blog"""
        approved = self.collection.count_documents({'blogId': blog_id, 'status': 'approved'})
        pending = self.collection.count_documents({'blogId': blog_id, 'status': 'pending'})
        rejected = self.collection.count_documents({'blogId': blog_id, 'status': 'rejected'})
        flagged = self.collection.count_documents({'blogId': blog_id, 'status': 'flagged'})

        return {
            'approved': approved,
            'pending': pending,
            'rejected': rejected,
            'flagged': flagged,
            'total': approved + pending + rejected + flagged
        }
