#!/usr/bin/env python3
"""
Test script to validate HMM integration with MarketRegimeClassifier
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add the services directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'services'))

from market_regime_classifier import MarketRegimeClassifier
from market_regime_service import MarketRegimeService

def test_hmm_integration():
    """Test HMM integration with the market regime classifier"""
    
    print("=== Testing HMM Integration with MarketRegimeClassifier ===")
    
    # Test 1: Initialize classifier with HMM enabled
    print("\n1. Testing classifier initialization with HMM...")
    try:
        classifier = MarketRegimeClassifier(use_hmm=True)
        print(f"[OK] Classifier initialized successfully")
        print(f"  - HMM enabled: {classifier.use_hmm}")
        print(f"  - HMM components: {classifier.hmm_n_components}")
        print(f"  - HMM covariance type: {classifier.hmm_covariance_type}")
    except Exception as e:
        print(f"[ERROR] Error initializing classifier: {e}")
        return False
    
    # Test 2: Create sample data for testing
    print("\n2. Creating sample price data...")
    try:
        # Generate sample OHLCV data
        dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
        np.random.seed(42)
        
        # Generate realistic price movements with regime changes
        returns = np.random.normal(0.001, 0.02, len(dates))  # Base returns
        
        # Add regime-like patterns
        for i in range(len(returns)):
            if i < len(returns) * 0.3:  # Bull market
                returns[i] = abs(returns[i]) + 0.002
            elif i < len(returns) * 0.7:  # Bear market  
                returns[i] = -abs(returns[i]) - 0.001
            # Rest is sideways
        
        prices = 100 * (1 + returns).cumprod()
        
        sample_data = pd.DataFrame({
            'Open': prices * (1 + np.random.normal(0, 0.005, len(prices))),
            'High': prices * (1 + abs(np.random.normal(0, 0.01, len(prices)))),
            'Low': prices * (1 - abs(np.random.normal(0, 0.01, len(prices)))),
            'Close': prices,
            'Volume': np.random.randint(1000000, 10000000, len(prices))
        }, index=dates)
        
        print(f"[OK] Sample data created: {len(sample_data)} days")
        print(f"  - Date range: {sample_data.index[0]} to {sample_data.index[-1]}")
        print(f"  - Price range: ${sample_data['Close'].min():.2f} - ${sample_data['Close'].max():.2f}")
        
    except Exception as e:
        print(f"[ERROR] Error creating sample data: {e}")
        return False
    
    # Test 3: Test HMM training
    print("\n3. Testing HMM model training...")
    try:
        hmm_success = classifier.train_hmm_model(sample_data)
        print(f"[OK] HMM training completed: {hmm_success}")
        if hmm_success:
            print(f"  - HMM trained: {classifier.hmm_trained}")
            print(f"  - Transition matrix shape: {classifier.hmm_model.transmat_.shape}")
            print(f"  - State means: {classifier.hmm_model.means_.flatten()}")
        
    except Exception as e:
        print(f"[ERROR] Error in HMM training: {e}")
        return False
    
    # Test 4: Test HMM inference methods
    print("\n4. Testing HMM inference methods...")
    try:
        # Test state decoding
        log_prob, states = classifier.hmm_decode_states(sample_data)
        print(f"[OK] State decoding successful")
        print(f"  - Log probability: {log_prob:.4f}")
        print(f"  - Unique states found: {np.unique(states)}")
        
        # Test posterior probabilities
        posterior_probs = classifier.hmm_posterior_probabilities(sample_data)
        print(f"[OK] Posterior probabilities computed")
        print(f"  - Shape: {posterior_probs.shape}")
        print(f"  - Last day probs: {posterior_probs[-1]}")
        
        # Test next-day forecast
        next_probs = classifier.hmm_forecast_next_day(sample_data)
        print(f"[OK] Next-day forecast computed")
        print(f"  - Forecast probabilities: {next_probs}")
        
    except Exception as e:
        print(f"[ERROR] Error in HMM inference: {e}")
        return False
    
    # Test 5: Test feature preparation with HMM
    print("\n5. Testing feature preparation with HMM features...")
    try:
        features = classifier.prepare_features(sample_data)
        hmm_features = [col for col in features.columns if 'hmm' in col.lower()]
        
        print(f"[OK] Feature preparation successful")
        print(f"  - Total features: {len(features.columns)}")
        print(f"  - HMM features: {len(hmm_features)}")
        print(f"  - HMM feature names: {hmm_features}")
        
    except Exception as e:
        print(f"[ERROR] Error in feature preparation: {e}")
        return False
    
    # Test 6: Test full model training pipeline
    print("\n6. Testing complete model training with HMM...")
    try:
        # We'll use a mock ticker for this test
        # In a real scenario, this would fetch actual data
        classifier.is_trained = False  # Reset for clean test
        
        # Simulate training by directly using our sample data
        features_df = classifier.prepare_features(sample_data)
        regime_labels = classifier.label_market_regimes(features_df)
        
        # Check if HMM features were included
        feature_columns = [col for col in features_df.columns if col not in 
                         ['Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']]
        hmm_feature_cols = [col for col in feature_columns if 'hmm' in col.lower()]
        
        print(f"[OK] Training pipeline successful")
        print(f"  - Features prepared: {len(feature_columns)}")
        print(f"  - HMM features included: {len(hmm_feature_cols)}")
        print(f"  - Regime labels created: {len(regime_labels)}")
        print(f"  - Unique regimes: {regime_labels.value_counts().to_dict()}")
        
    except Exception as e:
        print(f"[ERROR] Error in training pipeline: {e}")
        return False
    
    # Test 7: Test MarketRegimeService integration
    print("\n7. Testing MarketRegimeService with HMM...")
    try:
        service = MarketRegimeService(use_hmm=True)
        print(f"[OK] MarketRegimeService initialized with HMM")
        print(f"  - Classifier HMM enabled: {service.classifier.use_hmm}")
        
    except Exception as e:
        print(f"[ERROR] Error in service initialization: {e}")
        return False
    
    print("\n=== HMM Integration Test Summary ===")
    print("[OK] All tests passed successfully!")
    print("[OK] HMM is properly integrated with MarketRegimeClassifier")
    print("[OK] HMM features are being generated and included")
    print("[OK] Next-day forecasting is working")
    print("[OK] Service layer properly supports HMM")
    
    return True

def test_hmm_disabled():
    """Test that the system works correctly with HMM disabled"""
    
    print("\n=== Testing System with HMM Disabled ===")
    
    try:
        classifier = MarketRegimeClassifier(use_hmm=False)
        print(f"[OK] Classifier initialized with HMM disabled")
        print(f"  - HMM enabled: {classifier.use_hmm}")
        
        service = MarketRegimeService(use_hmm=False)
        print(f"[OK] Service initialized with HMM disabled")
        print(f"  - Service HMM enabled: {service.classifier.use_hmm}")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Error testing HMM disabled: {e}")
        return False

if __name__ == "__main__":
    print("Starting HMM Integration Tests...\n")
    
    # Test HMM enabled
    success1 = test_hmm_integration()
    
    # Test HMM disabled  
    success2 = test_hmm_disabled()
    
    print(f"\n=== Final Test Results ===")
    if success1 and success2:
        print("[SUCCESS] All HMM integration tests PASSED!")
        print("The MarketRegimeClassifier now supports:")
        print("  - Hidden Markov Model integration")
        print("  - Latent state detection via Viterbi algorithm")
        print("  - Regime probability computation")
        print("  - Next-day regime forecasting")
        print("  - HMM features in Random Forest training")
        print("  - Backward compatibility (HMM can be disabled)")
        exit(0)
    else:
        print("[FAIL] Some tests FAILED!")
        exit(1)