"""
Notification Model
Handle user notifications for various activities
"""

from datetime import datetime, timedelta
from bson import ObjectId
from typing import List, Optional, Dict, Any

class Notification:
    """Notification data model for user activity tracking"""

    def __init__(self, db):
        self.collection = db['notifications']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('user_id', 1)])
        self.collection.create_index([('type', 1)])
        self.collection.create_index([('read', 1)])
        self.collection.create_index([('timestamp', -1)])
        self.collection.create_index([('user_id', 1), ('read', 1)])

    def create(self, notification_data: dict) -> dict:
        """Create a new notification"""
        notification = {
            'user_id': notification_data['user_id'],
            'type': notification_data['type'],  # login, logout, password_change, payment_success, payment_failed,
                                                 # subscription_upgrade, subscription_downgrade, subscription_expiry,
                                                 # usage_limit, system, info
            'title': notification_data['title'],
            'message': notification_data['message'],
            'read': False,
            'timestamp': datetime.utcnow(),
            'action_url': notification_data.get('action_url'),  # Optional URL for action
            'metadata': notification_data.get('metadata', {})  # Additional contextual data
        }

        result = self.collection.insert_one(notification)
        notification['_id'] = result.inserted_id
        return notification

    def get_by_id(self, notification_id: str) -> Optional[dict]:
        """Get notification by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(notification_id)})
        except:
            return None

    def get_user_notifications(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 50,
        unread_only: bool = False
    ) -> dict:
        """Get notifications for a specific user"""
        query = {'user_id': user_id}

        if unread_only:
            query['read'] = False

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        notifications = list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'notifications': notifications,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit,
            'unreadCount': self.get_unread_count(user_id)
        }

    def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for a user"""
        return self.collection.count_documents({
            'user_id': user_id,
            'read': False
        })

    def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read"""
        try:
            result = self.collection.update_one(
                {
                    '_id': ObjectId(notification_id),
                    'user_id': user_id
                },
                {
                    '$set': {'read': True}
                }
            )
            return result.modified_count > 0
        except:
            return False

    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user"""
        result = self.collection.update_many(
            {
                'user_id': user_id,
                'read': False
            },
            {
                '$set': {'read': True}
            }
        )
        return result.modified_count

    def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Delete a notification"""
        try:
            result = self.collection.delete_one({
                '_id': ObjectId(notification_id),
                'user_id': user_id
            })
            return result.deleted_count > 0
        except:
            return False

    def delete_all_user_notifications(self, user_id: str) -> int:
        """Delete all notifications for a user"""
        result = self.collection.delete_many({'user_id': user_id})
        return result.deleted_count

    def get_by_type(
        self,
        user_id: str,
        notification_type: str,
        page: int = 1,
        limit: int = 50
    ) -> dict:
        """Get notifications by type for a user"""
        query = {
            'user_id': user_id,
            'type': notification_type
        }

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        notifications = list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'notifications': notifications,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def cleanup_old_notifications(self, days: int = 90) -> int:
        """Delete notifications older than specified days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        result = self.collection.delete_many({
            'timestamp': {'$lt': cutoff_date}
        })
        return result.deleted_count

    def get_recent_notifications(self, user_id: str, limit: int = 10) -> List[dict]:
        """Get most recent notifications for a user"""
        return list(
            self.collection.find({'user_id': user_id})
            .sort('timestamp', -1)
            .limit(limit)
        )

    def bulk_create(self, notifications: List[dict]) -> List[str]:
        """Create multiple notifications at once"""
        for notification in notifications:
            if 'timestamp' not in notification:
                notification['timestamp'] = datetime.utcnow()
            if 'read' not in notification:
                notification['read'] = False

        result = self.collection.insert_many(notifications)
        return [str(id) for id in result.inserted_ids]
