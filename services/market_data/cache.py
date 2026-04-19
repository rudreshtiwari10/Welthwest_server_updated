"""
Redis-backed caching layer for MarketDataProvider.

Wraps any MarketDataProvider with TTL caching. Gracefully degrades to a
no-op when Redis is unavailable (local dev without Redis works unchanged).

Design:
    CachedMarketDataProvider implements the same MarketDataProvider interface
    so it is a drop-in replacement. Call sites never know they're talking
    to a cache.

TTLs:
    quote           30 sec   (live prices)
    history         1 hour   (OHLCV bars)
    fundamentals    24 hours (P/E, ROE, etc.)
    symbol search   7 days   (symbol→ticker mappings rarely change)
    index quote     30 sec
    corp actions    24 hours

Key format:
    welth:md:{provider}:{method}:{args_hash}
"""

import hashlib
import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Optional

from services.market_data.base import (
    Candle,
    Fundamentals,
    MarketDataProvider,
    Quote,
    SymbolMatch,
)

logger = logging.getLogger(__name__)


# ---- TTLs (seconds) --------------------------------------------------------

TTL_QUOTE = 30
TTL_HISTORY = 60 * 60
TTL_FUNDAMENTALS = 60 * 60 * 24
TTL_SYMBOL_SEARCH = 60 * 60 * 24 * 7
TTL_INDEX_QUOTE = 30
TTL_CORP_ACTIONS = 60 * 60 * 24


# ---- Lazy Redis client (mirrors services/usage_service.py) -----------------

_redis_client = None
_redis_initialized = False


def _get_redis_client():
    """Lazily initialize Redis client on first use. Returns None if unavailable."""
    global _redis_client, _redis_initialized
    if not _redis_initialized:
        _redis_initialized = True
        try:
            import redis
            from config import get_config

            config = get_config()
            _redis_client = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=config.REDIS_DB,
                password=config.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            _redis_client.ping()
            logger.info(
                "market_data cache: Redis connection established at %s:%s",
                config.REDIS_HOST,
                config.REDIS_PORT,
            )
        except Exception as e:
            logger.info(
                "market_data cache: Redis unavailable (%s) — caching disabled",
                type(e).__name__,
            )
            _redis_client = None
    return _redis_client


# ---- Serialization helpers -------------------------------------------------


def _default_encoder(obj: Any):
    """JSON encoder for dataclasses + datetimes."""
    if is_dataclass(obj):
        return {"__dc__": obj.__class__.__name__, "data": asdict(obj)}
    if isinstance(obj, datetime):
        return {"__dt__": obj.isoformat()}
    raise TypeError(f"Not JSON serializable: {type(obj)!r}")


_DATACLASS_REGISTRY = {
    "Quote": Quote,
    "Candle": Candle,
    "SymbolMatch": SymbolMatch,
    "Fundamentals": Fundamentals,
}


def _object_hook(d: dict):
    """JSON decoder inverse of _default_encoder."""
    if "__dc__" in d:
        cls = _DATACLASS_REGISTRY.get(d["__dc__"])
        if cls is None:
            return d["data"]
        payload = d["data"]
        # Restore datetime fields stored as ISO strings.
        for k, v in list(payload.items()):
            if isinstance(v, dict) and "__dt__" in v:
                payload[k] = datetime.fromisoformat(v["__dt__"])
        return cls(**payload)
    if "__dt__" in d:
        return datetime.fromisoformat(d["__dt__"])
    return d


def _serialize(value: Any) -> str:
    return json.dumps(value, default=_default_encoder)


def _deserialize(raw: str) -> Any:
    return json.loads(raw, object_hook=_object_hook)


def _build_key(provider: str, method: str, args: tuple, kwargs: dict) -> str:
    """Stable cache key from method + args."""
    payload = json.dumps(
        {"args": list(args), "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]
    return f"welth:md:{provider}:{method}:{digest}"


# ---- CachedMarketDataProvider ----------------------------------------------


class CachedMarketDataProvider(MarketDataProvider):
    """
    Wraps another MarketDataProvider with Redis TTL caching.

    Usage:
        inner = YFinanceProvider()
        provider = CachedMarketDataProvider(inner)
        provider.get_quote("RELIANCE")   # cached for 30s
    """

    def __init__(self, inner: MarketDataProvider):
        self._inner = inner
        self.name = f"cached:{inner.name}"

    # ---- cache helpers ----

    def _cache_get(self, key: str):
        client = _get_redis_client()
        if client is None:
            return None
        try:
            raw = client.get(key)
            if raw is None:
                return None
            return _deserialize(raw)
        except Exception as e:
            logger.debug("cache get failed (%s): %s", key, e)
            return None

    def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        client = _get_redis_client()
        if client is None:
            return
        try:
            client.setex(key, ttl, _serialize(value))
        except Exception as e:
            logger.debug("cache set failed (%s): %s", key, e)

    def _cached_call(self, method_name: str, ttl: int, args: tuple, kwargs: dict):
        """Core cache-aside logic: check cache → fall through to inner → store."""
        key = _build_key(self._inner.name, method_name, args, kwargs)
        hit = self._cache_get(key)
        if hit is not None:
            return hit

        result = getattr(self._inner, method_name)(*args, **kwargs)
        # Only cache truthy results — don't pin empty lists that hide
        # transient upstream failures.
        if result:
            self._cache_set(key, result, ttl)
        return result

    # ---- MarketDataProvider interface ----

    def get_quote(self, symbol: str) -> Quote:
        return self._cached_call("get_quote", TTL_QUOTE, (symbol,), {})

    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> list[Candle]:
        return self._cached_call(
            "get_history",
            TTL_HISTORY,
            (symbol,),
            {"period": period, "interval": interval},
        )

    def search_symbols(self, query: str, limit: int = 5) -> list[SymbolMatch]:
        return self._cached_call(
            "search_symbols",
            TTL_SYMBOL_SEARCH,
            (query,),
            {"limit": limit},
        )

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        return self._cached_call(
            "get_fundamentals", TTL_FUNDAMENTALS, (symbol,), {}
        )

    def get_index_quote(self, index: str) -> Quote:
        return self._cached_call(
            "get_index_quote", TTL_INDEX_QUOTE, (index,), {}
        )

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        return self._cached_call(
            "get_corporate_actions", TTL_CORP_ACTIONS, (symbol,), {}
        )

    def health_check(self) -> bool:
        return self._inner.health_check()
