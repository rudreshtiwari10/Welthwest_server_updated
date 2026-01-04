#!/usr/bin/env python3
"""
Admin User Creation Script
Creates or promotes users to admin role for WelthWest platform

Usage:
    python create_admin.py <email>

Example:
    python create_admin.py admin@welthwest.com
"""

import sys
from pymongo import MongoClient
from config import get_config
from datetime import datetime

def create_admin(email):
    """Promote a user to admin role"""
    try:
        # Get config
        config = get_config()

        # Connect to MongoDB
        client = MongoClient(config.MONGODB_URI)
        db = client[config.DB_NAME]

        print(f"Connecting to database: {config.DB_NAME}")

        # Find user by email
        user = db.users.find_one({'email': email})

        if not user:
            print(f"❌ Error: User with email '{email}' not found.")
            print("\nPlease make sure the user has registered on the platform first.")
            return False

        # Check if already admin
        current_role = user.get('role', 'user')
        if current_role == 'admin':
            print(f"✅ User '{email}' is already an admin.")
            return True

        # Update user role to admin
        result = db.users.update_one(
            {'email': email},
            {
                '$set': {
                    'role': 'admin',
                    'updated_at': datetime.utcnow()
                }
            }
        )

        if result.modified_count > 0:
            print(f"\n✅ SUCCESS! User '{email}' has been promoted to admin.")
            print(f"\nUser Details:")
            print(f"  - Email: {user.get('email')}")
            print(f"  - Name: {user.get('first_name', '')} {user.get('last_name', '')}")
            print(f"  - Username: {user.get('username')}")
            print(f"  - Previous Role: {current_role}")
            print(f"  - New Role: admin")
            print(f"\nThe user can now access the Admin Dashboard at /admin")
            return True
        else:
            print(f"❌ Error: Failed to update user role.")
            return False

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False
    finally:
        if 'client' in locals():
            client.close()


def list_admins():
    """List all admin users"""
    try:
        # Get config
        config = get_config()

        # Connect to MongoDB
        client = MongoClient(config.MONGODB_URI)
        db = client[config.DB_NAME]

        # Find all admins
        admins = list(db.users.find({'role': 'admin'}, {
            'email': 1,
            'username': 1,
            'first_name': 1,
            'last_name': 1,
            'created_at': 1
        }))

        if not admins:
            print("No admin users found.")
            return

        print(f"\n📋 Admin Users ({len(admins)}):")
        print("-" * 80)
        for admin in admins:
            name = f"{admin.get('first_name', '')} {admin.get('last_name', '')}".strip()
            print(f"  • {admin.get('email'):<35} | {name or admin.get('username', 'N/A'):<25}")
        print("-" * 80)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        if 'client' in locals():
            client.close()


def revoke_admin(email):
    """Revoke admin role from a user"""
    try:
        # Get config
        config = get_config()

        # Connect to MongoDB
        client = MongoClient(config.MONGODB_URI)
        db = client[config.DB_NAME]

        # Find user
        user = db.users.find_one({'email': email})

        if not user:
            print(f"❌ Error: User with email '{email}' not found.")
            return False

        if user.get('role') != 'admin':
            print(f"⚠️  User '{email}' is not an admin.")
            return False

        # Update role back to user
        result = db.users.update_one(
            {'email': email},
            {
                '$set': {
                    'role': 'user',
                    'updated_at': datetime.utcnow()
                }
            }
        )

        if result.modified_count > 0:
            print(f"✅ Admin privileges revoked from '{email}'")
            return True
        else:
            print(f"❌ Error: Failed to revoke admin role.")
            return False

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False
    finally:
        if 'client' in locals():
            client.close()


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("WelthWest Admin User Management")
        print("=" * 80)
        print("\nUsage:")
        print("  Create admin:        python create_admin.py <email>")
        print("  List admins:         python create_admin.py --list")
        print("  Revoke admin:        python create_admin.py --revoke <email>")
        print("\nExamples:")
        print("  python create_admin.py admin@welthwest.com")
        print("  python create_admin.py --list")
        print("  python create_admin.py --revoke user@example.com")
        print("=" * 80)
        sys.exit(1)

    command = sys.argv[1]

    if command == '--list':
        list_admins()
    elif command == '--revoke':
        if len(sys.argv) < 3:
            print("❌ Error: Please provide an email address.")
            print("Usage: python create_admin.py --revoke <email>")
            sys.exit(1)
        email = sys.argv[2]
        revoke_admin(email)
    elif command.startswith('--'):
        print(f"❌ Error: Unknown command '{command}'")
        print("Use 'python create_admin.py' to see available commands.")
        sys.exit(1)
    else:
        # Assume it's an email address
        email = command
        create_admin(email)


if __name__ == '__main__':
    main()
