from flask import Flask, request, jsonify, g, current_app
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from services.stock_service import (
    get_historical_data, get_live_data, validate_ticker,
    get_ohlc_data, get_market_indices, get_top_gainers_losers, get_stock_fundamentals
)
from services.utils import normalize_data, calculate_statistics
from services.user_service import UserService
from services.ai_service import AIModelService
# nextgen_ai_service imported lazily to avoid 5s+ transformers/torch load at startup
from services.subscription_service import SubscriptionService
from services.email_service import email_service
from routes.premium import premium_bp
from routes.payment import payment_bp
from routes.subscription import subscription_bp
from routes.finance_ai_routes import register_finance_ai_routes
# from routes.news_blog_routes import news_blog_bp  # Commented out - using direct endpoints in app.py
from routes.admin import admin_bp
from routes.admin_content import admin_content_bp
from routes.admin_support import admin_support_bp
from routes.admin_monitoring import admin_monitoring_bp
from routes.support import support_bp
from routes.ai_screener_routes import ai_screener_bp
from middleware.feature_limit import feature_limit, admin_required
from database.seed_plans import initialize_premium_system
from services.google_auth_service import GoogleAuthService
from services.feedback_service import get_feedback_service
from services.notification_service import notification_service
from services.news_service import news_service
from services.news_aggregator import NewsAggregator
from middleware.subscription_middleware import require_subscription_feature, check_market_data_access
from middleware.anon_limit import anon_or_auth_feature_limit
import os
import requests
import logging
import uuid
import pandas as pd
from typing import Dict, Any, Optional, List
from config import get_config
from datetime import timedelta
from services.technical_analysis import TechnicalAnalysis
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
import json
from functools import wraps
import re
from services.session_service import InMemorySessionService
from bson import ObjectId
from datetime import datetime
import time
from services.cache_service import get_cached_data
from services.stock_service import warm_market_indices_cache

# Setup logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configure Werkzeug logger to only show errors
logging.getLogger('werkzeug').setLevel(logging.ERROR)

def is_binary_content(data):
    """Check if the request content appears to be binary data"""
    # Check for common TLS/SSL handshake patterns
    ssl_patterns = [
        rb'\x16\x03[\x00-\x03]',    # TLS record layer
        rb'\xc0[\x2b\x2f\x2c\x30]', # Common cipher suites (À+À/À,À0)
        rb'\x01\x00',               # Client Hello
        rb'\x03[\x00-\x03]',        # SSL/TLS versions
    ]
    
    if not data:
        return False
        
    # Convert to bytes if string
    if isinstance(data, str):
        data = data.encode('utf-8', errors='ignore')
        
    # Check for binary patterns
    for pattern in ssl_patterns:
        if re.search(pattern, data):
            return True
            
    # Check if data contains high proportion of non-printable characters
    printable = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
    return (printable / len(data)) < 0.75

def validate_json_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        try:
            # Check for binary content
            raw_data = request.get_data()
            if is_binary_content(raw_data):
                logger.warning(f"Rejected binary request from {request.remote_addr}")
                return jsonify({"error": "Binary/malformed request rejected"}), 400
                
            # Attempt to parse JSON
            if raw_data:
                json.loads(raw_data)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON format"}), 400
        except UnicodeDecodeError:
            logger.warning(f"Unicode decode error in request from {request.remote_addr}")
            return jsonify({"error": "Invalid request encoding"}), 400
        return f(*args, **kwargs)
    return decorated_function

# Initialize app with configuration
def create_app():
    app = Flask(__name__)
    config = get_config()
    app.config.from_object(config)
    
    # Set maximum content length (10MB)
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    
    # Configure JWT
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
    
    # Add clock skew tolerance to handle timing issues (especially with Google Auth)
    # This allows tokens to be valid 30 seconds before their nbf (not before) time
    # and 30 seconds after their exp (expires) time to handle clock drift
    app.config["JWT_DECODE_LEEWAY"] = timedelta(seconds=int(os.environ.get("JWT_DECODE_LEEWAY", 30)))
    
    # Configure CORS with specific origins and credentials support for anonymous sessions
    frontend_url = os.environ.get("FRONTEND_URL", "*")
    allowed_origins = [frontend_url]

    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True  # IMPORTANT: Allow cookies for anonymous sessions
        },
        r"/": {
            "origins": allowed_origins,
            "supports_credentials": True
        }
    })
    
    # Initialize email service
    email_service.init_app(app)

    # Error handlers
    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(e):
        return jsonify({"error": "Request entity too large. Maximum size is 10MB"}), 413

    @app.errorhandler(BadRequest)
    def handle_bad_request(e):
        return jsonify({"error": "Bad request format"}), 400
        
    @app.errorhandler(UnicodeDecodeError)
    def handle_unicode_error(e):
        return jsonify({"error": "Invalid request encoding"}), 400

    @app.before_request
    def validate_request():
        # Skip validation for GET requests and health checks
        if request.method == 'GET' or request.path in ['/', '/health']:
            return
            
        # Check for binary content early
        raw_data = request.get_data()
        if is_binary_content(raw_data):
            logger.warning(f"Rejected binary request from {request.remote_addr} to {request.path}")
            return jsonify({"error": "Binary/malformed request rejected"}), 400
            
        # Log request info for non-binary requests
        logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")
        if request.content_length:
            logger.info(f"Content Length: {request.content_length}")
    
    return app

app = create_app()
jwt = JWTManager(app)
# Services initialized on first request to avoid slow startup (saves ~3-4s)
_user_service = None
_subscription_service = None

def _get_user_service():
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service

def _get_subscription_service():
    global _subscription_service
    if _subscription_service is None:
        _subscription_service = SubscriptionService()
    return _subscription_service
session_service = InMemorySessionService()

# Add additional claims to JWT token (subscription info for side projects)
@jwt.additional_claims_loader
def add_claims_to_jwt(identity):
    """Add user subscription and profile info to JWT token"""
    try:
        # Get user data
        user_data = _get_user_service().get_user_by_id(identity)

        if not user_data:
            return {}

        # Return claims to be added to the token
        return {
            "userId": str(user_data.get('id', identity)),
            "username": user_data.get('username', ''),
            "email": user_data.get('email', ''),
            "role": user_data.get('role', 'user'),
            "subscription": {
                "plan": user_data.get('subscription', {}).get('plan', 'FREE'),
                "is_active": user_data.get('subscription', {}).get('is_active', False),
                "expiry_date": user_data.get('subscription', {}).get('expiry_date', None)
            }
        }
    except Exception as e:
        logger.error(f"Error adding claims to JWT: {str(e)}")
        return {}

# Register premium, payment, and subscription blueprints
app.register_blueprint(premium_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(subscription_bp)
# app.register_blueprint(news_blog_bp)  # Commented out - using direct endpoints in app.py
app.register_blueprint(admin_bp)

# Register user support blueprint
app.register_blueprint(support_bp)

# Register new admin module blueprints
app.register_blueprint(admin_content_bp)
app.register_blueprint(admin_support_bp)
app.register_blueprint(admin_monitoring_bp)


# Register AI Screener blueprint
app.register_blueprint(ai_screener_bp)

# Register enhanced Finance AI routes
register_finance_ai_routes(app)

# Defer premium system initialization to first request (thread-safe)
import threading
_premium_init_lock = threading.Lock()
_premium_initialized = False

@app.before_request
def _init_premium_once():
    global _premium_initialized
    if not _premium_initialized:
        with _premium_init_lock:
            if not _premium_initialized:
                logger.info("Initializing premium system on first request...")
                initialize_premium_system()
                _premium_initialized = True

# After request handler to set anonymous session cookie
@app.after_request
def set_anon_session_cookie(response):
    """Set anonymous session cookie if decorator created a new session"""
    new_session_id = getattr(g, '_new_anon_session_id', None)
    if new_session_id:
        cookie_name = app.config['ANON_SESSION_COOKIE']
        ttl_seconds = app.config['ANON_SESSION_TTL_SECONDS']
        response.set_cookie(
            cookie_name,
            new_session_id,
            max_age=ttl_seconds,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite='Lax'
        )
    return response

# Lazy service getters - initialized on first use, not at startup
_technical_analysis = None
_ai_service = None

def get_technical_analysis():
    """Lazily initialize TechnicalAnalysis on first use"""
    global _technical_analysis
    if _technical_analysis is None:
        _technical_analysis = TechnicalAnalysis()
    return _technical_analysis

def get_ai_service():
    """Lazily initialize AIModelService on first use"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIModelService()
    return _ai_service

# Warm market indices cache on startup
def warm_cache_on_startup():
    """Warm the market indices cache when the first request comes in"""
    try:
        logger.info("Warming market indices cache on startup...")
        warm_market_indices_cache()
        logger.info("Market indices cache warming completed")
    except Exception as e:
        logger.warning(f"Failed to warm market indices cache on startup: {str(e)}")

# Add startup event handler for modern Flask versions
@app.route('/startup', methods=['POST'])
def trigger_startup_tasks():
    """Trigger startup tasks like cache warming"""
    try:
        warm_cache_on_startup()
        return jsonify({
            "status": "success",
            "message": "Startup tasks completed",
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Startup tasks failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }), 500

# Root route for health checks
@app.route('/', methods=['GET', 'HEAD'])
def root():
    """Root endpoint for health checks"""
    return jsonify({"status": "healthy", "message": "Indian Stock Market API is running"}), 200

# Health check endpoint with cache status
@app.route('/health', methods=['GET'])
def health_check():
    """Health check with cache status and performance metrics"""
    try:
        # Check cache status for market indices
        cache_key = "market_indices"
        cached_data = get_cached_data(cache_key)
        
        # Warm cache if it's cold
        if not cached_data:
            warm_cache_on_startup()
            cached_data = get_cached_data(cache_key)
        
        health_data = {
            "status": "healthy",
            "message": "Indian Stock Market API is running",
            "timestamp": datetime.now().isoformat(),
            "cache": {
                "market_indices": "warm" if cached_data else "cold",
                "status": "operational"
            },
            "services": {
                "yfinance": "available",
                "cache": "operational"
            }
        }
        
        return jsonify(health_data), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


# Authentication routes
@app.route('/api/auth/register', methods=['POST'])
@validate_json_request
def register():
    """Register a new user - DEPRECATED: Use OTP verification flow instead"""
    return jsonify({
        "error": "This endpoint is deprecated. Please use the OTP verification flow: /api/auth/send-registration-otp followed by /api/auth/verify-registration-otp"
    }), 400

@app.route('/api/auth/send-registration-otp', methods=['POST'])
@validate_json_request
def send_registration_otp():
    """Send OTP for email verification during registration"""
    data = request.get_json()

    # Validate required fields
    if 'email' not in data:
        return jsonify({"error": "Email is required"}), 400

    email = data['email'].strip().lower()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()

    # Check if email already exists
    if _get_user_service().users.find_one({"email": email}):
        return jsonify({"error": "Email already exists"}), 400

    # Generate and send OTP with user's name
    success, message, otp = _get_user_service().create_registration_otp(email, first_name, last_name)

    if not success:
        return jsonify({"error": message}), 400

    # Send OTP email with user's name
    try:
        email_sent = email_service.send_registration_otp(email, otp, first_name, last_name)
        if email_sent:
            logger.info(f"Registration OTP sent to {email} for {first_name} {last_name}")
            return jsonify({
                "message": "OTP sent to your email for verification",
                "email_sent": True
            }), 200
        else:
            logger.error(f"Failed to send registration OTP email to {email}")
            return jsonify({
                "error": "Failed to send OTP email. Please try again."
            }), 500
    except Exception as e:
        logger.error(f"Error sending registration OTP: {str(e)}")
        return jsonify({
            "error": "Failed to send OTP email. Please try again."
        }), 500

@app.route('/api/auth/verify-registration-otp', methods=['POST'])
@validate_json_request
def verify_registration_otp():
    """Verify OTP only (without creating account)"""
    data = request.get_json()
    
    # Validate required fields for OTP verification
    required_fields = ['email', 'otp']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    email = data['email'].strip().lower()
    otp = data['otp'].strip()
    
    # Check OTP (without marking as used)
    success, message = _get_user_service().check_registration_otp(email, otp)
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"message": "OTP verified successfully"}), 200

@app.route('/api/auth/complete-registration', methods=['POST'])
@validate_json_request
def complete_registration():
    """Complete registration after OTP verification"""
    data = request.get_json()
    
    # Validate required fields (no OTP required anymore)
    required_fields = ['email', 'username', 'password', 'confirm_password']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Validate password match
    if data['password'] != data['confirm_password']:
        return jsonify({"error": "Passwords do not match"}), 400
    
    email = data['email'].strip().lower()
    username = data['username'].strip()
    password = data['password']

    # Check if email is verified
    if not _get_user_service().is_email_verified(email):
        return jsonify({"error": "Email not verified. Please verify your email first."}), 400

    # Retrieve first_name and last_name from OTP record
    otp_data = _get_user_service().get_registration_otp_data(email)
    first_name = otp_data.get("first_name", "") if otp_data else ""
    last_name = otp_data.get("last_name", "") if otp_data else ""

    # Register user with name
    success, message, user_data = _get_user_service().register_user(
        email=email,
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name
    )
    
    if not success:
        return jsonify({"error": message}), 400
    
    # Initialize subscription
    if not _get_subscription_service().initialize_subscription(user_data['id']):
        # If subscription initialization fails, delete the user and return error
        _get_user_service().users.delete_one({"_id": ObjectId(user_data['id'])})
        return jsonify({"error": "Failed to initialize user subscription"}), 500
    
    # Get the initialized subscription
    subscription = _get_subscription_service().get_subscription_details(user_data['id'])
    if not subscription:
        # This shouldn't happen, but if it does, clean up and return error
        _get_user_service().users.delete_one({"_id": ObjectId(user_data['id'])})
        return jsonify({"error": "Failed to retrieve user subscription"}), 500
    
    # Generate tokens
    access_token = create_access_token(identity=str(user_data['id']))
    refresh_token = create_refresh_token(identity=str(user_data['id']))
    
    # Store refresh token
    _get_user_service().store_refresh_token(user_data['id'], refresh_token)
    
    # Clean up email verification record (no longer needed)
    try:
        _get_user_service().verified_emails.delete_many({"email": email})
        logger.info(f"Cleaned up email verification for {email}")
    except Exception as e:
        logger.error(f"Failed to cleanup email verification for {email}: {str(e)}")
    
    # Send welcome email to new user
    try:
        # Use full name if available, otherwise use username
        full_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
        user_name = full_name if full_name else user_data['username']

        email_service.send_welcome_email(
            user_email=user_data['email'],
            user_name=user_name
        )
        logger.info(f"Welcome email sent to {user_data['email']}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user_data['email']}: {str(e)}")
        # Don't fail registration if email fails
    
    # Send new user notification to company
    try:
        from datetime import datetime
        registration_date = datetime.now().strftime('%B %d, %Y at %I:%M %p')
        email_service.send_new_user_notification_to_company(
            user_email=user_data['email'],
            user_name=user_data['username'],
            registration_date=registration_date
        )
        logger.info(f"Company notification email sent for new user: {user_data['email']}")
    except Exception as e:
        logger.error(f"Failed to send company notification email for user {user_data['email']}: {str(e)}")
        # Don't fail registration if email fails
    
    return jsonify({
        "message": "Registration successful",
        "user": user_data,
        "subscription": subscription,
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 201

@app.route('/api/auth/google', methods=['POST'])
@validate_json_request
def google_auth():
    try:
        data = request.get_json()
        token = data.get('token')
        
        if not token:
            logger.warning("Google auth attempted without token")
            return jsonify({"error": "Token is required"}), 400
            
        logger.info("Processing Google authentication request")
        
        google_auth_service = GoogleAuthService()
        user = google_auth_service.verify_google_token(token)
        
        if not user:
            logger.warning("Google token verification failed")
            return jsonify({"error": "Invalid Google token"}), 401
            
        logger.info(f"Google token verified successfully for user: {user.get('email', 'unknown')}")
        
        # Check if this is a newly created user using the flag from GoogleAuthService
        is_new_user = user.get('_is_new_user', False)
        if is_new_user:
            logger.info(f"Detected new Google user registration: {user.get('email', 'unknown')}")
        
        # Initialize subscription for new Google users
        if is_new_user:
            try:
                if not _get_subscription_service().initialize_subscription(user['id']):
                    logger.error(f"Failed to initialize subscription for Google user: {user.get('email', 'unknown')}")
                    # Note: Not deleting user here as they're already authenticated via Google
                else:
                    logger.info(f"Subscription initialized for new Google user: {user.get('email', 'unknown')}")
            except Exception as e:
                logger.error(f"Error initializing subscription for Google user: {str(e)}")
        
        # Send emails for new Google users in background threads (non-blocking)
        if is_new_user:
            import threading
            from datetime import datetime as _dt
            _user_email = user['email']
            _user_name = user.get('name', user.get('first_name', _user_email.split('@')[0]))
            _registration_date = _dt.now().strftime('%B %d, %Y at %I:%M %p')

            def _send_welcome():
                try:
                    email_service.send_welcome_email(user_email=_user_email, user_name=_user_name)
                    logger.info(f"Welcome email sent to new Google user: {_user_email}")
                except Exception as e:
                    logger.error(f"Failed to send welcome email to Google user {_user_email}: {str(e)}")

            def _send_company_notification():
                try:
                    email_service.send_new_user_notification_to_company(
                        user_email=_user_email,
                        user_name=_user_name,
                        registration_date=_registration_date,
                        registration_method="Google OAuth"
                    )
                    logger.info(f"Company notification email sent for new Google user: {_user_email}")
                except Exception as e:
                    logger.error(f"Failed to send company notification for Google user {_user_email}: {str(e)}")

            threading.Thread(target=_send_welcome, daemon=True).start()
            threading.Thread(target=_send_company_notification, daemon=True).start()
        
        # Create access and refresh tokens with current timestamp
        import time
        current_time = int(time.time())
        logger.info(f"Creating JWT tokens at timestamp: {current_time}")
        
        access_token = create_access_token(identity=str(user['id']))  # Changed from '_id' to 'id'
        refresh_token = create_refresh_token(identity=str(user['id']))  # Changed from '_id' to 'id'
        
        logger.info("JWT tokens created successfully for Google user")
        
        # Store refresh token
        _get_user_service().store_refresh_token(user['id'], refresh_token)  # Changed from '_id' to 'id'
        
        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": str(user['id']),  # Changed from '_id' to 'id'
                "email": user['email'],
                "name": user.get('name', ''),
                "profile_picture": user.get('profile_picture', ''),
                "is_google_user": True
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in Google authentication: {str(e)}", exc_info=True)
        return jsonify({"error": "Authentication failed", "details": str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
@validate_json_request
def login():
    """Login user"""
    data = request.get_json()
    
    # Validate required fields
    if 'username_or_email' not in data or 'password' not in data:
        return jsonify({"error": "Username/email and password are required"}), 400
    
    # Authenticate user
    success, message, user_data = _get_user_service().login_user(
        username_or_email=data['username_or_email'],
        password=data['password']
    )
    
    if not success:
        return jsonify({"error": message}), 401
    
    # Handle session conversion if session_id is provided
    session_id = data.get('session_id')
    if session_id:
        # Convert anonymous session to authenticated session
        conversion_success = session_service.convert_to_authenticated_session(session_id, user_data['id'])
        if not conversion_success:
            logger.warning(f"Failed to convert session {session_id} for user {user_data['id']}")
    
    # Generate tokens
    access_token = create_access_token(identity=str(user_data['id']))
    refresh_token = create_refresh_token(identity=str(user_data['id']))
    
    # Store refresh token
    _get_user_service().store_refresh_token(user_data['id'], refresh_token)

    # Create login notification
    try:
        notification_service.notify_login(user_id=str(user_data['id']))
    except Exception as e:
        logger.warning(f"Failed to create login notification: {str(e)}")

    response_data = {
        "message": "Login successful",
        "user": user_data,
        "access_token": access_token,
        "refresh_token": refresh_token
    }

    # Include session info if conversion happened
    if session_id:
        response_data["session_converted"] = conversion_success
        if conversion_success:
            response_data["session_id"] = session_id

    return jsonify(response_data), 200

@app.route('/api/auth/refresh', methods=['POST'])
@validate_json_request
def refresh():
    """Refresh access token"""
    data = request.get_json()
    
    if 'refresh_token' not in data:
        return jsonify({"error": "Refresh token is required"}), 400
    
    # Validate refresh token
    user_id = _get_user_service().validate_refresh_token(data['refresh_token'])
    
    if not user_id:
        return jsonify({"error": "Invalid or expired refresh token"}), 401
    
    # Get user data
    user_data = _get_user_service().get_user_by_id(user_id)
    
    if not user_data:
        return jsonify({"error": "User not found"}), 404
    
    # Generate new access token
    access_token = create_access_token(identity=user_id)
    
    return jsonify({
        "access_token": access_token,
        "user": user_data
    }), 200

@app.route('/api/auth/logout', methods=['POST'])
@validate_json_request
@jwt_required(optional=True)
def logout():
    """Logout user"""
    data = request.get_json()

    if 'refresh_token' not in data:
        return jsonify({"error": "Refresh token is required"}), 400

    # Get user ID before invalidating token (for notification)
    user_id = get_jwt_identity()

    # Invalidate refresh token
    success = _get_user_service().invalidate_refresh_token(data['refresh_token'])

    if success:
        # Create logout notification if user ID is available
        if user_id:
            try:
                notification_service.notify_logout(user_id=user_id)
            except Exception as e:
                logger.warning(f"Failed to create logout notification: {str(e)}")

        return jsonify({"message": "Logout successful"}), 200
    else:
        return jsonify({"error": "Invalid refresh token"}), 400

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user data"""
    user_id = get_jwt_identity()
    user_data = _get_user_service().get_user_by_id(user_id)
    
    if not user_data:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({"user": user_data}), 200

@app.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
@validate_json_request
def update_profile():
    """Update user profile"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    success, message, user_data = _get_user_service().update_user_profile(user_id, data)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({
        "message": "Profile updated successfully",
        "user": user_data
    }), 200

# Password Reset Endpoints
@app.route('/api/auth/forgot-password', methods=['POST'])
@validate_json_request
def forgot_password():
    """Initiate password reset process by sending OTP to email"""
    data = request.get_json()
    username_or_email = data.get('username_or_email', '').strip()
    
    if not username_or_email:
        return jsonify({"error": "Username or email is required"}), 400
    
    # Create OTP for password reset
    success, message, otp = _get_user_service().create_password_reset_otp(username_or_email)
    
    if not success:
        return jsonify({"error": message}), 400
    
    # Get user details for email
    user = _get_user_service().users.find_one({
        "$or": [
            {"username": username_or_email},
            {"email": username_or_email}
        ]
    })
    
    if user and otp:
        # Send OTP email
        email_sent = email_service.send_password_reset_otp(
            user['email'], 
            user.get('username', 'User'), 
            otp
        )
        
        if email_sent:
            logger.info(f"Password reset OTP sent to {user['email']}")
            return jsonify({
                "message": "Password reset OTP sent to your email",
                "email_sent": True
            }), 200
        else:
            logger.error(f"Failed to send password reset email to {user['email']}")
            return jsonify({
                "message": "OTP generated but email failed to send. Please try again.",
                "email_sent": False
            }), 500
    
    return jsonify({"error": "Failed to process password reset request"}), 500

@app.route('/api/auth/verify-reset-otp', methods=['POST'])
@validate_json_request
def verify_reset_otp():
    """Verify password reset OTP"""
    data = request.get_json()
    username_or_email = data.get('username_or_email', '').strip()
    otp = data.get('otp', '').strip()
    
    if not username_or_email or not otp:
        return jsonify({"error": "Username/email and OTP are required"}), 400
    
    # Verify OTP
    success, message, user_id = _get_user_service().verify_password_reset_otp(username_or_email, otp)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({
        "message": message,
        "user_id": user_id,
        "otp_verified": True
    }), 200

@app.route('/api/auth/reset-password', methods=['POST'])
@validate_json_request
def reset_password():
    """Reset password with OTP verification"""
    data = request.get_json()
    user_id = data.get('user_id', '').strip()
    new_password = data.get('new_password', '').strip()
    otp = data.get('otp', '').strip()
    
    if not user_id or not new_password or not otp:
        return jsonify({"error": "User ID, new password, and OTP are required"}), 400
    
    # Validate password strength
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400
    
    # Reset password with verification
    success, message = _get_user_service().reset_password_with_verification(user_id, new_password, otp)
    
    if not success:
        return jsonify({"error": message}), 400
    
    # Clean up expired OTPs
    _get_user_service().cleanup_expired_otps()
    
    logger.info(f"Password reset completed for user ID: {user_id}")

    # Create notification for password change
    try:
        notification_service.notify_password_change(user_id=user_id, success=True)
    except Exception as e:
        logger.error(f"Failed to create password change notification: {str(e)}")

    return jsonify({
        "message": message,
        "password_reset": True
    }), 200

# Notification API Endpoints
@app.route('/api/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    """Get user notifications with pagination"""
    try:
        user_id = get_jwt_identity()
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 50, type=int)
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'

        result = notification_service.get_user_notifications(
            user_id=user_id,
            page=page,
            limit=limit,
            unread_only=unread_only
        )

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching notifications: {str(e)}")
        return jsonify({"error": "Failed to fetch notifications"}), 500


@app.route('/api/notifications/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """Get count of unread notifications"""
    try:
        user_id = get_jwt_identity()
        count = notification_service.get_unread_count(user_id)

        return jsonify({"count": count}), 200

    except Exception as e:
        logger.error(f"Error fetching unread count: {str(e)}")
        return jsonify({"error": "Failed to fetch unread count", "count": 0}), 500


@app.route('/api/notifications/<notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_notification_as_read(notification_id):
    """Mark a notification as read"""
    try:
        user_id = get_jwt_identity()
        success = notification_service.mark_as_read(notification_id, user_id)

        if success:
            return jsonify({"message": "Notification marked as read"}), 200
        else:
            return jsonify({"error": "Notification not found"}), 404

    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        return jsonify({"error": "Failed to mark notification as read"}), 500


@app.route('/api/notifications/read-all', methods=['PUT'])
@jwt_required()
def mark_all_notifications_as_read():
    """Mark all notifications as read"""
    try:
        user_id = get_jwt_identity()
        count = notification_service.mark_all_as_read(user_id)

        return jsonify({
            "message": f"Marked {count} notifications as read",
            "count": count
        }), 200

    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        return jsonify({"error": "Failed to mark all notifications as read"}), 500


@app.route('/api/notifications/<notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        user_id = get_jwt_identity()
        success = notification_service.delete_notification(notification_id, user_id)

        if success:
            return jsonify({"message": "Notification deleted"}), 200
        else:
            return jsonify({"error": "Notification not found"}), 404

    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        return jsonify({"error": "Failed to delete notification"}), 500


@app.route('/api/notifications/clear-all', methods=['DELETE'])
@jwt_required()
def clear_all_notifications():
    """Delete all notifications for the user"""
    try:
        user_id = get_jwt_identity()
        count = notification_service.clear_all_notifications(user_id)

        return jsonify({
            "message": f"Deleted {count} notifications",
            "count": count
        }), 200

    except Exception as e:
        logger.error(f"Error clearing all notifications: {str(e)}")
        return jsonify({"error": "Failed to clear all notifications"}), 500


# Feedback API Endpoints
@app.route('/api/feedback/submit', methods=['POST'])
@validate_json_request
def submit_feedback():
    """Submit dynamic feedback form"""
    try:
        data = request.get_json()
        
        # Extract user IP and user agent for tracking
        user_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR'))
        user_agent = request.headers.get('User-Agent')
        
        # Add metadata to submission
        data['ip_address'] = user_ip
        data['user_agent'] = user_agent
        
        # Validate required fields
        user_info = data.get('user_info', {})
        if not user_info.get('email'):
            return jsonify({"error": "User email is required"}), 400
        
        if not user_info.get('name'):
            return jsonify({"error": "User name is required"}), 400
        
        # Validate WealthWest specific feedback fields
        required_fields = ['trading_learning', 'ai_features', 'interface_usability', 'value_recommendation']
        has_response = any(data.get(field, '').strip() for field in required_fields)
        
        if not has_response:
            return jsonify({"error": "At least one feedback response is required"}), 400
        
        # Submit feedback
        result = get_feedback_service().submit_feedback(data)
        
        if result['success']:
            # Send notification emails
            try:
                # Send confirmation email to user
                user_email = user_info.get('email')
                user_name = user_info.get('name')
                form_type = data.get('form_type', 'General Feedback')
                
                # Send user confirmation email
                _send_feedback_confirmation_email(user_email, user_name, "WelthWest Feedback", result['submission_id'])
                
                # Send notification to company
                _send_feedback_notification_email(user_info, data, result['submission_id'])
                
                logger.info(f"Feedback notification emails sent for submission {result['submission_id']}")
            except Exception as e:
                logger.error(f"Failed to send feedback emails: {str(e)}")
                # Don't fail the request if email sending fails
            
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        return jsonify({
            "error": "Failed to submit feedback. Please try again later."
        }), 500

@app.route('/api/feedback/list', methods=['GET'])
@jwt_required()
def get_feedback_list():
    """Get feedback submissions (Admin only)"""
    try:
        # Get current user
        current_user = get_jwt_identity()
        user_data = _get_user_service().get_user_by_email(current_user)
        
        # Check if user is admin (you might want to add admin role check here)
        if not user_data or user_data.get('role') != 'admin':
            return jsonify({"error": "Admin access required"}), 403
        
        # Get query parameters
        form_type = request.args.get('form_type')
        user_email = request.args.get('user_email')
        limit = min(int(request.args.get('limit', 50)), 100)  # Max 100 results
        skip = int(request.args.get('skip', 0))
        
        # Get feedback submissions
        submissions = get_feedback_service().get_feedback_submissions(
            form_type=form_type,
            user_email=user_email,
            limit=limit,
            skip=skip
        )
        
        return jsonify({
            "submissions": submissions,
            "count": len(submissions)
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving feedback list: {str(e)}")
        return jsonify({
            "error": "Failed to retrieve feedback submissions"
        }), 500

@app.route('/api/feedback/<submission_id>', methods=['GET'])
@jwt_required()
def get_feedback_by_id(submission_id):
    """Get specific feedback submission (Admin only)"""
    try:
        # Get current user
        current_user = get_jwt_identity()
        user_data = _get_user_service().get_user_by_email(current_user)
        
        # Check if user is admin
        if not user_data or user_data.get('role') != 'admin':
            return jsonify({"error": "Admin access required"}), 403
        
        # Get feedback submission
        submission = get_feedback_service().get_feedback_by_id(submission_id)
        
        if not submission:
            return jsonify({"error": "Feedback submission not found"}), 404
        
        return jsonify(submission), 200
        
    except Exception as e:
        logger.error(f"Error retrieving feedback: {str(e)}")
        return jsonify({
            "error": "Failed to retrieve feedback submission"
        }), 500

@app.route('/api/feedback/statistics', methods=['GET'])
@jwt_required()
def get_feedback_statistics():
    """Get feedback statistics (Admin only)"""
    try:
        # Get current user
        current_user = get_jwt_identity()
        user_data = _get_user_service().get_user_by_email(current_user)
        
        # Check if user is admin
        if not user_data or user_data.get('role') != 'admin':
            return jsonify({"error": "Admin access required"}), 403
        
        # Get statistics
        form_type = request.args.get('form_type')
        stats = get_feedback_service().get_feedback_statistics(form_type=form_type)
        
        return jsonify(stats), 200
        
    except Exception as e:
        logger.error(f"Error retrieving feedback statistics: {str(e)}")
        return jsonify({
            "error": "Failed to retrieve feedback statistics"
        }), 500

def _send_feedback_confirmation_email(user_email: str, user_name: str, form_type: str, submission_id: str):
    """Send confirmation email to user who submitted feedback"""
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Feedback Received</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: #10B981; color: white; padding: 20px; text-align: center; }
            .content { padding: 20px; background: #f9f9f9; }
            .footer { background: #333; color: white; padding: 20px; text-align: center; }
            .success { color: #10B981; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Thank You for Your Feedback!</h1>
            </div>
            
            <div class="content">
                <h2>Hi {{ user_name }},</h2>
                <p class="success">We've successfully received your feedback!</p>
                
                <p>Thank you for taking the time to share your thoughts with us. Your feedback is invaluable in helping us improve our services.</p>
                
                <div style="background: white; padding: 15px; margin: 15px 0; border: 1px solid #ddd; border-radius: 5px;">
                    <p><strong>Feedback Type:</strong> {{ form_type }}</p>
                    <p><strong>Submission ID:</strong> {{ submission_id }}</p>
                    <p><strong>Submitted On:</strong> {{ current_date }}</p>
                </div>
                
                <p>We review all feedback carefully and will get back to you if needed. If your feedback requires immediate attention, please contact our support team.</p>
                
                <p>Thank you for helping us serve you better!</p>
            </div>
            
            <div class="footer">
                <p>Best regards,</p>
                <p>The WelthWest Team</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    context = {
        'user_name': user_name,
        'form_type': form_type,
        'submission_id': submission_id,
        'current_date': datetime.now().strftime('%B %d, %Y at %I:%M %p')
    }
    
    subject = f"Your voice is in the model. Expect smarter updates, faster."
    email_service.send_email(user_email, subject, template, context)

def _send_feedback_notification_email(user_info: Dict[str, Any], feedback_data: Dict[str, Any], submission_id: str):
    """Send notification email to company about new feedback"""
    # Get company email from environment or use default
    company_email = os.environ.get('COMPANY_EMAIL', os.environ.get('MAIL_USERNAME'))
    
    if not company_email:
        logger.warning("No company email configured for feedback notifications")
        return
    
    template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>New Feedback Submission</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { background: #4F46E5; color: white; padding: 20px; text-align: center; }
            .content { padding: 20px; background: #f9f9f9; }
            .user-info { background: white; padding: 15px; margin: 15px 0; border: 1px solid #ddd; border-radius: 5px; }
            .response { background: white; padding: 15px; margin: 10px 0; border-left: 4px solid #4F46E5; }
            .footer { background: #333; color: white; padding: 20px; text-align: center; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📝 New Feedback Received</h1>
            </div>
            
            <div class="content">
                <h2>New {{ form_type }} Submission</h2>
                
                <div class="user-info">
                    <h3>User Information:</h3>
                    <p><strong>Name:</strong> {{ user_info.name }}</p>
                    <p><strong>Email:</strong> {{ user_info.email }}</p>
                    {% if user_info.phone %}
                    <p><strong>Phone:</strong> {{ user_info.phone }}</p>
                    {% endif %}
                    <p><strong>Submission ID:</strong> {{ submission_id }}</p>
                    <p><strong>Submitted On:</strong> {{ current_date }}</p>
                </div>
                
                <h3>WealthWest Feedback Responses:</h3>
                {% if trading_learning %}
                <div class="response">
                    <p><strong>Q:</strong> Does WealthWest help you learn trading? What resources would enhance your experience?</p>
                    <p><strong>A:</strong> {{ trading_learning }}</p>
                </div>
                {% endif %}
                
                {% if ai_features %}
                <div class="response">
                    <p><strong>Q:</strong> How effective are WealthWest's AI features (backtesting, signals, sentiment analysis) for learning or trading? Share examples or suggestions.</p>
                    <p><strong>A:</strong> {{ ai_features }}</p>
                </div>
                {% endif %}
                
                {% if interface_usability %}
                <div class="response">
                    <p><strong>Q:</strong> How user-friendly is WealthWest's interface (dashboards, strategy builder)? Suggest improvements.</p>
                    <p><strong>A:</strong> {{ interface_usability }}</p>
                </div>
                {% endif %}
                
                {% if value_recommendation %}
                <div class="response">
                    <p><strong>Q:</strong> What would make WealthWest more valuable, and would you recommend it or pay for basic/pro/Enterprise tiers ranging from rs 299 to rs 1999?</p>
                    <p><strong>A:</strong> {{ value_recommendation }}</p>
                </div>
                {% endif %}
                
                <p><em>Please review and follow up as appropriate.</em></p>
            </div>
            
            <div class="footer">
                <p>WelthWest Feedback</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    context = {
        'user_info': user_info,
        'trading_learning': feedback_data.get('trading_learning'),
        'ai_features': feedback_data.get('ai_features'),
        'interface_usability': feedback_data.get('interface_usability'),
        'value_recommendation': feedback_data.get('value_recommendation'),
        'submission_id': submission_id,
        'current_date': datetime.now().strftime('%B %d, %Y at %I:%M %p')
    }
    
    subject = f"New WealthWest Feedback - {user_info.get('name', 'Unknown User')}"
    email_service.send_email(company_email, subject, template, context)

# Anonymous Chat endpoint with session tracking
@app.route('/api/chat', methods=['POST'])
@validate_json_request
@anon_or_auth_feature_limit('welth-ai-assistant')
def chat_with_ai():
    """Chat with AI with automatic anonymous trial limiting"""
    try:
        data = request.get_json()

        # Process the chat message
        message = data.get('message', '')
        if not message:
            return jsonify({"error": "Message is required"}), 400

        model = data.get('model', 'openrouter')  # Default to OpenRouter

        # Validate model selection
        valid_models = ['openai', 'claude', 'openrouter', 'llama']
        if model not in valid_models:
            model = 'openrouter'  # Fallback to default

        # Check if the model's API key is configured
        api_key_map = {
            'openai': os.environ.get('OPENAI_API_KEY'),
            'claude': os.environ.get('CLAUDE_API_KEY'),
            'openrouter': os.environ.get('OPENROUTER_API_KEY')
        }

        # For llama or if the selected model's API key is not configured, use available model
        if model == 'llama' or not api_key_map.get(model):
            # Find first available model
            for available_model, key in api_key_map.items():
                if key:
                    model = available_model
                    break
            else:
                # If no API keys configured, use llama (simulated)
                model = 'llama'

        # Process the chat query
        ai_response = get_ai_service().process_chat_query(message, model)

        # Convert any numpy/pandas types to native Python types for JSON serialization
        def convert_to_serializable(obj):
            """Convert numpy/pandas types to JSON serializable types"""
            if obj is None:
                return None

            # Handle basic containers first
            if isinstance(obj, dict):
                return {k: convert_to_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [convert_to_serializable(v) for v in obj]

            # Check if it's a numpy/pandas type by string name to avoid import issues
            type_name = type(obj).__name__
            module_name = type(obj).__module__

            # Handle numpy types
            if 'numpy' in module_name or type_name.startswith('int') or type_name.startswith('float'):
                if 'int' in type_name or 'Int' in type_name:
                    return int(obj)
                elif 'float' in type_name or 'Float' in type_name:
                    return float(obj)
                elif 'ndarray' in type_name:
                    return obj.tolist()

            # Handle pandas types
            if 'pandas' in module_name:
                try:
                    import pandas as pd
                    if pd.isna(obj):
                        return None
                except ImportError:
                    pass

                # Convert pandas Series/DataFrame to dict/list
                if hasattr(obj, 'to_dict'):
                    return convert_to_serializable(obj.to_dict())
                elif hasattr(obj, 'tolist'):
                    return convert_to_serializable(obj.tolist())

            # For any other object that might not be serializable, convert to string
            try:
                import json
                json.dumps(obj)  # Test if it's JSON serializable
                return obj
            except (TypeError, OverflowError):
                return str(obj)

        # Clean the entire AI response for JSON serialization
        clean_ai_response = convert_to_serializable(ai_response)

        # Get usage info if available (set by decorator)
        usage_info = getattr(g, '_anon_feature_usage', None)

        # Prepare response data with explicit type conversions
        response_data = {
            "response": str(clean_ai_response.get('analysis', 'Sorry, I could not process your request.')),
            "model": str(clean_ai_response.get('model', model)),
            "stock_data": clean_ai_response.get('stock_data', {}),
            "usage": usage_info
        }

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": "An unexpected error occurred",
            "details": str(e)
        }), 500

# NextGen AI Chat endpoint with multi-model orchestration
@app.route('/api/nextgenchat', methods=['POST'])
@validate_json_request
@feature_limit('welth-ai-assistant')
def nextgen_chat():
    """
    NextGen AI Chat endpoint with multi-model orchestration
    Supports both authenticated users and anonymous sessions with trial limits
    """
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        conversation_history = data.get('conversation_history', [])

        if not message:
            return jsonify({"error": "Message is required"}), 400

        # Check if user is authenticated (decorator already handled trial limits)
        user_id = None
        is_authenticated = hasattr(g, 'current_user') and g.current_user is not None
        if is_authenticated:
            user_id = g.current_user.get('id') or g.current_user.get('email')
            logger.info(f"NextGen Chat request from authenticated user: {user_id}")

        # Process the query through NextGen AI Orchestrator
        logger.info(f"Processing NextGen query: {message[:100]}...")

        # Use async processing
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            from services.nextgen_ai_service import get_nextgen_orchestrator
            ai_response = loop.run_until_complete(
                get_nextgen_orchestrator().process_query(message, conversation_history)
            )
        finally:
            loop.close()

        logger.info(f"NextGen AI response type: {ai_response.get('query_type')}, model: {ai_response.get('model_used')}")
        logger.info(f"Analysis buttons: {ai_response.get('analysis_buttons')}")
        
        # Save chat history for authenticated users
        if is_authenticated and user_id:
            try:
                # Save to nextgen_chat_sessions collection
                from services.user_service import get_db_connection
                db = get_db_connection()
                nextgen_collection = db.nextgen_chat_sessions
                
                chat_entry = {
                    "user_id": user_id,
                    "message": message,
                    "response": ai_response.get('response', ''),
                    "query_type": ai_response.get('query_type', 'general'),
                    "model_used": ai_response.get('model_used', 'unknown'),
                    "confidence": ai_response.get('confidence', 0.0),
                    "stock_data": ai_response.get('stock_data'),
                    "sentiment": ai_response.get('sentiment'),
                    "timestamp": datetime.utcnow(),
                    "session_info": {
                        "conversation_length": len(conversation_history) + 1
                    }
                }
                
                nextgen_collection.insert_one(chat_entry)
                logger.info(f"Saved NextGen chat entry for user: {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to save NextGen chat history: {e}")
                # Continue without failing the request
        
        # Get usage info from decorator (for anonymous users)
        usage_info = getattr(g, '_anon_feature_usage', None)

        # Prepare response
        response_data = {
            "response": ai_response.get('response', 'Sorry, I could not process your request.'),
            "query_type": ai_response.get('query_type', 'general'),
            "model_used": ai_response.get('model_used', 'unknown'),
            "confidence": ai_response.get('confidence', 0.0),
            "stock_data": ai_response.get('stock_data'),
            "sentiment": ai_response.get('sentiment'),
            "analysis_buttons": ai_response.get('analysis_buttons', {'show_buttons': False, 'suggested_tools': []}),
            "requires_login": False
        }

        # Add usage info from decorator
        if usage_info:
            response_data["usage"] = usage_info

        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error in NextGen chat endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": "An unexpected error occurred",
            "details": str(e),
            "model_used": "error"
        }), 500


# Get current anonymous usage for all features
@app.route('/api/usage/anonymous', methods=['GET'])
def get_anonymous_usage():
    """Get current anonymous usage counts for all features"""
    try:
        from services.usage_service import get_all_feature_usage, is_redis_available

        # Get feature-specific limits from config
        ai_analysis_limit = current_app.config.get('ANON_AI_ANALYSIS_LIMIT', 10)
        backtest_limit = current_app.config.get('ANON_BACKTEST_LIMIT', 10)
        chat_limit = current_app.config.get('ANON_CHAT_LIMIT', 5)

        if not is_redis_available():
            # Redis not available, return default limits
            return jsonify({
                "status": "unavailable",
                "message": "Usage tracking unavailable",
                "features": {
                    "ai-market-analysis": {"remaining": ai_analysis_limit, "limit": ai_analysis_limit, "used": 0},
                    "backtest-beta": {"remaining": backtest_limit, "limit": backtest_limit, "used": 0},
                    "welth-ai-assistant": {"remaining": chat_limit, "limit": chat_limit, "used": 0}
                }
            }), 200

        # Get session ID from cookie
        cookie_name = current_app.config.get('ANON_SESSION_COOKIE', 'ww_session_id')
        session_id = request.cookies.get(cookie_name)

        # Get feature-specific limits from config
        ai_analysis_limit = current_app.config.get('ANON_AI_ANALYSIS_LIMIT', 10)
        backtest_limit = current_app.config.get('ANON_BACKTEST_LIMIT', 10)
        chat_limit = current_app.config.get('ANON_CHAT_LIMIT', 5)

        if not session_id:
            # No session yet, return full limits
            return jsonify({
                "status": "no_session",
                "features": {
                    "ai-market-analysis": {"remaining": ai_analysis_limit, "limit": ai_analysis_limit, "used": 0},
                    "backtest-beta": {"remaining": backtest_limit, "limit": backtest_limit, "used": 0},
                    "welth-ai-assistant": {"remaining": chat_limit, "limit": chat_limit, "used": 0}
                }
            }), 200

        # Get usage for all features
        all_usage = get_all_feature_usage(session_id)

        # Calculate remaining for each feature
        features = {
            "ai-market-analysis": {
                "used": all_usage.get("ai-market-analysis", 0),
                "limit": ai_analysis_limit,
                "remaining": max(0, ai_analysis_limit - all_usage.get("ai-market-analysis", 0))
            },
            "backtest-beta": {
                "used": all_usage.get("backtest-beta", 0),
                "limit": backtest_limit,
                "remaining": max(0, backtest_limit - all_usage.get("backtest-beta", 0))
            },
            "welth-ai-assistant": {
                "used": all_usage.get("welth-ai-assistant", 0),
                "limit": chat_limit,
                "remaining": max(0, chat_limit - all_usage.get("welth-ai-assistant", 0))
            }
        }

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "features": features
        }), 200

    except Exception as e:
        logger.error(f"Error getting anonymous usage: {str(e)}")
        return jsonify({"error": str(e)}), 500

# AI Chat Service Implementation
class AIModelService:
    """Service for handling interactions with various AI models"""
    
    def __init__(self):
        # Load API keys from environment variables
        self.openai_api_key = os.environ.get('OPENAI_API_KEY', '')
        self.openrouter_api_key = os.environ.get('OPENROUTER_API_KEY', '')
        self.claude_api_key = os.environ.get('CLAUDE_API_KEY', '')
        
        # Default system prompt for financial context
        self.default_system_prompt = """
        You are a helpful AI assistant for a financial platform called WelthWest. 
        Your primary role is to provide accurate information and insights about stocks, 
        market trends, investment strategies, and financial concepts.
        
        When discussing stocks:
        - Provide balanced perspectives on potential investments
        - Explain market concepts clearly without jargon
        - Never make specific buy/sell recommendations
        - Always remind users that all investments carry risk
        - Clarify that you're providing information, not financial advice
        
        If asked about specific stocks, provide general information about the company, 
        its sector, and recent market performance if available.
        """
    
    def extract_stock_symbols(self, query: str) -> list:
        """
        Extract potential stock symbols from the query
        This is a simple implementation - in production, you'd want a more robust approach
        """
        # Common Indian stock symbols to look for
        common_symbols = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
            'SBIN', 'HINDUNILVR', 'BHARTIARTL', 'ITC', 'KOTAKBANK',
            'NIFTY', 'SENSEX', 'BANKNIFTY'
        ]
        
        # Convert query to uppercase for case-insensitive matching
        upper_query = query.upper()
        
        # Check for common symbols in the query
        found_symbols = []
        for symbol in common_symbols:
            if symbol in upper_query.split():
                # For indices, handle special formatting
                if symbol == 'NIFTY':
                    found_symbols.append('^NSEI')
                elif symbol == 'SENSEX':
                    found_symbols.append('^BSESN')
                elif symbol == 'BANKNIFTY':
                    found_symbols.append('^NSEBANK')
                else:
                    # For regular stocks, add .NS suffix for NSE
                    found_symbols.append(f"{symbol}.NS")
        
        return found_symbols
    
    def get_stock_data_for_query(self, query: str) -> Dict[str, Any]:
        """
        Extract stock symbols from query and fetch their data
        """
        symbols = self.extract_stock_symbols(query)
        stock_data = {}
        
        if symbols:
            try:
                # Get live data for the symbols
                live_data = get_live_data(symbols)
                
                # Process the data into a more usable format
                for symbol in symbols:
                    if symbol in live_data.index:
                        data = live_data.loc[symbol]
                        stock_data[symbol] = {
                            'current_price': data.get('price'),
                            'change': {
                                'value': data.get('previousClose', 0) - data.get('price', 0),
                                'percent': ((data.get('price', 0) / data.get('previousClose', 0)) - 1) * 100 if data.get('previousClose', 0) else 0
                            },
                            'volume': data.get('volume'),
                            'market_cap': data.get('marketCap'),
                            'day_range': {
                                'low': data.get('dayLow'),
                                'high': data.get('dayHigh')
                            }
                        }
            except Exception as e:
                logger.error(f"Error fetching stock data: {str(e)}")
        
        return stock_data
    
    def chat_with_llama(self, query: str) -> Dict[str, Any]:
        """
        Simulate a response from a local Llama model
        In production, you would connect to an actual Llama model API or local instance
        """
        # This is a mock implementation
        response = {
            "analysis": f"Based on your query about {query}, I can provide some general information. "
                       f"This is a simulated response as if from a Llama model. "
                       f"In a real implementation, this would connect to an actual Llama model API or local instance. "
                       f"For specific financial advice, please consult with a financial advisor.",
            "model": "llama-simulated"
        }
        
        return response
    
    def chat_with_openai(self, query: str) -> Dict[str, Any]:
        """
        Send query to OpenAI API and get response
        """
        if not self.openai_api_key:
            return {"analysis": "OpenAI API key not configured. Please contact support.", "model": "openai-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": "gpt-3.5-turbo"
                }
            else:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from OpenAI. Status code: {response.status_code}", "model": "openai-error"}
                
        except Exception as e:
            logger.error(f"Exception in OpenAI chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "openai-error"}
    
    def chat_with_openrouter(self, query: str) -> Dict[str, Any]:
        """
        Send query to OpenRouter API and get response
        """
        if not self.openrouter_api_key:
            return {"analysis": "OpenRouter API key not configured. Please contact support.", "model": "openrouter-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "https://welthwest.com"  # Replace with your actual domain
            }
            
            payload = {
                "model": "anthropic/claude-3-opus",  # You can change this to any model supported by OpenRouter
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                used_model = result.get("model", "unknown")
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": used_model
                }
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from OpenRouter. Status code: {response.status_code}", "model": "openrouter-error"}
                
        except Exception as e:
            logger.error(f"Exception in OpenRouter chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "openrouter-error"}
    
    def chat_with_claude(self, query: str) -> Dict[str, Any]:
        """
        Send query to Anthropic's Claude API and get response
        """
        if not self.claude_api_key:
            return {"analysis": "Claude API key not configured. Please contact support.", "model": "claude-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.claude_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": "claude-3-opus-20240229",
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "analysis": result["content"][0]["text"],
                    "model": "claude-3-opus"
                }
            else:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from Claude. Status code: {response.status_code}", "model": "claude-error"}
                
        except Exception as e:
            logger.error(f"Exception in Claude chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "claude-error"}
    
    def process_chat_query(self, query: str, model: str = "llama", user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a chat query using the specified model
        """
        # Get any relevant stock data
        stock_data = self.get_stock_data_for_query(query)
        
        # Select the appropriate model handler
        if model == "openai":
            response = self.chat_with_openai(query)
        elif model == "openrouter":
            response = self.chat_with_openrouter(query)
        elif model == "claude":
            response = self.chat_with_claude(query)
        else:
            # Default to llama
            response = self.chat_with_llama(query)
        
        # Add stock data to the response
        response["stock_data"] = stock_data
        
        # In a production system, you might want to log this interaction
        if user_id:
            # Log the interaction for the user
            logger.info(f"Chat query from user {user_id}: {query}")
        
        return response

# AI service is lazily initialized via get_ai_service()

@app.route('/api/historical', methods=['GET'])
def historical_data():
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()
    period = request.args.get('period', default='1y', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    # Validate the ticker
    if not validate_ticker(ticker):
        return jsonify({"error": f"Invalid ticker symbol: {ticker}"}), 400
    
    try:
        data = get_historical_data(ticker, period, interval)
        # Convert DataFrame to dictionary for JSON serialization
        result = data.reset_index().to_dict(orient='records')
        return jsonify({
            "data": result, 
            "ticker": ticker, 
            "period": period, 
            "interval": interval
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ohlc', methods=['GET'])
def ohlc_data():
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()
    start_date = request.args.get('start_date', default=None, type=str)
    end_date = request.args.get('end_date', default=None, type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    # Validate the ticker
    if not validate_ticker(ticker):
        return jsonify({"error": f"Invalid ticker symbol: {ticker}"}), 400
    
    try:
        data = get_ohlc_data(ticker, start_date, end_date, interval)
        # Convert DataFrame to dictionary for JSON serialization
        result = data.reset_index().to_dict(orient='records')
        return jsonify({
            "data": result, 
            "ticker": ticker, 
            "start_date": start_date,
            "end_date": end_date,
            "interval": interval
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/live', methods=['GET'])
def live_data():
    try:
        ticker_input = request.args.get('tickers', default='RELIANCE', type=str).upper()
        ticker_list = [t.strip() for t in ticker_input.split(',')]
        
        logger.info(f"Live data request received for tickers: {ticker_list}")
        
        # Validate tickers
        valid_tickers = []
        invalid_tickers = []
        for ticker in ticker_list:
            if validate_ticker(ticker):
                valid_tickers.append(ticker)
            else:
                invalid_tickers.append(ticker)
        
        if not valid_tickers:
            logger.warning(f"No valid tickers found in request: {ticker_list}")
            return jsonify({
                "error": "No valid ticker symbols provided",
                "invalid_tickers": invalid_tickers
            }), 400
        
        logger.info(f"Fetching data for valid tickers: {valid_tickers}")
        data = get_live_data(valid_tickers)
        
        # Check for errors in the response
        error_tickers = []
        success_data = []
        
        for index, row in data.iterrows():
            if 'error' in row:
                error_tickers.append({
                    'ticker': index,
                    'error': row['error']
                })
            else:
                success_data.append({
                    'ticker': index,
                    **row.to_dict()
                })
        
        response = {
            "data": success_data,
            "valid_tickers": valid_tickers
        }
        
        if invalid_tickers:
            response["invalid_tickers"] = invalid_tickers
            
        if error_tickers:
            response["failed_tickers"] = error_tickers
            
        if not success_data:
            logger.error(f"Failed to fetch data for all tickers: {error_tickers}")
            return jsonify({
                "error": "Failed to fetch data for all tickers",
                "details": error_tickers
            }), 503
            
        logger.info(f"Successfully fetched data for {len(success_data)} tickers")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Unexpected error in live data endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": "An unexpected error occurred",
            "details": str(e)
        }), 500

@app.route('/api/validate', methods=['GET'])
def validate():
    ticker = request.args.get('ticker', type=str)
    
    if not ticker:
        return jsonify({"error": "No ticker symbol provided"}), 400
        
    is_valid = validate_ticker(ticker.upper())
    return jsonify({
        "ticker": ticker.upper(), 
        "valid": is_valid
    })

@app.route('/api/compare', methods=['GET'])
def compare_stocks():
    ticker_input = request.args.get('tickers', default='RELIANCE,TCS', type=str).upper()
    period = request.args.get('period', default='1y', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    ticker_list = [t.strip() for t in ticker_input.split(',')]
    
    # Validate tickers
    valid_tickers = []
    invalid_tickers = []
    for ticker in ticker_list:
        if validate_ticker(ticker):
            valid_tickers.append(ticker)
        else:
            invalid_tickers.append(ticker)
    
    if not valid_tickers:
        return jsonify({"error": "No valid ticker symbols provided"}), 400
    
    try:
        comparison_data = {}
        normalized_data = {}
        
        for ticker in valid_tickers:
            data = get_historical_data(ticker, period, interval)
            comparison_data[ticker] = data.reset_index().to_dict(orient='records')
            
            # Normalize data for better comparison
            norm_data = normalize_data(data, 'Close')
            normalized_data[ticker] = norm_data.reset_index().to_dict(orient='records')
        
        response = {
            "raw_data": comparison_data,
            "normalized_data": normalized_data,
            "valid_tickers": valid_tickers,
            "period": period,
            "interval": interval
        }
        
        if invalid_tickers:
            response["invalid_tickers"] = invalid_tickers
            
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    ticker = request.args.get('ticker', default='RELIANCE', type=str).upper()
    period = request.args.get('period', default='1y', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    
    # Validate the ticker
    if not validate_ticker(ticker):
        return jsonify({"error": f"Invalid ticker symbol: {ticker}"}), 400
    
    try:
        data = get_historical_data(ticker, period, interval)
        stats = calculate_statistics(data)
        
        return jsonify({
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "statistics": stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-indices', methods=['GET'])
def market_indices():
    """Get market indices data with performance monitoring.
    Optional query param: ?limit=N to return only the first N indices.
    """
    start_time = time.time()

    try:
        # Optional limit param (e.g. homepage only needs 4 indices)
        limit = request.args.get('limit', type=int)
        logger.info(f"Market indices request started (limit={limit})")
        indices_data = get_market_indices(limit=limit)

        # Calculate response time
        response_time = round(time.time() - start_time, 3)

        # Log performance metrics
        logger.info(f"Market indices request completed in {response_time} seconds")

        # Add performance metadata to response
        response_data = {
            "indices": indices_data,
            "performance": {
                "response_time_seconds": response_time,
                "timestamp": datetime.now().isoformat(),
                "cache_status": "hit" if response_time < 0.1 else "miss"
            }
        }
        
        # Add response time header for monitoring
        response = jsonify(response_data)
        response.headers['X-Response-Time'] = f"{response_time}s"
        
        return response
        
    except Exception as e:
        response_time = round(time.time() - start_time, 3)
        logger.error(f"Error in market indices endpoint after {response_time} seconds: {str(e)}")
        
        error_response = {
            "error": str(e),
            "performance": {
                "response_time_seconds": response_time,
                "timestamp": datetime.now().isoformat(),
                "status": "error"
            }
        }
        
        response = jsonify(error_response), 500
        response[0].headers['X-Response-Time'] = f"{response_time}s"
        
        return response

@app.route('/api/yahoo-suggest', methods=['GET'])
def yahoo_suggest():
    """
    Get stock suggestions based on search query
    Returns stocks that match the search query for autocomplete
    """
    try:
        query = request.args.get('q', '').strip().upper()
        
        if not query:
            return jsonify({"quotes": []}), 200
        
        if len(query) < 1:
            return jsonify({"quotes": []}), 200
        
        # Comprehensive list of Indian stocks
        indian_stocks = [
            # NIFTY 50 stocks
            {"symbol": "RELIANCE.NS", "name": "Reliance Industries Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TCS.NS", "name": "Tata Consultancy Services Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "HDFCBANK.NS", "name": "HDFC Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "INFY.NS", "name": "Infosys Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ICICIBANK.NS", "name": "ICICI Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "SBIN.NS", "name": "State Bank of India", "exchange": "NSE", "type": "equity"},
            {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ITC.NS", "name": "ITC Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "LT.NS", "name": "Larsen & Toubro Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "AXISBANK.NS", "name": "Axis Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "MARUTI.NS", "name": "Maruti Suzuki India Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ASIANPAINT.NS", "name": "Asian Paints Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TATAMOTORS.NS", "name": "Tata Motors Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "WIPRO.NS", "name": "Wipro Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "HCLTECH.NS", "name": "HCL Technologies Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical Industries Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TITAN.NS", "name": "Titan Company Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "NTPC.NS", "name": "NTPC Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ONGC.NS", "name": "Oil & Natural Gas Corporation Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "POWERGRID.NS", "name": "Power Grid Corporation of India Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "COALINDIA.NS", "name": "Coal India Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TECHM.NS", "name": "Tech Mahindra Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BAJAJFINSV.NS", "name": "Bajaj Finserv Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "NESTLEIND.NS", "name": "Nestle India Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ADANIPORTS.NS", "name": "Adani Ports and Special Economic Zone Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "GRASIM.NS", "name": "Grasim Industries Ltd", "exchange": "NSE", "type": "equity"},
            
            # Additional popular stocks
            {"symbol": "HDFC.NS", "name": "Housing Development Finance Corporation Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "JSWSTEEL.NS", "name": "JSW Steel Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TATASTEEL.NS", "name": "Tata Steel Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "HINDALCO.NS", "name": "Hindalco Industries Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BPCL.NS", "name": "Bharat Petroleum Corporation Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "HEROMOTOCO.NS", "name": "Hero MotoCorp Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TATACONSUM.NS", "name": "Tata Consumer Products Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "DIVISLAB.NS", "name": "Divi's Laboratories Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BRITANNIA.NS", "name": "Britannia Industries Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "CIPLA.NS", "name": "Cipla Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "SHREECEM.NS", "name": "Shree Cement Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "EICHERMOT.NS", "name": "Eicher Motors Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "APOLLOHOSP.NS", "name": "Apollo Hospitals Enterprise Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ADANIENT.NS", "name": "Adani Enterprises Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ADANIGREEN.NS", "name": "Adani Green Energy Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BAJAJ-AUTO.NS", "name": "Bajaj Auto Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "INDUSINDBK.NS", "name": "IndusInd Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "GODREJCP.NS", "name": "Godrej Consumer Products Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "MOTHERSUMI.NS", "name": "Motherson Sumi Systems Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "PIDILITIND.NS", "name": "Pidilite Industries Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "DABUR.NS", "name": "Dabur India Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "MARICO.NS", "name": "Marico Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "VEDL.NS", "name": "Vedanta Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "SAIL.NS", "name": "Steel Authority of India Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BANKBARODA.NS", "name": "Bank of Baroda", "exchange": "NSE", "type": "equity"},
            {"symbol": "PNB.NS", "name": "Punjab National Bank", "exchange": "NSE", "type": "equity"},
            {"symbol": "CANBK.NS", "name": "Canara Bank", "exchange": "NSE", "type": "equity"},
            {"symbol": "UNIONBANK.NS", "name": "Union Bank of India", "exchange": "NSE", "type": "equity"},
            {"symbol": "IOCL.NS", "name": "Indian Oil Corporation Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "HPCL.NS", "name": "Hindustan Petroleum Corporation Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "GAIL.NS", "name": "GAIL (India) Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "NMDC.NS", "name": "NMDC Ltd", "exchange": "NSE", "type": "equity"},
            
            # IT Sector
            {"symbol": "MPHASIS.NS", "name": "Mphasis Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "LTI.NS", "name": "L&T Infotech Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "MINDTREE.NS", "name": "Mindtree Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "COFORGE.NS", "name": "Coforge Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "PERSISTENT.NS", "name": "Persistent Systems Ltd", "exchange": "NSE", "type": "equity"},
            
            # Banking & Financial Services
            {"symbol": "YESBANK.NS", "name": "Yes Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "FEDERALBNK.NS", "name": "Federal Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BANDHANBNK.NS", "name": "Bandhan Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "RBLBANK.NS", "name": "RBL Bank Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "MUTHOOTFIN.NS", "name": "Muthoot Finance Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "CHOLAFIN.NS", "name": "Cholamandalam Investment and Finance Company Ltd", "exchange": "NSE", "type": "equity"},
            
            # Pharma & Healthcare
            {"symbol": "LUPIN.NS", "name": "Lupin Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "BIOCON.NS", "name": "Biocon Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "CADILAHC.NS", "name": "Cadila Healthcare Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "AUROPHARMA.NS", "name": "Aurobindo Pharma Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "TORNTPHARM.NS", "name": "Torrent Pharmaceuticals Ltd", "exchange": "NSE", "type": "equity"},
            {"symbol": "ALKEM.NS", "name": "Alkem Laboratories Ltd", "exchange": "NSE", "type": "equity"},
            
            # Market Indices
            {"symbol": "^NSEI", "name": "NIFTY 50", "exchange": "NSE", "type": "index"},
            {"symbol": "^BSESN", "name": "BSE SENSEX", "exchange": "BSE", "type": "index"},
            {"symbol": "^CNXIT", "name": "NIFTY IT", "exchange": "NSE", "type": "index"},
            {"symbol": "^NSEBANK", "name": "NIFTY BANK", "exchange": "NSE", "type": "index"},
        ]
        
        # Filter stocks based on query
        matching_stocks = []
        
        # First, find exact matches with symbol
        for stock in indian_stocks:
            symbol_base = stock["symbol"].replace(".NS", "").replace(".BO", "").replace("^", "")
            if symbol_base.startswith(query):
                matching_stocks.append(stock)
        
        # Then, find matches in company names
        for stock in indian_stocks:
            if stock not in matching_stocks:  # Avoid duplicates
                if query in stock["name"].upper():
                    matching_stocks.append(stock)
        
        # Limit results to top 10 matches
        matching_stocks = matching_stocks[:10]
        
        return jsonify({
            "quotes": matching_stocks
        })
        
    except Exception as e:
        logger.error(f"Error in yahoo-suggest: {str(e)}")
        return jsonify({"quotes": []}), 200

@app.route('/api/top-gainers-losers', methods=['GET'])
def top_gainers_losers():
    """
    Get top gainers and losers from NSE Nifty 50 index
    Data is automatically refreshed every 15 minutes during market hours
    """
    try:
        data = get_top_gainers_losers()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in top gainers/losers endpoint: {str(e)}")
        return jsonify({"error": str(e), "message": "Failed to fetch top gainers and losers data"}), 500


# AI Chat endpoint
@app.route('/api/market/chat', methods=['POST'])
@jwt_required()
@validate_json_request
@require_subscription_feature('llm_query')
def market_chat():
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({"error": "No query provided"}), 400
            
        query = data['query']
        model = data.get('model', 'openrouter')  # Default to OpenRouter
        user_id = data.get('user_id')
        
        # Log the request
        logger.info(f"Chat request - Model: {model}, Query: {query}, User: {user_id}")
        
        # Validate model selection
        valid_models = ['openai', 'claude', 'openrouter']
        if model not in valid_models:
            logger.warning(f"Invalid model requested: {model}")
            return jsonify({
                "error": f"Invalid model. Must be one of: {', '.join(valid_models)}",
                "available_models": valid_models
            }), 400
        
        # Check if the model's API key is configured
        api_key_map = {
            'openai': os.environ.get('OPENAI_API_KEY'),
            'claude': os.environ.get('CLAUDE_API_KEY'),
            'openrouter': os.environ.get('OPENROUTER_API_KEY')
        }
        
        if not api_key_map[model]:
            logger.error(f"API key not configured for model: {model}")
            return jsonify({
                "error": f"The {model} API key is not configured. Please try a different model or contact support.",
                "available_models": [m for m, key in api_key_map.items() if key]
            }), 503
        
        # Process the chat query
        response = get_ai_service().process_chat_query(query, model, user_id)
        
        # Check if the response indicates an error
        if not response.get('success', True):
            logger.error(f"Error in AI response: {response.get('analysis')}")
            return jsonify({
                "error": "Failed to get response from AI model",
                "details": response.get('analysis'),
                "model": response.get('model')
            }), 500
        
        # Save chat history for the user
        try:
            user_id_from_jwt = get_jwt_identity()
            chat_data = {
                'query': query,
                'response': response,
                'model': model,
                'timestamp': pd.Timestamp.now().isoformat()
            }
            result = _get_user_service().save_chat_history(user_id_from_jwt, chat_data)
            if result.get("success"):
                logger.info(f"Chat history saved for user {user_id_from_jwt}: {result.get('message')}")
            else:
                logger.warning(f"Failed to save chat history for user {user_id_from_jwt}: {result.get('message')}")
        except Exception as e:
            logger.warning(f"Failed to save chat history: {str(e)}")
        
        # Log successful response
        logger.info(f"Chat response generated successfully - Model: {response.get('model')}")
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": "An unexpected error occurred",
            "details": str(e),
            "analysis": "Sorry, I encountered an error processing your request."
        }), 500

# Health check endpoint (enhanced version is defined above)

# Technical Analysis Endpoints
@app.route('/api/indicators', methods=['GET'])
@jwt_required()
def get_indicators():
    """Get technical indicators for a stock"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        # Parse indicators from query string
        indicators = request.args.get('indicators', '').split(',')
        if not indicators or not indicators[0]:
            return jsonify({"error": "At least one indicator is required"}), 400
            
        # Parse parameters for indicators
        params = {}
        for key, value in request.args.items():
            if key not in ['ticker', 'indicators']:
                try:
                    params[key] = int(value)
                except ValueError:
                    params[key] = value
                    
        results = get_technical_analysis().calculate_indicators(ticker, indicators, params)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/screener', methods=['GET'])
@jwt_required()
def screen_stocks():
    """Screen stocks based on technical criteria"""
    try:
        criteria_str = request.args.get('criteria', '')
        if not criteria_str:
            return jsonify({"error": "Screening criteria are required"}), 400
            
        # Parse criteria string (e.g., "rsi<30,volume>1000000")
        criteria = {}
        try:
            for criterion in criteria_str.split(','):
                if '<' in criterion:
                    indicator, value = criterion.split('<')
                    criteria[indicator.strip()] = {"below": float(value)}
                elif '>' in criterion:
                    indicator, value = criterion.split('>')
                    criteria[indicator.strip()] = {"above": float(value)}
        except Exception as e:
            return jsonify({"error": f"Invalid criteria format: {str(e)}"}), 400
            
        results = get_technical_analysis().screen_stocks(criteria)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/intraday', methods=['GET'])
@jwt_required()
def get_intraday_data():
    """Get intraday data for a stock"""
    try:
        ticker = request.args.get('ticker')
        interval = request.args.get('interval', '5m')
        
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        valid_intervals = ['1m', '5m', '15m', '30m', '1h']
        if interval not in valid_intervals:
            return jsonify({"error": f"Invalid interval. Must be one of {valid_intervals}"}), 400
            
        df = get_historical_data(ticker, period="1d", interval=interval)
        if df.empty:
            return jsonify({"error": "No data available"}), 404
            
        # Convert DataFrame to list of dictionaries with datetime index as string
        data = []
        for idx, row in df.iterrows():
            entry = {
                "timestamp": idx.strftime('%Y-%m-%d %H:%M:%S'),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": float(row['Volume'])
            }
            data.append(entry)
            
        return jsonify({"data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/signals', methods=['GET'])
@jwt_required()
def get_trading_signals():
    """Get trading signals for a stock"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        signals = get_technical_analysis().get_trading_signals(ticker)
        return jsonify(signals)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/technical-analysis', methods=['GET'])
@jwt_required()
def get_comprehensive_technical_analysis():
    """Get comprehensive technical analysis for a stock with all indicators"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        # Get all indicators
        all_indicators = ['rsi', 'macd', 'bollinger', 'sma', 'ema', 'stochastic', 'atr', 'obv', 'vwap', 'pivot', 'fibonacci']
        
        # Get indicator data
        indicator_data = get_technical_analysis().calculate_indicators(ticker, all_indicators)
        
        # Get trading signals
        signals = get_technical_analysis().get_trading_signals(ticker)
        
        # Combine everything
        result = {
            "ticker": ticker,
            "timestamp": pd.Timestamp.now().isoformat(),
            "indicators": indicator_data,
            "signals": signals,
            "summary": {
                "overall_signal": signals.get("overall", {}).get("signal", "neutral"),
                "signal_strength": signals.get("overall", {}).get("strength", "weak"),
                "consensus_ratio": signals.get("overall", {}).get("consensus_ratio", 0),
                "total_indicators": signals.get("overall", {}).get("total_indicators", 0)
            }
        }
        
        # Save AI analysis result for the user
        try:
            user_id = get_jwt_identity()
            analysis_data = {
                'type': 'technical_analysis',
                'ticker': ticker,
                'result': result,
                'timestamp': pd.Timestamp.now().isoformat()
            }
            _get_user_service().save_ai_analysis_result(user_id, analysis_data)
            logger.info(f"Technical analysis result saved for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to save technical analysis result: {str(e)}")
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/levels', methods=['GET'])
@jwt_required()
def get_support_resistance():
    """Get support and resistance levels"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        levels = get_technical_analysis().get_support_resistance(ticker)
        return jsonify(levels)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/patterns', methods=['GET'])
@jwt_required()
def get_patterns():
    """Get chart patterns"""
    try:
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
            
        patterns = get_technical_analysis().identify_patterns(ticker)
        return jsonify(patterns)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/backtesting/generate-signals', methods=['POST'])
@jwt_required()
@validate_json_request
def generate_backtesting_signals():
    """Generate backtesting signals based on technical indicators"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['instrument', 'timeframe', 'start_date', 'end_date', 'indicators', 'combination_logic']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Validate timeframe format
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '1d']
        if data['timeframe'] not in valid_timeframes:
            return jsonify({"error": f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes)}"}), 400
            
        # Validate date formats
        try:
            pd.to_datetime(data['start_date'])
            pd.to_datetime(data['end_date'])
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
            
        # Validate combination logic
        if data['combination_logic'] not in ['AND', 'OR']:
            return jsonify({"error": "combination_logic must be either 'AND' or 'OR'"}), 400
            
        # Validate indicators array
        if not isinstance(data['indicators'], list) or len(data['indicators']) == 0:
            return jsonify({"error": "indicators must be a non-empty array"}), 400
            
        for indicator in data['indicators']:
            if not all(k in indicator for k in ['type', 'parameters', 'signal_condition', 'signal_type']):
                return jsonify({"error": "Each indicator must have type, parameters, signal_condition, and signal_type"}), 400
                
        # Get historical data
        df = get_ohlc_data(data['instrument'], data['timeframe'], data['start_date'], data['end_date'])
        if df.empty:
            return jsonify({"error": "No data available for the specified period"}), 404
            
        # Calculate indicator values and generate signals
        signals = []
        indicator_results = {}
        
        for indicator in data['indicators']:
            try:
                # Calculate indicator values
                indicator_type = indicator['type'].lower()
                params = indicator['parameters']
                
                if indicator_type == 'rsi':
                    values = get_technical_analysis()._calculate_rsi(df, params.get('period', 14))
                    indicator_results[indicator_type] = values
                elif indicator_type == 'macd':
                    macd_data = get_technical_analysis()._calculate_macd(
                        df,
                        params.get('fastperiod', 12),
                        params.get('slowperiod', 26),
                        params.get('signalperiod', 9)
                    )
                    indicator_results[indicator_type] = macd_data
                elif indicator_type == 'bollinger':
                    bb_data = get_technical_analysis()._calculate_bollinger_bands(df, params.get('period', 20))
                    indicator_results[indicator_type] = bb_data
                else:
                    return jsonify({"error": f"Unsupported indicator type: {indicator_type}"}), 400
                    
            except Exception as e:
                return jsonify({"error": f"Error calculating {indicator_type}: {str(e)}"}), 500
                
        # Generate signals based on indicator conditions
        for idx, row in df.iterrows():
            signal = None
            conditions_met = []
            
            for indicator in data['indicators']:
                indicator_type = indicator['type'].lower()
                condition = indicator['signal_condition']
                signal_type = indicator['signal_type']
                
                # Check conditions for each indicator
                condition_met = False
                
                if indicator_type == 'rsi':
                    rsi_value = indicator_results[indicator_type][idx]
                    if condition == 'oversold' and rsi_value < 30:
                        condition_met = signal_type == 'buy'
                    elif condition == 'overbought' and rsi_value > 70:
                        condition_met = signal_type == 'sell'
                        
                elif indicator_type == 'macd':
                    macd = indicator_results[indicator_type]['macd'][idx]
                    signal_line = indicator_results[indicator_type]['signal'][idx]
                    if condition == 'crossover' and macd > signal_line:
                        condition_met = signal_type == 'buy'
                    elif condition == 'crossunder' and macd < signal_line:
                        condition_met = signal_type == 'sell'
                        
                elif indicator_type == 'bollinger':
                    price = row['Close']
                    lower = indicator_results[indicator_type]['lower'][idx]
                    upper = indicator_results[indicator_type]['upper'][idx]
                    if condition == 'lower_band' and price <= lower:
                        condition_met = signal_type == 'buy'
                    elif condition == 'upper_band' and price >= upper:
                        condition_met = signal_type == 'sell'
                        
                conditions_met.append(condition_met)
                
            # Combine conditions based on logic
            if data['combination_logic'] == 'AND' and all(conditions_met):
                signal = {
                    'timestamp': idx.isoformat(),
                    'price': float(row['Close']),
                    'type': data['indicators'][0]['signal_type']  # Use first indicator's signal type
                }
            elif data['combination_logic'] == 'OR' and any(conditions_met):
                # For OR logic, use the signal type of the first condition that was met
                signal_type = next(ind['signal_type'] for i, ind in enumerate(data['indicators']) if conditions_met[i])
                signal = {
                    'timestamp': idx.isoformat(),
                    'price': float(row['Close']),
                    'type': signal_type
                }
                
            if signal:
                signals.append(signal)
                
        # Calculate performance metrics
        metrics = calculate_performance_metrics(signals, df)
        
        return jsonify({
            "signals": signals,
            "metrics": metrics,
            "summary": {
                "total_signals": len(signals),
                "period_start": data['start_date'],
                "period_end": data['end_date'],
                "instrument": data['instrument']
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def calculate_performance_metrics(signals, df):
    """Calculate performance metrics for the backtesting signals"""
    if not signals:
        return {
            "win_rate": 0,
            "total_trades": 0,
            "profit_loss": 0,
            "max_drawdown": 0
        }
        
    trades = []
    current_position = None
    total_profit_loss = 0
    max_drawdown = 0
    peak_value = 0
    
    for signal in signals:
        price = signal['price']
        
        if not current_position and signal['type'] == 'buy':
            current_position = {
                'entry_price': price,
                'entry_time': signal['timestamp']
            }
        elif current_position and signal['type'] == 'sell':
            profit_loss = price - current_position['entry_price']
            trades.append({
                'entry_price': current_position['entry_price'],
                'exit_price': price,
                'profit_loss': profit_loss,
                'entry_time': current_position['entry_time'],
                'exit_time': signal['timestamp']
            })
            total_profit_loss += profit_loss
            
            # Update peak value and drawdown
            if total_profit_loss > peak_value:
                peak_value = total_profit_loss
            else:
                drawdown = peak_value - total_profit_loss
                max_drawdown = max(max_drawdown, drawdown)
                
            current_position = None
            
    winning_trades = len([t for t in trades if t['profit_loss'] > 0])
    total_trades = len(trades)
    
    return {
        "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
        "total_trades": total_trades,
        "profit_loss": total_profit_loss,
        "max_drawdown": max_drawdown,
        "trades": trades
    }


@app.route('/api/backtesting/newrun', methods=['POST'])
@jwt_required()
@validate_json_request
@feature_limit('backtest-beta')
def run_new_backtest():
    """Run comprehensive backtest using IndianStockStrategyBuilder - Colab replication"""
    try:
        data = request.get_json()
        
        # Extract and validate all Colab parameters
        required_fields = ['stock_symbol', 'selected_indicators', 'voting_threshold', 
                          'period', 'timeframe', 'initial_capital', 'position_size_pct']
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Extract parameters
        symbol = data['stock_symbol']
        indicators = data['selected_indicators']
        voting_threshold = float(data['voting_threshold'])
        period = data['period']
        timeframe = data['timeframe']
        initial_capital = float(data['initial_capital'])
        position_size_pct = float(data['position_size_pct'])
        risk_reward_ratio = float(data.get('risk_reward_ratio', 2.0))
        max_drawdown_pct = float(data.get('max_drawdown_pct', 0.05))
        
        # Optional Monte Carlo parameters
        monte_carlo_simulations = int(data.get('monte_carlo_simulations', 0))
        confidence_level = float(data.get('confidence_level', 0.95))
        
        # Initialize builder and fetch data
        from services.backtesting_engine import IndianStockStrategyBuilder
        builder = IndianStockStrategyBuilder()
        
        df = builder.fetch_stock_data(symbol, period, timeframe)
        if df is None or df.empty:
            return jsonify({"error": f"No data found for symbol: {symbol}"}), 404
        
        # Run indicator and signal pipeline
        df = builder.calculate_indicators(df, indicators)
        df = builder.generate_voting_signals(df, indicators, voting_threshold)
        
        # Run backtest
        trades_df, equity_df, metrics = builder.backtest_strategy(
            df, initial_capital, position_size_pct, risk_reward_ratio, max_drawdown_pct
        )
        
        # Monte Carlo analysis (optional)
        mc_stats = None
        mc_results = None
        if monte_carlo_simulations > 0 and not trades_df.empty:
            mc_stats, mc_results = builder.monte_carlo_analysis(
                trades_df, initial_capital, monte_carlo_simulations, confidence_level
            )
        
        # Create visualizations
        candlestick_chart = builder.create_candlestick_chart(df, trades_df)
        equity_chart = builder.create_equity_curve_chart(equity_df)
        drawdown_chart = builder.create_drawdown_chart(equity_df)
        
        # Serialize dataframes and prepare response
        response = {
            "success": True,
            "data": {
                "metrics": metrics,
                "trades": trades_df.to_dict(orient='records') if not trades_df.empty else [],
                "equity_curve": equity_df.to_dict(orient='records'),
                "stock_data": df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Signal']].to_dict(orient='records'),
                "charts": {
                    "candlestick": candlestick_chart.to_json(),
                    "equity_curve": equity_chart.to_json(),
                    "drawdown": drawdown_chart.to_json()
                }
            }
        }
        
        # Add Monte Carlo results if available
        if mc_stats:
            response["data"]["monte_carlo"] = {
                "statistics": mc_stats,
                "results": mc_results.to_dict(orient='records') if mc_results is not None else []
            }
        
        # Add summary statistics
        response["data"]["summary"] = {
            "symbol": symbol,
            "period": period,
            "timeframe": timeframe,
            "total_data_points": len(df),
            "indicators_used": list(indicators.keys()),
            "voting_threshold": voting_threshold,
            "backtest_period": {
                "start_date": df['Date'].iloc[0].strftime('%Y-%m-%d'),
                "end_date": df['Date'].iloc[-1].strftime('%Y-%m-%d')
            }
        }

        # Get usage info if available (set by feature_limit decorator)
        usage_info = getattr(g, '_anon_feature_usage', None)
        if usage_info:
            response["usage"] = usage_info

        return jsonify(response), 200
        
    except ValueError as e:
        logger.error(f"Validation error in new backtest: {str(e)}")
        return jsonify({"error": f"Invalid parameter: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Error running new backtest: {str(e)}", exc_info=True)
        return jsonify({"error": "An error occurred while running the backtest"}), 500

# Subscription routes
@app.route('/api/user/subscription', methods=['GET'])
@jwt_required()
def get_subscription():
    """Get user's subscription details"""
    user_id = get_jwt_identity()
    
    # Try to get subscription details
    subscription = _get_subscription_service().get_subscription_details(user_id)
    
    # If subscription not found, try to fix it
    if not subscription:
        fixed = _get_subscription_service().fix_missing_subscription(user_id)
        if fixed:
            subscription = _get_subscription_service().get_subscription_details(user_id)
    
    if not subscription:
        return jsonify({"error": "Could not retrieve or create subscription"}), 500
        
    return jsonify(subscription), 200

@app.route('/api/user/subscription/upgrade', methods=['POST'])
@jwt_required()
@validate_json_request
def upgrade_subscription():
    """Upgrade user's subscription tier"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if 'tier' not in data:
        return jsonify({"error": "New tier is required"}), 400
        
    new_tier = data['tier']
    success, message = _get_subscription_service().upgrade_subscription(user_id, new_tier)
    
    if not success:
        return jsonify({"error": message}), 400
        
    return jsonify({"message": message}), 200

@app.route('/api/user/subscription/cancel', methods=['POST'])
@jwt_required()
@validate_json_request
def cancel_subscription():
    """Cancel user's subscription and downgrade to FREE tier"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Get cancellation reason (optional)
        reason = data.get('reason', 'User requested cancellation')
        
        # Cancel subscription
        success, message = _get_subscription_service().cancel_subscription(user_id, reason)
        
        if not success:
            return jsonify({
                "success": False,
                "error": message
            }), 400
        
        # Send cancellation email notification
        try:
            from services.email_service import email_service
            from services.user_service import UserService
            
            user_service_instance = UserService()
            user_data = user_service_instance.get_user_by_id(user_id)
            
            if user_data:
                # Get cancellation info
                cancellation_info = _get_subscription_service().get_cancellation_info(user_id)
                
                if cancellation_info:
                    # Send cancellation email
                    email_sent = email_service.send_subscription_upgrade_email(
                        user_email=user_data['email'],
                        user_name=user_data.get('username', 'User'),
                        old_plan=cancellation_info.get('cancelled_tier', 'PAID'),
                        new_plan='FREE',
                        upgrade_date=datetime.now().strftime('%B %d, %Y')
                    )
                    
                    if email_sent:
                        logger.info(f"Cancellation notification email sent to {user_data['email']}")
                    else:
                        logger.warning(f"Failed to send cancellation email to {user_data['email']}")
                        
        except Exception as email_error:
            logger.error(f"Error sending cancellation email: {str(email_error)}")
            # Don't fail the cancellation if email fails
        
        return jsonify({
            "success": True,
            "message": message
        }), 200
        
    except Exception as e:
        logger.error(f"Error cancelling subscription: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to cancel subscription",
            "message": str(e)
        }), 500

@app.route('/api/user/subscription/cancellation-info', methods=['GET'])
@jwt_required()
def get_cancellation_info():
    """Get cancellation information for user's subscription"""
    try:
        user_id = get_jwt_identity()
        
        cancellation_info = _get_subscription_service().get_cancellation_info(user_id)
        
        if cancellation_info:
            return jsonify({
                "success": True,
                "cancellation_info": cancellation_info
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "No cancellation information found"
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting cancellation info: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to get cancellation information",
            "message": str(e)
        }), 500

@app.route('/api/user/usage', methods=['GET'])
@jwt_required()
def get_usage_metrics():
    """Get user's usage metrics"""
    user_id = get_jwt_identity()
    metrics = _get_subscription_service().get_usage_metrics(user_id)
    
    if not metrics:
        return jsonify({"error": "Usage metrics not found"}), 404
        
    return jsonify(metrics), 200

@app.route('/api/user/usage/increment', methods=['POST'])
@jwt_required()
@validate_json_request
def increment_usage():
    """Increment usage counter for a specific feature"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'feature' not in data:
            return jsonify({"error": "Feature is required"}), 400
        
        feature = data['feature']
        
        # Validate feature
        if feature not in ['backtest', 'llm_query']:
            return jsonify({
                "error": "Invalid feature",
                "message": "Feature must be 'backtest' or 'llm_query'"
            }), 400
        
        # Increment usage
        success, message = _get_subscription_service().increment_usage(user_id, feature)
        
        if not success:
            return jsonify({
                "error": "Failed to increment usage",
                "message": message
            }), 500
        
        # Get updated usage metrics
        metrics = _get_subscription_service().get_usage_metrics(user_id)
        
        return jsonify({
            "success": True,
            "message": message,
            "usage": metrics
        }), 200
        
    except Exception as e:
        logger.error(f"Error in increment_usage endpoint: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500

# Subscription tier management routes
@app.route('/api/admin/subscription/tiers', methods=['GET'])
@jwt_required()
def get_subscription_tiers():
    """Get all subscription tiers"""
    # Check if user is admin
    user_id = get_jwt_identity()
    user = _get_user_service().get_user_by_id(user_id)
    if not user or user.get('role') != 'admin':
        return jsonify({"error": "Unauthorized access"}), 403
        
    tiers = _get_subscription_service().get_all_subscription_tiers()
    return jsonify(tiers), 200

@app.route('/api/admin/subscription/tiers', methods=['POST'])
@jwt_required()
@validate_json_request
def create_subscription_tier():
    """Create a new subscription tier"""
    # Check if user is admin
    user_id = get_jwt_identity()
    user = _get_user_service().get_user_by_id(user_id)
    if not user or user.get('role') != 'admin':
        return jsonify({"error": "Unauthorized access"}), 403
    
    data = request.get_json()
    if 'tier_name' not in data or 'tier_data' not in data:
        return jsonify({"error": "tier_name and tier_data are required"}), 400
    
    tier_name = data['tier_name'].upper()  # Convert to uppercase for consistency
    tier_data = data['tier_data']
    
    success, message = _get_subscription_service().create_subscription_tier(tier_name, tier_data)
    if not success:
        return jsonify({"error": message}), 400
        
    return jsonify({"message": message}), 201

# ============================================
# OLD RAZORPAY ROUTES REMOVED
# Now using Cashfree via routes/payment.py blueprint
# ============================================

# Get plan details with limits
@app.route('/api/subscription/plan-details/<plan_id>', methods=['GET'])
def get_plan_details(plan_id):
    """Get plan details including limits for each feature"""
    try:
        # Validate plan_id
        plan_id = plan_id.upper()
        if plan_id not in ['FREE', 'STARTER', 'PRO', 'ADVANCED', 'ENTERPRISE']:
            return jsonify({
                "success": False,
                "error": "Invalid plan ID"
            }), 400

        # Get plan limits from config
        plan_limits = app.config['PLAN_LIMITS'].get(plan_id, {})

        return jsonify({
            "success": True,
            "plan_details": {
                "plan": plan_id,
                "limits": plan_limits
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting plan details: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Billing details endpoints
@app.route('/api/user/billing-details', methods=['GET'])
@jwt_required()
def get_billing_details():
    """Get user's billing details"""
    try:
        user_id = get_jwt_identity()
        user_data = _get_user_service().get_user_by_id(user_id)
        
        if not user_data:
            return jsonify({"error": "User not found"}), 404
        
        billing_details = user_data.get('billing_details', {})
        
        return jsonify({
            "success": True,
            "billing_details": billing_details
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting billing details: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to get billing details",
            "message": str(e)
        }), 500

@app.route('/api/user/billing-details', methods=['POST', 'PUT'])
@jwt_required()
@validate_json_request
def update_billing_details():
    """Update user's billing details"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['full_name', 'email', 'phone']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Update user's billing details
        update_data = {
            "billing_details": {
                "full_name": data['full_name'],
                "email": data['email'],
                "phone": data['phone'],
                "address": data.get('address', {}),
                "updated_at": datetime.utcnow()
            }
        }
        
        result = _get_user_service().users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return jsonify({
                "success": True,
                "message": "Billing details updated successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to update billing details"
            }), 400
            
    except Exception as e:
        logger.error(f"Error updating billing details: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to update billing details",
            "message": str(e)
        }), 500

# Email service endpoints
@app.route('/api/email/send', methods=['POST'])
@jwt_required()
@validate_json_request
def send_email():
    """Send custom email (admin only)"""
    try:
        # Check if user is admin
        user_id = get_jwt_identity()
        user = _get_user_service().get_user_by_id(user_id)
        if not user or user.get('role') != 'admin':
            return jsonify({"error": "Unauthorized access"}), 403
            
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['to', 'subject', 'template']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: {field}"
                }), 400
        
        # Send email
        email_sent = email_service.send_email(
            to=data['to'],
            subject=data['subject'],
            template=data['template'],
            context=data.get('context', {}),
            attachments=data.get('attachments', [])
        )
        
        if email_sent:
            return jsonify({
                "success": True,
                "message": "Email sent successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to send email"
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to send email",
            "message": str(e)
        }), 500

@app.route('/api/email/send-welcome', methods=['POST'])
@jwt_required()
@validate_json_request
def send_welcome_email():
    """Send welcome email to user"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Get recipient details
        target_user_id = data.get('user_id')
        if target_user_id:
            # Admin sending to another user
            user = _get_user_service().get_user_by_id(user_id)
            if not user or user.get('role') != 'admin':
                return jsonify({"error": "Unauthorized access"}), 403
            target_user = _get_user_service().get_user_by_id(target_user_id)
        else:
            # User sending to themselves
            target_user = _get_user_service().get_user_by_id(user_id)
        
        if not target_user:
            return jsonify({"error": "User not found"}), 404
        
        # Send welcome email
        email_sent = email_service.send_welcome_email(
            user_email=target_user['email'],
            user_name=target_user.get('username', 'User')
        )
        
        if email_sent:
            return jsonify({
                "success": True,
                "message": "Welcome email sent successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to send welcome email"
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending welcome email: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to send welcome email",
            "message": str(e)
        }), 500

@app.route('/api/email/send-subscription-upgrade', methods=['POST'])
@jwt_required()
@validate_json_request
def send_subscription_upgrade_email():
    """Send subscription upgrade notification email"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['old_plan', 'new_plan']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: {field}"
                }), 400
        
        # Get user details
        user = _get_user_service().get_user_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Send upgrade email
        email_sent = email_service.send_subscription_upgrade_email(
            user_email=user['email'],
            user_name=user.get('username', 'User'),
            old_plan=data['old_plan'],
            new_plan=data['new_plan'],
            upgrade_date=datetime.now().strftime('%B %d, %Y')
        )
        
        if email_sent:
            return jsonify({
                "success": True,
                "message": "Upgrade notification email sent successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to send upgrade notification email"
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending upgrade notification email: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to send upgrade notification email",
            "message": str(e)
        }), 500


# User Data Persistence Endpoints
@app.route('/api/user/save-backtest', methods=['POST'])
@jwt_required()
@validate_json_request
def save_backtest_result():
    """Save backtest result for the authenticated user"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'backtest_data' not in data:
            return jsonify({"error": "backtest_data is required"}), 400
        
        # Save the backtest result
        success = _get_user_service().save_backtest_result(user_id, data['backtest_data'])
        
        if success:
            return jsonify({
                "success": True,
                "message": "Backtest result saved successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save backtest result"
            }), 500
            
    except Exception as e:
        logger.error(f"Error saving backtest result: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/api/user/save-ai-analysis', methods=['POST'])
@jwt_required()
@validate_json_request
def save_ai_analysis_result():
    """Save AI analysis result for the authenticated user"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'analysis_data' not in data:
            return jsonify({"error": "analysis_data is required"}), 400
        
        # Save the AI analysis result
        success = _get_user_service().save_ai_analysis_result(user_id, data['analysis_data'])
        
        if success:
            return jsonify({
                "success": True,
                "message": "AI analysis result saved successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save AI analysis result"
            }), 500
            
    except Exception as e:
        logger.error(f"Error saving AI analysis result: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/api/user/save-chat', methods=['POST'])
@jwt_required()
@validate_json_request
def save_chat_history():
    """Save chat history for the authenticated user"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'chat_data' not in data:
            return jsonify({"error": "chat_data is required"}), 400
        
        # Save the chat history
        result = _get_user_service().save_chat_history(user_id, data['chat_data'])
        
        if result.get("success"):
            return jsonify(result), 200
        else:
            return jsonify({
                "success": False,
                "error": result.get("message", "Failed to save chat history")
            }), 500
            
    except Exception as e:
        logger.error(f"Error saving chat history: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/api/user/backtests', methods=['GET'])
@jwt_required()
def get_user_backtests():
    """Get user's saved backtest results"""
    try:
        user_id = get_jwt_identity()
        
        # Get pagination parameters
        limit = request.args.get('limit', default=10, type=int)
        skip = request.args.get('skip', default=0, type=int)
        
        # Validate pagination parameters
        if limit > 100:
            limit = 100
        if skip < 0:
            skip = 0
        
        # Get user's backtest results
        backtests = _get_user_service().get_user_backtests(user_id, limit, skip)
        
        return jsonify({
            "success": True,
            "backtests": backtests,
            "count": len(backtests)
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving user backtests: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/api/user/backtests/<backtest_id>', methods=['DELETE'])
@jwt_required()
def delete_backtest(backtest_id):
    """Delete a saved backtest strategy"""
    try:
        user_id = get_jwt_identity()

        # Validate backtest_id format
        if not ObjectId.is_valid(backtest_id):
            return jsonify({
                "success": False,
                "error": "Invalid backtest ID"
            }), 400

        # Delete backtest (ensure it belongs to the user)
        result = _get_user_service().delete_backtest_result(user_id, backtest_id)

        if result:
            return jsonify({
                "success": True,
                "message": "Backtest deleted successfully"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Backtest not found or already deleted"
            }), 404

    except Exception as e:
        logger.error(f"Error deleting backtest: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500

@app.route('/api/user/ai-analyses', methods=['GET'])
@jwt_required()
def get_user_ai_analyses():
    """Get user's saved AI analysis results"""
    try:
        user_id = get_jwt_identity()
        
        # Get pagination parameters
        limit = request.args.get('limit', default=10, type=int)
        skip = request.args.get('skip', default=0, type=int)
        
        # Validate pagination parameters
        if limit > 100:
            limit = 100
        if skip < 0:
            skip = 0
        
        # Get user's AI analysis results
        analyses = _get_user_service().get_user_ai_analyses(user_id, limit, skip)
        
        return jsonify({
            "success": True,
            "analyses": analyses,
            "count": len(analyses)
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving user AI analyses: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/api/user/chat-history', methods=['GET'])
@jwt_required()
def get_user_chat_history():
    """Get user's saved chat history"""
    try:
        user_id = get_jwt_identity()

        # Get pagination parameters
        limit = request.args.get('limit', default=50, type=int)
        skip = request.args.get('skip', default=0, type=int)

        # Validate pagination parameters
        if limit > 200:
            limit = 200
        if skip < 0:
            skip = 0

        # Get user's chat history
        chat_history = _get_user_service().get_user_chat_history(user_id, limit, skip)

        return jsonify({
            "success": True,
            "chat_history": chat_history,
            "count": len(chat_history)
        }), 200

    except Exception as e:
        logger.error(f"Error retrieving user chat history: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@app.route('/api/usage/anonymous-status', methods=['GET'])
def get_anonymous_usage_status():
    """Get remaining anonymous trial quota for a specific feature"""
    from services.usage_service import get_feature_usage

    try:
        feature = request.args.get('feature')
        if not feature:
            return jsonify({
                "ok": False,
                "error": "feature_required",
                "message": "Feature parameter is required"
            }), 400

        # Get session ID from cookie
        cookie_name = app.config['ANON_SESSION_COOKIE']
        session_id = request.cookies.get(cookie_name)

        # If no session yet, return full limit available
        if not session_id:
            limit = app.config['ANON_TRIAL_LIMIT']
            return jsonify({
                "ok": True,
                "used": 0,
                "limit": limit,
                "remaining": limit,
                "feature": feature
            }), 200

        # Get usage from Redis
        used = get_feature_usage(session_id, feature)
        limit = app.config['ANON_TRIAL_LIMIT']

        return jsonify({
            "ok": True,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "feature": feature
        }), 200

    except Exception as e:
        logger.error(f"Error getting anonymous usage status: {str(e)}")
        return jsonify({
            "ok": False,
            "error": "internal_error",
            "message": "Failed to retrieve usage status"
        }), 500

@app.route('/api/market-indices-new', methods=['GET'])
def market_indices_new():
    from services.stock_service import get_market_indices_yfinance
    try:
        indices_data = get_market_indices_yfinance()
        return jsonify({
            "indices": indices_data
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================== NEWS & BLOGS API ENDPOINTS ===========================

@app.route('/api/news', methods=['GET'])
def get_news():
    """
    Get news from external sources
    Query params:
    - category: all|indian_markets|global_markets|nse|bse|ipos|economy|banking|corporate
    - region: indian|global
    - limit: number of articles
    """
    try:
        category = request.args.get('category', 'all')
        region = request.args.get('region', 'indian')
        limit = int(request.args.get('limit', 50))

        result = NewsAggregator.get_news(category=category, region=region, limit=limit)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching news: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/news/search', methods=['GET'])
def search_news():
    """
    Search news articles
    Query params:
    - q: search query
    - category: filter by category
    - limit: number of results
    """
    try:
        query = request.args.get('q', '')
        category = request.args.get('category', 'all')
        limit = int(request.args.get('limit', 20))

        if not query:
            return jsonify({
                'success': False,
                'error': 'Search query required'
            }), 400

        result = NewsAggregator.search_news(query=query, category=category, limit=limit)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error searching news: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/blogs', methods=['GET'])
def get_blogs():
    """Get all blog posts with pagination and filtering"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        category = request.args.get('category')
        featured_only = request.args.get('featured') == 'true'

        logger.info(f"GET /api/blogs - Page: {page}, Limit: {limit}, Category: {category}")

        result = news_service.get_all_blogs(
            page=page,
            limit=limit,
            category=category,
            featured_only=featured_only
        )

        logger.info(f"Result from news_service: success={result.get('success')}, blogs_count={len(result.get('blogs', []))}")

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error in get_blogs endpoint: {str(e)}\n{error_trace}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}",
            "error": str(e)
        }), 500

@app.route('/api/news/<post_id>', methods=['GET'])
def get_news_post(post_id):
    """Get a specific news post by ID"""
    try:
        result = news_service.get_post_by_id(post_id, post_type="news")
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 404
            
    except Exception as e:
        logger.error(f"Error in get_news_post endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/blogs/<post_id>', methods=['GET'])
def get_blog_post(post_id):
    """Get a specific blog post by ID"""
    try:
        result = news_service.get_post_by_id(post_id, post_type="blog")
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 404
            
    except Exception as e:
        logger.error(f"Error in get_blog_post endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/featured-posts', methods=['GET'])
def get_featured_posts():
    """Get featured posts from both news and blogs"""
    try:
        limit = int(request.args.get('limit', 5))
        result = news_service.get_featured_posts(limit=limit)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in get_featured_posts endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/search-posts', methods=['GET'])
def search_posts():
    """Search posts by title, content, or tags"""
    try:
        query = request.args.get('q', '')
        post_type = request.args.get('type', 'all')  # all, news, blog
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        
        if not query:
            return jsonify({
                "success": False,
                "message": "Search query is required"
            }), 400
        
        result = news_service.search_posts(
            query=query, 
            post_type=post_type, 
            page=page, 
            limit=limit
        )
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in search_posts endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/news', methods=['POST'])
@jwt_required()
def create_news_post():
    """Create a new news post (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        user_info = _get_user_service().get_user_by_id(current_user_id)
        
        if not user_info or user_info.get('role') != 'admin':
            return jsonify({
                "success": False,
                "message": "Admin access required"
            }), 403
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Request body is required"
            }), 400
        
        required_fields = ['title', 'content', 'author']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    "success": False,
                    "message": f"{field} is required"
                }), 400
        
        result = news_service.create_news_post(
            title=data['title'],
            content=data['content'],
            author=data['author'],
            category=data.get('category', 'General'),
            tags=data.get('tags', []),
            image_url=data.get('image_url'),
            summary=data.get('summary')
        )
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error in create_news_post endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/blogs', methods=['POST'])
@jwt_required()
def create_blog_post():
    """Create a new blog post (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        user_info = _get_user_service().get_user_by_id(current_user_id)
        
        if not user_info or user_info.get('role') != 'admin':
            return jsonify({
                "success": False,
                "message": "Admin access required"
            }), 403
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Request body is required"
            }), 400
        
        required_fields = ['title', 'content', 'author']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    "success": False,
                    "message": f"{field} is required"
                }), 400
        
        result = news_service.create_blog_post(
            title=data['title'],
            content=data['content'],
            author=data['author'],
            category=data.get('category', 'Finance'),
            tags=data.get('tags', []),
            image_url=data.get('image_url'),
            summary=data.get('summary')
        )
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"Error in create_blog_post endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/blogs/debug/count', methods=['GET'])
def debug_blogs_count():
    """Debug endpoint to check blog count in database"""
    try:
        from services.news_service import NewsService
        service = NewsService()

        # Get total blogs
        all_blogs = service.blogs_collection.count_documents({})
        blogs_with_type = service.blogs_collection.count_documents({"type": "blog"})

        # Get sample blog
        sample = service.blogs_collection.find_one({})
        sample_id = str(sample["_id"]) if sample else None
        sample_type = sample.get("type") if sample else None

        return jsonify({
            "success": True,
            "total_documents": all_blogs,
            "documents_with_type_blog": blogs_with_type,
            "sample_id": sample_id,
            "sample_type": sample_type,
            "sample_doc": {k: str(v) for k, v in sample.items()} if sample else None
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/blogs/debug/test', methods=['GET'])
def debug_blogs_test():
    """Test endpoint to check if blogs can be fetched and serialized"""
    try:
        from services.news_service import NewsService
        from datetime import datetime
        service = NewsService()

        # Try to fetch blogs directly
        blogs_raw = list(service.blogs_collection.find({"type": "blog"}).limit(3))
        logger.info(f"Found {len(blogs_raw)} raw blogs")

        # Manually serialize each blog
        serialized = []
        for i, blog in enumerate(blogs_raw):
            try:
                logger.info(f"Serializing blog {i}: keys = {list(blog.keys())}")
                item = {
                    "_id": str(blog.get("_id", "")),
                    "title": str(blog.get("title", "")),
                    "author": str(blog.get("author", "")),
                    "category": str(blog.get("category", "")),
                }

                # Check datetime fields
                created_at = blog.get("created_at")
                logger.info(f"created_at type: {type(created_at)}, value: {created_at}")

                if created_at:
                    if hasattr(created_at, 'isoformat'):
                        item["createdAt"] = created_at.isoformat()
                    else:
                        item["createdAt"] = str(created_at)
                else:
                    item["createdAt"] = ""

                serialized.append(item)
                logger.info(f"Successfully serialized blog {i}")
            except Exception as e:
                logger.error(f"Error serializing blog {i}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())

        return jsonify({
            "success": True,
            "count": len(serialized),
            "blogs": serialized
        }), 200
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Debug test error: {str(e)}\n{error_trace}")
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": error_trace
        }), 500

@app.route('/api/blogs/<post_id>', methods=['PUT'])
@jwt_required()
def update_blog_post(post_id):
    """Update a blog post (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        user_info = _get_user_service().get_user_by_id(current_user_id)

        if not user_info or user_info.get('role') != 'admin':
            return jsonify({
                "success": False,
                "message": "Admin access required"
            }), 403

        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "message": "Request body is required"
            }), 400

        result = news_service.update_blog_post(
            post_id=post_id,
            title=data.get('title'),
            content=data.get('content'),
            author=data.get('author'),
            category=data.get('category'),
            tags=data.get('tags'),
            image_url=data.get('image_url'),
            summary=data.get('summary'),
            status=data.get('status')
        )

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"Error in update_blog_post endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/blogs/<post_id>', methods=['DELETE'])
@jwt_required()
def delete_blog_post(post_id):
    """Delete a blog post (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        user_info = _get_user_service().get_user_by_id(current_user_id)

        if not user_info or user_info.get('role') != 'admin':
            return jsonify({
                "success": False,
                "message": "Admin access required"
            }), 403

        result = news_service.delete_post(post_id, post_type="blog")

        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        logger.error(f"Error in delete_blog_post endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

# ============================================
# ADMIN ENDPOINTS FOR PREMIUM SYSTEM
# ============================================

@app.route('/api/admin/manual-credit', methods=['POST'])
@jwt_required()
@admin_required
@validate_json_request
def manual_credit_subscription():
    """
    Manually credit a subscription to a user (admin only)

    Request Body:
        {
            "user_id": "user_object_id",
            "plan": "PRO",
            "duration": "monthly",
            "note": "Manual credit reason"
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        if not all(k in data for k in ['user_id', 'plan', 'duration']):
            return jsonify({
                "success": False,
                "error": "Missing required fields: user_id, plan, duration"
            }), 400

        user_id = data['user_id']
        plan = data['plan']
        duration = data['duration']
        note = data.get('note', 'Manual credit by admin')

        # Apply subscription
        success, message = _get_subscription_service().apply_premium_subscription(
            user_id=user_id,
            plan_name=plan,
            plan_duration=duration
        )

        if success:
            logger.info(f"Admin manually credited {plan} ({duration}) to user {user_id}: {note}")
            return jsonify({
                "success": True,
                "message": message,
                "user_id": user_id,
                "plan": plan,
                "duration": duration
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Error in manual credit: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500


@app.route('/api/admin/reset-usage', methods=['POST'])
@jwt_required()
@admin_required
@validate_json_request
def admin_reset_usage():
    """
    Reset usage for a user (admin only - for testing/support)

    Request Body:
        {
            "user_id": "user_object_id",
            "feature": "welth-market-regime"  # optional, omit to reset all
        }
    """
    try:
        from services.premium_usage_service import get_premium_usage_service
        usage_service = get_premium_usage_service()

        data = request.get_json()
        user_id = data.get('user_id')
        feature = data.get('feature')

        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id is required"
            }), 400

        if feature:
            # Reset specific feature
            success = usage_service.reset_usage(user_id, feature, is_anonymous=False)
            message = f"Reset usage for {feature}"
        else:
            # Reset all usage
            success = usage_service.delete_all_usage(user_id, is_anonymous=False)
            message = "Reset all usage"

        if success:
            logger.info(f"Admin reset usage for user {user_id}: {message}")
            return jsonify({
                "success": True,
                "message": message
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Failed to reset usage"
            }), 500

    except Exception as e:
        logger.error(f"Error resetting usage: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500

if __name__ == '__main__':
    # Get configuration
    config = get_config()

    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5000))

    # Use waitress on Windows to avoid WinError 10038 socket crashes
    # during long-running requests (e.g. AI screener yfinance downloads).
    # Falls back to Flask dev server on non-Windows or if waitress is missing.
    _use_waitress = os.name == 'nt'
    if _use_waitress:
        try:
            from waitress import serve
            print(f" * Serving Flask app with Waitress on http://0.0.0.0:{port}")
            serve(app, host='0.0.0.0', port=port, threads=8, channel_timeout=300)
        except ImportError:
            print(" * waitress not installed, falling back to Flask dev server")
            _use_waitress = False

    if not _use_waitress:
        app.run(
            host='0.0.0.0',
            port=port,
            debug=config.DEBUG if hasattr(config, 'DEBUG') else False,
            threaded=True
        )