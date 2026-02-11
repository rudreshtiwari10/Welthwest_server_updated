"""
Multi-Level Cache Manager with Redis + In-Memory Fallback

Provides high-performance caching with automatic fallback:
- Level 1: Redis (shared across processes/servers)
- Level 2: In-memory (fallback if Redis unavailable)

Usage:
    from middleware.cache_manager import cache

    # Get cached value
    value = cache.get('my_key')

    # Set with TTL
    cache.set('my_key', {'data': 'value'}, ttl=300)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try to import Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - using in-memory cache only. Install: pip install redis")


class CacheManager:
    """
    Multi-level cache manager with Redis + memory fallback
    """

    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        """Initialize cache manager"""
        self.redis_client = None
        self.memory_cache = {}  # Fallback if Redis down
        self.redis_available = False

        # Try to connect to Redis
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                # Test connection
                self.redis_client.ping()
                self.redis_available = True
                logger.info(f"Redis cache connected: {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using memory cache only.")
                self.redis_client = None
                self.redis_available = False
        else:
            logger.info("Using in-memory cache only (Redis not installed)")

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        # Try Redis first
        if self.redis_available and self.redis_client:
            try:
                val = self.redis_client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.debug(f"Redis get error for key '{key}': {e}")

        # Fallback to memory cache
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            expires_at = entry.get('expires_at')

            # Check if expired
            if expires_at and datetime.now() < expires_at:
                return entry['value']
            else:
                # Remove expired entry
                del self.memory_cache[key]

        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Set value in cache with TTL

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (default: 5 minutes)

        Returns:
            True if cached successfully
        """
        # Try Redis first
        if self.redis_available and self.redis_client:
            try:
                self.redis_client.setex(
                    key,
                    ttl,
                    json.dumps(value, default=str)
                )
                return True
            except Exception as e:
                logger.debug(f"Redis set error for key '{key}': {e}")

        # Fallback to memory cache
        try:
            self.memory_cache[key] = {
                'value': value,
                'expires_at': datetime.now() + timedelta(seconds=ttl)
            }
            return True
        except Exception as e:
            logger.error(f"Memory cache set error for key '{key}': {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key to delete

        Returns:
            True if deleted
        """
        deleted = False

        # Delete from Redis
        if self.redis_available and self.redis_client:
            try:
                self.redis_client.delete(key)
                deleted = True
            except Exception as e:
                logger.debug(f"Redis delete error for key '{key}': {e}")

        # Delete from memory
        if key in self.memory_cache:
            del self.memory_cache[key]
            deleted = True

        return deleted

    def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries

        Args:
            pattern: Optional pattern to match keys (e.g., 'screener_*')
                    If None, clears all memory cache

        Returns:
            Number of keys deleted
        """
        count = 0

        # Clear Redis by pattern
        if pattern and self.redis_available and self.redis_client:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    count += self.redis_client.delete(*keys)
            except Exception as e:
                logger.debug(f"Redis clear error for pattern '{pattern}': {e}")

        # Clear memory cache
        if pattern:
            # Match pattern in memory cache
            keys_to_delete = [k for k in self.memory_cache.keys() if self._match_pattern(k, pattern)]
            for key in keys_to_delete:
                del self.memory_cache[key]
                count += 1
        else:
            # Clear all
            count += len(self.memory_cache)
            self.memory_cache.clear()

        return count

    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching (supports * wildcard)"""
        if '*' not in pattern:
            return key == pattern

        # Convert pattern to regex-like matching
        pattern_parts = pattern.split('*')
        if len(pattern_parts) == 2:
            prefix, suffix = pattern_parts
            return key.startswith(prefix) and key.endswith(suffix)

        return False

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dictionary with cache stats
        """
        stats = {
            'redis_available': self.redis_available,
            'memory_cache_size': len(self.memory_cache)
        }

        if self.redis_available and self.redis_client:
            try:
                info = self.redis_client.info('stats')
                stats['redis_keys'] = self.redis_client.dbsize()
                stats['redis_hits'] = info.get('keyspace_hits', 0)
                stats['redis_misses'] = info.get('keyspace_misses', 0)

                total = stats['redis_hits'] + stats['redis_misses']
                if total > 0:
                    stats['redis_hit_rate'] = f"{(stats['redis_hits'] / total) * 100:.1f}%"
            except Exception as e:
                logger.debug(f"Redis stats error: {e}")

        return stats

    def cleanup_expired(self) -> int:
        """
        Cleanup expired entries from memory cache

        Returns:
            Number of entries removed
        """
        now = datetime.now()
        expired_keys = [
            k for k, v in self.memory_cache.items()
            if v.get('expires_at') and now >= v['expires_at']
        ]

        for key in expired_keys:
            del self.memory_cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)


# Singleton instance
_cache_manager = None


def get_cache_manager() -> CacheManager:
    """Get singleton cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


# Convenience instance
cache = get_cache_manager()
