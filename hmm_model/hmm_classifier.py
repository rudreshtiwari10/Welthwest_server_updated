import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from hmmlearn import hmm
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import yfinance as yf
from services.stock_service import get_historical_data
import warnings
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

class HMMMarketRegimeClassifier:
    """
    Hidden Markov Model for Market Regime Classification
    
    Uses HMM to identify market regimes based on:
    - Log returns
    - Volatility patterns
    - Volume characteristics
    """
    
    def __init__(self, n_components: int = 3, covariance_type: str = "full", 
                 n_iter: int = 100, random_state: int = 42):
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state
        
        # Initialize HMM model
        self.hmm_model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        
        # Regime definitions for HMM states
        self.regime_definitions = {
            0: {
                'name': 'Low Volatility Regime',
                'description': 'Stable market conditions with low volatility and predictable returns',
                'characteristics': 'Small price movements, consistent trends'
            },
            1: {
                'name': 'Medium Volatility Regime', 
                'description': 'Normal market conditions with moderate volatility',
                'characteristics': 'Regular price movements, typical market behavior'
            },
            2: {
                'name': 'High Volatility Regime',
                'description': 'Turbulent market conditions with high volatility and large price swings',
                'characteristics': 'Large price movements, unpredictable behavior, crisis periods'
            }
        }
        
        # Initialize the model
        self._initialize_hmm()
    
    def _initialize_hmm(self):
        """Initialize the Hidden Markov Model"""
        try:
            self.hmm_model = hmm.GaussianHMM(
                n_components=self.n_components,
                covariance_type=self.covariance_type,
                n_iter=self.n_iter,
                random_state=self.random_state,
                verbose=False
            )
            logger.info(f"HMM model initialized with {self.n_components} components")
        except Exception as e:
            logger.error(f"Error initializing HMM: {str(e)}")
            raise
    
    def prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Prepare features for HMM training/prediction
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            numpy array with features for HMM
        """
        try:
            # Calculate log returns
            log_returns = np.log(df['Close'] / df['Close'].shift(1)).dropna()
            
            # Calculate rolling volatility (using 5-day window)
            volatility = log_returns.rolling(window=5).std().dropna()
            
            # Calculate volume features if available
            if 'Volume' in df.columns:
                volume_returns = np.log(df['Volume'] / df['Volume'].shift(1)).dropna()
                # Align all series to same length
                min_len = min(len(log_returns), len(volatility), len(volume_returns))
                features = np.column_stack([
                    log_returns.iloc[-min_len:].values,
                    volatility.iloc[-min_len:].values,
                    volume_returns.iloc[-min_len:].values
                ])
            else:
                # Use only price-based features
                min_len = min(len(log_returns), len(volatility))
                features = np.column_stack([
                    log_returns.iloc[-min_len:].values,
                    volatility.iloc[-min_len:].values
                ])
            
            # Remove any NaN or infinite values
            features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
            
            return features
            
        except Exception as e:
            logger.error(f"Error preparing HMM features: {str(e)}")
            raise
    
    def train_model(self, ticker: str, period: str = "2y", retrain: bool = False) -> Dict:
        """
        Train the HMM model on historical data
        
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
                logger.info("HMM model already trained. Use retrain=True to retrain.")
                return {"status": "already_trained", "model_score": None}
            
            # Get historical data
            logger.info(f"Fetching data for {ticker} with period {period}")
            df = get_historical_data(ticker, period=period)
            
            if df.empty:
                logger.error(f"No data available for {ticker}")
                return {"status": "error", "message": "No data available"}
            
            # Prepare features
            logger.info("Preparing HMM features...")
            features = self.prepare_features(df)
            
            if len(features) < 50:  # Minimum data requirement
                logger.error("Insufficient data for HMM training")
                return {"status": "error", "message": "Insufficient data for HMM training"}
            
            # Scale features
            features_scaled = self.scaler.fit_transform(features)
            
            # Train HMM
            logger.info("Training HMM model...")
            self.hmm_model.fit(features_scaled)
            self.is_trained = True
            
            # Calculate model score
            model_score = self.hmm_model.score(features_scaled)
            
            # Get model parameters
            transition_matrix = self.hmm_model.transmat_
            means = self.hmm_model.means_
            covariances = self.hmm_model.covars_
            
            # Decode states for analysis
            log_prob, state_sequence = self.hmm_model.decode(features_scaled, algorithm="viterbi")
            
            # Calculate state statistics
            state_counts = np.bincount(state_sequence, minlength=self.n_components)
            state_percentages = state_counts / len(state_sequence) * 100
            
            # Save model
            self.save_model()
            
            logger.info(f"HMM model trained successfully. Model score: {model_score:.4f}")
            
            result = {
                "status": "success",
                "model_score": float(model_score),
                "log_likelihood": float(log_prob),
                "transition_matrix": transition_matrix.tolist(),
                "means": means.tolist(),
                "covariances": covariances.tolist() if covariances.ndim > 1 else [covariances.tolist()],
                "state_distribution": {
                    f"state_{i}": {
                        "count": int(state_counts[i]),
                        "percentage": float(state_percentages[i])
                    }
                    for i in range(self.n_components)
                },
                "training_samples": int(len(features_scaled)),
                "n_components": self.n_components
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error training HMM model: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def predict_regime(self, ticker: str, current_data: Optional[pd.DataFrame] = None) -> Dict:
        """
        Predict current market regime using HMM
        
        Args:
            ticker: Stock ticker symbol
            current_data: Optional DataFrame with current data
            
        Returns:
            Dictionary with prediction results
        """
        try:
            if not self.is_trained:
                logger.error("HMM model not trained. Please train the model first.")
                return {"status": "error", "message": "Model not trained"}
            
            # Get recent data if not provided
            if current_data is None:
                df = get_historical_data(ticker, period="3mo")
                if df.empty:
                    return {"status": "error", "message": "No data available"}
            else:
                df = current_data.copy()
            
            # Prepare features
            features = self.prepare_features(df)
            
            if len(features) == 0:
                return {"status": "error", "message": "Insufficient data for prediction"}
            
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Decode states using Viterbi algorithm
            log_prob, state_sequence = self.hmm_model.decode(features_scaled, algorithm="viterbi")
            
            # Get posterior probabilities
            posterior_probs = self.hmm_model.predict_proba(features_scaled)
            
            # Current regime (most recent state)
            current_regime = int(state_sequence[-1])
            current_probabilities = posterior_probs[-1]
            
            # Calculate confidence as the maximum probability
            confidence = float(max(current_probabilities))
            
            # Forecast next state probabilities
            next_state_probs = self._forecast_next_state(state_sequence)
            
            # Get regime information
            regime_info = self.regime_definitions[current_regime]
            
            result = {
                "status": "success",
                "regime": current_regime,
                "regime_name": regime_info['name'],
                "regime_description": regime_info['description'],
                "confidence": confidence,
                "current_probabilities": {
                    f"state_{i}": float(prob) for i, prob in enumerate(current_probabilities)
                },
                "next_state_probabilities": {
                    f"state_{i}": float(prob) for i, prob in enumerate(next_state_probs)
                },
                "state_sequence": state_sequence[-10:].tolist(),  # Last 10 states
                "model_score": float(log_prob),
                "timestamp": datetime.now().isoformat()
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error predicting HMM regime: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _forecast_next_state(self, state_sequence: np.ndarray) -> np.ndarray:
        """
        Forecast next state probabilities based on current state
        
        Args:
            state_sequence: Array of decoded states
            
        Returns:
            Array of next state probabilities
        """
        try:
            if len(state_sequence) == 0:
                return np.ones(self.n_components) / self.n_components
            
            # Get current state
            current_state = state_sequence[-1]
            
            # Get transition probabilities from current state
            next_probs = self.hmm_model.transmat_[current_state]
            
            return next_probs
            
        except Exception as e:
            logger.error(f"Error forecasting next state: {str(e)}")
            return np.ones(self.n_components) / self.n_components
    
    def analyze_regime_persistence(self, ticker: str, period: str = "6mo") -> Dict:
        """
        Analyze regime persistence and transition patterns
        
        Args:
            ticker: Stock ticker symbol
            period: Analysis period
            
        Returns:
            Dictionary with regime analysis results
        """
        try:
            if not self.is_trained:
                return {"status": "error", "message": "Model not trained"}
            
            # Get data
            df = get_historical_data(ticker, period=period)
            if df.empty:
                return {"status": "error", "message": "No data available"}
            
            # Prepare features and decode states
            features = self.prepare_features(df)
            features_scaled = self.scaler.transform(features)
            log_prob, state_sequence = self.hmm_model.decode(features_scaled, algorithm="viterbi")
            
            # Calculate regime persistence (average duration in each state)
            persistence = {}
            for state in range(self.n_components):
                state_periods = []
                current_period = 0
                
                for s in state_sequence:
                    if s == state:
                        current_period += 1
                    else:
                        if current_period > 0:
                            state_periods.append(current_period)
                        current_period = 0
                
                if current_period > 0:
                    state_periods.append(current_period)
                
                persistence[f"state_{state}"] = {
                    "average_duration": float(np.mean(state_periods)) if state_periods else 0.0,
                    "max_duration": int(np.max(state_periods)) if state_periods else 0,
                    "num_periods": len(state_periods)
                }
            
            # Calculate transition frequencies
            transition_counts = np.zeros((self.n_components, self.n_components))
            for i in range(len(state_sequence) - 1):
                transition_counts[state_sequence[i], state_sequence[i + 1]] += 1
            
            # Convert to percentages
            transition_percentages = np.zeros_like(transition_counts)
            for i in range(self.n_components):
                row_sum = transition_counts[i].sum()
                if row_sum > 0:
                    transition_percentages[i] = transition_counts[i] / row_sum * 100
            
            result = {
                "status": "success",
                "regime_persistence": persistence,
                "transition_matrix": self.hmm_model.transmat_.tolist(),
                "observed_transitions": transition_percentages.tolist(),
                "state_distribution": {
                    f"state_{i}": int(np.sum(state_sequence == i))
                    for i in range(self.n_components)
                },
                "analysis_period": period,
                "total_periods": int(len(state_sequence))
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error analyzing regime persistence: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def save_model(self, filename: str = "hmm_model.pkl"):
        """Save the trained HMM model"""
        try:
            model_data = {
                'hmm_model': self.hmm_model,
                'scaler': self.scaler,
                'is_trained': self.is_trained,
                'n_components': self.n_components,
                'covariance_type': self.covariance_type,
                'regime_definitions': self.regime_definitions
            }
            
            filepath = f"hmm_model/{filename}"
            with open(filepath, 'wb') as f:
                pickle.dump(model_data, f)
                
            logger.info(f"HMM model saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Error saving HMM model: {str(e)}")
    
    def load_model(self, filename: str = "hmm_model.pkl"):
        """Load a trained HMM model"""
        try:
            filepath = f"hmm_model/{filename}"
            with open(filepath, 'rb') as f:
                model_data = pickle.load(f)
            
            self.hmm_model = model_data['hmm_model']
            self.scaler = model_data['scaler']
            self.is_trained = model_data['is_trained']
            self.n_components = model_data['n_components']
            self.covariance_type = model_data['covariance_type']
            self.regime_definitions = model_data['regime_definitions']
            
            logger.info(f"HMM model loaded from {filepath}")
            
        except Exception as e:
            logger.error(f"Error loading HMM model: {str(e)}")
            self.is_trained = False
    
    def get_model_info(self) -> Dict:
        """Get information about the HMM model"""
        try:
            if not self.is_trained:
                return {"status": "error", "message": "Model not trained"}
            
            result = {
                "status": "success",
                "model_type": "Hidden Markov Model",
                "n_components": self.n_components,
                "covariance_type": self.covariance_type,
                "is_trained": self.is_trained,
                "regime_definitions": self.regime_definitions,
                "transition_matrix": self.hmm_model.transmat_.tolist(),
                "means": self.hmm_model.means_.tolist(),
                "covariances": self.hmm_model.covars_.tolist() if hasattr(self.hmm_model, 'covars_') else []
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error getting HMM model info: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def evaluate_model(self, ticker: str, test_period: str = "6mo") -> Dict:
        """
        Evaluate HMM model performance
        
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
            
            # Prepare features
            features = self.prepare_features(df)
            features_scaled = self.scaler.transform(features)
            
            # Calculate model likelihood
            model_score = self.hmm_model.score(features_scaled)
            
            # Decode states
            log_prob, state_sequence = self.hmm_model.decode(features_scaled, algorithm="viterbi")
            
            # Calculate state stability (how often states change)
            state_changes = np.sum(np.diff(state_sequence) != 0)
            stability_ratio = 1.0 - (state_changes / len(state_sequence))
            
            # Calculate state distribution
            state_counts = np.bincount(state_sequence, minlength=self.n_components)
            state_percentages = state_counts / len(state_sequence) * 100
            
            result = {
                "status": "success",
                "model_score": float(model_score),
                "log_likelihood": float(log_prob),
                "stability_ratio": float(stability_ratio),
                "state_changes": int(state_changes),
                "total_periods": int(len(state_sequence)),
                "state_distribution": {
                    f"state_{i}": {
                        "count": int(state_counts[i]),
                        "percentage": float(state_percentages[i])
                    }
                    for i in range(self.n_components)
                },
                "evaluation_period": test_period
            }
            
            return convert_numpy_types(result)
            
        except Exception as e:
            logger.error(f"Error evaluating HMM model: {str(e)}")
            return {"status": "error", "message": str(e)}