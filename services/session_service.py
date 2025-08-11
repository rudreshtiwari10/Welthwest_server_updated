import uuid
import json
import time
from datetime import datetime, timedelta
import threading

class InMemorySessionService:
    def __init__(self):
        # Feature limits for anonymous users
        self.free_message_limit = 5  # Chat messages
        self.free_backtest_limit = 3  # Backtesting attempts
        self.free_ai_analysis_limit = 2  # AI analysis attempts
        
        self.session_cleanup_interval = 3600  # Run cleanup every hour
        self.sessions = {}  # In-memory storage
        self.lock = threading.RLock()  # Thread-safe operations
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def create_anonymous_session(self):
        """Create a new anonymous session for a visitor"""
        session_id = str(uuid.uuid4())
        
        with self.lock:
            self.sessions[session_id] = {
                'created_at': datetime.now().isoformat(),
                'message_count': 0,
                'backtest_count': 0,
                'ai_analysis_count': 0,
                'last_activity_at': datetime.now().isoformat(),
                'is_anonymous': True,
                'expires_at': (datetime.now() + timedelta(days=7)).isoformat()
            }
        
        return session_id
    
    def get_session(self, session_id):
        """Get session data by ID"""
        with self.lock:
            session_data = self.sessions.get(session_id)
            
            # Check if session has expired
            if session_data and session_data.get('expires_at'):
                expires_at = datetime.fromisoformat(session_data['expires_at'])
                if datetime.now() > expires_at:
                    del self.sessions[session_id]
                    return None
                    
            return session_data
    
    def update_message_count(self, session_id):
        """Increment message count for a session"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Increment message count
            session_data['message_count'] += 1
            session_data['last_activity_at'] = datetime.now().isoformat()
            
            return session_data['message_count']
    
    def update_backtest_count(self, session_id):
        """Increment backtest count for a session"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Increment backtest count
            session_data['backtest_count'] += 1
            session_data['last_activity_at'] = datetime.now().isoformat()
            
            return session_data['backtest_count']
    
    def update_ai_analysis_count(self, session_id):
        """Increment AI analysis count for a session"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Increment AI analysis count
            session_data['ai_analysis_count'] += 1
            session_data['last_activity_at'] = datetime.now().isoformat()
            
            return session_data['ai_analysis_count']
    
    def convert_to_authenticated_session(self, session_id, user_id):
        """Convert anonymous session to authenticated"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Update session data
            session_data['is_anonymous'] = False
            session_data['user_id'] = user_id
            session_data['authenticated_at'] = datetime.now().isoformat()
            session_data.pop('expires_at', None)  # Remove expiry for authenticated sessions
            
            # Also store user's active session
            self.sessions[f"user_{user_id}"] = session_id
            
            return True
    
    def check_can_send_message(self, session_id):
        """Check if a session can send more messages"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Authenticated users can always send messages
            if not session_data.get('is_anonymous', True):
                return True
            
            # Check if anonymous user is within limits
            return session_data.get('message_count', 0) < self.free_message_limit
    
    def check_can_backtest(self, session_id):
        """Check if a session can run more backtests"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Authenticated users can always backtest (subject to subscription limits)
            if not session_data.get('is_anonymous', True):
                return True
            
            # Check if anonymous user is within limits
            return session_data.get('backtest_count', 0) < self.free_backtest_limit
    
    def check_can_ai_analyze(self, session_id):
        """Check if a session can run more AI analyses"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return False
            
            # Authenticated users can always use AI analysis (subject to subscription limits)
            if not session_data.get('is_anonymous', True):
                return True
            
            # Check if anonymous user is within limits
            return session_data.get('ai_analysis_count', 0) < self.free_ai_analysis_limit
    
    def get_remaining_usage(self, session_id):
        """Get remaining usage counts for a session"""
        with self.lock:
            session_data = self.get_session(session_id)
            if not session_data:
                return None
            
            if not session_data.get('is_anonymous', True):
                # Authenticated users have unlimited usage (subject to subscription)
                return {
                    'messages': -1,  # Unlimited
                    'backtests': -1,  # Unlimited
                    'ai_analyses': -1  # Unlimited
                }
            
            return {
                'messages': max(0, self.free_message_limit - session_data.get('message_count', 0)),
                'backtests': max(0, self.free_backtest_limit - session_data.get('backtest_count', 0)),
                'ai_analyses': max(0, self.free_ai_analysis_limit - session_data.get('ai_analysis_count', 0))
            }
    
    def _start_cleanup_thread(self):
        """Start a thread to periodically clean up expired sessions"""
        def cleanup_job():
            while True:
                try:
                    self._cleanup_expired_sessions()
                except Exception as e:
                    print(f"Error in cleanup job: {e}")
                
                # Sleep for the cleanup interval
                time.sleep(self.session_cleanup_interval)
        
        cleanup_thread = threading.Thread(target=cleanup_job, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_expired_sessions(self):
        """Remove expired sessions from memory"""
        now = datetime.now()
        
        with self.lock:
            session_ids_to_remove = []
            
            for session_id, data in self.sessions.items():
                # Skip sessions without expiry (authenticated)
                if not data.get('expires_at'):
                    continue
                
                # Check if expired
                expires_at = datetime.fromisoformat(data['expires_at'])
                if now > expires_at:
                    session_ids_to_remove.append(session_id)
            
            # Remove expired sessions
            for session_id in session_ids_to_remove:
                del self.sessions[session_id]