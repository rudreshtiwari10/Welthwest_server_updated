import os
import json
import time
from datetime import datetime, timedelta
import logging
import requests
import base64
import hashlib
import secrets

logger = logging.getLogger(__name__)

class UpstoxAutoAuth:
    def __init__(self, upstox_api):
        self.upstox_api = upstox_api
        self.config = upstox_api.config
        self.token_info_file = "upstox_token_info.json"
        self.max_retries = 3
        self.retry_delay = 60  # seconds
        self.base_url = "https://api.upstox.com/v2"
        
    def generate_code_verifier(self):
        """Generate a code verifier for PKCE"""
        token = secrets.token_urlsafe(32)
        return token
        
    def generate_code_challenge(self, code_verifier):
        """Generate a code challenge for PKCE"""
        sha256 = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')
        return code_challenge
        
    def save_token_info(self, token_data):
        """Save token information including expiry"""
        try:
            token_info = {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),  # Upstox tokens typically valid for 7 days
                "timestamp": datetime.now().isoformat()
            }
            with open(self.token_info_file, 'w') as f:
                json.dump(token_info, f)
            logger.info("Saved token information")
            return True
        except Exception as e:
            logger.error(f"Error saving token info: {str(e)}")
            return False
            
    def load_token_info(self):
        """Load token information"""
        try:
            if os.path.exists(self.token_info_file):
                with open(self.token_info_file, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logger.error(f"Error loading token info: {str(e)}")
            return None
            
    def is_token_valid(self):
        """Check if current token is valid"""
        token_info = self.load_token_info()
        if not token_info:
            return False
            
        try:
            expires_at = datetime.fromisoformat(token_info["expires_at"])
            # Consider token invalid if it expires in less than 1 day
            return datetime.now() < (expires_at - timedelta(days=1))
        except Exception as e:
            logger.error(f"Error checking token validity: {str(e)}")
            return False

    def check_internet_connection(self):
        """Check internet connectivity"""
        try:
            requests.get("https://api.upstox.com", timeout=5)
            return True
        except requests.RequestException:
            return False

    def wait_for_internet(self, timeout=300):
        """Wait for internet connection to be available"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_internet_connection():
                return True
            logger.warning("No internet connection. Waiting...")
            time.sleep(30)
        return False

    def get_token_direct(self):
        """Get access token directly using API credentials"""
        try:
            # Generate PKCE code verifier and challenge
            code_verifier = self.generate_code_verifier()
            code_challenge = self.generate_code_challenge(code_verifier)
            
            # Step 1: Get authorization code
            auth_url = f"{self.base_url}/login/authorization/dialog"
            auth_params = {
                'response_type': 'code',
                'client_id': self.config.UPSTOX_API_KEY,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
                'redirect_uri': self.config.UPSTOX_REDIRECT_URI,
            }
            
            # Step 2: Exchange code for token
            token_url = f"{self.base_url}/login/authorization/token"
            token_data = {
                'code': 'authorization_code',  # This will be auto-generated
                'client_id': self.config.UPSTOX_API_KEY,
                'client_secret': self.config.UPSTOX_API_SECRET,
                'redirect_uri': self.config.UPSTOX_REDIRECT_URI,
                'code_verifier': code_verifier,
                'grant_type': 'authorization_code'
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'X-API-KEY': self.config.UPSTOX_API_KEY
            }
            
            response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
            response.raise_for_status()
            
            token_response = response.json()
            if token_response.get('access_token'):
                self.save_token_info(token_response)
                logger.info("Successfully obtained token directly via API")
                return True
                
            logger.error("No access token in response")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error getting token: {str(e)}")
            return False

    def refresh_token(self, refresh_token):
        """Refresh an expired token using the refresh token"""
        try:
            token_url = f"{self.base_url}/login/authorization/token"
            token_data = {
                'refresh_token': refresh_token,
                'client_id': self.config.UPSTOX_API_KEY,
                'client_secret': self.config.UPSTOX_API_SECRET,
                'grant_type': 'refresh_token'
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'X-API-KEY': self.config.UPSTOX_API_KEY
            }
            
            response = requests.post(token_url, data=token_data, headers=headers, timeout=30)
            response.raise_for_status()
            
            token_response = response.json()
            if token_response.get('access_token'):
                self.save_token_info(token_response)
                logger.info("Successfully refreshed token")
                return True
                
            logger.error("No access token in refresh response")
            return False
            
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return False

    def automated_login(self):
        """Get token using API credentials with retries"""
        # Check if required environment variables are set
        if not all([
            self.config.UPSTOX_API_KEY,
            self.config.UPSTOX_API_SECRET
        ]):
            logger.error("Missing required Upstox API credentials in environment variables")
            return False

        # Check internet connectivity
        if not self.wait_for_internet():
            logger.error("No internet connection available")
            return False

        # Try to refresh existing token first
        token_info = self.load_token_info()
        if token_info and token_info.get('refresh_token'):
            if self.refresh_token(token_info['refresh_token']):
                return True

        # If refresh fails or no refresh token, try direct token generation
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Token generation attempt {attempt + 1} of {self.max_retries}")
                if self.get_token_direct():
                    return True
                    
            except Exception as e:
                logger.error(f"Error during token generation attempt {attempt + 1}: {str(e)}")
            
            if attempt < self.max_retries - 1:
                logger.info(f"Waiting {self.retry_delay} seconds before next attempt")
                time.sleep(self.retry_delay)
            
        logger.error(f"Failed to get token after {self.max_retries} attempts")
        return False
            
    def ensure_valid_token(self):
        """Ensure a valid token is available, getting new one if necessary"""
        if self.is_token_valid():
            logger.info("Token is still valid")
            return True
            
        logger.info("Token invalid or expired, getting new token")
        return self.automated_login() 