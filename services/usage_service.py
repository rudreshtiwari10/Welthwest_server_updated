"""
Anonymous Usage Service - Redis-based usage tracking for anonymous users with in-memory fallback
Handles per-feature usage counting with TTL expiration
"""
import redis
from typing import Optional, Dict
from config import get_config
from datetime import datetime, timedelta
import threading

# Initialize Redis client
config = get_config()
redis_client = None

# In-memory fallback storage
in_memory_storage: Dict[str, Dict] = {}
storage_lock = threading.Lock()

try:
    redis_client = redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=config.REDIS_DB,
        password=config.REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=5
    )
    # Test connection
    redis_client.ping()
    print(f"✓ Redis connection established at {config.REDIS_HOST}:{config.REDIS_PORT}")
except Exception as e:
    print(f"⚠ Redis connection failed: {e}. Using in-memory storage as fallback.")
    redis_client = None


def incr_feature_usage(session_id: str, feature: str) -> int:
    """
    Atomically increment usage count for a feature and return new count.
    Also refreshes TTL on the key.

    Args:
        session_id: Anonymous session identifier
        feature: Feature name (e.g., 'welth-ai-assistant', 'backtest-beta')

    Returns:
        New usage count for this feature
    """
    cfg = get_config()

    if redis_client:
        # Use Redis if available
        key = f"anon:{session_id}:usage:{feature}"

        # Atomically increment
        new_count = redis_client.incr(key)

        # Refresh TTL
        redis_client.expire(key, cfg.ANON_SESSION_TTL_SECONDS)

        return int(new_count)
    else:
        # Use in-memory fallback
        with storage_lock:
            key = f"{session_id}:{feature}"

            # Clean expired entries
            _cleanup_expired_entries()

            if key not in in_memory_storage:
                in_memory_storage[key] = {
                    'count': 0,
                    'expires_at': datetime.now() + timedelta(seconds=cfg.ANON_SESSION_TTL_SECONDS)
                }

            # Increment count
            in_memory_storage[key]['count'] += 1
            # Refresh TTL
            in_memory_storage[key]['expires_at'] = datetime.now() + timedelta(seconds=cfg.ANON_SESSION_TTL_SECONDS)

            return in_memory_storage[key]['count']


def get_feature_usage(session_id: str, feature: str) -> int:
    """
    Get current usage count for a specific feature.

    Args:
        session_id: Anonymous session identifier
        feature: Feature name

    Returns:
        Current usage count (0 if not found)
    """
    if redis_client:
        # Use Redis if available
        key = f"anon:{session_id}:usage:{feature}"
        val = redis_client.get(key)
        return int(val) if val else 0
    else:
        # Use in-memory fallback
        with storage_lock:
            key = f"{session_id}:{feature}"
            _cleanup_expired_entries()

            if key in in_memory_storage:
                return in_memory_storage[key]['count']
            return 0


def get_all_feature_usage(session_id: str) -> dict:
    """
    Get usage counts for all features for a session.

    Args:
        session_id: Anonymous session identifier

    Returns:
        Dictionary mapping feature names to usage counts
    """
    if redis_client:
        # Use Redis if available
        pattern = f"anon:{session_id}:usage:*"
        keys = redis_client.keys(pattern)

        usage = {}
        for key in keys:
            # Extract feature name from key
            feature = key.split(':')[-1]
            val = redis_client.get(key)
            usage[feature] = int(val) if val else 0

        return usage
    else:
        # Use in-memory fallback
        with storage_lock:
            _cleanup_expired_entries()

            usage = {}
            for key, data in in_memory_storage.items():
                if key.startswith(f"{session_id}:"):
                    feature = key.split(':', 1)[1]
                    usage[feature] = data['count']

            return usage


def reset_feature_usage(session_id: str, feature: str) -> bool:
    """
    Reset usage count for a specific feature (admin/testing purpose).

    Args:
        session_id: Anonymous session identifier
        feature: Feature name

    Returns:
        True if reset successful
    """
    if redis_client:
        # Use Redis if available
        key = f"anon:{session_id}:usage:{feature}"
        redis_client.delete(key)
        return True
    else:
        # Use in-memory fallback
        with storage_lock:
            key = f"{session_id}:{feature}"
            if key in in_memory_storage:
                del in_memory_storage[key]
        return True


def delete_session(session_id: str) -> bool:
    """
    Delete all usage data for a session (admin/testing purpose).

    Args:
        session_id: Anonymous session identifier

    Returns:
        True if deletion successful
    """
    if redis_client:
        # Use Redis if available
        pattern = f"anon:{session_id}:usage:*"
        keys = redis_client.keys(pattern)

        if keys:
            redis_client.delete(*keys)
        return True
    else:
        # Use in-memory fallback
        with storage_lock:
            keys_to_delete = [k for k in in_memory_storage.keys() if k.startswith(f"{session_id}:")]
            for key in keys_to_delete:
                del in_memory_storage[key]
        return True


def is_redis_available() -> bool:
    """Check if Redis connection is available"""
    if not redis_client:
        return False

    try:
        redis_client.ping()
        return True
    except:
        return False


def _cleanup_expired_entries():
    """Remove expired entries from in-memory storage (internal helper)"""
    now = datetime.now()
    expired_keys = [k for k, v in in_memory_storage.items() if v['expires_at'] < now]
    for key in expired_keys:
        del in_memory_storage[key]