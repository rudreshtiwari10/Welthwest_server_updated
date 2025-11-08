"""
LSTM Prediction Service
Handles prediction workflow for LSTM stock prediction
Based on LSTM_STOCK_PREDICTION_SPEC.md
"""

import numpy as np
import json
import pickle
import os
from datetime import datetime
import tensorflow as tf
from tensorflow import keras

from services.lstm_data_service import LSTMDataService


class LSTMPredictionService:
    """Service for making stock predictions using trained LSTM models."""

    def __init__(self, model_dir, scaler_dir, metadata_dir):
        """
        Initialize prediction service.

        Args:
            model_dir (str): Directory containing model files
            scaler_dir (str): Directory containing scaler files
            metadata_dir (str): Directory containing metadata files
        """
        self.model_dir = model_dir
        self.scaler_dir = scaler_dir
        self.metadata_dir = metadata_dir

        # Cache for loaded models and scalers
        self.model_cache = {}
        self.scaler_cache = {}

    def predict(self, stock_symbol, forecast_days=3):
        """
        Make predictions for a stock.

        Args:
            stock_symbol (str): Stock ticker symbol
            forecast_days (int): Number of days to predict (default: 3)

        Returns:
            dict: Prediction results with metadata

        Raises:
            ValueError: If model not found or prediction fails
        """
        # Normalize stock symbol
        symbol_normalized = stock_symbol.replace(".", "_").lower()

        # Check if model exists
        model_path = os.path.join(self.model_dir, f"lstm_{symbol_normalized}.keras")
        scaler_path = os.path.join(self.scaler_dir, f"scaler_{symbol_normalized}.pkl")
        metadata_path = os.path.join(self.metadata_dir, f"{symbol_normalized}.json")

        if not os.path.exists(model_path):
            # Get list of available models
            available_stocks = self._list_available_stocks()
            raise ValueError({
                "code": "MODEL_NOT_FOUND",
                "message": f"Model not trained for stock '{stock_symbol}'",
                "details": "This stock has not been trained yet. Please contact admin to train this model.",
                "available_stocks": available_stocks
            })

        # Load model, scaler, and metadata
        model = self._load_model(model_path, symbol_normalized)
        scaler = self._load_scaler(scaler_path, symbol_normalized)
        metadata = self._load_metadata(metadata_path)

        # Get time steps from metadata
        time_steps = metadata.get("model_config", {}).get("time_steps", 60)

        # Fetch latest data
        try:
            latest_data = LSTMDataService.fetch_latest_data(stock_symbol, days=time_steps + 10)
        except Exception as e:
            raise ValueError({
                "code": "DATA_FETCH_FAILED",
                "message": "Unable to fetch latest stock data",
                "details": f"Yahoo Finance API error: {str(e)}",
                "retry_after": 300
            })

        # Prepare prediction input
        forecast_input, scaled_data = LSTMDataService.prepare_prediction_input(
            latest_data, scaler, time_steps
        )

        # Make iterative predictions
        predictions = []
        last_actual_price = float(latest_data['close'].iloc[-1])
        last_actual_date = latest_data['date'].iloc[-1]

        # Get prediction dates (skip weekends)
        prediction_dates = LSTMDataService.get_next_trading_dates(last_actual_date, forecast_days)

        # Iterative prediction
        current_input = scaled_data.copy()

        for day_num in range(forecast_days):
            # Reshape for prediction
            X_forecast = current_input[-time_steps:].reshape(1, time_steps, 1)

            # Predict next day (scaled)
            predicted_scaled = model.predict(X_forecast, verbose=0)

            # Inverse transform to actual price
            predicted_price = scaler.inverse_transform(predicted_scaled)[0][0]

            # Calculate change from last actual price
            change_from_last = predicted_price - last_actual_price
            change_percentage = (change_from_last / last_actual_price) * 100

            # Determine confidence level (decreases with forecast horizon)
            confidence = "high" if day_num == 0 else "medium" if day_num == 1 else "low"

            # Determine trend
            trend = "up" if change_from_last > 0 else "down" if change_from_last < 0 else "neutral"

            # Store prediction
            prediction = {
                "day": day_num + 1,
                "date": prediction_dates[day_num].strftime('%Y-%m-%d'),
                "predicted_close_price": round(float(predicted_price), 2),
                "change_from_last": round(float(change_from_last), 2),
                "change_percentage": round(float(change_percentage), 2),
                "confidence": confidence,
                "trend": trend
            }
            predictions.append(prediction)

            # Update input for next iteration (append prediction)
            current_input = np.append(current_input, predicted_scaled, axis=0)

        # Prepare response
        response = {
            "success": True,
            "message": "Predictions generated successfully",
            "data": {
                "stock_symbol": stock_symbol,
                "prediction_generated_at": datetime.now().isoformat() + "Z",
                "last_actual_price": {
                    "date": last_actual_date.strftime('%Y-%m-%d'),
                    "close_price": round(last_actual_price, 2)
                },
                "predictions": predictions,
                "model_info": {
                    "trained_on": metadata.get("training_info", {}).get("trained_at"),
                    "training_period": f"{metadata.get('training_info', {}).get('training_start_date')} to {metadata.get('training_info', {}).get('training_end_date')}",
                    "model_performance": metadata.get("model_performance", {}),
                    "time_steps_used": time_steps
                },
                "disclaimer": "Predictions are based on historical data and should not be considered as financial advice. Stock markets are subject to high volatility and risks."
            }
        }

        return response

    def _load_model(self, model_path, cache_key):
        """
        Load model from file or cache.

        Args:
            model_path (str): Path to model file
            cache_key (str): Cache key for the model

        Returns:
            keras.Model: Loaded model
        """
        if cache_key not in self.model_cache:
            self.model_cache[cache_key] = keras.models.load_model(model_path)
        return self.model_cache[cache_key]

    def _load_scaler(self, scaler_path, cache_key):
        """
        Load scaler from file or cache.

        Args:
            scaler_path (str): Path to scaler file
            cache_key (str): Cache key for the scaler

        Returns:
            StandardScaler: Loaded scaler
        """
        if cache_key not in self.scaler_cache:
            with open(scaler_path, 'rb') as f:
                self.scaler_cache[cache_key] = pickle.load(f)
        return self.scaler_cache[cache_key]

    def _load_metadata(self, metadata_path):
        """
        Load metadata from file.

        Args:
            metadata_path (str): Path to metadata file

        Returns:
            dict: Metadata
        """
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        return metadata

    def _list_available_stocks(self):
        """
        List all available trained stocks.

        Returns:
            list: List of stock symbols
        """
        stocks = []
        if os.path.exists(self.model_dir):
            for filename in os.listdir(self.model_dir):
                if filename.startswith("lstm_") and filename.endswith(".keras"):
                    symbol_normalized = filename.replace("lstm_", "").replace(".keras", "")
                    symbol = symbol_normalized.replace("_", ".").upper()
                    stocks.append(symbol)
        return stocks

    def clear_cache(self):
        """Clear model and scaler cache."""
        self.model_cache.clear()
        self.scaler_cache.clear()
