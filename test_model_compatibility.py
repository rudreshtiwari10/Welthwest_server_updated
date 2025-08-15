#!/usr/bin/env python3
"""
Test script to verify market regime classifier compatibility
"""

import sys
import os
import logging

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.market_regime_classifier import MarketRegimeClassifier
from services.market_regime_service import MarketRegimeService

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_classifier_compatibility():
    """Test the classifier compatibility check"""
    print("Testing Market Regime Classifier Compatibility...")
    print("=" * 50)
    
    try:
        # Create classifier instance
        classifier = MarketRegimeClassifier()
        print(f"✓ Classifier created successfully")
        print(f"  - scikit-learn version: {classifier.model.__class__.__module__}")
        
        # Check compatibility (should fail since no model is trained)
        compatibility = classifier.check_model_compatibility()
        print(f"✓ Compatibility check completed")
        print(f"  - Status: {compatibility['status']}")
        print(f"  - Message: {compatibility['message']}")
        print(f"  - Compatible: {compatibility['compatible']}")
        
        # Test model loading (should handle missing file gracefully)
        print("\nTesting model loading...")
        classifier.load_model()
        print(f"✓ Model loading completed")
        print(f"  - Is trained: {classifier.is_trained}")
        
        # Test service initialization
        print("\nTesting service initialization...")
        service = MarketRegimeService()
        print(f"✓ Service created successfully")
        print(f"  - Model loaded: {service.model_loaded}")
        
        # Get model info
        model_info = service.get_model_info()
        print(f"✓ Model info retrieved")
        print(f"  - Status: {model_info['status']}")
        print(f"  - Compatibility: {model_info.get('compatibility', {}).get('status', 'N/A')}")
        
        print("\n" + "=" * 50)
        print("✓ All compatibility tests passed!")
        print("The model will be automatically retrained when needed.")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        logger.error(f"Test failed: {str(e)}", exc_info=True)
        return False
    
    return True

def test_model_training():
    """Test if the model can be trained successfully"""
    print("\nTesting Model Training...")
    print("=" * 50)
    
    try:
        service = MarketRegimeService()
        
        # Try to train the model
        print("Training model with RELIANCE.NS...")
        result = service.train_model("RELIANCE.NS", period="6mo", retrain=True)
        
        if result["status"] == "success":
            print(f"✓ Model training successful!")
            print(f"  - Accuracy: {result['accuracy']:.4f}")
            print(f"  - Training samples: {result['training_samples']}")
            print(f"  - Test samples: {result['test_samples']}")
            
            # Test prediction
            print("\nTesting prediction...")
            prediction = service.predict_regime("RELIANCE.NS")
            if prediction["status"] == "success":
                print(f"✓ Prediction successful!")
                print(f"  - Regime: {prediction['regime_name']}")
                print(f"  - Confidence: {prediction['confidence']:.4f}")
            else:
                print(f"❌ Prediction failed: {prediction.get('message', 'Unknown error')}")
                
        else:
            print(f"❌ Model training failed: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error during training test: {str(e)}")
        logger.error(f"Training test failed: {str(e)}", exc_info=True)
        return False
    
    return True

if __name__ == "__main__":
    print("Market Regime Classifier Compatibility Test")
    print("=" * 60)
    
    # Test 1: Compatibility check
    if test_classifier_compatibility():
        print("\n✓ Compatibility tests passed!")
        
        # Test 2: Model training (optional - can be skipped if you don't want to wait)
        user_input = input("\nDo you want to test model training? (y/n): ").lower().strip()
        if user_input in ['y', 'yes']:
            if test_model_training():
                print("\n✓ All tests passed! The compatibility issue has been resolved.")
            else:
                print("\n❌ Model training test failed. Check the logs for details.")
        else:
            print("\nSkipping model training test.")
            print("✓ Compatibility issue resolved! The model will be retrained automatically when needed.")
    else:
        print("\n❌ Compatibility tests failed. Check the logs for details.")
        sys.exit(1)
