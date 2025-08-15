from flask import Flask, request, jsonify
from services.market_regime_classifier import MarketRegimeClassifier
from services.cache_service import get_cached_data, set_cached_data
from services.stock_service import get_historical_data
from datetime import datetime, timedelta
import logging
import threading
import time
import schedule
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketRegimeService:
    """
    Service layer for Market Regime Classification
    Handles real-time prediction, caching, and model management
    """
    
    def __init__(self):
        self.classifier = MarketRegimeClassifier()
        self.model_loaded = False
        self.last_training_time = None
        self.scheduler_running = False
        self.supported_tickers = [
            'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS',
            'SBIN.NS', 'HINDUNILVR.NS', 'BHARTIARTL.NS', 'ITC.NS', 'KOTAKBANK.NS',
            'LT.NS', 'AXISBANK.NS', 'MARUTI.NS', 'ASIANPAINT.NS', 'TATAMOTORS.NS',
            'WIPRO.NS', 'BAJFINANCE.NS', 'HCLTECH.NS', 'SUNPHARMA.NS', 'ULTRACEMCO.NS'
        ]
        
        # Initialize model on startup
        self._initialize_model()
        
        # Start background scheduler
        self._start_scheduler()
    
    def _initialize_model(self):
        """Initialize the classifier model"""
        try:
            # Try to load existing model first
            self.classifier.load_model()
            self.model_loaded = True
            logger.info("Market regime model loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load existing model: {str(e)}")
            logger.info("Model will be trained on first use")
            self.model_loaded = False
    
    def _start_scheduler(self):
        """Start background scheduler for model updates"""
        if not self.scheduler_running:
            # Schedule daily retraining at 6 PM (after market close)
            schedule.every().day.at("18:00").do(self._scheduled_retrain)
            
            # Schedule hourly model updates during market hours
            schedule.every().hour.do(self._scheduled_update)
            
            # Start scheduler in background thread
            def run_scheduler():
                while True:
                    schedule.run_pending()
                    time.sleep(60)  # Check every minute
            
            scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
            scheduler_thread.start()
            self.scheduler_running = True
            logger.info("Market regime scheduler started")
    
    def _scheduled_retrain(self):
        """Scheduled full model retraining"""
        try:
            logger.info("Starting scheduled model retraining")
            # Use a major index for training
            result = self.train_model("RELIANCE.NS", period="2y", retrain=True)
            if result["status"] == "success":
                logger.info(f"Scheduled retraining completed. Accuracy: {result['accuracy']:.4f}")
            else:
                logger.error(f"Scheduled retraining failed: {result.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error in scheduled retraining: {str(e)}")
    
    def _scheduled_update(self):
        """Scheduled model update with recent data"""
        try:
            if self.model_loaded:
                logger.info("Starting scheduled model update")
                self.classifier.retrain_with_recent_data("RELIANCE.NS", days_back=7)
                logger.info("Scheduled model update completed")
        except Exception as e:
            logger.error(f"Error in scheduled update: {str(e)}")
    
    def train_model(self, ticker: str = "RELIANCE.NS", period: str = "2y", retrain: bool = False) -> Dict:
        """
        Train the market regime classifier
        
        Args:
            ticker: Stock ticker for training
            period: Historical period for training
            retrain: Whether to retrain existing model
            
        Returns:
            Training results
        """
        try:
            logger.info(f"Training model with ticker: {ticker}, period: {period}")
            
            result = self.classifier.train_model(ticker, period, retrain)
            
            if result["status"] == "success":
                self.model_loaded = True
                self.last_training_time = datetime.now()
                
                # Cache training results
                cache_key = "model_training_results"
                training_info = {
                    "ticker": ticker,
                    "period": period,
                    "accuracy": result["accuracy"],
                    "training_time": self.last_training_time.isoformat(),
                    "feature_importance": result["feature_importance"][:10]  # Top 10 features
                }
                set_cached_data(cache_key, training_info, 86400)  # Cache for 24 hours
                
                logger.info(f"Model training completed successfully. Accuracy: {result['accuracy']:.4f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in model training: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def predict_regime(self, ticker: str) -> Dict:
        """
        Predict market regime for a given ticker
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Regime prediction results
        """
        try:
            # Check cache first
            cache_key = f"regime_prediction_{ticker}"
            cached_result = get_cached_data(cache_key)
            
            if cached_result:
                logger.info(f"Using cached regime prediction for {ticker}")
                return cached_result
            
            # Ensure model is trained
            if not self.model_loaded:
                logger.info("Model not loaded. Training now...")
                train_result = self.train_model()
                if train_result["status"] != "success":
                    return train_result
            
            # Get prediction
            result = self.classifier.predict_regime(ticker)
            
            if result["status"] == "success":
                # Cache the result for 15 minutes (real-time with delay)
                set_cached_data(cache_key, result, 900)
                
                logger.info(f"Regime prediction for {ticker}: {result['regime_name']} (confidence: {result['confidence']:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error predicting regime for {ticker}: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_regime_analysis(self, ticker: str) -> Dict:
        """
        Get comprehensive regime analysis including historical patterns
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Comprehensive regime analysis
        """
        try:
            # Get current prediction
            current_prediction = self.predict_regime(ticker)
            
            if current_prediction["status"] != "success":
                return current_prediction
            
            # Get historical regime patterns
            historical_analysis = self._analyze_historical_regimes(ticker)
            
            # Get regime transitions
            transitions = self._analyze_regime_transitions(ticker)
            
            # Combine results
            analysis = {
                "status": "success",
                "ticker": ticker,
                "current_regime": current_prediction,
                "historical_analysis": historical_analysis,
                "regime_transitions": transitions,
                "timestamp": datetime.now().isoformat()
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error in regime analysis for {ticker}: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _analyze_historical_regimes(self, ticker: str, period: str = "1y") -> Dict:
        """Analyze historical regime patterns"""
        try:
            # Get historical data
            df = get_historical_data(ticker, period=period)
            
            if df.empty:
                return {"error": "No historical data available"}
            
            # Prepare features and predict for historical data
            features_df = self.classifier.prepare_features(df)
            
            # Predict regimes for historical data
            historical_regimes = []
            for i in range(len(features_df)):
                if i < self.classifier.lookback_period:
                    continue
                
                try:
                    features = features_df[self.classifier.feature_names].iloc[i:i+1].ffill()
                    features_scaled = self.classifier.scaler.transform(features)
                    regime_pred = self.classifier.model.predict(features_scaled)[0]
                    historical_regimes.append({
                        "date": df.index[i].strftime('%Y-%m-%d'),
                        "regime": regime_pred,
                        "regime_name": self.classifier.regime_definitions[regime_pred]['name']
                    })
                except Exception:
                    continue
            
            # Calculate regime statistics
            regime_counts = {}
            for regime in historical_regimes:
                regime_name = regime['regime_name']
                regime_counts[regime_name] = regime_counts.get(regime_name, 0) + 1
            
            total_periods = len(historical_regimes)
            regime_percentages = {
                regime: (count / total_periods) * 100 
                for regime, count in regime_counts.items()
            }
            
            return {
                "total_periods": total_periods,
                "regime_distribution": regime_counts,
                "regime_percentages": regime_percentages,
                "recent_regimes": historical_regimes[-30:] if len(historical_regimes) > 30 else historical_regimes
            }
            
        except Exception as e:
            logger.error(f"Error analyzing historical regimes: {str(e)}")
            return {"error": str(e)}
    
    def _analyze_regime_transitions(self, ticker: str, period: str = "6mo") -> Dict:
        """Analyze regime transition patterns"""
        try:
            # Get historical data
            df = get_historical_data(ticker, period=period)
            
            if df.empty:
                return {"error": "No data available for transition analysis"}
            
            # Prepare features
            features_df = self.classifier.prepare_features(df)
            
            # Predict regimes
            regimes = []
            for i in range(self.classifier.lookback_period, len(features_df)):
                try:
                    features = features_df[self.classifier.feature_names].iloc[i:i+1].ffill()
                    features_scaled = self.classifier.scaler.transform(features)
                    regime_pred = self.classifier.model.predict(features_scaled)[0]
                    regimes.append(regime_pred)
                except Exception:
                    continue
            
            # Find transitions
            transitions = []
            for i in range(1, len(regimes)):
                if regimes[i] != regimes[i-1]:
                    transitions.append({
                        "from_regime": self.classifier.regime_definitions[regimes[i-1]]['name'],
                        "to_regime": self.classifier.regime_definitions[regimes[i]]['name'],
                        "date": df.index[i + self.classifier.lookback_period].strftime('%Y-%m-%d')
                    })
            
            # Calculate transition matrix
            transition_matrix = {}
            for transition in transitions:
                from_regime = transition['from_regime']
                to_regime = transition['to_regime']
                
                if from_regime not in transition_matrix:
                    transition_matrix[from_regime] = {}
                
                if to_regime not in transition_matrix[from_regime]:
                    transition_matrix[from_regime][to_regime] = 0
                
                transition_matrix[from_regime][to_regime] += 1
            
            return {
                "total_transitions": len(transitions),
                "recent_transitions": transitions[-10:] if len(transitions) > 10 else transitions,
                "transition_matrix": transition_matrix
            }
            
        except Exception as e:
            logger.error(f"Error analyzing regime transitions: {str(e)}")
            return {"error": str(e)}
    
    def get_model_info(self) -> Dict:
        """Get information about the current model"""
        try:
            if not self.model_loaded:
                return {
                    "status": "not_trained",
                    "message": "Model not trained yet"
                }
            
            # Get cached training info
            cache_key = "model_training_results"
            training_info = get_cached_data(cache_key)
            
            model_info = {
                "status": "trained",
                "is_loaded": self.model_loaded,
                "last_training_time": self.last_training_time.isoformat() if self.last_training_time else None,
                "regime_definitions": self.classifier.get_regime_definitions(),
                "supported_tickers": self.supported_tickers
            }
            
            if training_info:
                model_info.update(training_info)
            
            return model_info
            
        except Exception as e:
            logger.error(f"Error getting model info: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def evaluate_model_performance(self, ticker: str = "RELIANCE.NS") -> Dict:
        """Evaluate model performance"""
        try:
            if not self.model_loaded:
                return {"status": "error", "message": "Model not trained"}
            
            # Check cache first
            cache_key = f"model_evaluation_{ticker}"
            cached_result = get_cached_data(cache_key)
            
            if cached_result:
                return cached_result
            
            # Evaluate model
            result = self.classifier.evaluate_model(ticker)
            
            if result["status"] == "success":
                # Cache for 6 hours
                set_cached_data(cache_key, result, 21600)
                
                logger.info(f"Model evaluation completed. Accuracy: {result['accuracy']:.4f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating model: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_multiple_regime_predictions(self, tickers: List[str]) -> Dict:
        """Get regime predictions for multiple tickers"""
        try:
            results = {}
            
            for ticker in tickers:
                if ticker in self.supported_tickers:
                    prediction = self.predict_regime(ticker)
                    results[ticker] = prediction
                else:
                    results[ticker] = {
                        "status": "error",
                        "message": f"Ticker {ticker} not supported"
                    }
            
            return {
                "status": "success",
                "predictions": results,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting multiple predictions: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def get_regime_recommendations(self, ticker: str) -> Dict:
        """Get trading recommendations based on regime"""
        try:
            # Get current regime prediction
            regime_prediction = self.predict_regime(ticker)
            
            if regime_prediction["status"] != "success":
                return regime_prediction
            
            regime_name = regime_prediction["regime_name"]
            confidence = regime_prediction["confidence"]
            
            # Generate recommendations based on regime
            recommendations = self._generate_regime_recommendations(regime_name, confidence)
            
            return {
                "status": "success",
                "ticker": ticker,
                "current_regime": regime_prediction,
                "recommendations": recommendations,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _generate_regime_recommendations(self, regime_name: str, confidence: float) -> Dict:
        """Generate trading recommendations based on regime"""
        base_recommendations = {
            "Bull Trending": {
                "strategy": "Long/Buy",
                "risk_level": "Low-Medium",
                "position_size": "Large" if confidence > 0.8 else "Medium",
                "stop_loss": "Below recent swing low",
                "take_profit": "Trail with moving average",
                "notes": "Strong upward momentum. Consider buying on dips."
            },
            "Bear Trending": {
                "strategy": "Short/Sell",
                "risk_level": "Low-Medium",
                "position_size": "Large" if confidence > 0.8 else "Medium",
                "stop_loss": "Above recent swing high",
                "take_profit": "Trail with moving average",
                "notes": "Strong downward momentum. Consider selling on rallies."
            },
            "Sideways/Ranging": {
                "strategy": "Range Trading",
                "risk_level": "Medium",
                "position_size": "Small-Medium",
                "stop_loss": "Beyond range boundaries",
                "take_profit": "At opposite range boundary",
                "notes": "Trade within range. Buy at support, sell at resistance."
            },
            "High Volatility": {
                "strategy": "Reduced Position/Wait",
                "risk_level": "High",
                "position_size": "Small" if confidence > 0.7 else "None",
                "stop_loss": "Tight stops required",
                "take_profit": "Quick profit taking",
                "notes": "High risk environment. Consider staying out or using tight stops."
            },
            "Accumulation/Distribution": {
                "strategy": "Gradual Accumulation",
                "risk_level": "Medium",
                "position_size": "Medium",
                "stop_loss": "Below accumulation zone",
                "take_profit": "Breakout direction",
                "notes": "Transitional phase. Watch for breakout direction."
            }
        }
        
        recommendation = base_recommendations.get(regime_name, {
            "strategy": "Wait and Watch",
            "risk_level": "Unknown",
            "position_size": "None",
            "stop_loss": "N/A",
            "take_profit": "N/A",
            "notes": "Unknown regime. Wait for clearer signals."
        })
        
        # Adjust based on confidence
        if confidence < 0.6:
            recommendation["notes"] += " LOW CONFIDENCE - Consider waiting for clearer signals."
            if recommendation["position_size"] == "Large":
                recommendation["position_size"] = "Medium"
            elif recommendation["position_size"] == "Medium":
                recommendation["position_size"] = "Small"
        
        recommendation["confidence_level"] = "High" if confidence > 0.8 else "Medium" if confidence > 0.6 else "Low"
        
        return recommendation

# Create global service instance
market_regime_service = MarketRegimeService()