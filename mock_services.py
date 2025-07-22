"""
Mock services for development without MongoDB
"""
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MockSubscriptionService:
    """Mock subscription service for development without MongoDB"""
    
    def __init__(self):
        # In-memory storage for testing
        self.users_data = {}
        self.default_subscription = {
            'tier': 'FREE',
            'expires_at': datetime.utcnow() + timedelta(days=30),
            'usage': {
                'backtest': {'daily_count': 0, 'last_reset': datetime.utcnow().date()},
                'llm_query': {'daily_count': 0, 'last_reset': datetime.utcnow().date()}
            }
        }
        
    def initialize_subscription(self, user_id: str) -> bool:
        """Initialize a new user's subscription with FREE tier"""
        self.users_data[user_id] = {
            '_id': user_id,
            'subscription': self.default_subscription.copy()
        }
        return True
        
    def get_subscription_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's subscription details"""
        user_data = self.users_data.get(user_id)
        if not user_data:
            # Initialize if not exists
            self.initialize_subscription(user_id)
            user_data = self.users_data.get(user_id)
            
        return user_data.get('subscription') if user_data else None
        
    def upgrade_subscription(self, user_id: str, new_tier: str) -> Tuple[bool, str]:
        """Upgrade user's subscription tier"""
        if user_id not in self.users_data:
            return False, "User not found"
            
        valid_tiers = ['FREE', 'BASIC', 'PRO', 'ENTERPRISE']
        if new_tier.upper() not in valid_tiers:
            return False, f"Invalid tier. Must be one of: {', '.join(valid_tiers)}"
            
        self.users_data[user_id]['subscription']['tier'] = new_tier.upper()
        return True, f"Subscription upgraded to {new_tier.upper()}"
        
    def get_usage_metrics(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's usage metrics"""
        user_data = self.users_data.get(user_id)
        if not user_data:
            return None
            
        return user_data.get('subscription', {}).get('usage', {})
        
    def increment_usage(self, user_id: str, feature: str) -> Tuple[bool, str]:
        """Increment usage counter for a specific feature"""
        if user_id not in self.users_data:
            return False, "User not found"
            
        usage = self.users_data[user_id]['subscription']['usage']
        if feature in usage:
            usage[feature]['daily_count'] += 1
            return True, f"Usage incremented for {feature}"
        else:
            return False, f"Unknown feature: {feature}"

class MockUserService:
    """Mock user service for development without MongoDB"""
    
    def __init__(self):
        self.users_data = {}
        self.tokens = {}
        
    def register_user(self, email: str, username: str, password: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Register a new user"""
        user_id = f"user_{len(self.users_data) + 1}"
        user_data = {
            'id': user_id,
            'email': email,
            'username': username,
            'created_at': datetime.utcnow().isoformat()
        }
        self.users_data[user_id] = user_data
        return True, "User registered successfully", user_data
        
    def login_user(self, username_or_email: str, password: str) -> Tuple[bool, str, Dict[str, Any]]:
        """Login user"""
        # Mock successful login
        user_id = "mock_user_1"
        if user_id not in self.users_data:
            self.users_data[user_id] = {
                'id': user_id,
                'email': 'test@example.com',
                'username': 'testuser',
                'created_at': datetime.utcnow().isoformat()
            }
        return True, "Login successful", self.users_data[user_id]
        
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        return self.users_data.get(user_id)
        
    def store_refresh_token(self, user_id: str, token: str) -> bool:
        """Store refresh token"""
        self.tokens[user_id] = token
        return True
        
    def validate_refresh_token(self, token: str) -> Optional[str]:
        """Validate refresh token"""
        for user_id, stored_token in self.tokens.items():
            if stored_token == token:
                return user_id
        return None
        
    def invalidate_refresh_token(self, token: str) -> bool:
        """Invalidate refresh token"""
        for user_id, stored_token in list(self.tokens.items()):
            if stored_token == token:
                del self.tokens[user_id]
                return True
        return False
        
    def update_user_profile(self, user_id: str, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """Update user profile"""
        if user_id not in self.users_data:
            return False, "User not found", {}
            
        self.users_data[user_id].update(data)
        return True, "Profile updated", self.users_data[user_id]
        
    def add_to_portfolio(self, user_id: str, data: Dict[str, Any]) -> bool:
        """Add to portfolio"""
        if user_id not in self.users_data:
            return False
            
        if 'portfolio' not in self.users_data[user_id]:
            self.users_data[user_id]['portfolio'] = []
            
        self.users_data[user_id]['portfolio'].append(data)
        return True