from pymongo import MongoClient
from config import get_config

config = get_config()
client = MongoClient(config.MONGODB_URI)
db = client.get_database(config.DB_NAME)
users = db.users

# Update user with email 'test@example.com' to admin
result = users.update_one(
    {'email': 'admin@essxample.com'},
    {'$set': {'role': 'admin'}}
)
print(f'Updated {result.modified_count} user(s) to admin role')

# Verify the update
admin_user = users.find_one({'role': 'admin'})
if admin_user:
    print(f'Admin user ID: {admin_user["_id"]}')
    print(f'Admin email: {admin_user["email"]}')
    print(f'Admin username: {admin_user["username"]}')
else:
    print('No admin user found')