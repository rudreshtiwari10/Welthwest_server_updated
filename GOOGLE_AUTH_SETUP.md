# Google Authentication Setup Guide

This guide explains how to set up Google Authentication for the WelthWest application.

## 1. Create Google OAuth Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth client ID"
5. Select "Web application" as the application type
6. Add a name for your OAuth client
7. Add authorized JavaScript origins:
   - For development: `http://localhost:3000`
   - For production: `https://your-domain.com`
8. Add authorized redirect URIs:
   - For development: `http://localhost:3000`
   - For production: `https://your-domain.com`
9. Click "Create" and note your Client ID and Client Secret

## 2. Configure Environment Variables

Add the following to your `.env` file in the WelthWestServer2 directory:

```
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id-goes-here
GOOGLE_CLIENT_SECRET=your-google-client-secret-goes-here
```

Replace the placeholder values with your actual Google OAuth credentials.

## 3. Testing Google Authentication Backend

1. Make sure you have set up the environment variables correctly
2. Run the test script:
   ```
   python test_google_auth.py
   ```
3. You will be prompted to enter a Google ID token
4. To get a token, open `test_google_auth.html` in a browser
5. Replace `YOUR_GOOGLE_CLIENT_ID` in the HTML file with your actual client ID
6. Click "Sign in with Google" and complete the authentication
7. Copy the displayed token
8. Paste the token into the test script prompt
9. The script should verify the token and display the user information

## 4. Testing the Complete Flow

1. Start your backend server:
   ```
   python run.py
   ```

2. Open `test_google_auth.html` in a browser
3. Sign in with Google
4. Click "Test Backend API" to test the backend endpoint
5. You should see a successful response with user information and JWT tokens

## 5. Integration with Frontend

1. Make sure the frontend environment variables are set correctly:
   ```
   REACT_APP_GOOGLE_CLIENT_ID=your-google-client-id-goes-here
   ```

2. Start your frontend development server:
   ```
   cd ../WelthWestClientSharing
   npm start
   ```

3. Navigate to the login page and click the "Continue with Google" button
4. Select your Google account
5. You should be automatically logged in and redirected to the dashboard

## Troubleshooting

- If you see "Error 400: redirect_uri_mismatch", make sure the redirect URI in your Google Cloud Console matches the URI of your application.
- If you see "Invalid Client ID", double-check that you've correctly set the GOOGLE_CLIENT_ID in your .env file.
- If you see "Invalid token", ensure that your GOOGLE_CLIENT_ID in the backend .env file matches the Client ID from Google Cloud Console.
- If the backend API call fails, check the server logs for more detailed error information.

## Security Considerations

- Always validate tokens on the server side
- Never trust client-side validation alone
- Use HTTPS in production to protect tokens in transit
- Store tokens securely and never expose them in client-side code
- Set appropriate expiration times for tokens
- Implement proper token revocation when users log out