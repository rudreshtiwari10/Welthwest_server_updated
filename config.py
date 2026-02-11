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
        self.FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

        # Logging Configuration
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_FORMAT = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Security Configuration
        self.CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
        self.RATE_LIMIT = os.getenv('RATE_LIMIT', '100/hour')

        # Anonymous Trial Configuration
        self.ANON_TRIAL_LIMIT = int(os.getenv('ANON_TRIAL_LIMIT', 0))  # Default limit for all features - set to 0 to require login
        self.ANON_AI_ANALYSIS_LIMIT = int(os.getenv('ANON_AI_ANALYSIS_LIMIT', self.ANON_TRIAL_LIMIT))
        self.ANON_BACKTEST_LIMIT = int(os.getenv('ANON_BACKTEST_LIMIT', self.ANON_TRIAL_LIMIT))
        self.ANON_CHAT_LIMIT = int(os.getenv('ANON_CHAT_LIMIT', 0))
        self.ANON_SESSION_COOKIE = os.getenv('ANON_SESSION_COOKIE', 'ww_session_id')
        self.ANON_SESSION_TTL_SECONDS = int(os.getenv('ANON_SESSION_TTL_SECONDS', 30 * 24 * 3600))  # 30 days default
        self.ENABLE_ANON_TRIALS = os.getenv('ENABLE_ANON_TRIALS', 'True').lower() == 'true'

        # Feature Flags
        self.ENABLE_CACHING = os.getenv('ENABLE_CACHING', 'True').lower() == 'true'
        self.ENABLE_RATE_LIMITING = os.getenv('ENABLE_RATE_LIMITING', 'True').lower() == 'true'
        self.ENABLE_JWT_BLACKLIST = os.getenv('ENABLE_JWT_BLACKLIST', 'True').lower() == 'true'

        # Development/Production mode
        self.DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
        self.TESTING = os.getenv('TESTING', 'False').lower() == 'true'
        self.ENV = os.getenv('FLASK_ENV', 'development')

        # ============================================
        # PREMIUM PLAN CONFIGURATION
        # ============================================

        # Cashfree Payment Gateway Configuration
        self.IS_PAYMENT_GATEWAY_ENABLED = os.getenv('IS_PAYMENT_GATEWAY_ENABLED', 'false').lower() == 'true'
        self.CASHFREE_ENV = os.getenv('CASHFREE_ENV', 'sandbox')  # 'sandbox' or 'production'
        self.CASHFREE_APP_ID_SANDBOX = os.getenv('CASHFREE_APP_ID_SANDBOX')
        self.CASHFREE_SECRET_KEY_SANDBOX = os.getenv('CASHFREE_SECRET_KEY_SANDBOX')
        self.CASHFREE_APP_ID_PROD = os.getenv('CASHFREE_APP_ID_PROD')
        self.CASHFREE_SECRET_KEY_PROD = os.getenv('CASHFREE_SECRET_KEY_PROD')
        self.CASHFREE_WEBHOOK_SECRET = os.getenv('CASHFREE_WEBHOOK_SECRET')

        # Get active Cashfree credentials based on environment
        if self.CASHFREE_ENV == 'production':
            self.CASHFREE_APP_ID = self.CASHFREE_APP_ID_PROD
            self.CASHFREE_SECRET_KEY = self.CASHFREE_SECRET_KEY_PROD
        else:
            self.CASHFREE_APP_ID = self.CASHFREE_APP_ID_SANDBOX
            self.CASHFREE_SECRET_KEY = self.CASHFREE_SECRET_KEY_SANDBOX

        # Server Timezone for daily limit resets
        self.SERVER_TIMEZONE = os.getenv('SERVER_TIMEZONE', 'Asia/Kolkata')

        # Premium Plan Pricing (INR)
        self.PLAN_PRICES = {
            'FREE': {
                'weekly': 0,
                'monthly': 0,
                'annual': 0
            },
            'STARTER': {
                'weekly': int(os.getenv('PLAN_STARTER_WEEKLY', 149)),
                'monthly': int(os.getenv('PLAN_STARTER_MONTHLY', 299)),
                'annual': int(os.getenv('PLAN_STARTER_ANNUAL', 2999))
            },
            'PRO': {
                'weekly': int(os.getenv('PLAN_PRO_WEEKLY', 249)),
                'monthly': int(os.getenv('PLAN_PRO_MONTHLY', 499)),
                'annual': int(os.getenv('PLAN_PRO_ANNUAL', 4999))
            },
            'ADVANCED': {
                'weekly': int(os.getenv('PLAN_ADVANCED_WEEKLY', 499)),
                'monthly': int(os.getenv('PLAN_ADVANCED_MONTHLY', 999)),
                'annual': int(os.getenv('PLAN_ADVANCED_ANNUAL', 9999))
            },
            'ENTERPRISE': {
                'weekly': int(os.getenv('PLAN_ENTERPRISE_WEEKLY', 999)),
                'monthly': int(os.getenv('PLAN_ENTERPRISE_MONTHLY', 1999)),
                'annual': int(os.getenv('PLAN_ENTERPRISE_ANNUAL', 19999))
            }
        }

        # Premium Plan Limits (per-feature, per-day)
        # Feature keys: welth-market-regime, welth-ai-assistant, backtest-beta, mtf-screener, risk-calculator
        self.PLAN_LIMITS = {
            'FREE': {
                'welth-market-regime': int(os.getenv('PLAN_FREE__MARKET_REGIME', 10)),
                'welth-ai-assistant': int(os.getenv('PLAN_FREE__AI_ASSISTANT', 15)),
                'backtest-beta': int(os.getenv('PLAN_FREE__BACKTEST', 5)),
                'mtf-screener': int(os.getenv('PLAN_FREE__MTF_SCREENER', 5)),
                'risk-calculator': int(os.getenv('PLAN_FREE__RISK_CALCULATOR', 20))
            },
            'STARTER': {
                'welth-market-regime': int(os.getenv('PLAN_STARTER__MARKET_REGIME', 20)),
                'welth-ai-assistant': int(os.getenv('PLAN_STARTER__AI_ASSISTANT', 25)),
                'backtest-beta': int(os.getenv('PLAN_STARTER__BACKTEST', 15)),
                'mtf-screener': int(os.getenv('PLAN_STARTER__MTF_SCREENER', 15)),
                'risk-calculator': int(os.getenv('PLAN_STARTER__RISK_CALCULATOR', 50))
            },
            'PRO': {
                'welth-market-regime': int(os.getenv('PLAN_PRO__MARKET_REGIME', 30)),
                'welth-ai-assistant': int(os.getenv('PLAN_PRO__AI_ASSISTANT', 35)),
                'backtest-beta': int(os.getenv('PLAN_PRO__BACKTEST', 25)),
                'mtf-screener': int(os.getenv('PLAN_PRO__MTF_SCREENER', 30)),
                'risk-calculator': int(os.getenv('PLAN_PRO__RISK_CALCULATOR', 100))
            },
            'ADVANCED': {
                'welth-market-regime': int(os.getenv('PLAN_ADVANCED__MARKET_REGIME', 40)),
                'welth-ai-assistant': int(os.getenv('PLAN_ADVANCED__AI_ASSISTANT', 45)),
                'backtest-beta': int(os.getenv('PLAN_ADVANCED__BACKTEST', 40)),
                'mtf-screener': int(os.getenv('PLAN_ADVANCED__MTF_SCREENER', 50)),
                'risk-calculator': int(os.getenv('PLAN_ADVANCED__RISK_CALCULATOR', 200))
            },
            'ENTERPRISE': {
                'welth-market-regime': int(os.getenv('PLAN_ENTERPRISE__MARKET_REGIME', 50)),
                'welth-ai-assistant': int(os.getenv('PLAN_ENTERPRISE__AI_ASSISTANT', 55)),
                'backtest-beta': int(os.getenv('PLAN_ENTERPRISE__BACKTEST', 45)),
                'mtf-screener': int(os.getenv('PLAN_ENTERPRISE__MTF_SCREENER', 1010)),
                'risk-calculator': int(os.getenv('PLAN_ENTERPRISE__RISK_CALCULATOR', 500))
            }
        }

        # Anonymous User Limits (session-based) - set to 0 to require login
        self.ANON_LIMITS = {
            'welth-market-regime': int(os.getenv('ANON_MARKET_REGIME_LIMIT', 0)),
            'welth-ai-assistant': int(os.getenv('ANON_AI_ASSISTANT_LIMIT', 0)),
            'backtest-beta': int(os.getenv('ANON_BACKTEST_LIMIT', 0)),
            'mtf-screener': int(os.getenv('ANON_MTF_SCREENER_LIMIT', 0)),
            'risk-calculator': int(os.getenv('ANON_RISK_CALCULATOR_LIMIT', 3))
        }

        # Usage Counter Configuration
        self.USAGE_COUNTER_TTL_SECONDS = int(os.getenv('USAGE_COUNTER_TTL_SECONDS', 86400))  # 24 hours

        # ============================================
        # LSTM STOCK PREDICTION CONFIGURATION
        # ============================================

        # LSTM Admin API Key
        self.LSTM_ADMIN_API_KEY = os.getenv('LSTM_ADMIN_API_KEY', 'change-this-admin-key-in-production')

        # LSTM Model Directories
        self.LSTM_MODEL_DIR = os.getenv('LSTM_MODEL_DIR', './lstm_model/models')
        self.LSTM_SCALER_DIR = os.getenv('LSTM_SCALER_DIR', './lstm_model/scalers')
        self.LSTM_METADATA_DIR = os.getenv('LSTM_METADATA_DIR', './lstm_model/metadata')

        # LSTM Training Configuration
        self.LSTM_TIME_STEPS = int(os.getenv('LSTM_TIME_STEPS', 60))
        self.LSTM_FORECAST_DAYS = int(os.getenv('LSTM_FORECAST_DAYS', 3))
        self.LSTM_TRAINING_EPOCHS = int(os.getenv('LSTM_TRAINING_EPOCHS', 25))
        self.LSTM_BATCH_SIZE = int(os.getenv('LSTM_BATCH_SIZE', 32))
        self.LSTM_TRAIN_TEST_SPLIT = float(os.getenv('LSTM_TRAIN_TEST_SPLIT', 0.95))

        # LSTM Data Configuration
        self.LSTM_DATA_START_YEAR = os.getenv('LSTM_DATA_START_YEAR', '2019-01-01')
        self.LSTM_DATA_SOURCE = os.getenv('LSTM_DATA_SOURCE', 'yahoo_finance')

        # LSTM Rate Limiting
        self.LSTM_RATE_LIMIT_PER_MINUTE = int(os.getenv('LSTM_RATE_LIMIT_PER_MINUTE', 10))
        self.LSTM_ADMIN_RATE_LIMIT_PER_HOUR = int(os.getenv('LSTM_ADMIN_RATE_LIMIT_PER_HOUR', 5))

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