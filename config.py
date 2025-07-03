import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Base configuration."""
    DEBUG = False
    TESTING = False
    PORT = int(os.environ.get('PORT', 8000))
    
    # AI API keys
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
    CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')
    
    # MongoDB configuration
    MONGODB_URI = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
    
    # JWT configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-secret-key')
    
class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    
class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    
# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

# Get configuration based on environment
def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default']) 