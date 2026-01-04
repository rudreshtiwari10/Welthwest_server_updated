"""
Support Ticket Model
Handle user support issues efficiently
"""

from datetime import datetime
from bson import ObjectId
from typing import List, Optional

class SupportTicket:
    """Support Ticket data model"""

    def __init__(self, db):
        self.collection = db['support_tickets']
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes"""
        self.collection.create_index([('userId', 1)])
        self.collection.create_index([('status', 1)])
        self.collection.create_index([('priority', 1)])
        self.collection.create_index([('assignedTo', 1)])
        self.collection.create_index([('createdAt', -1)])

    def create(self, ticket_data: dict) -> dict:
        """Create a new support ticket"""
        ticket = {
            'ticketNumber': self._generate_ticket_number(),
            'userId': ticket_data['userId'],
            'userEmail': ticket_data['userEmail'],
            'userName': ticket_data['userName'],
            'subject': ticket_data['subject'],
            'description': ticket_data['description'],
            'category': ticket_data.get('category', 'general'),  # general | billing | technical | feature_request
            'priority': ticket_data.get('priority', 'medium'),  # low | medium | high | urgent
            'status': 'open',  # open | in_progress | waiting | resolved | closed
            'assignedTo': None,
            'assignedAt': None,
            'notes': [],
            'replies': [],
            'attachments': ticket_data.get('attachments', []),
            'tags': ticket_data.get('tags', []),
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow(),
            'resolvedAt': None,
            'closedAt': None
        }

        result = self.collection.insert_one(ticket)
        ticket['_id'] = result.inserted_id
        return ticket

    def _generate_ticket_number(self) -> str:
        """Generate unique ticket number"""
        import random
        import string
        timestamp = datetime.utcnow().strftime('%Y%m%d')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f'TKT-{timestamp}-{random_str}'

    def get_by_id(self, ticket_id: str) -> Optional[dict]:
        """Get ticket by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(ticket_id)})
        except:
            return None

    def get_by_ticket_number(self, ticket_number: str) -> Optional[dict]:
        """Get ticket by ticket number"""
        return self.collection.find_one({'ticketNumber': ticket_number})

    def get_all(self, page: int = 1, limit: int = 20, filters: Optional[dict] = None) -> dict:
        """Get all tickets with pagination and filters"""
        query = {}

        if filters:
            if filters.get('status'):
                query['status'] = filters['status']
            if filters.get('priority'):
                query['priority'] = filters['priority']
            if filters.get('category'):
                query['category'] = filters['category']
            if filters.get('assignedTo'):
                query['assignedTo'] = filters['assignedTo']
            if filters.get('userId'):
                query['userId'] = filters['userId']

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        tickets = list(
            self.collection.find(query)
            .sort('createdAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'tickets': tickets,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def get_by_user(self, user_id: str, page: int = 1, limit: int = 20) -> dict:
        """Get tickets for a specific user"""
        query = {'userId': user_id}

        total = self.collection.count_documents(query)
        skip = (page - 1) * limit

        tickets = list(
            self.collection.find(query)
            .sort('createdAt', -1)
            .skip(skip)
            .limit(limit)
        )

        return {
            'tickets': tickets,
            'total': total,
            'page': page,
            'limit': limit,
            'totalPages': (total + limit - 1) // limit
        }

    def assign(self, ticket_id: str, staff_id: str, staff_name: str) -> bool:
        """Assign ticket to staff member"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(ticket_id)},
                {
                    '$set': {
                        'assignedTo': staff_id,
                        'assignedToName': staff_name,
                        'assignedAt': datetime.utcnow(),
                        'status': 'in_progress',
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def add_note(self, ticket_id: str, note_data: dict) -> bool:
        """Add internal note to ticket"""
        try:
            note = {
                'author': note_data['author'],
                'content': note_data['content'],
                'isInternal': True,
                'createdAt': datetime.utcnow()
            }

            result = self.collection.update_one(
                {'_id': ObjectId(ticket_id)},
                {
                    '$push': {'notes': note},
                    '$set': {'updatedAt': datetime.utcnow()}
                }
            )
            return result.modified_count > 0
        except:
            return False

    def add_reply(self, ticket_id: str, reply_data: dict) -> bool:
        """Add reply to ticket (visible to user)"""
        try:
            reply = {
                'author': reply_data['author'],
                'content': reply_data['content'],
                'isStaff': reply_data.get('isStaff', False),
                'createdAt': datetime.utcnow()
            }

            result = self.collection.update_one(
                {'_id': ObjectId(ticket_id)},
                {
                    '$push': {'replies': reply},
                    '$set': {'updatedAt': datetime.utcnow()}
                }
            )
            return result.modified_count > 0
        except:
            return False

    def update_status(self, ticket_id: str, status: str) -> bool:
        """Update ticket status"""
        try:
            update_data = {
                'status': status,
                'updatedAt': datetime.utcnow()
            }

            if status == 'resolved':
                update_data['resolvedAt'] = datetime.utcnow()
            elif status == 'closed':
                update_data['closedAt'] = datetime.utcnow()

            result = self.collection.update_one(
                {'_id': ObjectId(ticket_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except:
            return False

    def update_priority(self, ticket_id: str, priority: str) -> bool:
        """Update ticket priority"""
        try:
            result = self.collection.update_one(
                {'_id': ObjectId(ticket_id)},
                {
                    '$set': {
                        'priority': priority,
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except:
            return False

    def get_stats(self) -> dict:
        """Get ticket statistics"""
        total = self.collection.count_documents({})
        open_tickets = self.collection.count_documents({'status': 'open'})
        in_progress = self.collection.count_documents({'status': 'in_progress'})
        resolved = self.collection.count_documents({'status': 'resolved'})
        closed = self.collection.count_documents({'status': 'closed'})

        urgent = self.collection.count_documents({'priority': 'urgent'})
        high = self.collection.count_documents({'priority': 'high'})

        return {
            'total': total,
            'open': open_tickets,
            'inProgress': in_progress,
            'resolved': resolved,
            'closed': closed,
            'urgent': urgent,
            'high': high
        }

    def get_unassigned(self, limit: int = 20) -> List[dict]:
        """Get unassigned tickets"""
        return list(
            self.collection.find({'assignedTo': None, 'status': 'open'})
            .sort('createdAt', -1)
            .limit(limit)
        )
