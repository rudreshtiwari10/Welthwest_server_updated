# WelthWest Server Setup Instructions

## Issues Fixed

✅ **Updated Python Dependencies**: Updated all packages to compatible versions for Python 3.11
✅ **Created Environment Configuration**: Created `.env` file with all required variables
✅ **Fixed Configuration Validation**: Modified config to handle missing optional variables gracefully
✅ **Created Test Server**: Built `app_test.py` for testing without external dependencies

## Current Status

### ✅ Working (Test Mode)
- **Test Server**: `app_test.py` runs successfully on http://localhost:8000
- **Basic Flask App**: All core Flask functionality working
- **JWT Authentication**: Token generation and validation working
- **CORS**: Cross-origin requests configured
- **Mock Services**: In-memory user and subscription services

### ❌ Requires Setup (Full Production Mode)
- **MongoDB**: Database connection needed for full app.py
- **Redis**: Caching service (optional, falls back to in-memory)
- **Upstox API**: Trading platform integration (optional)
- **AI Services**: OpenAI/Claude/OpenRouter API keys (optional)

## Quick Start (Test Mode)

```bash
# 1. Navigate to project directory
cd "C:\\Users\\Kunal Kumar\\Desktop\\Human bot collection\\Human bot 20 Deplyment with AI model correct one\\WelthWestServer2"

# 2. Run test server
python app_test.py
```

The server will start on http://localhost:8000 with these endpoints:
- `GET /` - Health check
- `GET /health` - Health check  
- `POST /api/auth/test-login` - Test authentication
- `GET /api/test/data` - Test data endpoint

## Full Setup (Production Mode)

### 1. Install MongoDB

**Option A: MongoDB Community Server (Local)**
1. Download from https://www.mongodb.com/try/download/community
2. Install and start MongoDB service
3. MongoDB will run on default port 27017

**Option B: MongoDB Atlas (Cloud)**
1. Create account at https://cloud.mongodb.com
2. Create a cluster and get connection string
3. Update `MONGODB_URI` in `.env` file

### 2. Install Redis (Optional)

**Windows:**
1. Download Redis from https://github.com/microsoftarchive/redis/releases
2. Install and start Redis service
3. Redis will run on default port 6379

### 3. Configure Environment Variables

Edit the `.env` file and update these values:

```env
# Required for full functionality
MONGODB_URI=mongodb://localhost:27017/  # or your Atlas connection string
JWT_SECRET_KEY=your-secure-secret-key-here

# Optional: Trading features (Upstox)
UPSTOX_API_KEY=your-upstox-api-key
UPSTOX_API_SECRET=your-upstox-api-secret

# Optional: AI Chat features
OPENAI_API_KEY=your-openai-api-key
CLAUDE_API_KEY=your-claude-api-key
OPENROUTER_API_KEY=your-openrouter-api-key
```

### 4. Run Full Server

```bash
python app.py
```

## Dependencies Installed

All required Python packages have been updated and installed:

- Flask 2.3.3 (web framework)
- Flask-CORS 4.0.0 (cross-origin requests)
- Flask-JWT-Extended 4.5.3 (authentication)
- pymongo 4.5.0 (MongoDB driver)
- pandas 2.1.3 (data analysis)
- numpy 1.25.2 (numerical computing)
- yfinance 0.2.22 (financial data)
- scikit-learn 1.3.2 (machine learning)
- And many more...

## Troubleshooting

### MongoDB Connection Issues
- Ensure MongoDB is running: `mongod --version`
- Check connection string in `.env`
- For local MongoDB: `mongodb://localhost:27017/`

### Port Already in Use
```bash
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

### Import Errors
- Ensure you're in the correct directory
- Verify all dependencies installed: `pip list`
- Check Python version: `python --version` (should be 3.11.0)

## Development vs Production

**Test Mode (app_test.py):**
- No external dependencies
- Mock services for users/subscriptions
- Basic endpoints for testing
- Good for development and testing

**Production Mode (app.py):**
- Full feature set
- Real database connections
- All trading and AI features
- Requires proper configuration

## Next Steps

1. **For Development**: Use `app_test.py` to test API endpoints and develop frontend
2. **For Production**: Set up MongoDB and other services, then use `app.py`
3. **API Documentation**: Check existing README files for API endpoint details
4. **Frontend Integration**: Update frontend to connect to http://localhost:8000

## Support

If you encounter issues:
1. Check this setup guide first
2. Verify all dependencies are installed
3. Check log output for specific error messages
4. Ensure ports 8000 and 27017 (MongoDB) are available