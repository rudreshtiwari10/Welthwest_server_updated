#!/usr/bin/env python3
"""Test MongoDB connection to diagnose connection issues"""

import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGODB_URI = os.getenv('MONGODB_URI')

print("Testing MongoDB connection...")
print(f"URI: {MONGODB_URI[:30]}...{MONGODB_URI[-30:]}")  # Hide sensitive parts

try:
    # Set a shorter timeout for testing
    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=10000  # 10 seconds timeout
    )

    # Trigger actual connection
    client.admin.command('ping')

    print("✓ Successfully connected to MongoDB!")

    # List databases
    dbs = client.list_database_names()
    print(f"✓ Available databases: {dbs}")

    # Check specific database
    db_name = os.getenv('DB_NAME', 'welthwest')
    db = client[db_name]
    collections = db.list_collection_names()
    print(f"✓ Collections in '{db_name}': {collections}")

    client.close()
    print("\n✓ Connection test passed!")

except Exception as e:
    print(f"\n✗ Connection failed!")
    print(f"Error: {type(e).__name__}: {str(e)}")
    print("\nPossible causes:")
    print("1. IP address not whitelisted in MongoDB Atlas")
    print("2. Incorrect credentials in MONGODB_URI")
    print("3. Network/firewall blocking connection")
    print("4. MongoDB Atlas cluster is paused or unavailable")
    print("\nRecommended actions:")
    print("- Go to MongoDB Atlas > Network Access")
    print("- Add your current IP address or use 0.0.0.0/0 for testing")
    print("- Wait 1-2 minutes for changes to take effect")
