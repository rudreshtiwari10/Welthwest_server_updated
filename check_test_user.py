from pymongo import MongoClient
from config import get_config
import os
import sys

# Change directory if needed, but we should run it from the server directory
config = get_config()
client = MongoClient(config.MONGODB_URI)
db = client.get_database(config.DB_NAME)
users = db.users

for email in ['#Test@email.com', 'Test@email.com', 'test@email.com']:
    user = users.find_one({'email': email})
    if user:
        print(f"User found for email {email}:")
        print(f"  ID: {user['_id']}")
        print(f"  Email: {user['email']}")
        print(f"  Password Hash: {user.get('password')}")
        
    else:
        print(f"User NOT found for email {email}")
