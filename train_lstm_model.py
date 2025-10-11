"""
Advanced LSTM Model Training Script
Complete training pipeline for stock price prediction with technical indicators

Features:
- Configurable training parameters
- Multiple data sources (Yahoo Finance, Alpha Vantage)
- 50+ technical indicators
- Model persistence (save/load)
- Performance evaluation
- Visualization
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Tuple, Optional
import os
import json
import pickle

# Deep Learning Libraries
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.model_selection import train_test_split
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("⚠️ TensorFlow not available. Install with: pip install tensorflow")

# Technical Analysis
from lstm_model.technical_analysis_engine import technical_engine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TRAINING CONFIGURATION
# ============================================================================

class TrainingConfig:
    """All configurable training parameters in one place"""

    # ===== DATA PARAMETERS =====
    TICKER = 'TVSMOTOR.NS'  # Stock ticker to train on
    DATA_SOURCE = 'yfinance'  # 'yfinance' or 'alphavantage'
    START_DATE = '2023-08-01'  # Training data start date
    END_DATE = datetime.now().strftime('%Y-%m-%d')  # Training data end date

    # Alternative: Use period instead of dates
    USE_PERIOD = True
    PERIOD = '10y'  # '1y', '2y', '5y', '10y', 'max'

    # ===== MODEL ARCHITECTURE =====
    SEQUENCE_LENGTH = 60  # Number of days to look back
    PREDICTION_HORIZON = 20  # Predict next N days

    # LSTM Layers Configuration
    LSTM_LAYERS = [
        {'units': 128, 'return_sequences': True, 'dropout': 0.1},
        {'units': 64, 'return_sequences': True, 'dropout': 0.1},
        {'units': 32, 'return_sequences': False, 'dropout': 0.3}
    ]

    # Dense Layers Configuration
    DENSE_LAYERS = [
        {'units': 16, 'activation': 'relu', 'dropout': 0.3},
        {'units': PREDICTION_HORIZON, 'activation': 'linear'}
    ]

    # ===== TRAINING PARAMETERS =====
    BATCH_SIZE = 32
    EPOCHS = 100
    VALIDATION_SPLIT = 0.2
    LEARNING_RATE = 0.001
    OPTIMIZER = 'adam'  # 'adam', 'rmsprop', 'sgd'
    LOSS = 'mse'  # 'mse', 'mae', 'huber'

    # ===== TECHNICAL INDICATORS =====
    USE_TECHNICAL_INDICATORS = True
    INDICATORS = {
        'sma': [5, 10, 20, 50, 200],
        'ema': [5, 12, 26, 50],
        'rsi': [14, 21],
        'macd': True,
        'bollinger': True,
        'atr': [14, 21],
        'volume': True,
        'stochastic': True
    }

    # ===== FEATURE ENGINEERING =====
    USE_PRICE_FEATURES = True  # Open, High, Low, Close
    USE_VOLUME_FEATURES = True
    USE_RETURNS = True  # Price returns
    USE_LOG_RETURNS = True
    NORMALIZE_DATA = True

    # ===== MODEL PERSISTENCE =====
    SAVE_MODEL = True
    MODEL_DIR = 'models/lstm'
    MODEL_NAME = f'lstm_{TICKER.replace(".", "_")}_{datetime.now().strftime("%Y%m%d")}'
    SAVE_SCALER = True
    SAVE_TRAINING_HISTORY = True

    # ===== EVALUATION =====
    TEST_SIZE = 0.2
    EVALUATE_ON_TEST = True
    GENERATE_PLOTS = True
    PLOT_DIR = 'plots/lstm'

    # ===== CALLBACKS =====
    USE_EARLY_STOPPING = True
    EARLY_STOPPING_PATIENCE = 15
    EARLY_STOPPING_MIN_DELTA = 0.0001

    USE_REDUCE_LR = True
    REDUCE_LR_PATIENCE = 5
    REDUCE_LR_FACTOR = 0.5
    REDUCE_LR_MIN_LR = 1e-4

    USE_MODEL_CHECKPOINT = True
    CHECKPOINT_SAVE_BEST_ONLY = True

    # ===== ALPHA VANTAGE API (if using) =====
    ALPHA_VANTAGE_API_KEY = 'YOUR_API_KEY_HERE'

    # ===== ADVANCED SETTINGS =====
    RANDOM_SEED = 42
    GPU_MEMORY_LIMIT = 4096  # MB, None for no limit
    VERBOSE = 1  # 0=silent, 1=progress bar, 2=one line per epoch


# ============================================================================
# DATA FETCHING
# ============================================================================

class DataFetcher:
    """Fetch stock data from various sources"""

    def __init__(self, config: TrainingConfig):
        self.config = config

    def fetch_data(self) -> pd.DataFrame:
        """Fetch data based on configured source"""
        logger.info(f"Fetching data for {self.config.TICKER} from {self.config.DATA_SOURCE}")

        if self.config.DATA_SOURCE == 'yfinance':
            return self._fetch_yfinance()
        elif self.config.DATA_SOURCE == 'alphavantage':
            return self._fetch_alphavantage()
        else:
            raise ValueError(f"Unknown data source: {self.config.DATA_SOURCE}")

    def _fetch_yfinance(self) -> pd.DataFrame:
        """Fetch data from Yahoo Finance"""
        try:
            ticker = yf.Ticker(self.config.TICKER)

            if self.config.USE_PERIOD:
                df = ticker.history(period=self.config.PERIOD)
            else:
                df = ticker.history(
                    start=self.config.START_DATE,
                    end=self.config.END_DATE
                )

            if df.empty:
                raise ValueError(f"No data returned for {self.config.TICKER}")

            logger.info(f"✓ Fetched {len(df)} records from Yahoo Finance")
            logger.info(f"  Date range: {df.index[0]} to {df.index[-1]}")

            return df

        except Exception as e:
            logger.error(f"Error fetching from Yahoo Finance: {str(e)}")
            raise

    def _fetch_alphavantage(self) -> pd.DataFrame:
        """Fetch data from Alpha Vantage"""
        try:
            import requests

            if self.config.ALPHA_VANTAGE_API_KEY == 'YOUR_API_KEY_HERE':
                raise ValueError("Please set ALPHA_VANTAGE_API_KEY in config")

            # Alpha Vantage API call
            url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={self.config.TICKER}&apikey={self.config.ALPHA_VANTAGE_API_KEY}&outputsize=full'

            response = requests.get(url)
            data = response.json()

            if 'Time Series (Daily)' not in data:
                raise ValueError(f"Invalid response from Alpha Vantage: {data}")

            # Convert to DataFrame
            df = pd.DataFrame.from_dict(
                data['Time Series (Daily)'],
                orient='index'
            )

            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # Rename columns
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df = df.astype(float)

            # Filter by date range
            if not self.config.USE_PERIOD:
                df = df[self.config.START_DATE:self.config.END_DATE]

            logger.info(f"✓ Fetched {len(df)} records from Alpha Vantage")
            return df

        except Exception as e:
            logger.error(f"Error fetching from Alpha Vantage: {str(e)}")
            raise


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

class FeatureEngineering:
    """Create features for LSTM model"""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.technical_engine = technical_engine

    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create all features based on configuration"""
        logger.info("Creating features...")

        # Make a copy
        data = df.copy()

        # 1. Basic price features
        if self.config.USE_PRICE_FEATURES:
            logger.info("  ✓ Price features (OHLC)")

        # 2. Volume features
        if self.config.USE_VOLUME_FEATURES:
            data['Volume_MA_20'] = data['Volume'].rolling(window=20).mean()
            data['Volume_Ratio'] = data['Volume'] / data['Volume_MA_20']
            logger.info("  ✓ Volume features")

        # 3. Returns
        if self.config.USE_RETURNS:
            data['Returns'] = data['Close'].pct_change()
            logger.info("  ✓ Returns")

        if self.config.USE_LOG_RETURNS:
            data['Log_Returns'] = np.log(data['Close'] / data['Close'].shift(1))
            logger.info("  ✓ Log returns")

        # 4. Technical indicators
        if self.config.USE_TECHNICAL_INDICATORS:
            data = self.technical_engine.calculate_all_indicators(data)
            logger.info("  ✓ 50+ Technical indicators")

        # Drop NaN values
        data = data.dropna()

        logger.info(f"✓ Feature engineering complete: {len(data)} samples, {len(data.columns)} features")

        return data


# ============================================================================
# DATA PREPARATION
# ============================================================================

class DataPreparation:
    """Prepare data for LSTM training"""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.feature_columns = None

    def prepare_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, MinMaxScaler]:
        """Prepare sequences for LSTM"""
        logger.info("Preparing data for LSTM...")

        # Select features
        self.feature_columns = df.columns.tolist()
        data = df[self.feature_columns].values

        # Normalize
        if self.config.NORMALIZE_DATA:
            data_scaled = self.scaler.fit_transform(data)
            logger.info(f"  ✓ Data normalized using MinMaxScaler")
        else:
            data_scaled = data

        # Create sequences
        X, y = self._create_sequences(data_scaled)

        logger.info(f"  ✓ Created {len(X)} sequences")
        logger.info(f"  ✓ Input shape: {X.shape}")
        logger.info(f"  ✓ Output shape: {y.shape}")

        return X, y, self.scaler

    def _create_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Create time series sequences"""
        X, y = [], []

        close_idx = self.feature_columns.index('Close') if 'Close' in self.feature_columns else 0

        for i in range(self.config.SEQUENCE_LENGTH, len(data) - self.config.PREDICTION_HORIZON + 1):
            # Input: sequence of all features
            X.append(data[i - self.config.SEQUENCE_LENGTH:i])

            # Output: next N days of closing prices
            y.append(data[i:i + self.config.PREDICTION_HORIZON, close_idx])

        return np.array(X), np.array(y)


# ============================================================================
# MODEL BUILDER
# ============================================================================

class LSTMModelBuilder:
    """Build LSTM model based on configuration"""

    def __init__(self, config: TrainingConfig):
        self.config = config

    def build_model(self, input_shape: Tuple) -> keras.Model:
        """Build LSTM model"""
        logger.info("Building LSTM model...")

        model = Sequential()

        # Add Input layer
        model.add(Input(shape=input_shape))

        # Add LSTM layers
        for i, layer_config in enumerate(self.config.LSTM_LAYERS):
            logger.info(f"  ✓ LSTM Layer {i+1}: {layer_config['units']} units")

            model.add(LSTM(
                units=layer_config['units'],
                return_sequences=layer_config.get('return_sequences', False)
            ))

            if 'dropout' in layer_config:
                model.add(Dropout(layer_config['dropout']))

        # Add Dense layers
        for i, layer_config in enumerate(self.config.DENSE_LAYERS):
            logger.info(f"  ✓ Dense Layer {i+1}: {layer_config['units']} units")

            model.add(Dense(
                units=layer_config['units'],
                activation=layer_config.get('activation', 'linear')
            ))

            if 'dropout' in layer_config:
                model.add(Dropout(layer_config['dropout']))

        # Compile model
        optimizer = self._get_optimizer()
        model.compile(
            optimizer=optimizer,
            loss=self.config.LOSS,
            metrics=['mae', 'mse']
        )

        logger.info(f"✓ Model compiled with {self.config.OPTIMIZER} optimizer")
        logger.info(f"✓ Total parameters: {model.count_params():,}")

        return model

    def _get_optimizer(self):
        """Get configured optimizer"""
        if self.config.OPTIMIZER == 'adam':
            return keras.optimizers.Adam(learning_rate=self.config.LEARNING_RATE)
        elif self.config.OPTIMIZER == 'rmsprop':
            return keras.optimizers.RMSprop(learning_rate=self.config.LEARNING_RATE)
        elif self.config.OPTIMIZER == 'sgd':
            return keras.optimizers.SGD(learning_rate=self.config.LEARNING_RATE)
        else:
            raise ValueError(f"Unknown optimizer: {self.config.OPTIMIZER}")


# ============================================================================
# TRAINER
# ============================================================================

class LSTMTrainer:
    """Train LSTM model"""

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.history = None

    def train(self, model: keras.Model, X_train: np.ndarray, y_train: np.ndarray,
              X_val: np.ndarray, y_val: np.ndarray) -> keras.Model:
        """Train the model"""
        logger.info(f"Starting training for {self.config.EPOCHS} epochs...")

        # Setup callbacks
        callbacks = self._setup_callbacks()

        # Train
        self.history = model.fit(
            X_train, y_train,
            batch_size=self.config.BATCH_SIZE,
            epochs=self.config.EPOCHS,
            validation_data=(X_val, y_val),
            callbacks=callbacks,
            verbose=self.config.VERBOSE
        )

        logger.info("✓ Training complete!")

        return model

    def _setup_callbacks(self) -> List:
        """Setup training callbacks"""
        callbacks = []

        # Early stopping
        if self.config.USE_EARLY_STOPPING:
            early_stop = EarlyStopping(
                monitor='val_loss',
                patience=self.config.EARLY_STOPPING_PATIENCE,
                min_delta=self.config.EARLY_STOPPING_MIN_DELTA,
                restore_best_weights=True,
                verbose=1
            )
            callbacks.append(early_stop)
            logger.info("  ✓ Early stopping enabled")

        # Reduce learning rate
        if self.config.USE_REDUCE_LR:
            reduce_lr = ReduceLROnPlateau(
                monitor='val_loss',
                factor=self.config.REDUCE_LR_FACTOR,
                patience=self.config.REDUCE_LR_PATIENCE,
                min_lr=self.config.REDUCE_LR_MIN_LR,
                verbose=1
            )
            callbacks.append(reduce_lr)
            logger.info("  ✓ Learning rate reduction enabled")

        # Model checkpoint
        if self.config.USE_MODEL_CHECKPOINT:
            os.makedirs(self.config.MODEL_DIR, exist_ok=True)
            checkpoint_path = os.path.join(
                self.config.MODEL_DIR,
                f'{self.config.MODEL_NAME}_checkpoint.h5'
            )

            checkpoint = ModelCheckpoint(
                checkpoint_path,
                monitor='val_loss',
                save_best_only=self.config.CHECKPOINT_SAVE_BEST_ONLY,
                verbose=1
            )
            callbacks.append(checkpoint)
            logger.info(f"  ✓ Model checkpoint enabled: {checkpoint_path}")

        return callbacks


# ============================================================================
# EVALUATOR
# ============================================================================

class ModelEvaluator:
    """Evaluate model performance"""

    def __init__(self, config: TrainingConfig):
        self.config = config

    def evaluate(self, model: keras.Model, X_test: np.ndarray, y_test: np.ndarray,
                 scaler: MinMaxScaler, feature_columns: List[str]) -> Dict:
        """Evaluate model on test data"""
        logger.info("Evaluating model on test data...")

        # Predictions
        y_pred = model.predict(X_test)

        # Denormalize if needed
        if self.config.NORMALIZE_DATA:
            # CRITICAL FIX: Find the actual index of 'Close' column
            if 'Close' not in feature_columns:
                logger.error("Close column not found in features!")
                close_idx = 3  # Fallback to typical OHLC position
            else:
                close_idx = feature_columns.index('Close')
                logger.info(f"Close column found at index: {close_idx}")

            # Create dummy array with same shape as original features
            dummy = np.zeros((len(y_pred), scaler.n_features_in_))

            # Reconstruct predictions for denormalization using CORRECT Close index
            for i in range(self.config.PREDICTION_HORIZON):
                dummy_pred = dummy.copy()
                dummy_pred[:, close_idx] = y_pred[:, i]  # Use correct Close index
                y_pred[:, i] = scaler.inverse_transform(dummy_pred)[:, close_idx]

            dummy_true = dummy.copy()
            for i in range(self.config.PREDICTION_HORIZON):
                dummy_true[:, close_idx] = y_test[:, i]
                y_test[:, i] = scaler.inverse_transform(dummy_true)[:, close_idx]

        # Calculate metrics
        mae = np.mean(np.abs(y_pred - y_test))
        mse = np.mean((y_pred - y_test) ** 2)
        rmse = np.sqrt(mse)
        mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100

        # Directional accuracy
        y_true_direction = np.sign(y_test[:, 0] - np.roll(y_test[:, 0], 1))
        y_pred_direction = np.sign(y_pred[:, 0] - np.roll(y_pred[:, 0], 1))
        directional_accuracy = np.mean(y_true_direction == y_pred_direction) * 100

        results = {
            'mae': float(mae),
            'mse': float(mse),
            'rmse': float(rmse),
            'mape': float(mape),
            'directional_accuracy': float(directional_accuracy)
        }

        logger.info("✓ Evaluation Results:")
        logger.info(f"  MAE:  {mae:.2f}")
        logger.info(f"  RMSE: {rmse:.2f}")
        logger.info(f"  MAPE: {mape:.2f}%")
        logger.info(f"  Directional Accuracy: {directional_accuracy:.2f}%")

        return results


# ============================================================================
# MODEL SAVER
# ============================================================================

class ModelSaver:
    """Save model and related artifacts"""

    def __init__(self, config: TrainingConfig):
        self.config = config

    def save_all(self, model: keras.Model, scaler: MinMaxScaler,
                 history: keras.callbacks.History, metrics: Dict,
                 feature_columns: List[str]):
        """Save model, scaler, and metadata"""
        os.makedirs(self.config.MODEL_DIR, exist_ok=True)

        # Save model
        model_path = os.path.join(self.config.MODEL_DIR, f'{self.config.MODEL_NAME}.h5')
        model.save(model_path)
        logger.info(f"✓ Model saved: {model_path}")

        # Save scaler
        if self.config.SAVE_SCALER:
            scaler_path = os.path.join(self.config.MODEL_DIR, f'{self.config.MODEL_NAME}_scaler.pkl')
            with open(scaler_path, 'wb') as f:
                pickle.dump(scaler, f)
            logger.info(f"✓ Scaler saved: {scaler_path}")

        # Save metadata
        metadata = {
            'ticker': self.config.TICKER,
            'sequence_length': self.config.SEQUENCE_LENGTH,
            'prediction_horizon': self.config.PREDICTION_HORIZON,
            'features': feature_columns,
            'metrics': metrics,
            'training_date': datetime.now().isoformat(),
            'config': {
                'batch_size': self.config.BATCH_SIZE,
                'epochs': self.config.EPOCHS,
                'learning_rate': self.config.LEARNING_RATE,
                'optimizer': self.config.OPTIMIZER
            }
        }

        metadata_path = os.path.join(self.config.MODEL_DIR, f'{self.config.MODEL_NAME}_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"✓ Metadata saved: {metadata_path}")

        # Save training history
        if self.config.SAVE_TRAINING_HISTORY and history:
            history_path = os.path.join(self.config.MODEL_DIR, f'{self.config.MODEL_NAME}_history.pkl')
            with open(history_path, 'wb') as f:
                pickle.dump(history.history, f)
            logger.info(f"✓ Training history saved: {history_path}")


# ============================================================================
# MAIN TRAINING PIPELINE
# ============================================================================

def main():
    """Main training pipeline"""

    print("=" * 80)
    print("LSTM MODEL TRAINING PIPELINE")
    print("=" * 80)
    print(f"\nTicker: {TrainingConfig.TICKER}")
    print(f"Data Source: {TrainingConfig.DATA_SOURCE}")
    print(f"Sequence Length: {TrainingConfig.SEQUENCE_LENGTH}")
    print(f"Prediction Horizon: {TrainingConfig.PREDICTION_HORIZON}")
    print(f"Epochs: {TrainingConfig.EPOCHS}")
    print(f"Batch Size: {TrainingConfig.BATCH_SIZE}")
    print("")

    # Check TensorFlow
    if not TENSORFLOW_AVAILABLE:
        logger.error("TensorFlow is not installed. Please install it first.")
        return

    # Set random seeds
    np.random.seed(TrainingConfig.RANDOM_SEED)
    tf.random.set_seed(TrainingConfig.RANDOM_SEED)

    try:
        # 1. Fetch data
        fetcher = DataFetcher(TrainingConfig)
        df = fetcher.fetch_data()

        # 2. Feature engineering
        feature_eng = FeatureEngineering(TrainingConfig)
        df_features = feature_eng.create_features(df)

        # 3. Prepare data
        prep = DataPreparation(TrainingConfig)
        X, y, scaler = prep.prepare_data(df_features)

        # 4. Train/test split
        split_idx = int(len(X) * (1 - TrainingConfig.TEST_SIZE))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # Validation split from training data
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train,
            test_size=TrainingConfig.VALIDATION_SPLIT,
            random_state=TrainingConfig.RANDOM_SEED
        )

        logger.info(f"Data split:")
        logger.info(f"  Train: {len(X_train)} samples")
        logger.info(f"  Validation: {len(X_val)} samples")
        logger.info(f"  Test: {len(X_test)} samples")

        # 5. Build model
        builder = LSTMModelBuilder(TrainingConfig)
        model = builder.build_model(input_shape=(X_train.shape[1], X_train.shape[2]))

        # 6. Train model
        trainer = LSTMTrainer(TrainingConfig)
        model = trainer.train(model, X_train, y_train, X_val, y_val)

        # 7. Evaluate
        evaluator = ModelEvaluator(TrainingConfig)
        metrics = evaluator.evaluate(model, X_test, y_test, scaler, prep.feature_columns)

        # 8. Save model
        if TrainingConfig.SAVE_MODEL:
            saver = ModelSaver(TrainingConfig)
            saver.save_all(model, scaler, trainer.history, metrics, prep.feature_columns)

        print("\n" + "=" * 80)
        print("TRAINING COMPLETE!")
        print("=" * 80)
        print(f"\nFinal Metrics:")
        print(f"  RMSE: {metrics['rmse']:.2f}")
        print(f"  MAPE: {metrics['mape']:.2f}%")
        print(f"  Directional Accuracy: {metrics['directional_accuracy']:.2f}%")
        print(f"\nModel saved to: {TrainingConfig.MODEL_DIR}/{TrainingConfig.MODEL_NAME}.h5")

    except Exception as e:
        logger.error(f"Training failed: {str(e)}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
