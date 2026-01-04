"""
Activity Log Model
Track every admin action for security & accountability
"""

from datetime import datetime
from bson import ObjectId
from typing import List, Optional, Dict, Any

class ActivityLog:
    """Activity Log data model for admin actions"""

    def __init__(self, db):
        self.collection = db['activity_logs']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('adminId', 1)])
        self.collection.create_index([('module', 1)])
        self.collection.create_index([('action', 1)])
        self.collection.create_index([('timestamp', -1)])
        self.collection.create_index([('severity', 1)])

    def log(self, log_data: dict) -> dict:
        """Create a new activity log entry"""
        log_entry = {
            'adminId': log_data['adminId'],
            'adminUsername': log_data['adminUsername'],
            'adminEmail': log_data.get('adminEmail'),
            'action': log_data['action'],  # create | update | delete | view | export | import | approve | reject
            'module': log_data['module'],  # users | subscriptions | content | alerts | settings | etc
            'targetType': log_data.get('targetType'),  # user | blog | ticket | alert | etc
            'targetId': log_data.get('targetId'),
            'description': log_data['description'],
            'beforeState': log_data.get('beforeState'),  # Snapshot before change
            'afterState': log_data.get('afterState'),  # Snapshot after change
            'ipAddress': log_data.get('ipAddress'),
            'userAgent': log_data.get('userAgent'),
            'severity': log_data.get('severity', 'info'),  # info | warning | critical
            'timestamp': datetime.utcnow(),
            'metadata': log_data.get('metadata', {})  # Additional contextual data
        }

        result = self.collection.insert_one(log_entry)
        log_entry['_id'] = result.inserted_id
        return log_entry

    def get_by_id(self, log_id: str) -> Optional[dict]:
        """Get log entry by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(log_id)})
        except:
            return None

    def get_all(self, page: int = 1, limit: int = 50, filters: Optional[dict] = None) -> dict:
        """Get all activity logs with pagination and filters"""
        query = {}

        if filters:
            if filters.get('adminId'):
                query['adminId'] = filters['adminId']
            if filters.get('module'):
                query['module'] = filters['module']
            if filters.get('action'):
                query['action'] = filters['action']
            if filters.get('severity'):
                query['severity'] = filters['severity']
            if filters.get('targetType'):
                query['targetType'] = filters['targetType']
            if filters.get('dateFrom'):
                query['timestamp'] = {'$gte': filters['dateFrom']}
            if filters.get('dateTo'):
                if 'timestamp' in query:
                    query['timestamp']['$lte'] = filters['dateTo']
                else:
                    query['timestamp'] = {'$lte': filters['dateTo']}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        logs = list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'logs': logs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_by_admin(self, admin_id: str, page: int = 1, limit: int = 50) -> dict:
        """Get logs for a specific admin"""
        query = {'adminId': admin_id}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        logs = list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'logs': logs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_by_module(self, module: str, page: int = 1, limit: int = 50) -> dict:
        """Get logs for a specific module"""
        query = {'module': module}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        logs = list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'logs': logs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_by_target(self, target_type: str, target_id: str, page: int = 1, limit: int = 50) -> dict:
        """Get logs for a specific target (e.g., all actions on a specific user)"""
        query = {
            'targetType': target_type,
            'targetId': target_id
        }

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        logs = list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'logs': logs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_critical_logs(self, page: int = 1, limit: int = 50) -> dict:
        """Get critical severity logs"""
        return self.get_all(page, limit, {'severity': 'critical'})

    def get_recent_logs(self, limit: int = 100) -> List[dict]:
        """Get most recent logs"""
        return list(
            self.collection.find({})
            .sort('timestamp', -1)
            .limit(limit)
        )

    def get_stats(self) -> dict:
        """Get activity log statistics"""
        total = self.collection.count_documents({})

        # Count by severity
        info = self.collection.count_documents({'severity': 'info'})
        warning = self.collection.count_documents({'severity': 'warning'})
        critical = self.collection.count_documents({'severity': 'critical'})

        # Count by action
        pipeline = [
            {
                '$group': {
                    '_id': '$action',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'count': -1}}
        ]
        actions = list(self.collection.aggregate(pipeline))

        # Count by module
        pipeline = [
            {
                '$group': {
                    '_id': '$module',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'count': -1}}
        ]
        modules = list(self.collection.aggregate(pipeline))

        # Most active admins
        pipeline = [
            {
                '$group': {
                    '_id': '$adminId',
                    'username': {'$first': '$adminUsername'},
                    'actionCount': {'$sum': 1},
                    'lastAction': {'$max': '$timestamp'}
                }
            },
            {'$sort': {'actionCount': -1}},
            {'$limit': 10}
        ]
        active_admins = list(self.collection.aggregate(pipeline))

        return {
            'total': total,
            'severity': {
                'info': info,
                'warning': warning,
                'critical': critical
            },
            'topActions': actions,
            'topModules': modules,
            'activeAdmins': active_admins
        }

    def search(self, query: str, page: int = 1, limit: int = 50) -> dict:
        """Search logs by description or admin username"""
        search_query = {
            '$or': [
                {'description': {'$regex': query, '$options': 'i'}},
                {'adminUsername': {'$regex': query, '$options': 'i'}},
                {'action': {'$regex': query, '$options': 'i'}},
                {'module': {'$regex': query, '$options': 'i'}}
            ]
        }

        total = self.collection.count_documents(search_query)
        skip = (page - 1) * limit

        logs = list(
            self.collection.find(search_query)
            .sort('timestamp', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'logs': logs,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def export_logs(self, filters: Optional[dict] = None) -> List[dict]:
        """Export logs for reporting (no pagination)"""
        query = {}

        if filters:
            if filters.get('adminId'):
                query['adminId'] = filters['adminId']
            if filters.get('module'):
                query['module'] = filters['module']
            if filters.get('dateFrom'):
                query['timestamp'] = {'$gte': filters['dateFrom']}
            if filters.get('dateTo'):
                if 'timestamp' in query:
                    query['timestamp']['$lte'] = filters['dateTo']
                else:
                    query['timestamp'] = {'$lte': filters['dateTo']}

        return list(
            self.collection.find(query)
            .sort('timestamp', -1)
            .limit(10000)  # Safety limit
        )
