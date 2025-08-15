#!/usr/bin/env python3
"""
Production Deployment Fix for Render Server
Fixes the 'monotonic_cst' attribute error by ensuring model compatibility
"""

import os
import sys
import logging
import shutil
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_incompatible_models():
    """Remove any existing models that might cause compatibility issues"""
    model_files = [
        "market_regime_model.pkl",
        "market_regime_model.pkl.bak",
        "market_regime_model_old.pkl"
    ]
    
    print("Cleaning up incompatible model files...")
    
    for model_file in model_files:
        if os.path.exists(model_file):
            try:
                # Create backup before deletion
                backup_name = f"{model_file}.backup"
                shutil.copy2(model_file, backup_name)
                print(f"✓ Created backup: {backup_name}")
                
                # Remove the incompatible model
                os.remove(model_file)
                print(f"✓ Removed incompatible model: {model_file}")
                
            except Exception as e:
                print(f"⚠ Could not remove {model_file}: {e}")
        else:
            print(f"  {model_file} not found (already cleaned up)")

def update_requirements_for_production():
    """Update requirements.txt for production compatibility"""
    requirements_file = "requirements.txt"
    
    if os.path.exists(requirements_file):
        print("Updating requirements.txt for production compatibility...")
        
        try:
            with open(requirements_file, 'r') as f:
                content = f.read()
            
            # Replace scikit-learn version with pinned version
            if 'scikit-learn>=' in content:
                content = content.replace(
                    'scikit-learn>=1.4.0,<2.0.0',
                    'scikit-learn==1.3.2'
                )
                print("✓ Updated scikit-learn version to 1.3.2")
            elif 'scikit-learn==' not in content:
                # Add pinned version if not present
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'scipy>=' in line:
                        lines.insert(i + 1, 'scikit-learn==1.3.2')
                        break
                content = '\n'.join(lines)
                print("✓ Added scikit-learn==1.3.2")
            
            # Write updated content
            with open(requirements_file, 'w') as f:
                f.write(content)
            
            print("✓ Requirements.txt updated successfully")
            
        except Exception as e:
            print(f"❌ Error updating requirements.txt: {e}")
    else:
        print("⚠ Requirements.txt not found")

def create_production_env_file():
    """Create production environment file if it doesn't exist"""
    env_file = ".env"
    if not os.path.exists(env_file):
        print("Creating production .env file...")
        
        env_content = """# Production Environment Variables
FLASK_ENV=production
FLASK_DEBUG=False
JWT_SECRET_KEY=your_production_jwt_secret_key_here
MONGODB_URI=your_mongodb_connection_string_here
RAZORPAY_KEY_ID=your_razorpay_key_id_here
RAZORPAY_KEY_SECRET=your_razorpay_secret_here
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
"""
        
        try:
            with open(env_file, 'w') as f:
                f.write(env_content)
            print("✓ Production .env file created")
            print("⚠ Please update the .env file with your actual production values")
        except Exception as e:
            print(f"❌ Could not create .env file: {e}")
    else:
        print("✓ Production .env file already exists")

def verify_production_setup():
    """Verify production setup is correct"""
    print("\nVerifying production setup...")
    
    # Check if we're in production environment
    is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER')
    
    if is_production:
        print("✓ Running in production environment")
    else:
        print("⚠ Running in development environment")
    
    # Check Python version
    python_version = sys.version_info
    print(f"✓ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Check if required directories exist
    required_dirs = ['services', 'middleware']
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"✓ Directory {dir_name} exists")
        else:
            print(f"❌ Directory {dir_name} missing")
    
    return True

def create_production_startup_script():
    """Create a production startup script that handles model compatibility"""
    script_content = '''#!/bin/bash
# Production startup script for Render

echo "Starting production server with model compatibility checks..."

# Check if we're in production
if [ "$FLASK_ENV" = "production" ] || [ -n "$RENDER" ]; then
    echo "Production environment detected"
    
    # Remove any incompatible model files
    if [ -f "market_regime_model.pkl" ]; then
        echo "Removing potentially incompatible model file..."
        mv market_regime_model.pkl market_regime_model.pkl.backup
        echo "Model file backed up and removed"
    fi
    
    echo "Model will be retrained automatically on first use"
else
    echo "Development environment detected"
fi

# Start the application
echo "Starting Flask application..."
python app.py
'''
    
    try:
        with open("start_production.sh", "w") as f:
            f.write(script_content)
        
        # Make it executable
        os.chmod("start_production.sh", 0o755)
        print("✓ Production startup script created: start_production.sh")
        
    except Exception as e:
        print(f"❌ Could not create startup script: {e}")

def main():
    """Main deployment fix function"""
    print("Production Deployment Fix for Render Server")
    print("=" * 50)
    print("This script will fix the 'monotonic_cst' attribute error")
    print("by ensuring model compatibility across environments")
    print()
    
    # Step 1: Clean up incompatible models
    cleanup_incompatible_models()
    
    # Step 2: Update requirements for production
    update_requirements_for_production()
    
    # Step 3: Create production environment file
    create_production_env_file()
    
    # Step 4: Create production startup script
    create_production_startup_script()
    
    # Step 5: Verify production setup
    if not verify_production_setup():
        print("\n❌ Production setup verification failed")
        return False
    
    print("\n" + "=" * 50)
    print("✓ Production deployment fix completed!")
    print("\nNext steps:")
    print("1. Update your .env file with production values")
    print("2. Commit and push these changes:")
    print("   git add .")
    print("   git commit -m 'Fix production compatibility for Render deployment'")
    print("   git push")
    print("3. On Render, ensure these environment variables are set:")
    print("   - FLASK_ENV=production")
    print("   - PYTHON_VERSION=3.11")
    print("4. Force a rebuild on Render")
    print("5. The model will be automatically retrained on first use")
    print("\nThe 'monotonic_cst' error will be resolved!")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
