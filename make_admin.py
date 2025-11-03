"""
Script to make a user admin
Usage: python make_admin.py test1112@email.com
"""
import sys
from pymongo import MongoClient
from config import get_config

def make_admin(email):
    """Make a user admin by email"""
    config = get_config()

    # Connect to MongoDB
    client = MongoClient(config.MONGODB_URI)
    db = client[config.DB_NAME]
    users = db.users

    # Find user
    user = users.find_one({"email": email})

    if not user:
        print(f"❌ User with email '{email}' not found!")
        return False

    # Update to admin
    result = users.update_one(
        {"email": email},
        {"$set": {"role": "admin"}}
    )

    if result.modified_count > 0:
        print(f"✅ User '{email}' is now an admin!")
        print(f"   User ID: {user['_id']}")
        print(f"   Username: {user.get('username', 'N/A')}")
        return True
    else:
        # Check if already admin
        if user.get('role') == 'admin':
            print(f"ℹ️  User '{email}' is already an admin!")
            print(f"   User ID: {user['_id']}")
            return True
        else:
            print(f"❌ Failed to update user to admin")
            return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        email = "test1113@email.com"  # Default email
    else:
        email = sys.argv[1]

    print(f"Making user '{email}' an admin...")
    make_admin(email)
