import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for the application"""
    
    def __init__(self):
        # MongoDB Configuration
        self.MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self.DB_NAME = os.getenv('DB_NAME', 'welthwest')

        # JWT Configuration
        self.JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')
        self.JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))

        # Subscription Tiers Configuration
        self.SUBSCRIPTION_TIERS = {
            'FREE': {
                'price': 0,
                'backtest_daily_limit': int(os.getenv('FREE_BACKTEST_LIMIT', 2)),
                'llm_daily_limit': int(os.getenv('FREE_LLM_LIMIT', 5)),
                'market_data_delay': 'delayed',
                'description': 'Free tier with basic features'
            },
            'BASIC': {
                'price': 399,
                'backtest_daily_limit': int(os.getenv('BASIC_BACKTEST_LIMIT', 10)),
                'llm_daily_limit': int(os.getenv('BASIC_LLM_LIMIT', 20)),
                'market_data_delay': '15min',
                'description': 'Basic tier with increased limits'
            },
            'PRO': {
                'price': 999,
                'backtest_daily_limit': int(os.getenv('PRO_BACKTEST_LIMIT', 30)),
                'llm_daily_limit': int(os.getenv('PRO_LLM_LIMIT', 50)),
                'market_data_delay': 'realtime',
                'description': 'Pro tier with advanced features'
            },
            'ENTERPRISE': {
                'price': 2999,
                'backtest_daily_limit': float('inf'),
                'llm_daily_limit': float('inf'),
                'market_data_delay': 'realtime',
                'description': 'Enterprise tier with unlimited usage'
            }
        }

        # Usage Reset Configuration
        self.USAGE_RESET_HOUR = int(os.getenv('USAGE_RESET_HOUR', 0))  # Reset at midnight
        self.USAGE_RESET_TIMEZONE = os.getenv('USAGE_RESET_TIMEZONE', 'Asia/Kolkata')

        # Redis Configuration
        self.REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
        self.REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
        self.REDIS_DB = int(os.getenv('REDIS_DB', 0))
        self.REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

        # Upstox Configuration
        self.UPSTOX_API_KEY = os.getenv('UPSTOX_API_KEY')
        self.UPSTOX_API_SECRET = os.getenv('UPSTOX_API_SECRET')
        self.UPSTOX_REDIRECT_URI = os.getenv('UPSTOX_REDIRECT_URI', 'http://localhost:8000/api/upstox/callback')
        self.UPSTOX_API_BASE_URL = "https://api.upstox.com/v2"

        # Razorpay Configuration
        self.RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
        self.RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
        self.RAZORPAY_WEBHOOK_SECRET = os.getenv('RAZORPAY_WEBHOOK_SECRET')
        self.RAZORPAY_ENVIRONMENT = os.getenv('RAZORPAY_ENVIRONMENT', 'test')
        self.RAZORPAY_CURRENCY = os.getenv('RAZORPAY_CURRENCY', 'INR')

        # Cache Configuration
        self.CACHE_TYPE = os.getenv('CACHE_TYPE', 'redis')
        self.CACHE_REDIS_HOST = self.REDIS_HOST
        self.CACHE_REDIS_PORT = self.REDIS_PORT
        self.CACHE_REDIS_DB = int(os.getenv('CACHE_REDIS_DB', 1))
        self.CACHE_REDIS_PASSWORD = self.REDIS_PASSWORD
        self.CACHE_DEFAULT_TIMEOUT = int(os.getenv('CACHE_DEFAULT_TIMEOUT', 300))

        # API Configuration
        self.API_VERSION = os.getenv('API_VERSION', 'v1')
        self.BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')

        # Logging Configuration
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FORMAT = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Security Configuration
        self.CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
        self.RATE_LIMIT = os.getenv('RATE_LIMIT', '100/hour')

        # Feature Flags
        self.ENABLE_CACHING = os.getenv('ENABLE_CACHING', 'True').lower() == 'true'
        self.ENABLE_RATE_LIMITING = os.getenv('ENABLE_RATE_LIMITING', 'True').lower() == 'true'
        self.ENABLE_JWT_BLACKLIST = os.getenv('ENABLE_JWT_BLACKLIST', 'True').lower() == 'true'

        # Development/Production mode
        self.DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
        self.TESTING = os.getenv('TESTING', 'False').lower() == 'true'
        self.ENV = os.getenv('FLASK_ENV', 'development')

        # Validate required configuration
        self._validate_config()

    def _validate_config(self):
        """Validate required configuration values"""
        required_fields = [
            ('MONGODB_URI', self.MONGODB_URI),
            ('JWT_SECRET_KEY', self.JWT_SECRET_KEY)
        ]
        
        missing_fields = [field for field, value in required_fields if not value or value in ['your-jwt-secret-key-change-this-in-production', 'your-upstox-api-key', 'your-upstox-api-secret']]
        if missing_fields:
            print(f"Warning: Using default values for: {', '.join(missing_fields)}")
        
        # Optional fields that won't cause startup failure
        optional_fields = [
            ('UPSTOX_API_KEY', self.UPSTOX_API_KEY),
            ('UPSTOX_API_SECRET', self.UPSTOX_API_SECRET),
            ('RAZORPAY_KEY_ID', self.RAZORPAY_KEY_ID),
            ('RAZORPAY_KEY_SECRET', self.RAZORPAY_KEY_SECRET),
            ('RAZORPAY_WEBHOOK_SECRET', self.RAZORPAY_WEBHOOK_SECRET)
        ]
        
        missing_upstox = [field for field, value in optional_fields[:2] if not value or value in ['your-upstox-api-key', 'your-upstox-api-secret']]
        if missing_upstox:
            print(f"Info: Upstox features will be disabled. Missing: {', '.join(missing_upstox)}")
            
        missing_razorpay = [field for field, value in optional_fields[2:] if not value or value in ['rzp_test_your_key_id', 'your_key_secret', 'your_webhook_secret']]
        if missing_razorpay:
            print(f"Info: Razorpay payment features will be disabled. Missing: {', '.join(missing_razorpay)}")

_config = None

def get_config():
    """Get the application configuration"""
    global _config
    if _config is None:
        _config = Config()
    return _config 