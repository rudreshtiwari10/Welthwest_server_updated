"""
Market Alerts Model
Push critical alerts to users (market movement, warnings, announcements)
"""

from datetime import datetime
from bson import ObjectId
from typing import List, Optional

class Alert:
    """Market Alert data model"""

    def __init__(self, db):
        self.collection = db['alerts']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('createdAt', -1)])
        self.collection.create_index([('scheduledFor', 1)])
        self.collection.create_index([('status', 1)])
        self.collection.create_index([('targetGroup', 1)])

    def create(self, alert_data: dict) -> dict:
        """Create a new market alert"""
        alert = {
            'title': alert_data['title'],
            'message': alert_data['message'],
            'intent': alert_data.get('intent', 'info'),  # info | warning | critical
            'targetGroup': alert_data.get('targetGroup', 'all'),  # all | free | premium | starter | pro | advanced | enterprise
            'status': alert_data.get('status', 'draft'),  # draft | scheduled | sent
            'scheduledFor': alert_data.get('scheduledFor'),  # None for instant send
            'sentAt': None,
            'createdBy': alert_data['createdBy'],
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow(),
            'recipientCount': 0,
            'viewCount': 0
        }

        result = self.collection.insert_one(alert)
        alert['_id'] = result.inserted_id
        return alert

    def get_by_id(self, alert_id: str) -> Optional[dict]:
        """Get alert by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(alert_id)})
        except:
            return None

    def get_all(self, page: int = 1, limit: int = 20, status: Optional[str] = None) -> dict:
        """Get all alerts with pagination"""
        query = {}
        if status:
            query['status'] = status

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        alerts = list(
            self.collection.find(query)
            .sort('createdAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'alerts': alerts,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def update(self, alert_id: str, update_data: dict) -> bool:
        """Update alert"""
        try:
            update_data['updatedAt'] = datetime.utcnow()

            result = self.collection.update_one(
                {'_id': ObjectId(alert_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except:
            return False

    def delete(self, alert_id: str) -> bool:
        """Delete alert"""
        try:
            result = self.collection.delete_one({'_id': ObjectId(alert_id)})
            return result.deleted_count > 0
        except:
            return False

    def send_now(self, alert_id: str) -> bool:
        """Mark alert as sent immediately"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(alert_id)},
                {
                    '$set': {
                        'status': 'sent',
                        'sentAt': datetime.utcnow(),
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def get_pending_scheduled(self) -> List[dict]:
        """Get alerts scheduled to be sent"""
        now = datetime.utcnow()
        return list(
            self.collection.find({
                'status': 'scheduled',
                'scheduledFor': {'$lte': now}
            })
        )

    def increment_view(self, alert_id: str) -> bool:
        """Increment view count"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(alert_id)},
                {'$inc': {'viewCount': 1}}
            )
            return result.modified_count > 0
        except:
            return False

    def get_user_alerts(self, user_plan: str, page: int = 1, limit: int = 20) -> dict:
        """Get alerts for a specific user based on their plan"""
        query = {
            'status': 'sent',
            '$or': [
                {'targetGroup': 'all'},
                {'targetGroup': user_plan.lower()}
            ]
        }

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        alerts = list(
            self.collection.find(query)
            .sort('sentAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'alerts': alerts,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }
