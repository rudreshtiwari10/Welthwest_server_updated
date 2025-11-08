"""
LSTM Training Service
Handles model training workflow for LSTM stock prediction
Based on LSTM_STOCK_PREDICTION_SPEC.md
"""

import numpy as np
import time
import json
import pickle
import os
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from models.lstm_stock_model import build_lstm_model
from services.lstm_data_service import LSTMDataService


class LSTMTrainingService:
    """Service for training LSTM models."""

    def __init__(self, model_dir, scaler_dir, metadata_dir):
        """
        Initialize training service.

        Args:
            model_dir (str): Directory for storing model files
            scaler_dir (str): Directory for storing scaler files
            metadata_dir (str): Directory for storing metadata files
        """
        self.model_dir = model_dir
        self.scaler_dir = scaler_dir
        self.metadata_dir = metadata_dir

        # Create directories if they don't exist
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(scaler_dir, exist_ok=True)
        os.makedirs(metadata_dir, exist_ok=True)

    def train_model(self, stock_symbol, train_start="2019-01-01", train_end="auto",
                    time_steps=60, epochs=25, batch_size=32, force_retrain=False):
        """
        Train LSTM model for a stock.

        Args:
            stock_symbol (str): Stock ticker symbol
            train_start (str): Training start date
            train_end (str): Training end date ('auto' for yesterday)
            time_steps (int): Number of time steps
            epochs (int): Number of training epochs
            batch_size (int): Training batch size
            force_retrain (bool): Force retrain if model exists

        Returns:
            dict: Training results with performance metrics

        Raises:
            ValueError: If training fails or model already exists
        """
        # Normalize stock symbol for file naming
        symbol_normalized = stock_symbol.replace(".", "_").lower()

        # Check if model already exists
        model_path = os.path.join(self.model_dir, f"lstm_{symbol_normalized}.keras")
        if os.path.exists(model_path) and not force_retrain:
            # Load existing metadata
            metadata_path = os.path.join(self.metadata_dir, f"{symbol_normalized}.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    existing_metadata = json.load(f)
                raise ValueError({
                    "code": "MODEL_EXISTS",
                    "message": f"Model already exists for stock '{stock_symbol}'",
                    "details": "Use 'force_retrain: true' to retrain existing model",
                    "existing_model_info": {
                        "trained_at": existing_metadata.get("training_info", {}).get("trained_at"),
                        "model_performance": existing_metadata.get("model_performance", {})
                    }
                })

        # Start timing
        start_time = time.time()

        # Step 1: Fetch training data
        print(f"Fetching training data for {stock_symbol}...")
        data = LSTMDataService.fetch_stock_data(stock_symbol, train_start, train_end)

        # Step 2: Prepare training data
        print("Preparing training data...")
        X_train, y_train, X_test, y_test, scaler, training_data_len = \
            LSTMDataService.prepare_training_data(data, time_steps=time_steps)

        # Step 3: Build model
        print("Building LSTM model...")
        model = build_lstm_model(time_steps=time_steps)

        # Step 4: Train model
        print(f"Training model with {epochs} epochs...")
        history = model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.1,
            verbose=0  # Silent training for API
        )

        # Step 5: Evaluate on test set
        print("Evaluating model...")
        if len(X_test) > 0:
            test_predictions = model.predict(X_test, verbose=0)
            test_predictions = scaler.inverse_transform(test_predictions)

            # Calculate metrics
            mae = mean_absolute_error(y_test, test_predictions)
            rmse = np.sqrt(mean_squared_error(y_test, test_predictions))
            r2 = r2_score(y_test, test_predictions)
            mape = np.mean(np.abs((y_test - test_predictions) / y_test)) * 100
        else:
            # If no test data, use training metrics
            mae = history.history['loss'][-1]
            rmse = history.history['root_mean_squared_error'][-1]
            r2 = 0.0
            mape = 0.0

        # Step 6: Save model and scaler
        print("Saving model and scaler...")
        scaler_path = os.path.join(self.scaler_dir, f"scaler_{symbol_normalized}.pkl")
        with open(scaler_path, 'wb') as f:
            pickle.dump(scaler, f)

        model.save(model_path)

        # Step 7: Save metadata
        metadata = self._create_metadata(
            stock_symbol=stock_symbol,
            data=data,
            training_data_len=training_data_len,
            time_steps=time_steps,
            epochs=epochs,
            batch_size=batch_size,
            mae=mae,
            rmse=rmse,
            r2=r2,
            mape=mape,
            model_path=model_path,
            scaler_path=scaler_path,
            training_duration=time.time() - start_time
        )

        metadata_path = os.path.join(self.metadata_dir, f"{symbol_normalized}.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Step 8: Prepare response
        last_training_price = float(data['close'].iloc[-1])
        training_duration = time.time() - start_time

        response = {
            "success": True,
            "message": "Model trained successfully",
            "data": {
                "stock_symbol": stock_symbol,
                "training_completed_at": datetime.now().isoformat() + "Z",
                "training_duration_seconds": int(training_duration),
                "model_performance": {
                    "mae": float(mae),
                    "rmse": float(rmse),
                    "r2": float(r2),
                    "mape": float(mape)
                },
                "training_data": {
                    "start_date": str(data['date'].iloc[0]),
                    "end_date": str(data['date'].iloc[-1]),
                    "total_days": len(data),
                    "training_samples": len(X_train),
                    "test_samples": len(X_test) if len(X_test) > 0 else 0
                },
                "model_files": {
                    "model_path": model_path,
                    "scaler_path": scaler_path,
                    "metadata_path": metadata_path
                },
                "last_training_price": last_training_price
            }
        }

        print("Training complete!")
        return response

    def _create_metadata(self, stock_symbol, data, training_data_len, time_steps, epochs,
                         batch_size, mae, rmse, r2, mape, model_path, scaler_path,
                         training_duration):
        """
        Create metadata for trained model.

        Args:
            Various training parameters and metrics

        Returns:
            dict: Metadata dictionary
        """
        metadata = {
            "stock_symbol": stock_symbol,
            "training_info": {
                "trained_at": datetime.now().isoformat() + "Z",
                "training_duration_seconds": int(training_duration),
                "training_start_date": str(data['date'].iloc[0]),
                "training_end_date": str(data['date'].iloc[-1]),
                "total_training_days": len(data),
                "training_samples": training_data_len - time_steps,
                "test_samples": len(data) - training_data_len
            },
            "model_config": {
                "time_steps": time_steps,
                "forecast_days": 3,
                "epochs": epochs,
                "batch_size": batch_size,
                "lstm_layers": [128, 64, 32],
                "dense_layers": [64, 1],
                "dropout_rate": [0.2, 0.2, 0.2, 0.3]
            },
            "model_performance": {
                "mae": float(mae),
                "rmse": float(rmse),
                "r2": float(r2),
                "mape": float(mape)
            },
            "last_training_price": float(data['close'].iloc[-1]),
            "model_files": {
                "model_path": model_path,
                "scaler_path": scaler_path
            },
            "version": "1.0",
            "created_by": "admin",
            "last_updated": datetime.now().isoformat() + "Z"
        }

        return metadata

    def list_trained_models(self):
        """
        List all trained models.

        Returns:
            list: List of trained stock symbols
        """
        models = []
        if os.path.exists(self.model_dir):
            for filename in os.listdir(self.model_dir):
                if filename.startswith("lstm_") and filename.endswith(".keras"):
                    # Extract stock symbol
                    symbol_normalized = filename.replace("lstm_", "").replace(".keras", "")
                    symbol = symbol_normalized.replace("_", ".").upper()
                    models.append(symbol)
        return models

    def get_model_info(self, stock_symbol):
        """
        Get metadata for a trained model.

        Args:
            stock_symbol (str): Stock ticker symbol

        Returns:
            dict: Model metadata

        Raises:
            ValueError: If model not found
        """
        symbol_normalized = stock_symbol.replace(".", "_").lower()
        metadata_path = os.path.join(self.metadata_dir, f"{symbol_normalized}.json")

        if not os.path.exists(metadata_path):
            raise ValueError(f"Model not found for {stock_symbol}")

        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        return metadata
