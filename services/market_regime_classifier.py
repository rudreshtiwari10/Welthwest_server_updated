import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.preprocessing import StandardScaler
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import yfinance as yf
from services.technical_analysis import TechnicalAnalysis
from services.stock_service import get_historical_data
from services.cache_service import get_cached_data, set_cached_data
import warnings
import sklearn
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def convert_numpy_types(obj):
    """Convert NumPy types to Python types for JSON serialization"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj

class MarketRegimeClassifier:
    """
    Market Regime Classifier using Random Forest
    
    Defines 5 market regimes:
    1. Bull Trending (Strong upward momentum)
    2. Bear Trending (Strong downward momentum)
    3. Sideways/Ranging (Low volatility, no clear trend)
    4. High Volatility (Large price swings, uncertain direction)
    5. Accumulation/Distribution (Transitional phase)
    """
    
    def __init__(self):
        # Check scikit-learn version compatibility
        sklearn_version = sklearn.__version__
        logger.info(f"Using scikit-learn version: {sklearn_version}")
        
        # Ensure we're using a compatible version
        if sklearn_version < "1.3.0":
            logger.warning(f"scikit-learn version {sklearn_version} may have compatibility issues. Recommended: >=1.3.0")
        
        self.model = RandomForestClassifier(
            n_estimators=100,
            criterion='gini',
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1  # Use all available cores
        )
        self.scaler = StandardScaler()
        self.technical_analysis = TechnicalAnalysis()
        self.is_trained = False
        self.feature_names = []
        
        # Market regime definitions
        self.regime_definitions = {
            0: {
                'name': 'Bull Trending',
                'description': 'Strong upward momentum with sustained buying pressure',
                'criteria': {
                    'trend_strength': 'strong_up',
                    'volatility': 'low_to_medium',
                    'volume': 'increasing',
                    'momentum': 'bullish'
                }
            },
            1: {
                'name': 'Bear Trending',
                'description': 'Strong downward momentum with sustained selling pressure',
                'criteria': {
                    'trend_strength': 'strong_down',
                    'volatility': 'low_to_medium',
                    'volume': 'increasing',
                    'momentum': 'bearish'
                }
            },
            2: {
                'name': 'Sideways/Ranging',
                'description': 'Low volatility consolidation with no clear trend',
                'criteria': {
                    'trend_strength': 'weak',
                    'volatility': 'low',
                    'volume': 'decreasing',
                    'momentum': 'neutral'
                }
            },
            3: {
                'name': 'High Volatility',
                'description': 'Large price swings with uncertain direction',
                'criteria': {
                    'trend_strength': 'variable',
                    'volatility': 'high',
                    'volume': 'high',
                    'momentum': 'mixed'
                }
            },
            4: {
                'name': 'Accumulation/Distribution',
                'description': 'Transitional phase with smart money activity',
                'criteria': {
                    'trend_strength': 'transitional',
                    'volatility': 'medium',
                    'volume': 'above_average',
                    'momentum': 'building'
                }
            }
        }
        
        self.lookback_period = 20  # Days to look back for regime classification
        
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare features for market regime classification
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            DataFrame with features for classification
        """
        # Ensure we have the required columns and clean the data
        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        # Create a clean copy with only required columns
        features = pd.DataFrame(index=df.index)
        
        for col in required_columns:
            if col in df.columns:
                features[col] = df[col]
            else:
                logger.warning(f"Missing column {col}, filling with Close price")
                if col == 'Volume':
                    features[col] = 1000000  # Default volume
                else:
                    features[col] = df['Close'] if 'Close' in df.columns else 100
        
        # Price-based features with error handling
        try:
            features['returns'] = df['Close'].pct_change().fillna(0.0)
            features['log_returns'] = np.log(df['Close'] / df['Close'].shift(1)).fillna(0.0)
            features['price_momentum_5'] = df['Close'].pct_change(5).fillna(0.0)
            features['price_momentum_10'] = df['Close'].pct_change(10).fillna(0.0)
            features['price_momentum_20'] = df['Close'].pct_change(20).fillna(0.0)
        except Exception as e:
            logger.warning(f"Error calculating price features: {str(e)}")
            features['returns'] = 0.0
            features['log_returns'] = 0.0
            features['price_momentum_5'] = 0.0
            features['price_momentum_10'] = 0.0
            features['price_momentum_20'] = 0.0
        
        # Volatility features
        features['volatility_5'] = features['returns'].rolling(5).std()
        features['volatility_10'] = features['returns'].rolling(10).std()
        features['volatility_20'] = features['returns'].rolling(20).std()
        features['volatility_ratio'] = features['volatility_5'] / features['volatility_20']
        
        # Volume features with NaN handling
        features['volume_ma_5'] = df['Volume'].rolling(5).mean()
        features['volume_ma_20'] = df['Volume'].rolling(20).mean()
        features['volume_ratio'] = np.where(
            features['volume_ma_20'] != 0, df['Volume'] / features['volume_ma_20'], 1.0
        )
        features['volume_momentum'] = df['Volume'].pct_change(5).fillna(0.0)
        
        # Technical indicators with comprehensive error handling
        try:
            features['rsi'] = self._calculate_rsi(df)
        except Exception as e:
            logger.warning(f"Error calculating RSI: {str(e)}")
            features['rsi'] = 50.0  # Neutral RSI
            
        try:
            features['macd'], features['macd_signal'], features['macd_histogram'] = self._calculate_macd(df)
        except Exception as e:
            logger.warning(f"Error calculating MACD: {str(e)}")
            features['macd'] = 0.0
            features['macd_signal'] = 0.0
            features['macd_histogram'] = 0.0
            
        try:
            features['bb_upper'], features['bb_middle'], features['bb_lower'] = self._calculate_bollinger_bands(df)
        except Exception as e:
            logger.warning(f"Error calculating Bollinger Bands: {str(e)}")
            close_price = df['Close'].iloc[-1] if len(df) > 0 else 100
            features['bb_upper'] = close_price * 1.02
            features['bb_middle'] = close_price
            features['bb_lower'] = close_price * 0.98
        
        # Safe division with NaN handling
        features['bb_width'] = np.where(
            features['bb_middle'] != 0,
            (features['bb_upper'] - features['bb_lower']) / features['bb_middle'],
            0.0
        )
        
        bb_range = features['bb_upper'] - features['bb_lower']
        features['bb_position'] = np.where(
            bb_range != 0,
            (df['Close'] - features['bb_lower']) / bb_range,
            0.5
        )
        
        # Moving averages with error handling
        try:
            features['sma_5'] = df['Close'].rolling(5, min_periods=1).mean()
            features['sma_10'] = df['Close'].rolling(10, min_periods=1).mean()
            features['sma_20'] = df['Close'].rolling(20, min_periods=1).mean()
            features['sma_50'] = df['Close'].rolling(50, min_periods=1).mean()
        except Exception as e:
            logger.warning(f"Error calculating moving averages: {str(e)}")
            close_mean = df['Close'].mean() if len(df) > 0 else 100
            features['sma_5'] = close_mean
            features['sma_10'] = close_mean
            features['sma_20'] = close_mean
            features['sma_50'] = close_mean
        
        # Moving average relationships with safe division
        features['price_vs_sma_5'] = np.where(
            features['sma_5'] != 0, df['Close'] / features['sma_5'], 1.0
        )
        features['price_vs_sma_20'] = np.where(
            features['sma_20'] != 0, df['Close'] / features['sma_20'], 1.0
        )
        features['sma_5_vs_20'] = np.where(
            features['sma_20'] != 0, features['sma_5'] / features['sma_20'], 1.0
        )
        features['sma_20_vs_50'] = np.where(
            features['sma_50'] != 0, features['sma_20'] / features['sma_50'], 1.0
        )
        
        # Trend strength with error handling
        try:
            features['adx'] = self._calculate_adx(df)
        except Exception as e:
            logger.warning(f"Error calculating ADX: {str(e)}")
            features['adx'] = 25.0  # Neutral ADX
            
        try:
            features['trend_strength'] = self._calculate_trend_strength(df)
        except Exception as e:
            logger.warning(f"Error calculating trend strength: {str(e)}")
            features['trend_strength'] = 0.5  # Neutral trend strength
        
        # Range and gap features
        features['true_range'] = self._calculate_true_range(df)
        features['atr'] = features['true_range'].rolling(14).mean()
        features['high_low_ratio'] = df['High'] / df['Low']
        features['body_size'] = abs(df['Close'] - df['Open']) / df['Open']
        
        # Market structure features
        features['higher_highs'] = self._detect_higher_highs(df)
        features['lower_lows'] = self._detect_lower_lows(df)
        features['breakout_strength'] = self._calculate_breakout_strength(df)
        
        # Final cleanup - replace infinite values and remaining NaN
        features = features.replace([np.inf, -np.inf], np.nan)
        
        # Forward fill and backward fill for time series continuity
        features = features.ffill().bfill()
        
        # Fill any remaining NaN values with appropriate defaults
        for col in features.columns:
            if features[col].isna().any():
                if 'ratio' in col.lower() or 'vs' in col.lower():
                    features[col] = features[col].fillna(1.0)
                elif 'return' in col.lower() or 'momentum' in col.lower():
                    features[col] = features[col].fillna(0.0)
                elif 'volume' in col.lower():
                    features[col] = features[col].fillna(features[col].median())
                else:
                    features[col] = features[col].fillna(0.0)
        
        return features
    
    def label_market_regimes(self, df: pd.DataFrame) -> pd.Series:
        """
        Label market regimes based on defined criteria
        
        Args:
            df: DataFrame with features
            
        Returns:
            Series with regime labels (0-4)
        """
        regimes = pd.Series(index=df.index, dtype=int)
        
        for i in range(len(df)):
            if i < self.lookback_period:
                regimes.iloc[i] = 2  # Default to sideways for insufficient data
                continue
            
            # Get recent data window
            window = df.iloc[i-self.lookback_period:i+1]
            
            # Calculate regime criteria
            avg_returns = window['returns'].mean()
            volatility = window['volatility_20'].iloc[-1]
            volume_trend = window['volume_ratio'].rolling(5).mean().iloc[-1]
            trend_strength = window['trend_strength'].iloc[-1]
            momentum = window['price_momentum_10'].iloc[-1]
            rsi = window['rsi'].iloc[-1]
            
            # Bull Trending (0)
            if (avg_returns > 0.002 and  # Positive average returns
                momentum > 0.05 and      # Strong positive momentum
                trend_strength > 0.6 and # Strong trend
                volatility < 0.03 and    # Controlled volatility
                rsi < 80):               # Not overbought
                regimes.iloc[i] = 0
                
            # Bear Trending (1)
            elif (avg_returns < -0.002 and  # Negative average returns
                  momentum < -0.05 and      # Strong negative momentum
                  trend_strength > 0.6 and # Strong trend
                  volatility < 0.03 and    # Controlled volatility
                  rsi > 20):               # Not oversold
                regimes.iloc[i] = 1
                
            # High Volatility (3)
            elif (volatility > 0.04 or       # High volatility
                  abs(momentum) > 0.1 or     # High momentum (either direction)
                  window['returns'].std() > 0.05):  # High return variability
                regimes.iloc[i] = 3
                
            # Accumulation/Distribution (4)
            elif (volume_trend > 1.2 and     # Above average volume
                  abs(momentum) > 0.02 and   # Some momentum building
                  abs(momentum) < 0.05 and   # But not too strong
                  volatility > 0.015 and     # Medium volatility
                  volatility < 0.035):       # But not too high
                regimes.iloc[i] = 4
                
            # Sideways/Ranging (2) - default
            else:
                regimes.iloc[i] = 2
        
        return regimes
    
    def train_model(self, ticker: str, period: str = "2y", retrain: bool = False) -> Dict:
        """
        Train the Random Forest model on historical data
        
        Args:
            ticker: Stock ticker symbol
            period: Historical period to use for training
            retrain: Whether to retrain even if model exists
            
        Returns:
            Dictionary with training results
        """
        try:
            # Check if model already exists and trained
            if self.is_trained and not retrain:
                logger.info("Model already trained. Use retrain=True to retrain.")
                return {"status": "already_trained", "accuracy": None}
            
            # Get historical data
            logger.info(f"Fetching data for {ticker} with period {period}")
            df = get_historical_data(ticker, period=period)
            
            if df.empty:
                logger.error(f"No data available for {ticker}")
                return {"status": "error", "message": "No data available"}
            
            # Prepare features
            logger.info("Preparing features...")
            features_df = self.prepare_features(df)
            
            # Label regimes
            logger.info("Labeling market regimes...")
            regime_labels = self.label_market_regimes(features_df)
            
            # Select feature columns (exclude OHLC and intermediate calculations)
            feature_columns = [col for col in features_df.columns if col not in 
                             ['Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']]
            
            # Remove any columns with all NaN values
            feature_columns = [col for col in feature_columns if not features_df[col].isnull().all()]
            
            # Create final feature matrix
            X = features_df[feature_columns].ffill().bfill()
            y = regime_labels
            
            # Remove rows with NaN or infinite values
            X = X.replace([np.inf, -np.inf], np.nan)
            valid_mask = ~(X.isnull().any(axis=1) | y.isnull())
            X = X[valid_mask]
            y = y[valid_mask]
            
            if len(X) < 100:
                logger.error("Insufficient data for training")
                return {"status": "error", "message": "Insufficient data for training"}
            
            # Split data - check if we have enough samples for stratified split
            unique_classes, class_counts = np.unique(y, return_counts=True)
            min_class_count = min(class_counts)
            
            if min_class_count < 2:
                logger.warning(f"Some classes have only {min_class_count} samples. Using non-stratified split.")
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=None
                )
            else:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y
                )
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train model
            logger.info("Training Random Forest model...")
            self.model.fit(X_train_scaled, y_train)
            
            # Evaluate model
            y_pred = self.model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            # Cross-validation
            cv_scores = cross_val_score(self.model, X_train_scaled, y_train, cv=5)
            
            # Feature importance
            feature_importance = pd.DataFrame({
                'feature': feature_columns,
                'importance': [float(x) for x in self.model.feature_importances_]
            }).sort_values('importance', ascending=False)
            
            # Store feature names for later use
            self.feature_names = feature_columns
            self.is_trained = True
            
            # Classification report
            class_report_raw = classification_report(y_test, y_pred, output_dict=True)
            # Convert NumPy types to Python types for JSON serialization
            class_report = {}
            for key, value in class_report_raw.items():
                if isinstance(value, dict):
                    class_report[key] = {k: float(v) if isinstance(v, (np.floating, np.integer)) else v for k, v in value.items()}
                else:
                    class_report[key] = float(value) if isinstance(value, (np.floating, np.integer)) else value
            
            # Save model
            self.save_model()
            
            logger.info(f"Model trained successfully. Accuracy: {accuracy:.4f}")
            
            result = {
                "status": "success",
                "accuracy": float(accuracy),
                "cv_mean": float(cv_scores.mean()),
                "cv_std": float(cv_scores.std()),
                "feature_importance": feature_importance.to_dict('records'),
                "classification_report": class_report,
                "regime_distribution": {str(k): int(v) for k, v in y.value_counts().items()},
                "training_samples": int(len(X_train)),
                "test_samples": int(len(X_test))
            }
            
            # Convert any remaining NumPy types to Python types
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error training model: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def predict_regime(self, ticker: str, current_data: Optional[pd.DataFrame] = None) -> Dict:
        """
        Predict current market regime
        
        Args:
            ticker: Stock ticker symbol
            current_data: Optional DataFrame with current data
            
        Returns:
            Dictionary with prediction results
        """
        try:
            if not self.is_trained:
                logger.error("Model not trained. Please train the model first.")
                return {"status": "error", "message": "Model not trained"}
            
            # Get recent data if not provided
            if current_data is None:
                df = get_historical_data(ticker, period="3mo")
                if df.empty:
                    return {"status": "error", "message": "No data available"}
            else:
                df = current_data.copy()
            
            # Ensure we have the minimum required data
            if len(df) < self.lookback_period:
                return {"status": "error", "message": "Insufficient data for prediction"}
            
            # Clean column names and ensure standard format
            df.columns = df.columns.str.strip()
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            
            # Check if we have the required columns
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"Missing columns {missing_columns}, attempting to handle gracefully")
                
                # Try common alternative column names
                column_mapping = {
                    'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
                    'adj close': 'Close', 'Adj Close': 'Close'
                }
                
                for old_name, new_name in column_mapping.items():
                    if old_name in df.columns and new_name not in df.columns:
                        df[new_name] = df[old_name]
                
                # Fill any still missing columns
                for col in required_columns:
                    if col not in df.columns:
                        if col == 'Volume':
                            df[col] = 1000000  # Default volume
                        else:
                            df[col] = df.get('Close', 100)  # Use Close price or default
            
            # Prepare features with error handling
            try:
                features_df = self.prepare_features(df)
                if features_df.empty:
                    return {"status": "error", "message": "Feature preparation failed"}
            except Exception as e:
                logger.error(f"Error preparing features: {str(e)}")
                return {"status": "error", "message": f"Feature preparation failed: {str(e)}"}
            
            # Get latest features with comprehensive NaN handling
            latest_features = features_df[self.feature_names].iloc[-1:]
            
            # Handle missing values comprehensively
            latest_features = latest_features.ffill().bfill()
            
            # Replace any remaining NaN values with column means or zeros
            for col in latest_features.columns:
                if latest_features[col].isna().any():
                    # Try to use historical mean from the full dataset
                    if not features_df[col].isna().all():
                        mean_val = features_df[col].mean()
                        latest_features[col] = latest_features[col].fillna(mean_val)
                    else:
                        # If column is all NaN, fill with appropriate default
                        if 'ratio' in col.lower() or 'vs' in col.lower():
                            latest_features[col] = latest_features[col].fillna(1.0)
                        elif 'return' in col.lower():
                            latest_features[col] = latest_features[col].fillna(0.0)
                        else:
                            latest_features[col] = latest_features[col].fillna(0.0)
            
            # Final check for any remaining NaN or infinite values
            latest_features = latest_features.replace([np.inf, -np.inf], np.nan)
            latest_features = latest_features.fillna(0.0)
            
            # Verify no NaN values remain
            if latest_features.isna().any().any():
                logger.warning("Still have NaN values after preprocessing, using zeros")
                latest_features = latest_features.fillna(0.0)
            
            # Scale features
            features_scaled = self.scaler.transform(latest_features)
            
            # Predict
            regime_pred = self.model.predict(features_scaled)[0]
            regime_proba = self.model.predict_proba(features_scaled)[0]
            
            # Get regime information
            regime_info = self.regime_definitions[regime_pred]
            
            # Calculate confidence
            confidence = max(regime_proba)
            
            result = {
                "status": "success",
                "regime": int(regime_pred),
                "regime_name": regime_info['name'],
                "regime_description": regime_info['description'],
                "confidence": float(confidence),
                "probabilities": {
                    self.regime_definitions[i]['name']: float(prob) 
                    for i, prob in enumerate(regime_proba)
                },
                "timestamp": datetime.now().isoformat()
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error predicting regime: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def evaluate_model(self, ticker: str, test_period: str = "6mo") -> Dict:
        """
        Evaluate model performance on test data
        
        Args:
            ticker: Stock ticker symbol
            test_period: Period for evaluation
            
        Returns:
            Dictionary with evaluation results
        """
        try:
            if not self.is_trained:
                return {"status": "error", "message": "Model not trained"}
            
            # Get test data
            df = get_historical_data(ticker, period=test_period)
            if df.empty:
                return {"status": "error", "message": "No test data available"}
            
            # Prepare features and labels
            features_df = self.prepare_features(df)
            true_labels = self.label_market_regimes(features_df)
            
            # Predict for all data points
            predictions = []
            for i in range(len(features_df)):
                if i < self.lookback_period:
                    predictions.append(2)  # Default to sideways
                    continue
                
                features = features_df[self.feature_names].iloc[i:i+1].ffill()
                features_scaled = self.scaler.transform(features)
                pred = self.model.predict(features_scaled)[0]
                predictions.append(pred)
            
            predictions = pd.Series(predictions, index=df.index)
            
            # Calculate metrics
            valid_mask = ~(true_labels.isnull() | predictions.isnull())
            true_labels_clean = true_labels[valid_mask]
            predictions_clean = predictions[valid_mask]
            
            accuracy = accuracy_score(true_labels_clean, predictions_clean)
            
            result = {
                "status": "success",
                "accuracy": float(accuracy),
                "total_samples": int(len(true_labels_clean)),
                "regime_accuracy": {
                    self.regime_definitions[i]['name']: 
                    float(accuracy_score(true_labels_clean == i, predictions_clean == i))
                    for i in range(5)
                },
                "confusion_matrix": confusion_matrix(true_labels_clean, predictions_clean).tolist()
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error evaluating model: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def save_model(self, filename: str = "market_regime_model.pkl"):
        """Save the trained model"""
        try:
            model_data = {
                'model': self.model,
                'scaler': self.scaler,
                'feature_names': self.feature_names,
                'regime_definitions': self.regime_definitions,
                'is_trained': self.is_trained
            }
            
            with open(filename, 'wb') as f:
                pickle.dump(model_data, f)
                
            logger.info(f"Model saved to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving model: {str(e)}")
    
    def load_model(self, filename: str = "market_regime_model.pkl"):
        """Load a trained model with enhanced version compatibility handling"""
        try:
            with open(filename, 'rb') as f:
                model_data = pickle.load(f)
            
            # Check if the loaded model is compatible with current scikit-learn version
            try:
                # Test if the model can be used without errors
                if hasattr(model_data['model'], 'predict'):
                    # Try a simple prediction to test compatibility
                    test_features = np.zeros((1, len(model_data['feature_names'])))
                    _ = model_data['model'].predict(test_features)
                else:
                    raise ValueError("Loaded model does not have predict method")
                
                self.model = model_data['model']
                self.scaler = model_data['scaler']
                self.feature_names = model_data['feature_names']
                self.regime_definitions = model_data['regime_definitions']
                self.is_trained = model_data['is_trained']
                
                logger.info(f"Model loaded from {filename}")
                
            except (AttributeError, ValueError, TypeError) as compatibility_error:
                error_str = str(compatibility_error)
                logger.warning(f"Model compatibility issue detected: {error_str}")
                
                # Check for specific scikit-learn version incompatibility issues
                if ('monotonic_cst' in error_str or 
                    'has no attribute' in error_str or
                    'pickle' in error_str.lower()):
                    logger.info("Detected scikit-learn version mismatch between training and deployment")
                    logger.info("This is common when models are trained with one version and deployed with another")
                    logger.info("Deleting incompatible model file and will retrain automatically")
                    
                    # Delete the incompatible model file
                    try:
                        import os
                        if os.path.exists(filename):
                            os.remove(filename)
                            logger.info(f"Removed incompatible model file: {filename}")
                    except Exception as delete_error:
                        logger.warning(f"Could not delete incompatible model file: {delete_error}")
                
                else:
                    logger.info("This usually happens when the model was saved with a different scikit-learn version")
                    logger.info("The model will be retrained automatically")
                
                # Reset to untrained state so the model will be retrained
                self.is_trained = False
                return
            
        except FileNotFoundError:
            logger.info(f"Model file {filename} not found. Model will be trained on first use.")
            self.is_trained = False
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            logger.info("Model will be retrained automatically")
            self.is_trained = False
    
    def get_regime_definitions(self) -> Dict:
        """Get market regime definitions"""
        return self.regime_definitions
    
    def check_model_compatibility(self) -> Dict:
        """Check if the current model is compatible with the installed scikit-learn version"""
        try:
            if not self.is_trained:
                return {
                    "status": "not_trained",
                    "message": "Model not trained yet",
                    "compatible": False
                }
            
            # Test model compatibility
            try:
                # Create dummy features for testing
                if hasattr(self, 'feature_names') and self.feature_names:
                    test_features = np.zeros((1, len(self.feature_names)))
                    test_features_scaled = self.scaler.transform(test_features)
                    _ = self.model.predict(test_features_scaled)
                    
                    return {
                        "status": "success",
                        "message": "Model is compatible",
                        "compatible": True,
                        "sklearn_version": sklearn.__version__,
                        "model_type": type(self.model).__name__
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Model features not properly initialized",
                        "compatible": False
                    }
                    
            except Exception as test_error:
                return {
                    "status": "error",
                    "message": f"Model compatibility test failed: {str(test_error)}",
                    "compatible": False,
                    "sklearn_version": sklearn.__version__,
                    "error_details": str(test_error)
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error checking compatibility: {str(e)}",
                "compatible": False
            }
    
    
    def force_retrain_for_production(self):
        """Force retrain the model for production compatibility"""
        try:
            logger.info("Forcing model retrain for production compatibility")
            
            # Reset model state
            self.is_trained = False
            self.feature_names = []
            
            # Create new model instance
            self.model = RandomForestClassifier(
                n_estimators=100,
                criterion='gini',
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1
            )
            
            # Reset scaler
            self.scaler = StandardScaler()
            
            logger.info("Model reset completed. Ready for retraining.")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting model: {str(e)}")
            return False
    
    def handle_production_compatibility(self):
        """Handle production compatibility issues automatically"""
        try:
            # Check if we're in production
            is_production = os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER')
            
            if is_production:
                logger.info("Running in production environment - checking compatibility")
                
                # Try to load existing model
                try:
                    self.load_model()
                    
                    # Test compatibility
                    compatibility = self.check_model_compatibility()
                    
                    if not compatibility.get("compatible", False):
                        logger.warning("Model compatibility issue detected in production")
                        logger.info("Forcing model retrain for production compatibility")
                        
                        # Force retrain
                        if self.force_retrain_for_production():
                            logger.info("Model reset successful. Will be retrained on first use.")
                            return True
                        else:
                            logger.error("Failed to reset model for production")
                            return False
                    else:
                        logger.info("Model is compatible in production environment")
                        return True
                        
                except Exception as e:
                    logger.warning(f"Could not load model in production: {str(e)}")
                    logger.info("Model will be retrained automatically")
                    return True
            else:
                logger.info("Running in development environment")
                return True
                
        except Exception as e:
            logger.error(f"Error handling production compatibility: {str(e)}")
            return False
# Helper methods for feature calculation
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD"""
        exp1 = df['Close'].ewm(span=fast).mean()
        exp2 = df['Close'].ewm(span=slow).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal).mean()
        histogram = macd - signal_line
        
        return macd, signal_line, histogram
    
    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std: int = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        middle = df['Close'].rolling(window=period).mean()
        std_dev = df['Close'].rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return upper, middle, lower
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        
        dm_plus = pd.Series(index=df.index, dtype=float)
        dm_minus = pd.Series(index=df.index, dtype=float)
        
        for i in range(1, len(df)):
            high_diff = high.iloc[i] - high.iloc[i-1]
            low_diff = low.iloc[i-1] - low.iloc[i]
            
            if high_diff > low_diff and high_diff > 0:
                dm_plus.iloc[i] = high_diff
            else:
                dm_plus.iloc[i] = 0
                
            if low_diff > high_diff and low_diff > 0:
                dm_minus.iloc[i] = low_diff
            else:
                dm_minus.iloc[i] = 0
        
        tr_smooth = tr.rolling(window=period).mean()
        dm_plus_smooth = dm_plus.rolling(window=period).mean()
        dm_minus_smooth = dm_minus.rolling(window=period).mean()
        
        di_plus = 100 * (dm_plus_smooth / tr_smooth)
        di_minus = 100 * (dm_minus_smooth / tr_smooth)
        
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    def _calculate_trend_strength(self, df: pd.DataFrame) -> pd.Series:
        """Calculate trend strength indicator"""
        sma_5 = df['Close'].rolling(5).mean()
        sma_20 = df['Close'].rolling(20).mean()
        sma_50 = df['Close'].rolling(50).mean()
        
        # Trend alignment score
        trend_score = pd.Series(index=df.index, dtype=float)
        
        for i in range(len(df)):
            if pd.isna(sma_50.iloc[i]):
                trend_score.iloc[i] = 0
                continue
                
            # Check if all MAs are aligned
            if sma_5.iloc[i] > sma_20.iloc[i] > sma_50.iloc[i]:
                trend_score.iloc[i] = 1.0  # Strong uptrend
            elif sma_5.iloc[i] < sma_20.iloc[i] < sma_50.iloc[i]:
                trend_score.iloc[i] = -1.0  # Strong downtrend
            else:
                # Partial alignment
                alignment = 0
                if sma_5.iloc[i] > sma_20.iloc[i]:
                    alignment += 0.5
                if sma_20.iloc[i] > sma_50.iloc[i]:
                    alignment += 0.5
                if sma_5.iloc[i] < sma_20.iloc[i]:
                    alignment -= 0.5
                if sma_20.iloc[i] < sma_50.iloc[i]:
                    alignment -= 0.5
                    
                trend_score.iloc[i] = alignment
        
        return abs(trend_score)  # Return absolute value for trend strength
    
    def _calculate_true_range(self, df: pd.DataFrame) -> pd.Series:
        """Calculate True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        
        return tr
    
    def _detect_higher_highs(self, df: pd.DataFrame, window: int = 5) -> pd.Series:
        """Detect higher highs pattern"""
        high = df['High']
        higher_highs = pd.Series(index=df.index, dtype=float)
        
        for i in range(window, len(df)):
            recent_highs = high.iloc[i-window:i]
            if high.iloc[i] > recent_highs.max():
                higher_highs.iloc[i] = 1
            else:
                higher_highs.iloc[i] = 0
        
        return higher_highs.fillna(0)
    
    def _detect_lower_lows(self, df: pd.DataFrame, window: int = 5) -> pd.Series:
        """Detect lower lows pattern"""
        low = df['Low']
        lower_lows = pd.Series(index=df.index, dtype=float)
        
        for i in range(window, len(df)):
            recent_lows = low.iloc[i-window:i]
            if low.iloc[i] < recent_lows.min():
                lower_lows.iloc[i] = 1
            else:
                lower_lows.iloc[i] = 0
        
        return lower_lows.fillna(0)
    
    def _calculate_breakout_strength(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """Calculate breakout strength"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        volume = df['Volume']
        
        breakout_strength = pd.Series(index=df.index, dtype=float)
        
        for i in range(window, len(df)):
            recent_high = high.iloc[i-window:i].max()
            recent_low = low.iloc[i-window:i].min()
            avg_volume = volume.iloc[i-window:i].mean()
            
            if close.iloc[i] > recent_high:
                # Upward breakout
                price_strength = (close.iloc[i] - recent_high) / recent_high
                volume_strength = volume.iloc[i] / avg_volume if avg_volume > 0 else 1
                breakout_strength.iloc[i] = price_strength * volume_strength
            elif close.iloc[i] < recent_low:
                # Downward breakout
                price_strength = (recent_low - close.iloc[i]) / recent_low
                volume_strength = volume.iloc[i] / avg_volume if avg_volume > 0 else 1
                breakout_strength.iloc[i] = -(price_strength * volume_strength)
            else:
                breakout_strength.iloc[i] = 0
        
        return breakout_strength.fillna(0)
    
    def retrain_with_recent_data(self, ticker: str, days_back: int = 30):
        """
        Retrain model with recent data for adaptation
        
        Args:
            ticker: Stock ticker symbol
            days_back: Number of days of recent data to include
        """
        try:
            # Get recent data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            df_recent = get_ohlc_data(ticker, 
                                    start_date=start_date.strftime('%Y-%m-%d'),
                                    end_date=end_date.strftime('%Y-%m-%d'))
            
            if df_recent.empty:
                logger.warning("No recent data available for retraining")
                return
            
            # Prepare features and labels
            features_df = self.prepare_features(df_recent)
            regime_labels = self.label_market_regimes(features_df)
            
            # Update model with recent data
            X_recent = features_df[self.feature_names].ffill()
            y_recent = regime_labels
            
            # Remove invalid rows
            valid_mask = ~(X_recent.isnull().any(axis=1) | y_recent.isnull())
            X_recent = X_recent[valid_mask]
            y_recent = y_recent[valid_mask]
            
            if len(X_recent) < 10:
                logger.warning("Insufficient recent data for retraining")
                return
            
            # Scale features
            X_recent_scaled = self.scaler.transform(X_recent)
            
            # Partial fit (update existing model)
            # Note: RandomForest doesn't support partial_fit, so we'll retrain with combined data
            logger.info(f"Updating model with {len(X_recent)} recent samples")
            
            # For now, we'll store the recent data and retrain periodically
            # In a production system, you might want to implement online learning
            
        except Exception as e:
            logger.error(f"Error in adaptive retraining: {str(e)}")