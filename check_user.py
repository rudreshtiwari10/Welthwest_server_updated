from pymongo import MongoClient
from config import get_config

config = get_config()
client = MongoClient(config.MONGODB_URI)
db = client.get_database(config.DB_NAME)
users = db.users

# Check if user with email 'admin@essxample.com' exists
user = users.find_one({'email': 'admin@essxample.com'})
if user:
    print(f'User found:')
    print(f'User ID: {user["_id"]}')
    print(f'Email: {user["email"]}')
    print(f'Username: {user["username"]}')
    print(f'Role: {user.get("role", "regular")}')
else:
    print('User with email admin@essxample.com not found')
    print('You need to register this user first')

# Show all admin users
print('\nAll admin users:')
admin_users = users.find({'role': 'admin'})
for admin in admin_users:
    print(f'- {admin["email"]} ({admin["username"]})')