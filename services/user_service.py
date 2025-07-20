import os
import bcrypt
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from urllib.parse import quote_plus
from config import get_config

# MongoDB connection
def get_db_connection():
    """
    Connect to MongoDB using connection string from environment variable
    """
    config = get_config()
    mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
    
    # Handle potential special characters in connection string
    try:
        client = MongoClient(mongo_uri)
        db = client.get_database(config.DB_NAME)
        return db
    except Exception as e:
        print(f"MongoDB connection error: {str(e)}")
        # Fallback to local connection without authentication
        client = MongoClient('mongodb://localhost:27017')
        db = client.get_database(config.DB_NAME)
        return db

class UserService:
    """Service for user authentication and profile management"""
    
    def __init__(self):
        self.db = get_db_connection()
        self.users = self.db.users
        self.tokens = self.db.refresh_tokens
    
    def hash_password(self, password: str) -> bytes:
        """Hash a password for storing"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed
    
    def check_password(self, password: str, hashed_password: bytes) -> bool:
        """Check if password matches the hashed password"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password)
    
    def register_user(self, email: str, username: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Register a new user
        
        Returns:
        Tuple containing:
        - Success status (bool)
        - Message (str)
        - User data (Dict or None)
        """
        # Check if username or email already exists
        if self.users.find_one({"username": username}):
            return False, "Username already exists", None
        
        if self.users.find_one({"email": email}):
            return False, "Email already exists", None
        
        # Create user document without subscription (will be initialized separately)
        user = {
            "username": username,
            "email": email,
            "password": self.hash_password(password),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "first_name": "",
            "last_name": "",
            "avatar_url": "",
            "watchlists": []
        }
        
        try:
            # Insert user into database
            result = self.users.insert_one(user)
            
            if result.inserted_id:
                # Return user data without password
                user_data = self.get_user_by_id(result.inserted_id)
                if user_data:
                    return True, "User registered successfully", user_data
            
            return False, "Failed to register user", None
        except Exception as e:
            print(f"Error registering user: {str(e)}")
            return False, "Failed to register user", None
    
    def login_user(self, username_or_email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Authenticate a user
        
        Returns:
        Tuple containing:
        - Success status (bool)
        - Message (str)
        - User data (Dict or None)
        """
        # Find user by username or email
        user = self.users.find_one({"$or": [{"username": username_or_email}, {"email": username_or_email}]})
        
        if not user:
            return False, "Invalid username or email", None
        
        # Check password
        if not self.check_password(password, user["password"]):
            return False, "Invalid password", None
        
        # Return user data without password
        user_data = {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "avatar_url": user.get("avatar_url", "")
        }
        
        return True, "Login successful", user_data
    
    def get_user_by_id(self, user_id) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        if isinstance(user_id, str):
            try:
                user_id = ObjectId(user_id)
            except:
                return None
        
        user = self.users.find_one({"_id": user_id})
        
        if not user:
            return None
        
        # Return user data without password
        return {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "avatar_url": user.get("avatar_url", ""),
            "role": user.get("role", "user"),
            "subscription": user.get("subscription", {
                "tier": "FREE",
                "starts_at": datetime.utcnow(),
                "expires_at": None,
                "usage": {
                    "daily": {
                        "backtest_count": 0,
                        "llm_query_count": 0,
                        "last_reset": datetime.utcnow()
                    },
                    "monthly": {
                        "backtest_count": 0,
                        "llm_query_count": 0,
                        "last_reset": datetime.utcnow()
                    }
                }
            })
        }
    
    def update_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Update user profile"""
        try:
            object_id = ObjectId(user_id)
        except:
            return False, "Invalid user ID", None
        
        # Get allowed fields to update
        allowed_fields = ["first_name", "last_name", "avatar_url"]
        update_data = {k: v for k, v in profile_data.items() if k in allowed_fields}
        
        # Add updated timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        # Update user
        result = self.users.update_one(
            {"_id": object_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            # Get updated user
            user_data = self.get_user_by_id(user_id)
            return True, "Profile updated successfully", user_data
        
        return False, "Failed to update profile", None
    
    def store_refresh_token(self, user_id: str, token: str) -> bool:
        """Store refresh token in database"""
        token_data = {
            "user_id": user_id,
            "token": token,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=30)
        }
        
        result = self.tokens.insert_one(token_data)
        return bool(result.inserted_id)
    
    def validate_refresh_token(self, token: str) -> Optional[str]:
        """Validate refresh token and return user ID if valid"""
        token_data = self.tokens.find_one({
            "token": token,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if token_data:
            return token_data["user_id"]
        
        return None
    
    def invalidate_refresh_token(self, token: str) -> bool:
        """Remove refresh token from database"""
        result = self.tokens.delete_one({"token": token})
        return result.deleted_count > 0 