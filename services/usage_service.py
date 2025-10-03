"""
Anonymous Usage Service - Redis-based usage tracking for anonymous users
Handles per-feature usage counting with TTL expiration
"""
import redis
from typing import Optional
from config import get_config

# Initialize Redis client
config = get_config()

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
    print(f"⚠ Redis connection failed: {e}")
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
    if not redis_client:
        raise Exception("Redis is not available")

    key = f"anon:{session_id}:usage:{feature}"
    config = get_config()

    # Atomically increment
    new_count = redis_client.incr(key)

    # Refresh TTL
    redis_client.expire(key, config.ANON_SESSION_TTL_SECONDS)

    return int(new_count)


def get_feature_usage(session_id: str, feature: str) -> int:
    """
    Get current usage count for a specific feature.

    Args:
        session_id: Anonymous session identifier
        feature: Feature name

    Returns:
        Current usage count (0 if not found)
    """
    if not redis_client:
        return 0

    key = f"anon:{session_id}:usage:{feature}"
    val = redis_client.get(key)

    return int(val) if val else 0


def get_all_feature_usage(session_id: str) -> dict:
    """
    Get usage counts for all features for a session.

    Args:
        session_id: Anonymous session identifier

    Returns:
        Dictionary mapping feature names to usage counts
    """
    if not redis_client:
        return {}

    pattern = f"anon:{session_id}:usage:*"
    keys = redis_client.keys(pattern)

    usage = {}
    for key in keys:
        # Extract feature name from key
        feature = key.split(':')[-1]
        val = redis_client.get(key)
        usage[feature] = int(val) if val else 0

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
    if not redis_client:
        return False

    key = f"anon:{session_id}:usage:{feature}"
    redis_client.delete(key)

    return True


def delete_session(session_id: str) -> bool:
    """
    Delete all usage data for a session (admin/testing purpose).

    Args:
        session_id: Anonymous session identifier

    Returns:
        True if deletion successful
    """
    if not redis_client:
        return False

    pattern = f"anon:{session_id}:usage:*"
    keys = redis_client.keys(pattern)

    if keys:
        redis_client.delete(*keys)

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