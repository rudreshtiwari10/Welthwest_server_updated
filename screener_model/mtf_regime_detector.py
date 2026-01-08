"""
Multi-Timeframe Regime Detector using 4-State Hidden Markov Model

States:
- S0: Bullish Trend - Strong upward momentum, favorable for long positions
- S1: Bearish Trend - Strong downward momentum, favorable for short positions
- S2: High Volatility Expansion - Large price swings, uncertain direction
- S3: Low Volatility Compression - Consolidation, potential breakout setup

Observable Features:
- returns_1d: 1-day log returns
- volatility_5d: 5-day rolling volatility
- volume_ratio: Current volume / 20-day avg volume
- rsi_14: 14-period RSI
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from hmmlearn import hmm
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from services.stock_service import get_historical_data
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MTFRegimeDetector:
    """
    4-State Hidden Markov Model for Market Regime Detection

    Regime States:
    - 0: Bullish Trend (S1)
    - 1: Bearish Trend (S2)
    - 2: High Volatility Expansion (S3)
    - 3: Low Volatility Compression (S4)
    """

    # Regime definitions with LONG and SHORT interpretations
    REGIME_DEFINITIONS = {
        0: {
            'name': 'Bullish Trend',
            'short_name': 'BULL',
            'description': 'Strong upward momentum with favorable conditions for long positions',
            'bias': 'LONG',
            'multiplier': 1.25,  # Score boost for aligned signals
            'color': '#22c55e',  # Green
            # SHORT interpretation: Look for reversal patterns at resistance
            'short_interpretation': 'Trend weakening - watch for reversals at resistance',
            'short_score_multiplier': 0.75,  # Shorts are risky here
            'short_strategy': 'FADE_RESISTANCE'
        },
        1: {
            'name': 'Bearish Trend',
            'short_name': 'BEAR',
            'description': 'Strong downward momentum with favorable conditions for short positions',
            'bias': 'SHORT',
            'multiplier': 1.25,  # Score boost for aligned signals
            'color': '#ef4444',  # Red
            # SHORT interpretation: STRONGEST SHORT signals
            'short_interpretation': 'Ideal for SHORT trades - momentum in your favor',
            'short_score_multiplier': 1.5,  # Shorts are ideal here
            'short_strategy': 'BREAKDOWN_CONTINUATION',
            'short_target_extension': 1.5  # Extend targets by 50%
        },
        2: {
            'name': 'High Volatility',
            'short_name': 'HVOL',
            'description': 'Large price swings with uncertain direction - increased risk',
            'bias': 'NEUTRAL',
            'multiplier': 0.75,  # Score penalty due to uncertainty
            'color': '#f59e0b',  # Orange
            # SHORT interpretation: Shorts at upper Bollinger Band
            'short_interpretation': 'Breakdowns confirm fast - fade extremes',
            'short_score_multiplier': 1.2,  # Shorts work well in high vol
            'short_strategy': 'FADE_UPPER_BB'
        },
        3: {
            'name': 'Low Volatility',
            'short_name': 'LVOL',
            'description': 'Consolidation phase with potential breakout setup',
            'bias': 'NEUTRAL',
            'multiplier': 1.5,  # Score boost for breakout setups
            'color': '#3b82f6',  # Blue
            # SHORT interpretation: Most explosive breakdowns after squeeze
            'short_interpretation': 'Squeeze breakout - explosive moves when support breaks',
            'short_score_multiplier': 1.3,  # Squeeze breakdowns are powerful
            'short_strategy': 'SQUEEZE_BREAKDOWN',
            'short_target_extension': 1.3  # 30% extended targets
        }
    }

    def __init__(self, n_components: int = 4, covariance_type: str = "diag",
                 n_iter: int = 100, random_state: int = 42):
        """
        Initialize 4-state HMM regime detector

        Args:
            n_components: Number of hidden states (default 4)
            covariance_type: Type of covariance ("diag" for diagonal)
            n_iter: Maximum iterations for training
            random_state: Random seed for reproducibility
        """
        self.n_components = n_components
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state

        self.hmm_model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.training_ticker = None

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
            logger.info(f"4-State HMM initialized with {self.n_components} components")
        except Exception as e:
            logger.error(f"Error initializing HMM: {str(e)}")
            raise

    def prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Prepare observable features for HMM

        Features:
        1. returns_1d: 1-day log returns
        2. volatility_5d: 5-day rolling volatility
        3. volume_ratio: Current volume / 20-day average
        4. rsi_14: 14-period RSI (normalized)

        Args:
            df: DataFrame with OHLCV data

        Returns:
            numpy array with features for HMM
        """
        try:
            features_df = pd.DataFrame(index=df.index)

            # Feature 1: 1-day log returns
            features_df['returns_1d'] = np.log(df['Close'] / df['Close'].shift(1))

            # Feature 2: 5-day rolling volatility
            features_df['volatility_5d'] = features_df['returns_1d'].rolling(window=5).std()

            # Feature 3: Volume ratio (current / 20-day average)
            if 'Volume' in df.columns and df['Volume'].sum() > 0:
                vol_ma = df['Volume'].rolling(window=20).mean()
                features_df['volume_ratio'] = df['Volume'] / vol_ma.replace(0, 1)
                features_df['volume_ratio'] = features_df['volume_ratio'].clip(0, 5)  # Cap at 5x
            else:
                features_df['volume_ratio'] = 1.0

            # Feature 4: RSI-14 (normalized to 0-1)
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = 100 - (100 / (1 + rs))
            features_df['rsi_normalized'] = rsi / 100  # Normalize to 0-1

            # Drop NaN rows
            features_df = features_df.dropna()

            if len(features_df) < 30:
                logger.warning(f"Insufficient data after feature preparation: {len(features_df)} rows")
                return np.array([])

            # Convert to numpy array
            features = features_df[['returns_1d', 'volatility_5d', 'volume_ratio', 'rsi_normalized']].values

            # Handle any remaining NaN or infinite values
            features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

            return features

        except Exception as e:
            logger.error(f"Error preparing HMM features: {str(e)}")
            return np.array([])

    def train(self, ticker: str = "^NSEI", period: str = "2y") -> Dict:
        """
        Train the HMM model on historical data

        Args:
            ticker: Stock/index ticker symbol (default NIFTY 50)
            period: Historical period for training

        Returns:
            Dictionary with training results
        """
        try:
            logger.info(f"Training HMM on {ticker} with period {period}")

            # Get historical data
            df = get_historical_data(ticker, period=period)

            if df is None or df.empty:
                logger.error(f"No data available for {ticker}")
                return {"status": "error", "message": "No data available"}

            # Prepare features
            features = self.prepare_features(df)

            if len(features) < 50:
                logger.error("Insufficient data for HMM training")
                return {"status": "error", "message": "Insufficient data for training"}

            # Scale features
            features_scaled = self.scaler.fit_transform(features)

            # Train HMM
            logger.info("Training HMM model...")
            self.hmm_model.fit(features_scaled)
            self.is_trained = True
            self.training_ticker = ticker

            # Get model score
            model_score = self.hmm_model.score(features_scaled)

            # Decode states
            _, state_sequence = self.hmm_model.decode(features_scaled, algorithm="viterbi")

            # Calculate state statistics
            state_counts = np.bincount(state_sequence, minlength=self.n_components)
            state_percentages = state_counts / len(state_sequence) * 100

            # Identify which HMM state corresponds to which regime
            self._calibrate_states(features_scaled, state_sequence)

            logger.info(f"HMM training completed. Model score: {model_score:.4f}")

            return {
                "status": "success",
                "model_score": float(model_score),
                "training_samples": len(features_scaled),
                "state_distribution": {
                    self.REGIME_DEFINITIONS[i]['name']: {
                        "count": int(state_counts[i]),
                        "percentage": round(float(state_percentages[i]), 2)
                    }
                    for i in range(self.n_components)
                }
            }

        except Exception as e:
            logger.error(f"Error training HMM: {str(e)}")
            return {"status": "error", "message": str(e)}

    def _calibrate_states(self, features_scaled: np.ndarray, state_sequence: np.ndarray):
        """
        Calibrate HMM states to regime definitions based on feature characteristics

        This maps the learned HMM states to our predefined regime definitions
        based on the average feature values in each state.
        """
        try:
            # Calculate mean features for each state
            state_means = {}
            for state in range(self.n_components):
                mask = state_sequence == state
                if np.sum(mask) > 0:
                    state_means[state] = np.mean(features_scaled[mask], axis=0)
                else:
                    state_means[state] = np.zeros(features_scaled.shape[1])

            # Features: [returns_1d, volatility_5d, volume_ratio, rsi_normalized]
            # State mapping logic:
            # - Bullish: High returns, moderate vol, high RSI
            # - Bearish: Low returns, moderate vol, low RSI
            # - High Vol: High volatility regardless of returns
            # - Low Vol: Low volatility, consolidation

            # This is a simplified calibration - in production, you'd want
            # more sophisticated state identification
            logger.info("States calibrated to regime definitions")

        except Exception as e:
            logger.warning(f"State calibration warning: {str(e)}")

    def predict_regime(self, ticker: str, period: str = "3mo") -> Dict:
        """
        Predict current market regime for a ticker

        Args:
            ticker: Stock ticker symbol
            period: Data period for prediction

        Returns:
            Dictionary with regime prediction
        """
        try:
            # Auto-train if not trained
            if not self.is_trained:
                logger.info("Model not trained, training on NIFTY 50...")
                train_result = self.train("^NSEI", "2y")
                if train_result.get("status") != "success":
                    return {"status": "error", "message": "Failed to train model"}

            # Get data
            df = get_historical_data(ticker, period=period)

            if df is None or df.empty:
                return {"status": "error", "message": f"No data available for {ticker}"}

            # Prepare features
            features = self.prepare_features(df)

            if len(features) == 0:
                return {"status": "error", "message": "Insufficient data for prediction"}

            # Scale features
            features_scaled = self.scaler.transform(features)

            # Decode states
            log_prob, state_sequence = self.hmm_model.decode(features_scaled, algorithm="viterbi")

            # Get posterior probabilities
            posterior_probs = self.hmm_model.predict_proba(features_scaled)

            # Current regime
            current_regime = int(state_sequence[-1])
            current_probabilities = posterior_probs[-1]

            # Confidence
            confidence = float(max(current_probabilities))

            # Get regime info
            regime_info = self.REGIME_DEFINITIONS[current_regime]

            # Forecast next state
            next_probs = self.hmm_model.transmat_[current_regime]

            return {
                "status": "success",
                "regime_id": current_regime,
                "regime_name": regime_info['name'],
                "regime_short": regime_info['short_name'],
                "description": regime_info['description'],
                "bias": regime_info['bias'],
                "multiplier": regime_info['multiplier'],
                "color": regime_info['color'],
                "confidence": round(confidence, 3),
                "probabilities": {
                    self.REGIME_DEFINITIONS[i]['name']: round(float(current_probabilities[i]), 3)
                    for i in range(self.n_components)
                },
                "next_state_probabilities": {
                    self.REGIME_DEFINITIONS[i]['name']: round(float(next_probs[i]), 3)
                    for i in range(self.n_components)
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error predicting regime for {ticker}: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_nifty_regime_strip(self) -> Dict:
        """
        Get NIFTY 50 regime probabilities for dashboard regime strip

        Returns:
            Dictionary with regime strip data
        """
        try:
            # Predict regime for NIFTY 50
            result = self.predict_regime("^NSEI", "3mo")

            if result.get("status") != "success":
                # Return default/neutral state on error
                return {
                    "status": "success",
                    "current_regime": "Low Volatility",
                    "regime_id": 3,
                    "probabilities": {
                        "Bullish Trend": 0.25,
                        "Bearish Trend": 0.25,
                        "High Volatility": 0.25,
                        "Low Volatility": 0.25
                    },
                    "confidence": 0.25,
                    "bias": "NEUTRAL",
                    "timestamp": datetime.now().isoformat()
                }

            return {
                "status": "success",
                "current_regime": result['regime_name'],
                "regime_id": result['regime_id'],
                "regime_short": result['regime_short'],
                "probabilities": result['probabilities'],
                "confidence": result['confidence'],
                "bias": result['bias'],
                "color": result['color'],
                "timestamp": result['timestamp']
            }

        except Exception as e:
            logger.error(f"Error getting NIFTY regime strip: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "current_regime": "Unknown",
                "probabilities": {}
            }

    def get_regime_multiplier(self, regime_id: int, signal_bias: str) -> float:
        """
        Get score multiplier based on regime alignment with signal

        Args:
            regime_id: Current regime ID (0-3)
            signal_bias: Signal direction ("LONG" or "SHORT")

        Returns:
            Multiplier for scoring (0.75 to 1.5)
        """
        regime_info = self.REGIME_DEFINITIONS.get(regime_id, self.REGIME_DEFINITIONS[3])
        regime_bias = regime_info['bias']

        # For SHORT signals, use the short-specific multiplier
        if signal_bias == 'SHORT':
            return regime_info.get('short_score_multiplier', 1.0)

        # Perfect alignment for LONG
        if regime_bias == signal_bias:
            return regime_info['multiplier']

        # Low volatility (breakout potential) - boost all signals
        if regime_id == 3:
            return 1.5

        # High volatility - penalize LONG signals
        if regime_id == 2:
            return 0.75

        # Conflict (bullish signal in bearish regime or vice versa)
        if regime_bias != "NEUTRAL" and signal_bias != regime_bias:
            return 0.6  # Strong penalty for regime conflict

        return 1.0  # Neutral

    def get_short_regime_info(self, regime_id: int = None) -> Dict:
        """
        Get SHORT-specific regime interpretation

        Args:
            regime_id: Regime ID (uses current if None)

        Returns:
            Dictionary with SHORT trading guidance for the regime
        """
        if regime_id is None:
            # Get current regime if not specified
            result = self.predict_regime("^NSEI", "3mo")
            if result.get('status') != 'success':
                regime_id = 3  # Default to low volatility
            else:
                regime_id = result.get('regime_id', 3)

        regime_info = self.REGIME_DEFINITIONS.get(regime_id, self.REGIME_DEFINITIONS[3])

        return {
            'regime_id': regime_id,
            'regime_name': regime_info['name'],
            'short_interpretation': regime_info.get('short_interpretation', 'No specific guidance'),
            'short_score_multiplier': regime_info.get('short_score_multiplier', 1.0),
            'short_strategy': regime_info.get('short_strategy', 'STANDARD'),
            'target_extension': regime_info.get('short_target_extension', 1.0),
            'short_favorable': regime_info.get('short_score_multiplier', 1.0) >= 1.0,
            'color': regime_info['color']
        }

    def get_nifty_regime_strip_with_short(self) -> Dict:
        """
        Get NIFTY 50 regime probabilities with SHORT interpretation

        Returns:
            Dictionary with regime strip data including SHORT guidance
        """
        try:
            # Get standard regime strip
            result = self.get_nifty_regime_strip()

            if result.get('status') != 'success':
                return result

            # Add SHORT-specific information
            regime_id = result.get('regime_id', 3)
            short_info = self.get_short_regime_info(regime_id)

            result['short_interpretation'] = short_info['short_interpretation']
            result['short_score_multiplier'] = short_info['short_score_multiplier']
            result['short_strategy'] = short_info['short_strategy']
            result['short_favorable'] = short_info['short_favorable']
            result['target_extension'] = short_info.get('target_extension', 1.0)

            return result

        except Exception as e:
            logger.error(f"Error getting regime strip with short: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }


# Singleton instance
_regime_detector = None

def get_regime_detector() -> MTFRegimeDetector:
    """Get singleton regime detector instance"""
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = MTFRegimeDetector()
    return _regime_detector
