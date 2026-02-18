"""
Database module for MongoDB connection - Lazy-loaded for faster startup
"""

import os
from pymongo import MongoClient
from config import Config

_client = None
_db = None


def get_db():
    """Get database connection, creating it lazily on first use"""
    global _client, _db
    if _db is None:
        config = Config()
        _client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=5000)
        _db = _client[config.DB_NAME]
    return _db


def get_client():
    """Get MongoDB client, creating it lazily on first use"""
    global _client
    if _client is None:
        get_db()
    return _client


class _LazyDB:
    """Proxy object that lazily initializes MongoDB connection on first attribute access"""
    def __getattr__(self, name):
        return getattr(get_db(), name)

    def __getitem__(self, name):
        return get_db()[name]

    def __repr__(self):
        return f"<LazyDB proxy -> {get_db().name}>"


class _LazyClient:
    """Proxy object that lazily initializes MongoDB client on first attribute access"""
    def __getattr__(self, name):
        return getattr(get_client(), name)

    def __getitem__(self, name):
        return get_client()[name]


# These proxies maintain backward compatibility - code using `from database import db, client`
# will work transparently, but the actual connection is deferred until first use
db = _LazyDB()
client = _LazyClient()

__all__ = ['db', 'client', 'get_db', 'get_client']
