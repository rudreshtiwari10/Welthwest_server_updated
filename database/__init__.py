"""
Database module for MongoDB connection
"""

import os
from pymongo import MongoClient
from config import Config

# Initialize configuration
config = Config()

# Create MongoDB client
client = MongoClient(config.MONGODB_URI)

# Get database
db = client[config.DB_NAME]

__all__ = ['db', 'client']
