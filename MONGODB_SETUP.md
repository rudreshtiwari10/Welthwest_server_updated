# MongoDB Setup for Authentication

This guide explains how to set up MongoDB for the authentication system in this project.

## Local Development Setup

1. **Install MongoDB Community Edition**

   Follow the official installation guide for your operating system:
   - [Windows](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-windows/)
   - [macOS](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-os-x/)
   - [Linux](https://www.mongodb.com/docs/manual/administration/install-on-linux/)

2. **Start MongoDB Service**

   - On Windows, MongoDB is installed as a service and should start automatically
   - On macOS with Homebrew: `brew services start mongodb-community`
   - On Linux: `sudo systemctl start mongod`

3. **Verify MongoDB is Running**

   ```
   mongo
   ```

   Or for newer MongoDB versions:

   ```
   mongosh
   ```

4. **Configure Environment Variables**

   Create a `.env` file in the project root with:

   ```
   MONGODB_URI=mongodb://localhost:27017
   JWT_SECRET_KEY=your-secret-key-here
   ```

## MongoDB Atlas Setup (Production)

For production, it's recommended to use MongoDB Atlas, a cloud-hosted MongoDB service:

1. **Create a MongoDB Atlas Account**

   Sign up at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register)

2. **Create a New Cluster**

   - Click "Build a Cluster"
   - Choose the free tier option
   - Select a cloud provider and region
   - Click "Create Cluster"

3. **Configure Database Access**

   - Go to "Database Access" under Security
   - Click "Add New Database User"
   - Create a username and password
   - Set appropriate privileges (read/write)

4. **Configure Network Access**

   - Go to "Network Access" under Security
   - Click "Add IP Address"
   - Add your application server IP or use "0.0.0.0/0" for development (not recommended for production)

5. **Get Connection String**

   - Click "Connect" on your cluster
   - Select "Connect your application"
   - Copy the connection string
   - Replace `<password>` with your database user's password

6. **Update Environment Variables**

   Update your `.env` file or environment variables with:

   ```
   MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
   JWT_SECRET_KEY=your-secure-secret-key
   ```

## Database Structure

The authentication system uses the following collections:

1. **users**
   - `_id`: ObjectId (automatically generated)
   - `username`: String (unique)
   - `email`: String (unique)
   - `password`: String (hashed)
   - `first_name`: String
   - `last_name`: String
   - `avatar_url`: String
   - `created_at`: Date
   - `updated_at`: Date
   - `watchlists`: Array

2. **refresh_tokens**
   - `user_id`: String
   - `token`: String
   - `created_at`: Date
   - `expires_at`: Date

## Testing the Database Connection

After setting up MongoDB, you can test the connection by running:

```
python test_auth.py
```

This will attempt to register a test user, login, and perform other authentication operations to verify the database connection is working correctly. 