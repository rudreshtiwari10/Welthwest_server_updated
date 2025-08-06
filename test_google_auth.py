import os
import sys
import json
from dotenv import load_dotenv
from services.google_auth_service import GoogleAuthService

# Load environment variables
load_dotenv()

def test_google_auth():
    """Test Google authentication service with a valid token"""
    print("Google Authentication Test")
    print("=========================")
    
    # Check if Google Client ID is set
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    if not client_id:
        print("Error: GOOGLE_CLIENT_ID not set in environment variables")
        return False
    
    # Get token from command line argument or prompt
    token = None
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        token = input("Enter Google ID token: ")
    
    if not token:
        print("Error: No token provided")
        return False
    
    # Initialize Google Auth Service
    google_auth_service = GoogleAuthService()
    
    # Verify token
    print("Verifying token...")
    user = google_auth_service.verify_google_token(token)
    
    if user:
        print("Token verified successfully!")
        print("User details:")
        print(json.dumps(user, indent=2))
        return True
    else:
        print("Failed to verify token")
        return False

if __name__ == "__main__":
    success = test_google_auth()
    if success:
        print("Test completed successfully")
    else:
        print("Test failed")