import os
import bcrypt
import random
import string
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import quote_plus
from config import get_config
import logging

logger = logging.getLogger(__name__)

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
        self.password_reset_otps = self.db.password_reset_otps
    
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
            "id": str(user["_id"]),  # Changed from "_id" to "id" for consistency
            "username": user.get("username", ""),
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "avatar_url": user.get("avatar_url", ""),
            "profile_picture": user.get("profile_picture", ""),
            "google_id": user.get("google_id", ""),
            "is_google_user": user.get("is_google_user", False),
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
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        user = self.users.find_one({"email": email})
        
        if not user:
            return None
        
        # Convert user to dict with string ID
        user_data = self.get_user_by_id(user["_id"])
        return user_data
    
    def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Google ID"""
        user = self.users.find_one({"google_id": google_id})
        
        if not user:
            return None
        
        # Convert user to dict with string ID
        user_data = self.get_user_by_id(user["_id"])
        return user_data
    
    def create_user(self, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new user with the provided data"""
        # Check if email already exists
        if self.get_user_by_email(user_data["email"]):
            return None
        
        # Check if Google ID already exists if provided
        if "google_id" in user_data and user_data["google_id"]:
            if self.get_user_by_google_id(user_data["google_id"]):
                return None
        
        # Set default values
        user = {
            "email": user_data["email"],
            "username": user_data.get("email", "").split("@")[0],  # Default username from email
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "first_name": user_data.get("name", "").split(" ")[0] if user_data.get("name") else "",
            "last_name": " ".join(user_data.get("name", "").split(" ")[1:]) if user_data.get("name") and len(user_data.get("name", "").split(" ")) > 1 else "",
            "avatar_url": user_data.get("picture", ""),
            "profile_picture": user_data.get("picture", ""),
            "google_id": user_data.get("google_id", ""),
            "is_google_user": user_data.get("is_google_user", False),
            "watchlists": []
        }
        
        try:
            # Insert user into database
            result = self.users.insert_one(user)
            
            if result.inserted_id:
                # Return user data
                user_data = self.get_user_by_id(result.inserted_id)
                return user_data
            
            return None
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            return None
    
    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        """Update user data"""
        try:
            object_id = ObjectId(user_id)
        except:
            return False
        
        # Add updated timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        # Update user
        result = self.users.update_one(
            {"_id": object_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
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
            "expires_at": datetime.utcnow() + timedelta(days=30)  # 30-day expiry
        }
        
        try:
            result = self.tokens.insert_one(token_data)
            return bool(result.inserted_id)
        except Exception as e:
            print(f"Error storing refresh token: {str(e)}")
            return False
    
    def validate_refresh_token(self, token: str) -> Optional[str]:
        """Validate a refresh token and return user ID if valid"""
        token_data = self.tokens.find_one({
            "token": token,
            "expires_at": {"$gt": datetime.utcnow()}
        })
        
        if token_data:
            return token_data["user_id"]
        
        return None
    
    def invalidate_refresh_token(self, token: str) -> bool:
        """Remove a refresh token from database"""
        result = self.tokens.delete_one({"token": token})
        return result.deleted_count > 0
    
    def save_backtest_result(self, user_id: str, backtest_data: Dict[str, Any]) -> bool:
        """Save backtest result to user's history"""
        try:
            # Create backtest document
            backtest = {
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "type": "backtest",
                "backtest_data": backtest_data,  # Use consistent field name
                "name": backtest_data.get("name", f"Backtest {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"),
                "symbol": backtest_data.get("stock_symbol", backtest_data.get("symbol", "Unknown")),
                "strategy": backtest_data.get("strategy_type", backtest_data.get("strategy", "Custom")),
                "performance": backtest_data.get("metrics", backtest_data.get("performance", {}))
            }
            
            # Insert backtest into database
            result = self.db.backtests.insert_one(backtest)
            logger.info(f"Saved backtest for user {user_id}: {backtest['name']} ({backtest['symbol']})")
            return bool(result.inserted_id)
        except Exception as e:
            logger.error(f"Error saving backtest result: {str(e)}")
            print(f"Error saving backtest result: {str(e)}")
            return False
    
    def save_ai_analysis_result(self, user_id: str, analysis_data: Dict[str, Any]) -> bool:
        """Save AI analysis result to user's history"""
        try:
            # Create analysis document
            analysis = {
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "data": analysis_data,
                "name": analysis_data.get("name", f"Analysis {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"),
                "symbol": analysis_data.get("symbol", "Unknown"),
                "model": analysis_data.get("model", "Unknown"),
                "summary": analysis_data.get("summary", "")
            }
            
            # Insert analysis into database
            result = self.db.ai_analyses.insert_one(analysis)
            return bool(result.inserted_id)
        except Exception as e:
            print(f"Error saving AI analysis result: {str(e)}")
            return False
    
    def save_chat_history(self, user_id: str, chat_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save chat history to user's history, supporting both new and existing sessions"""
        try:
            # Generate dynamic title from user query (ChatGPT-like naming)
            def generate_chat_title(conversation: List[Dict[str, Any]]) -> str:
                # Find first user message for title
                first_user_message = ""
                for msg in conversation:
                    if msg.get("sender") == "user" and msg.get("text"):
                        first_user_message = msg["text"]
                        break
                
                if not first_user_message:
                    return f"Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
                
                # Clean and truncate the query for title
                words = first_user_message.strip().split()[:5]  # First 5 words
                title = ' '.join(words)
                
                # Truncate if too long
                if len(title) > 50:
                    title = title[:47] + '...'
                
                return title or f"Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            
            # Check if chat_id is provided for updating existing chat
            chat_id = chat_data.get("chat_id")
            conversation = chat_data.get("conversation", [])
            
            if chat_id:
                # Update existing chat session
                try:
                    object_id = ObjectId(chat_id)
                    chat_title = chat_data.get("title") or generate_chat_title(conversation)
                    
                    update_data = {
                        "data": chat_data,
                        "title": chat_title,
                        "name": chat_title,  # Keep both for backward compatibility
                        "model": chat_data.get("model", "Unknown"),
                        "summary": chat_data.get("summary", ""),
                        "updated_at": datetime.utcnow()
                    }
                    
                    result = self.db.chat_history.update_one(
                        {"_id": object_id, "user_id": user_id},
                        {"$set": update_data}
                    )
                    
                    if result.modified_count > 0:
                        return {
                            "success": True,
                            "chat_id": chat_id,
                            "message": "Chat history updated successfully"
                        }
                    else:
                        # Chat not found or no changes, create new one
                        chat_id = None
                except:
                    # Invalid ObjectId, create new chat
                    chat_id = None
            
            # Create new chat session
            chat_title = chat_data.get("title") or generate_chat_title(conversation)
            chat = {
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "data": chat_data,
                "title": chat_title,
                "name": chat_title,  # Keep both for backward compatibility
                "model": chat_data.get("model", "Unknown"),
                "summary": chat_data.get("summary", "")
            }
            
            # Insert new chat into database
            result = self.db.chat_history.insert_one(chat)
            if result.inserted_id:
                return {
                    "success": True,
                    "chat_id": str(result.inserted_id),
                    "message": "Chat history saved successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to save chat history"
                }
                
        except Exception as e:
            print(f"Error saving chat history: {str(e)}")
            return {
                "success": False,
                "message": f"Error saving chat history: {str(e)}"
            }
    
    def get_user_backtests(self, user_id: str, limit: int = 10, skip: int = 0) -> List[Dict[str, Any]]:
        """Get user's saved backtest results with full data"""
        try:
            backtests = list(self.db.backtests.find(
                {"user_id": user_id}
                # Include all data including results, metrics, charts, etc.
            ).sort("created_at", -1).skip(skip).limit(limit))
            
            # Convert ObjectIds to strings and ensure consistent structure
            for backtest in backtests:
                backtest["_id"] = str(backtest["_id"])
                # Handle both old and new data structures
                if "data" in backtest and "backtest_data" not in backtest:
                    backtest["backtest_data"] = backtest["data"]
                # Ensure backtest_data is available for dashboard display
                if "backtest_data" not in backtest and "data" not in backtest:
                    logger.warning(f"No backtest data found for backtest {backtest['_id']}")
            
            logger.info(f"Retrieved {len(backtests)} backtests for user {user_id}")
            return backtests
        except Exception as e:
            logger.error(f"Error getting user backtests: {str(e)}")
            print(f"Error getting user backtests: {str(e)}")
            return []
    
    def get_user_ai_analyses(self, user_id: str, limit: int = 10, skip: int = 0) -> List[Dict[str, Any]]:
        """Get user's saved AI analysis results"""
        try:
            # Return full documents including the nested analysis data
            analyses = list(
                self.db.ai_analyses
                .find({"user_id": user_id})
                .sort("created_at", -1)
                .skip(skip)
                .limit(limit)
            )
            
            # Convert ObjectIds to strings
            for analysis in analyses:
                analysis["_id"] = str(analysis["_id"])
                # Backward compatibility: expose nested data under a stable key
                if "analysis_data" not in analysis and "data" in analysis:
                    analysis["analysis_data"] = analysis.get("data")
            
            return analyses
        except Exception as e:
            print(f"Error getting user AI analyses: {str(e)}")
            return []
    
    def get_user_chat_history(self, user_id: str, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        """Get user's saved chat history"""
        try:
            chats = list(self.db.chat_history.find(
                {"user_id": user_id}
            ).sort("created_at", -1).skip(skip).limit(limit))
            
            # Convert ObjectIds to strings and ensure title field
            for chat in chats:
                chat["_id"] = str(chat["_id"])
                # Ensure title field exists (use name as fallback for old records)
                if "title" not in chat and "name" in chat:
                    chat["title"] = chat["name"]
                # Use timestamp as final fallback
                if "title" not in chat or not chat["title"]:
                    chat["title"] = f"Chat {chat.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M')}"
                
                # Extract conversation from nested data for frontend compatibility
                if "data" in chat and "conversation" in chat["data"]:
                    chat["conversation"] = chat["data"]["conversation"]
                elif "data" in chat:
                    # Handle legacy format where data might contain query/response
                    if "query" in chat["data"]:
                        chat["query"] = chat["data"]["query"]
                    if "response" in chat["data"]:
                        chat["response"] = chat["data"]["response"]
            
            return chats
        except Exception as e:
            print(f"Error getting user chat history: {str(e)}")
            return []
    
    def generate_otp(self, length: int = 6) -> str:
        """Generate a random OTP"""
        return ''.join(random.choices(string.digits, k=length))
    
    def create_password_reset_otp(self, username_or_email: str) -> Tuple[bool, str, Optional[str]]:
        """
        Create password reset OTP for user
        
        Returns:
        - Success status (bool)
        - Message (str)  
        - OTP code (str or None)
        """
        try:
            # Find user by username or email
            user = self.users.find_one({
                "$or": [
                    {"username": username_or_email},
                    {"email": username_or_email}
                ]
            })
            
            if not user:
                return False, "User not found", None
            
            # Generate OTP
            otp = self.generate_otp()
            expires_at = datetime.utcnow() + timedelta(minutes=15)  # 15 minutes expiry
            
            # Store OTP in database
            otp_record = {
                "user_id": user["_id"],
                "email": user["email"],
                "username": user["username"],
                "otp": otp,
                "expires_at": expires_at,
                "used": False,
                "created_at": datetime.utcnow()
            }
            
            # Remove any existing OTPs for this user
            self.password_reset_otps.delete_many({"user_id": user["_id"]})
            
            # Insert new OTP
            self.password_reset_otps.insert_one(otp_record)
            
            logger.info(f"Password reset OTP created for user: {user['username']}")
            return True, "OTP generated successfully", otp
            
        except Exception as e:
            logger.error(f"Error creating password reset OTP: {str(e)}")
            return False, "Failed to generate OTP", None
    
    def verify_password_reset_otp(self, username_or_email: str, otp: str) -> Tuple[bool, str, Optional[str]]:
        """
        Verify password reset OTP
        
        Returns:
        - Success status (bool)
        - Message (str)
        - User ID (str or None) if verified
        """
        try:
            # Find user and OTP record
            user = self.users.find_one({
                "$or": [
                    {"username": username_or_email},
                    {"email": username_or_email}
                ]
            })
            
            if not user:
                return False, "User not found", None
            
            # Find matching OTP record
            otp_record = self.password_reset_otps.find_one({
                "user_id": user["_id"],
                "otp": otp,
                "used": False
            })
            
            if not otp_record:
                return False, "Invalid OTP", None
            
            # Check if OTP has expired
            if datetime.utcnow() > otp_record["expires_at"]:
                # Clean up expired OTP
                self.password_reset_otps.delete_one({"_id": otp_record["_id"]})
                return False, "OTP has expired", None
            
            # Mark OTP as used
            self.password_reset_otps.update_one(
                {"_id": otp_record["_id"]},
                {"$set": {"used": True, "used_at": datetime.utcnow()}}
            )
            
            logger.info(f"Password reset OTP verified for user: {user['username']}")
            return True, "OTP verified successfully", str(user["_id"])
            
        except Exception as e:
            logger.error(f"Error verifying password reset OTP: {str(e)}")
            return False, "Failed to verify OTP", None
    
    def reset_password_with_verification(self, user_id: str, new_password: str, otp: str) -> Tuple[bool, str]:
        """
        Reset password with OTP verification
        
        Returns:
        - Success status (bool)
        - Message (str)
        """
        try:
            # Find user
            user = self.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False, "User not found"
            
            # Find valid used OTP record (recently used within last 5 minutes for security)
            recent_time = datetime.utcnow() - timedelta(minutes=5)
            otp_record = self.password_reset_otps.find_one({
                "user_id": ObjectId(user_id),
                "otp": otp,
                "used": True,
                "used_at": {"$gte": recent_time}
            })
            
            if not otp_record:
                return False, "OTP verification required or expired"
            
            # Update password
            hashed_password = self.hash_password(new_password)
            result = self.users.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "password": hashed_password,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                # Clean up all OTP records for this user
                self.password_reset_otps.delete_many({"user_id": ObjectId(user_id)})
                
                logger.info(f"Password reset completed for user: {user['username']}")
                return True, "Password reset successfully"
            else:
                return False, "Failed to update password"
                
        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}")
            return False, "Failed to reset password"
    
    def cleanup_expired_otps(self):
        """Clean up expired OTP records"""
        try:
            current_time = datetime.utcnow()
            result = self.password_reset_otps.delete_many({
                "expires_at": {"$lt": current_time}
            })
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} expired OTP records")
        except Exception as e:
            logger.error(f"Error cleaning up expired OTPs: {str(e)}")