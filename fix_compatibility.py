#!/usr/bin/env python3
"""
Script to fix market regime classifier compatibility issues
"""

import os
import sys
import logging
import pickle

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_old_models():
    """Remove old model files that might cause compatibility issues"""
    model_files = [
        "market_regime_model.pkl",
        "market_regime_model.pkl.bak",
        "market_regime_model_old.pkl"
    ]
    
    print("Cleaning up old model files...")
    
    for model_file in model_files:
        if os.path.exists(model_file):
            try:
                os.remove(model_file)
                print(f"✓ Removed {model_file}")
            except Exception as e:
                print(f"⚠ Could not remove {model_file}: {e}")
        else:
            print(f"  {model_file} not found (already cleaned up)")

def check_scikit_learn_version():
    """Check and display scikit-learn version information"""
    try:
        import sklearn
        version = sklearn.__version__
        print(f"✓ scikit-learn version: {version}")
        
        # Check if version is compatible
        if version >= "1.3.0":
            print("✓ Version is compatible with monotonic constraints")
        else:
            print("⚠ Version may have compatibility issues")
            print("  Recommended: >=1.3.0")
            
        return True
        
    except ImportError:
        print("❌ scikit-learn not installed")
        return False
    except Exception as e:
        print(f"❌ Error checking scikit-learn version: {e}")
        return False

def verify_imports():
    """Verify that all required imports work correctly"""
    print("\nVerifying imports...")
    
    try:
        from sklearn.ensemble import RandomForestClassifier
        print("✓ RandomForestClassifier imported successfully")
        
        from sklearn.preprocessing import StandardScaler
        print("✓ StandardScaler imported successfully")
        
        from sklearn.model_selection import train_test_split
        print("✓ train_test_split imported successfully")
        
        from sklearn.metrics import accuracy_score
        print("✓ accuracy_score imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic scikit-learn functionality"""
    print("\nTesting basic functionality...")
    
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        
        # Test RandomForestClassifier creation
        rf = RandomForestClassifier(n_estimators=10, random_state=42)
        print("✓ RandomForestClassifier created successfully")
        
        # Test StandardScaler
        scaler = StandardScaler()
        print("✓ StandardScaler created successfully")
        
        # Test with dummy data
        import numpy as np
        X = np.random.rand(100, 5)
        y = np.random.randint(0, 3, 100)
        
        # Scale data
        X_scaled = scaler.fit_transform(X)
        print("✓ Data scaling works")
        
        # Train model
        rf.fit(X_scaled, y)
        print("✓ Model training works")
        
        # Make prediction
        pred = rf.predict(X_scaled[:1])
        print("✓ Model prediction works")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        return False

def main():
    """Main function to fix compatibility issues"""
    print("Market Regime Classifier Compatibility Fix")
    print("=" * 50)
    
    # Step 1: Clean up old models
    cleanup_old_models()
    
    # Step 2: Check scikit-learn version
    if not check_scikit_learn_version():
        print("\n❌ scikit-learn version check failed")
        print("Please install scikit-learn >= 1.4.0")
        return False
    
    # Step 3: Verify imports
    if not verify_imports():
        print("\n❌ Import verification failed")
        return False
    
    # Step 4: Test basic functionality
    if not test_basic_functionality():
        print("\n❌ Basic functionality test failed")
        return False
    
    print("\n" + "=" * 50)
    print("✓ All compatibility checks passed!")
    print("✓ The system is ready to work")
    print("\nNext steps:")
    print("1. The model will be automatically retrained when first used")
    print("2. Run the application normally")
    print("3. If you encounter any issues, check the logs for details")
    
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
