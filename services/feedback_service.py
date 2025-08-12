import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pymongo import MongoClient
from bson import ObjectId
import config

logger = logging.getLogger(__name__)

class FeedbackService:
    """Service to handle dynamic feedback form submissions"""
    
    def __init__(self):
        """Initialize feedback service with database connection"""
        self.config = config.get_config()
        self.db = self._get_db_connection()
        self.feedback_collection = self.db.feedback_submissions
        
        # Create indexes for better query performance
        self._create_indexes()
    
    def _get_db_connection(self):
        """Get database connection"""
        try:
            client = MongoClient(self.config.MONGODB_URI)
            return client.get_database(self.config.DB_NAME)
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise
    
    def _create_indexes(self):
        """Create necessary indexes"""
        try:
            self.feedback_collection.create_index("created_at")
            self.feedback_collection.create_index("user_email")
            self.feedback_collection.create_index("form_type")
            logger.info("Feedback collection indexes created successfully")
        except Exception as e:
            logger.error(f"Failed to create indexes: {str(e)}")
    
    def submit_feedback(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit dynamic feedback form data
        
        Args:
            feedback_data: Dictionary containing:
                - user_info: Dict with user details (name, email, etc.)
                - form_type: String identifying the form type
                - responses: List of question-answer pairs
                - form_metadata: Optional metadata about the form
                
        Returns:
            Dict containing submission result and ID
        """
        try:
            # Validate required fields
            if not self._validate_feedback_data(feedback_data):
                return {
                    'success': False,
                    'message': 'Invalid feedback data provided'
                }
            
            # Prepare submission document
            submission = {
                'user_info': feedback_data.get('user_info', {}),
                'form_type': feedback_data.get('form_type', 'general'),
                'responses': feedback_data.get('responses', []),
                'form_metadata': feedback_data.get('form_metadata', {}),
                'created_at': datetime.utcnow(),
                'status': 'submitted',
                'ip_address': feedback_data.get('ip_address'),
                'user_agent': feedback_data.get('user_agent')
            }
            
            # Insert into database
            result = self.feedback_collection.insert_one(submission)
            
            logger.info(f"Feedback submitted successfully with ID: {result.inserted_id}")
            
            return {
                'success': True,
                'message': 'Feedback submitted successfully',
                'submission_id': str(result.inserted_id)
            }
            
        except Exception as e:
            logger.error(f"Failed to submit feedback: {str(e)}")
            return {
                'success': False,
                'message': 'Failed to submit feedback. Please try again.'
            }
    
    def _validate_feedback_data(self, data: Dict[str, Any]) -> bool:
        """Validate feedback submission data"""
        # Check required fields
        user_info = data.get('user_info', {})
        if not user_info.get('email'):
            logger.warning("Missing user email in feedback submission")
            return False
        
        responses = data.get('responses', [])
        if not responses or not isinstance(responses, list):
            logger.warning("Missing or invalid responses in feedback submission")
            return False
        
        # Validate responses format
        for response in responses:
            if not isinstance(response, dict):
                return False
            if 'question' not in response or 'answer' not in response:
                return False
        
        return True
    
    def get_feedback_submissions(self, 
                               form_type: Optional[str] = None,
                               user_email: Optional[str] = None,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None,
                               limit: int = 100,
                               skip: int = 0) -> List[Dict[str, Any]]:
        """
        Retrieve feedback submissions with filtering options
        
        Args:
            form_type: Filter by form type
            user_email: Filter by user email
            start_date: Filter submissions after this date
            end_date: Filter submissions before this date
            limit: Maximum number of results
            skip: Number of results to skip
            
        Returns:
            List of feedback submissions
        """
        try:
            # Build query
            query = {}
            
            if form_type:
                query['form_type'] = form_type
            
            if user_email:
                query['user_info.email'] = user_email
            
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter['$gte'] = start_date
                if end_date:
                    date_filter['$lte'] = end_date
                query['created_at'] = date_filter
            
            # Execute query
            cursor = self.feedback_collection.find(query)\
                                           .sort('created_at', -1)\
                                           .limit(limit)\
                                           .skip(skip)
            
            submissions = []
            for doc in cursor:
                doc['_id'] = str(doc['_id'])
                submissions.append(doc)
            
            return submissions
            
        except Exception as e:
            logger.error(f"Failed to retrieve feedback submissions: {str(e)}")
            return []
    
    def get_feedback_by_id(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Get specific feedback submission by ID"""
        try:
            submission = self.feedback_collection.find_one({'_id': ObjectId(submission_id)})
            if submission:
                submission['_id'] = str(submission['_id'])
                return submission
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve feedback by ID {submission_id}: {str(e)}")
            return None
    
    def get_feedback_statistics(self, form_type: Optional[str] = None) -> Dict[str, Any]:
        """Get feedback statistics"""
        try:
            match_stage = {}
            if form_type:
                match_stage['form_type'] = form_type
            
            pipeline = [
                {'$match': match_stage} if match_stage else {'$match': {}},
                {
                    '$group': {
                        '_id': None,
                        'total_submissions': {'$sum': 1},
                        'unique_users': {'$addToSet': '$user_info.email'},
                        'forms_by_type': {'$addToSet': '$form_type'},
                        'latest_submission': {'$max': '$created_at'},
                        'earliest_submission': {'$min': '$created_at'}
                    }
                },
                {
                    '$project': {
                        '_id': 0,
                        'total_submissions': 1,
                        'unique_users_count': {'$size': '$unique_users'},
                        'form_types_count': {'$size': '$forms_by_type'},
                        'latest_submission': 1,
                        'earliest_submission': 1
                    }
                }
            ]
            
            result = list(self.feedback_collection.aggregate(pipeline))
            
            if result:
                return result[0]
            else:
                return {
                    'total_submissions': 0,
                    'unique_users_count': 0,
                    'form_types_count': 0,
                    'latest_submission': None,
                    'earliest_submission': None
                }
                
        except Exception as e:
            logger.error(f"Failed to get feedback statistics: {str(e)}")
            return {}
    
    def delete_feedback(self, submission_id: str) -> bool:
        """Delete a feedback submission"""
        try:
            result = self.feedback_collection.delete_one({'_id': ObjectId(submission_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete feedback {submission_id}: {str(e)}")
            return False
    
    def update_feedback_status(self, submission_id: str, status: str) -> bool:
        """Update feedback submission status"""
        try:
            result = self.feedback_collection.update_one(
                {'_id': ObjectId(submission_id)},
                {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update feedback status {submission_id}: {str(e)}")
            return False

# Global feedback service instance
feedback_service = FeedbackService()