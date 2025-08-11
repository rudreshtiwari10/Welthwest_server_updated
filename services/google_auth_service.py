from google.oauth2 import id_token
from google.auth.transport import requests
from flask import current_app
from services.user_service import UserService
import os
import time

class GoogleAuthService:
    def __init__(self):
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        self.user_service = UserService()
        # Allow configurable clock skew (in seconds) to tolerate minor time drift
        try:
            self.clock_skew = int(os.getenv('GOOGLE_CLOCK_SKEW', '60'))
        except ValueError:
            self.clock_skew = 60

    def verify_google_token(self, token):
        try:
            # Verify the token with tolerance for minor clock skew if supported
            verify_kwargs = {}
            try:
                # google-auth >= 2.16 supports clock_skew_in_seconds
                verify_kwargs['clock_skew_in_seconds'] = self.clock_skew
            except Exception:
                pass

            idinfo = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                self.client_id,
                **verify_kwargs
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
            # Handle timing issues gracefully: if token is used too early, wait briefly and retry once
            message = str(e)
            current_app.logger.error(f"Invalid token: {message}")
            if 'Token used too early' in message or 'used too early' in message:
                current_app.logger.warning("Detected Google ID token timing issue. Waiting 2 seconds and retrying verification...")
                time.sleep(2)
                try:
                    idinfo = id_token.verify_oauth2_token(
                        token,
                        requests.Request(),
                        self.client_id,
                        **({ 'clock_skew_in_seconds': self.clock_skew } if hasattr(id_token, 'verify_oauth2_token') else {})
                    )
                    user_data = {
                        'email': idinfo['email'],
                        'name': idinfo.get('name', ''),
                        'picture': idinfo.get('picture', ''),
                        'google_id': idinfo['sub']
                    }
                    existing_user = self.user_service.get_user_by_email(user_data['email'])
                    if existing_user:
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
                    new_user = {
                        'email': user_data['email'],
                        'name': user_data['name'],
                        'google_id': user_data['google_id'],
                        'profile_picture': user_data['picture'],
                        'is_google_user': True
                    }
                    created_user = self.user_service.create_user(new_user)
                    return created_user
                except Exception as retry_error:
                    current_app.logger.error(f"Retry after timing issue failed: {str(retry_error)}")
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