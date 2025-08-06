from google.oauth2 import id_token
from google.auth.transport import requests
from flask import current_app
from services.user_service import UserService
import os

class GoogleAuthService:
    def __init__(self):
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        self.user_service = UserService()

    def verify_google_token(self, token):
        try:
            # Verify the token
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                self.client_id
            )

            # Get user info from the token
            user_data = {
                'email': idinfo['email'],
                'name': idinfo.get('name', ''),
                'picture': idinfo.get('picture', ''),
                'google_id': idinfo['sub']
            }

            # Check if user exists
            existing_user = self.user_service.get_user_by_email(user_data['email'])
            
            if existing_user:
                # Update existing user with Google info if needed
                if not existing_user.get('google_id'):
                    self.user_service.update_user(
                        existing_user['_id'],
                        {
                            'google_id': user_data['google_id'],
                            'profile_picture': user_data['picture'],
                            'is_google_user': True
                        }
                    )
                return existing_user
            
            # Create new user
            new_user = {
                'email': user_data['email'],
                'name': user_data['name'],
                'google_id': user_data['google_id'],
                'profile_picture': user_data['picture'],
                'is_google_user': True
            }
            
            created_user = self.user_service.create_user(new_user)
            return created_user

        except ValueError as e:
            # Invalid token
            current_app.logger.error(f"Invalid token: {str(e)}")
            return None
        except Exception as e:
            current_app.logger.error(f"Error verifying Google token: {str(e)}")
            return None

    def get_user_by_google_id(self, google_id):
        try:
            return self.user_service.get_user_by_google_id(google_id)
        except Exception as e:
            current_app.logger.error(f"Error getting user by Google ID: {str(e)}")
            return None