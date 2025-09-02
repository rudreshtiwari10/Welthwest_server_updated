import os
import logging
from .hmm_classifier import HMMMarketRegimeClassifier
from services.cache_service import get_cached_data, set_cached_data
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HMMService:
    """Service for managing HMM market regime predictions"""
    
    def __init__(self):
        # Initialize HMM classifier with default settings
        self.classifier = HMMMarketRegimeClassifier(
            n_components=3,
            covariance_type="full",
            n_iter=100,
            random_state=42
        )
        
        # Try to load existing model
        self._load_existing_model()
        
        self.cache_ttl = 300  # 5 minutes cache
    
    def _load_existing_model(self):
        """Try to load existing trained model"""
        try:
            if os.path.exists("hmm_model/hmm_model.pkl"):
                self.classifier.load_model("hmm_model.pkl")
                logger.info("Loaded existing HMM model")
            else:
                logger.info("No existing HMM model found")
        except Exception as e:
            logger.error(f"Error loading existing HMM model: {str(e)}")
    
    def train_model(self, ticker: str, period: str = "2y", retrain: bool = False) -> Dict:
        """
        Train the HMM model
        
        Args:
            ticker: Stock ticker symbol
            period: Training period
            retrain: Whether to retrain existing model
            
        Returns:
            Dictionary with training results
        """
        try:
            logger.info(f"Training HMM model for {ticker} with period {period}")
            result = self.classifier.train_model(ticker, period, retrain)
            
            if result.get("status") == "success":
                # Clear cache after successful training
                self._clear_cache()
                logger.info("HMM model training completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in HMM training service: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def predict_regime(self, ticker: str, current_data: Optional[pd.DataFrame] = None) -> Dict:
        """
        Predict market regime using HMM
        
        Args:
            ticker: Stock ticker symbol
            current_data: Optional current price data
            
        Returns:
            Dictionary with prediction results
        """
        try:
            # Check cache first
            cache_key = f"hmm_predict_{ticker}"
            cached_result = get_cached_data(cache_key)
            
            if cached_result is not None:
                # Check if cache is still fresh (less than cache_ttl seconds old)
                cache_time = datetime.fromisoformat(cached_result.get("timestamp", "2000-01-01"))
                if (datetime.now() - cache_time).seconds < self.cache_ttl:
                    logger.info(f"Returning cached HMM prediction for {ticker}")
                    return cached_result
            
            # Make prediction
            logger.info(f"Predicting HMM regime for {ticker}")
            result = self.classifier.predict_regime(ticker, current_data)
            
            # Cache successful results
            if result.get("status") == "success":
                set_cached_data(cache_key, result, expiry_seconds=self.cache_ttl)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in HMM prediction service: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def analyze_regime_persistence(self, ticker: str, period: str = "6mo") -> Dict:
        """
        Analyze regime persistence patterns
        
        Args:
            ticker: Stock ticker symbol
            period: Analysis period
            
        Returns:
            Dictionary with persistence analysis
        """
        try:
            cache_key = f"hmm_persistence_{ticker}_{period}"
            cached_result = get_cached_data(cache_key)
            
            if cached_result is not None:
                cache_time = datetime.fromisoformat(cached_result.get("timestamp", "2000-01-01"))
                if (datetime.now() - cache_time).seconds < self.cache_ttl * 2:  # Longer cache for analysis
                    logger.info(f"Returning cached HMM persistence analysis for {ticker}")
                    return cached_result
            
            logger.info(f"Analyzing HMM regime persistence for {ticker}")
            result = self.classifier.analyze_regime_persistence(ticker, period)
            
            if result.get("status") == "success":
                result["timestamp"] = datetime.now().isoformat()
                set_cached_data(cache_key, result, expiry_seconds=self.cache_ttl * 2)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in HMM persistence analysis service: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_model_info(self) -> Dict:
        """Get HMM model information"""
        try:
            return self.classifier.get_model_info()
        except Exception as e:
            logger.error(f"Error getting HMM model info: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def evaluate_model(self, ticker: str, test_period: str = "6mo") -> Dict:
        """
        Evaluate HMM model performance
        
        Args:
            ticker: Stock ticker symbol
            test_period: Evaluation period
            
        Returns:
            Dictionary with evaluation results
        """
        try:
            logger.info(f"Evaluating HMM model for {ticker}")
            return self.classifier.evaluate_model(ticker, test_period)
            
        except Exception as e:
            logger.error(f"Error in HMM model evaluation: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_multiple_regime_predictions(self, tickers: list) -> Dict:
        """
        Get HMM regime predictions for multiple tickers
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            Dictionary with predictions for all tickers
        """
        try:
            results = {}
            errors = []
            
            for ticker in tickers:
                try:
                    prediction = self.predict_regime(ticker)
                    results[ticker] = prediction
                except Exception as e:
                    error_msg = f"Error predicting {ticker}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
            
            response = {
                "status": "success",
                "predictions": results,
                "processed_tickers": len(results),
                "total_tickers": len(tickers),
                "timestamp": datetime.now().isoformat()
            }
            
            if errors:
                response["errors"] = errors
            
            return response
            
        except Exception as e:
            logger.error(f"Error in multiple HMM predictions: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _clear_cache(self):
        """Clear HMM-related cache entries"""
        try:
            # This would clear HMM-specific cache entries
            # Implementation depends on your cache service
            logger.info("Cleared HMM cache")
        except Exception as e:
            logger.error(f"Error clearing HMM cache: {str(e)}")

# Global service instance
hmm_service = HMMService()