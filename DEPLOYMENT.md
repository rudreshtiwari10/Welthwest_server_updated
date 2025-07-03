# Deployment Guide

## Deploying on Render

### Backend Deployment

1. Sign in to your Render account and create a new Web Service
2. Connect your GitHub repository
3. Configure the service with the following settings:
   - **Name**: stock-market-api
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`

4. Add the following environment variables:
   - `PYTHONUNBUFFERED`: true
   - `FRONTEND_URL`: Set to your frontend URL or `*` to allow all origins

### Frontend Deployment

1. Create a new Web Service for the frontend
2. Configure the service with the following settings:
   - **Name**: welthwest-frontend
   - **Environment**: Node
   - **Build Command**: `npm install && npm run build`
   - **Start Command**: `npm start`

3. Add the following environment variables:
   - `REACT_APP_API_URL`: https://stock-market-api.onrender.com/api

## Environment Variables

### Backend Environment Variables

- `PORT`: Automatically provided by Render, used by gunicorn to bind the application
- `FRONTEND_URL`: URL of your frontend application for CORS configuration
  - Set to `*` to allow all origins
  - Set to specific URL like `https://welthwest-frontend.onrender.com` to restrict access

### Frontend Environment Variables

- `REACT_APP_API_URL`: URL of your backend API
  - Example: `https://stock-market-api.onrender.com/api`

## Troubleshooting

### CORS Issues

If you're experiencing CORS issues:

1. Verify that the `FRONTEND_URL` environment variable is correctly set in the backend service
2. Check that the frontend is using the correct API URL
3. Test the API connection using the test-api.html file in the frontend/public directory

### Port Issues

Render automatically assigns a port to your application through the `PORT` environment variable. Make sure:

1. Your application reads the port from the environment: `port = int(os.environ.get("PORT", 5000))`
2. You're not hardcoding port values in your application
3. The gunicorn configuration uses the `PORT` environment variable

## Testing the Deployment

1. Visit the backend URL to check if the API is running: `https://stock-market-api.onrender.com/`
2. Use the test page to verify the connection: `https://welthwest-frontend.onrender.com/test-api.html` 