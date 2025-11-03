"""
Premium Usage Service - Redis-based atomic usage tracking with Lua scripts
Handles per-feature usage counting for premium plans with atomic check-and-increment
"""
import redis
import logging
from typing import Tuple, Dict, Optional
from datetime import datetime, timedelta
from config import get_config
from pymongo import MongoClient
from bson import ObjectId
import pytz

logger = logging.getLogger(__name__)

# Lua script for atomic check-and-increment
# Returns {allowed (1/0), remaining}
LUA_CHECK_AND_INCREMENT = """
local current = redis.call("GET", KEYS[1])
if not current then
    redis.call("SET", KEYS[1], 1, "EX", ARGV[2])
    return {1, tonumber(ARGV[1]) - 1}
else
    current = tonumber(current)
    if current >= tonumber(ARGV[1]) then
        return {0, 0}
    else
        local val = redis.call("INCR", KEYS[1])
        return {1, tonumber(ARGV[1]) - val}
    end
end
"""


class PremiumUsageService:
    """Service for managing premium feature usage with Redis and MongoDB"""

    def __init__(self):
        self.config = get_config()

        # Initialize Redis
        try:
            self.redis_client = redis.Redis(
                host=self.config.REDIS_HOST,
                port=self.config.REDIS_PORT,
                db=self.config.REDIS_DB,
                password=self.config.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Premium Usage Service: Redis connection established")
        except Exception as e:
            logger.warning(f"Premium Usage Service: Redis not available, using MongoDB fallback: {e}")
            self.redis_client = None
            self.redis_available = False

        # Initialize MongoDB
        self.db = MongoClient(self.config.MONGODB_URI)[self.config.DB_NAME]
        self.usage_logs = self.db.usage_logs

        # Register Lua script
        if self.redis_available:
            try:
                self.check_and_incr_script = self.redis_client.register_script(LUA_CHECK_AND_INCREMENT)
                logger.info("Premium Usage Service: Lua script registered")
            except Exception as e:
                logger.error(f"Failed to register Lua script: {e}")
                self.check_and_incr_script = None

    def _get_date_str(self) -> str:
        """Get current date string in server timezone"""
        tz = pytz.timezone(self.config.SERVER_TIMEZONE)
        return datetime.now(tz).strftime('%Y%m%d')

    def _get_redis_key(self, actor_id: str, feature_key: str, is_anonymous: bool = False) -> str:
        """
        Generate Redis key for usage counter

        Args:
            actor_id: user_id or session_id
            feature_key: Feature identifier (e.g., 'welth-market-regime')
            is_anonymous: Whether this is an anonymous session

        Returns:
            Redis key string
        """
        if is_anonymous:
            # Anonymous: anon:{session_id}:usage:{feature}
            return f"anon:{actor_id}:usage:{feature_key}"
        else:
            # Authenticated: user:{user_id}:usage:{feature}:{YYYYMMDD}
            date_str = self._get_date_str()
            return f"user:{actor_id}:usage:{feature_key}:{date_str}"

    def check_and_increment(
        self,
        actor_id: str,
        feature_key: str,
        limit: int,
        is_anonymous: bool = False
    ) -> Tuple[bool, int]:
        """
        Atomically check if usage is under limit and increment if allowed

        Args:
            actor_id: user_id or session_id
            feature_key: Feature identifier
            limit: Maximum allowed uses
            is_anonymous: Whether this is an anonymous session

        Returns:
            Tuple of (allowed: bool, remaining: int)
        """
        redis_key = self._get_redis_key(actor_id, feature_key, is_anonymous)

        if self.redis_available and self.check_and_incr_script:
            try:
                # Use Lua script for atomic check-and-increment
                result = self.check_and_incr_script(
                    keys=[redis_key],
                    args=[limit, self.config.USAGE_COUNTER_TTL_SECONDS]
                )
                allowed = bool(result[0])
                remaining = int(result[1])

                # Log to MongoDB asynchronously (non-blocking)
                self._log_usage(actor_id, feature_key, allowed, remaining, is_anonymous)

                return allowed, remaining

            except Exception as e:
                logger.error(f"Redis error in check_and_increment: {e}, falling back to MongoDB")
                return self._check_and_increment_mongo(actor_id, feature_key, limit, is_anonymous)
        else:
            # Fallback to MongoDB
            return self._check_and_increment_mongo(actor_id, feature_key, limit, is_anonymous)

    def _check_and_increment_mongo(
        self,
        actor_id: str,
        feature_key: str,
        limit: int,
        is_anonymous: bool
    ) -> Tuple[bool, int]:
        """MongoDB fallback for check-and-increment (slower but functional)"""
        try:
            date_str = self._get_date_str()

            # Find or create usage document
            query = {
                'actor_id': actor_id,
                'feature': feature_key,
                'date': date_str,
                'is_anonymous': is_anonymous
            }

            usage_doc = self.usage_logs.find_one(query)

            if not usage_doc:
                # Create new usage document
                self.usage_logs.insert_one({
                    **query,
                    'count': 1,
                    'limit': limit,
                    'created_at': datetime.utcnow()
                })
                return True, limit - 1
            else:
                current_count = usage_doc.get('count', 0)
                if current_count >= limit:
                    return False, 0
                else:
                    # Increment count
                    self.usage_logs.update_one(
                        query,
                        {'$inc': {'count': 1}}
                    )
                    return True, limit - current_count - 1

        except Exception as e:
            logger.error(f"MongoDB fallback error: {e}")
            return False, 0

    def get_remaining(
        self,
        actor_id: str,
        feature_key: str,
        limit: int,
        is_anonymous: bool = False
    ) -> int:
        """
        Get remaining usage for a feature without incrementing

        Args:
            actor_id: user_id or session_id
            feature_key: Feature identifier
            limit: Maximum allowed uses
            is_anonymous: Whether this is an anonymous session

        Returns:
            Remaining usage count
        """
        redis_key = self._get_redis_key(actor_id, feature_key, is_anonymous)

        if self.redis_available:
            try:
                current = self.redis_client.get(redis_key)
                if current is None:
                    return limit
                else:
                    used = int(current)
                    return max(0, limit - used)
            except Exception as e:
                logger.error(f"Redis error in get_remaining: {e}")
                return self._get_remaining_mongo(actor_id, feature_key, limit, is_anonymous)
        else:
            return self._get_remaining_mongo(actor_id, feature_key, limit, is_anonymous)

    def _get_remaining_mongo(
        self,
        actor_id: str,
        feature_key: str,
        limit: int,
        is_anonymous: bool
    ) -> int:
        """MongoDB fallback for get_remaining"""
        try:
            date_str = self._get_date_str()
            query = {
                'actor_id': actor_id,
                'feature': feature_key,
                'date': date_str,
                'is_anonymous': is_anonymous
            }

            usage_doc = self.usage_logs.find_one(query)
            if not usage_doc:
                return limit
            else:
                used = usage_doc.get('count', 0)
                return max(0, limit - used)
        except Exception as e:
            logger.error(f"MongoDB error in _get_remaining_mongo: {e}")
            return 0

    def get_all_usage(
        self,
        actor_id: str,
        feature_keys: list,
        limits: Dict[str, int],
        is_anonymous: bool = False
    ) -> Dict[str, Dict[str, int]]:
        """
        Get usage for all features for an actor

        Args:
            actor_id: user_id or session_id
            feature_keys: List of feature identifiers
            limits: Dict mapping feature_key to limit
            is_anonymous: Whether this is an anonymous session

        Returns:
            Dict mapping feature_key to {used, remaining, limit}
        """
        result = {}

        for feature_key in feature_keys:
            limit = limits.get(feature_key, 0)
            remaining = self.get_remaining(actor_id, feature_key, limit, is_anonymous)
            used = limit - remaining

            result[feature_key] = {
                'used': used,
                'remaining': remaining,
                'limit': limit
            }

        return result

    def _log_usage(
        self,
        actor_id: str,
        feature_key: str,
        allowed: bool,
        remaining: int,
        is_anonymous: bool
    ):
        """Log usage event to MongoDB for auditing"""
        try:
            log_entry = {
                'actor_id': actor_id,
                'user_id': None if is_anonymous else ObjectId(actor_id),
                'session_id': actor_id if is_anonymous else None,
                'feature': feature_key,
                'action': 'USE',
                'result': 'ALLOWED' if allowed else 'DENIED',
                'remaining': remaining,
                'is_anonymous': is_anonymous,
                'created_at': datetime.utcnow()
            }

            self.usage_logs.insert_one(log_entry)
        except Exception as e:
            logger.error(f"Failed to log usage to MongoDB: {e}")

    def reset_usage(
        self,
        actor_id: str,
        feature_key: str,
        is_anonymous: bool = False
    ) -> bool:
        """
        Reset usage for a specific feature (admin/testing purpose)

        Args:
            actor_id: user_id or session_id
            feature_key: Feature identifier
            is_anonymous: Whether this is an anonymous session

        Returns:
            True if reset successful
        """
        redis_key = self._get_redis_key(actor_id, feature_key, is_anonymous)

        if self.redis_available:
            try:
                self.redis_client.delete(redis_key)
                logger.info(f"Reset usage for {redis_key}")
                return True
            except Exception as e:
                logger.error(f"Failed to reset usage in Redis: {e}")
                return False

        # Also reset in MongoDB
        try:
            date_str = self._get_date_str()
            self.usage_logs.delete_many({
                'actor_id': actor_id,
                'feature': feature_key,
                'date': date_str,
                'is_anonymous': is_anonymous
            })
            return True
        except Exception as e:
            logger.error(f"Failed to reset usage in MongoDB: {e}")
            return False

    def delete_all_usage(
        self,
        actor_id: str,
        is_anonymous: bool = False
    ) -> bool:
        """
        Delete all usage data for an actor (admin/testing purpose)

        Args:
            actor_id: user_id or session_id
            is_anonymous: Whether this is an anonymous session

        Returns:
            True if deletion successful
        """
        if self.redis_available:
            try:
                # Delete all Redis keys for this actor
                if is_anonymous:
                    pattern = f"anon:{actor_id}:usage:*"
                else:
                    pattern = f"user:{actor_id}:usage:*"

                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                logger.info(f"Deleted all usage keys for {actor_id}")
            except Exception as e:
                logger.error(f"Failed to delete usage keys in Redis: {e}")

        # Also delete from MongoDB
        try:
            self.usage_logs.delete_many({
                'actor_id': actor_id,
                'is_anonymous': is_anonymous
            })
            return True
        except Exception as e:
            logger.error(f"Failed to delete usage from MongoDB: {e}")
            return False


# Create singleton instance
_premium_usage_service = None

def get_premium_usage_service() -> PremiumUsageService:
    """Get the singleton PremiumUsageService instance"""
    global _premium_usage_service
    if _premium_usage_service is None:
        _premium_usage_service = PremiumUsageService()
    return _premium_usage_service
