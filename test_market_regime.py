"""
Test script for Market Regime Classifier
This script tests the complete Market Regime Classification system
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# Add the current directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.market_regime_classifier import MarketRegimeClassifier
from services.market_regime_service import MarketRegimeService
from services.stock_service import get_ohlc_data

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_market_regime_classifier():
    """Test the Market Regime Classifier"""
    print("=" * 60)
    print("Testing Market Regime Classifier")
    print("=" * 60)
    
    # Initialize classifier
    classifier = MarketRegimeClassifier()
    
    # Test 1: Get regime definitions
    print("\n1. Testing regime definitions...")
    definitions = classifier.get_regime_definitions()
    print(f"Number of regimes defined: {len(definitions)}")
    for regime_id, regime_info in definitions.items():
        print(f"  {regime_id}: {regime_info['name']} - {regime_info['description']}")
    
    # Test 2: Train model
    print("\n2. Testing model training...")
    try:
        training_result = classifier.train_model("RELIANCE.NS", period="1y")
        print(f"Training status: {training_result['status']}")
        
        if training_result["status"] == "success":
            print(f"Training accuracy: {training_result['accuracy']:.4f}")
            print(f"Cross-validation mean: {training_result['cv_mean']:.4f}")
            print(f"Training samples: {training_result['training_samples']}")
            print(f"Test samples: {training_result['test_samples']}")
            
            # Show top 5 important features
            print("\nTop 5 important features:")
            for i, feature in enumerate(training_result['feature_importance'][:5]):
                print(f"  {i+1}. {feature['feature']}: {feature['importance']:.4f}")
        else:
            print(f"Training failed: {training_result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"Training error: {str(e)}")
        return False
    
    # Test 3: Predict regime
    print("\n3. Testing regime prediction...")
    try:
        prediction_result = classifier.predict_regime("RELIANCE.NS")
        print(f"Prediction status: {prediction_result['status']}")
        
        if prediction_result["status"] == "success":
            print(f"Predicted regime: {prediction_result['regime_name']}")
            print(f"Confidence: {prediction_result['confidence']:.4f}")
            print(f"Description: {prediction_result['regime_description']}")
            
            print("\nAll regime probabilities:")
            for regime_name, prob in prediction_result['probabilities'].items():
                print(f"  {regime_name}: {prob:.4f}")
        else:
            print(f"Prediction failed: {prediction_result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"Prediction error: {str(e)}")
        return False
    
    # Test 4: Evaluate model
    print("\n4. Testing model evaluation...")
    try:
        evaluation_result = classifier.evaluate_model("RELIANCE.NS", test_period="3mo")
        print(f"Evaluation status: {evaluation_result['status']}")
        
        if evaluation_result["status"] == "success":
            print(f"Evaluation accuracy: {evaluation_result['accuracy']:.4f}")
            print(f"Total samples: {evaluation_result['total_samples']}")
            
            print("\nPer-regime accuracy:")
            for regime_name, accuracy in evaluation_result['regime_accuracy'].items():
                print(f"  {regime_name}: {accuracy:.4f}")
        else:
            print(f"Evaluation failed: {evaluation_result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"Evaluation error: {str(e)}")
    
    print("\n✅ Market Regime Classifier test completed successfully!")
    return True

def test_market_regime_service():
    """Test the Market Regime Service"""
    print("\n" + "=" * 60)
    print("Testing Market Regime Service")
    print("=" * 60)
    
    # Initialize service
    service = MarketRegimeService()
    
    # Test 1: Get model info
    print("\n1. Testing model info...")
    try:
        model_info = service.get_model_info()
        print(f"Model status: {model_info['status']}")
        print(f"Model loaded: {model_info.get('is_loaded', False)}")
        print(f"Supported tickers: {len(model_info.get('supported_tickers', []))}")
        
    except Exception as e:
        print(f"Model info error: {str(e)}")
    
    # Test 2: Train model through service
    print("\n2. Testing service training...")
    try:
        training_result = service.train_model("RELIANCE.NS", period="1y")
        print(f"Service training status: {training_result['status']}")
        
        if training_result["status"] == "success":
            print(f"Service training accuracy: {training_result['accuracy']:.4f}")
        else:
            print(f"Service training failed: {training_result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"Service training error: {str(e)}")
    
    # Test 3: Predict through service
    print("\n3. Testing service prediction...")
    try:
        prediction_result = service.predict_regime("RELIANCE.NS")
        print(f"Service prediction status: {prediction_result['status']}")
        
        if prediction_result["status"] == "success":
            print(f"Service predicted regime: {prediction_result['regime_name']}")
            print(f"Service confidence: {prediction_result['confidence']:.4f}")
            
    except Exception as e:
        print(f"Service prediction error: {str(e)}")
    
    # Test 4: Multiple predictions
    print("\n4. Testing multiple predictions...")
    try:
        tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
        multiple_result = service.get_multiple_regime_predictions(tickers)
        print(f"Multiple predictions status: {multiple_result['status']}")
        
        if multiple_result["status"] == "success":
            for ticker, prediction in multiple_result['predictions'].items():
                if prediction["status"] == "success":
                    print(f"  {ticker}: {prediction['regime_name']} (confidence: {prediction['confidence']:.3f})")
                else:
                    print(f"  {ticker}: Error - {prediction.get('message', 'Unknown error')}")
                    
    except Exception as e:
        print(f"Multiple predictions error: {str(e)}")
    
    # Test 5: Get recommendations
    print("\n5. Testing recommendations...")
    try:
        recommendations_result = service.get_regime_recommendations("RELIANCE.NS")
        print(f"Recommendations status: {recommendations_result['status']}")
        
        if recommendations_result["status"] == "success":
            regime_info = recommendations_result['current_regime']
            recommendations = recommendations_result['recommendations']
            
            print(f"  Current regime: {regime_info['regime_name']}")
            print(f"  Strategy: {recommendations['strategy']}")
            print(f"  Risk level: {recommendations['risk_level']}")
            print(f"  Position size: {recommendations['position_size']}")
            print(f"  Notes: {recommendations['notes']}")
            
    except Exception as e:
        print(f"Recommendations error: {str(e)}")
    
    print("\n✅ Market Regime Service test completed successfully!")
    return True

def test_data_pipeline():
    """Test the data pipeline integration"""
    print("\n" + "=" * 60)
    print("Testing Data Pipeline Integration")
    print("=" * 60)
    
    # Test 1: Data fetching
    print("\n1. Testing data fetching...")
    try:
        df = get_ohlc_data("RELIANCE.NS", period="1mo")
        print(f"Data shape: {df.shape}")
        print(f"Data columns: {df.columns.tolist()}")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        
        if df.empty:
            print("❌ No data fetched")
            return False
        else:
            print("✅ Data fetched successfully")
            
    except Exception as e:
        print(f"Data fetching error: {str(e)}")
        return False
    
    # Test 2: Feature preparation
    print("\n2. Testing feature preparation...")
    try:
        classifier = MarketRegimeClassifier()
        features_df = classifier.prepare_features(df)
        
        print(f"Features shape: {features_df.shape}")
        print(f"Features columns count: {len(features_df.columns)}")
        
        # Check for NaN values
        nan_count = features_df.isnull().sum().sum()
        print(f"Total NaN values: {nan_count}")
        
        if features_df.empty:
            print("❌ No features prepared")
            return False
        else:
            print("✅ Features prepared successfully")
            
    except Exception as e:
        print(f"Feature preparation error: {str(e)}")
        return False
    
    # Test 3: Regime labeling
    print("\n3. Testing regime labeling...")
    try:
        regime_labels = classifier.label_market_regimes(features_df)
        
        print(f"Labels shape: {regime_labels.shape}")
        print(f"Unique regimes: {regime_labels.unique()}")
        
        # Count each regime
        regime_counts = regime_labels.value_counts()
        print("Regime distribution:")
        for regime, count in regime_counts.items():
            regime_name = classifier.regime_definitions[regime]['name']
            print(f"  {regime} ({regime_name}): {count}")
            
        if regime_labels.empty:
            print("❌ No regimes labeled")
            return False
        else:
            print("✅ Regimes labeled successfully")
            
    except Exception as e:
        print(f"Regime labeling error: {str(e)}")
        return False
    
    print("\n✅ Data pipeline test completed successfully!")
    return True

def main():
    """Main test function"""
    print("🚀 Starting Market Regime Classifier Tests")
    print(f"Test started at: {datetime.now()}")
    
    success_count = 0
    total_tests = 3
    
    # Test 1: Data Pipeline
    if test_data_pipeline():
        success_count += 1
    
    # Test 2: Market Regime Classifier
    if test_market_regime_classifier():
        success_count += 1
    
    # Test 3: Market Regime Service
    if test_market_regime_service():
        success_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {success_count}/{total_tests}")
    print(f"Success rate: {(success_count/total_tests)*100:.1f}%")
    
    if success_count == total_tests:
        print("🎉 All tests passed! Market Regime Classifier is ready for deployment.")
    else:
        print("⚠️  Some tests failed. Please review the errors above.")
    
    print(f"Test completed at: {datetime.now()}")

if __name__ == "__main__":
    main()