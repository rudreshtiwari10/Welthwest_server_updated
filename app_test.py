from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token
import os
import logging
from datetime import timedelta
from mock_services import MockUserService, MockSubscriptionService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Basic configuration
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "test-secret-key")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
    
    # Configure CORS
    CORS(app, resources={
        r"/api/*": {"origins": "*"},
        r"/": {"origins": "*"}
    })
    
    return app

app = create_app()
jwt = JWTManager(app)


# Initialize mock services
user_service = MockUserService()
subscription_service = MockSubscriptionService()

# Root route for health checks
@app.route('/', methods=['GET', 'HEAD'])
def root():
    """Root endpoint for health checks"""
    return jsonify({"status": "healthy", "message": "WelthWest API is running (Test Mode)"}), 200

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "WelthWest API is running (Test Mode)"}), 200

# Test authentication route
@app.route('/api/auth/test-login', methods=['POST'])
def test_login():
    """Test login endpoint"""
    try:
        data = request.get_json() if request.is_json else {}
        
        # Mock successful login
        success, message, user_data = user_service.login_user("test", "test")
        
        if not success:
            return jsonify({"error": message}), 401
        
        # Initialize subscription
        subscription_service.initialize_subscription(user_data['id'])
        
        # Generate tokens
        access_token = create_access_token(identity=str(user_data['id']))
        refresh_token = create_refresh_token(identity=str(user_data['id']))
        
        # Store refresh token
        user_service.store_refresh_token(user_data['id'], refresh_token)
        
        return jsonify({
            "message": "Login successful (Test Mode)",
            "user": user_data,
            "access_token": access_token,
            "refresh_token": refresh_token
        }), 200
        
    except Exception as e:
        logger.error(f"Error in test login: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

# Test data endpoint
@app.route('/api/test/data', methods=['GET'])
def test_data():
    """Test data endpoint"""
    return jsonify({
        "message": "Test data endpoint working",
        "timestamp": "2024-01-01T00:00:00Z",
        "test_data": {
            "stocks": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"],
            "status": "mock_data"
        }
    }), 200

if __name__ == '__main__':
    print("Starting WelthWest Server in Test Mode...")
    print("MongoDB: Disabled (using mock services)")
    print("Redis: Disabled")
    print("Upstox: Disabled")
    print("AI Services: Disabled")
    print()
    print("Available endpoints:")
    print("- GET  /           - Health check")
    print("- GET  /health     - Health check")
    print("- POST /api/auth/test-login - Test login")
    print("- GET  /api/test/data - Test data")
    print()
    
    app.run(host='0.0.0.0', port=8000, debug=True)