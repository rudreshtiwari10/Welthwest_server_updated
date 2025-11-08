"""
LSTM API Routes
API endpoints for LSTM stock prediction
Based on LSTM_STOCK_PREDICTION_SPEC.md

Endpoints:
- POST /api/lstm/admin/train - Train new LSTM model (admin only)
- POST /api/lstm/predict - Get stock predictions (public)
- GET /api/lstm/models - List all trained models (admin only)
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import os
import traceback
from datetime import datetime

from services.lstm_training_service import LSTMTrainingService
from services.lstm_prediction_service import LSTMPredictionService
from utils.lstm_validators import LSTMValidators
from utils.lstm_file_manager import LSTMFileManager

# Create Blueprint
lstm_api = Blueprint('lstm_api', __name__)

# Configuration - will be set during initialization
ADMIN_API_KEY = None
MODEL_DIR = None
SCALER_DIR = None
METADATA_DIR = None

# Service instances
training_service = None
prediction_service = None


def init_lstm_routes(app_config):
    """
    Initialize LSTM routes with configuration.

    Args:
        app_config (dict): Application configuration
    """
    global ADMIN_API_KEY, MODEL_DIR, SCALER_DIR, METADATA_DIR
    global training_service, prediction_service

    ADMIN_API_KEY = app_config.get('LSTM_ADMIN_API_KEY')
    MODEL_DIR = app_config.get('LSTM_MODEL_DIR')
    SCALER_DIR = app_config.get('LSTM_SCALER_DIR')
    METADATA_DIR = app_config.get('LSTM_METADATA_DIR')

    # Ensure directories exist
    LSTMFileManager.ensure_directories(MODEL_DIR, SCALER_DIR, METADATA_DIR)

    # Initialize services
    training_service = LSTMTrainingService(MODEL_DIR, SCALER_DIR, METADATA_DIR)
    prediction_service = LSTMPredictionService(MODEL_DIR, SCALER_DIR, METADATA_DIR)


def require_admin_api_key(f):
    """
    Decorator to require admin API key for endpoint access.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key from header
        api_key = request.headers.get('X-Admin-API-Key')

        if not api_key:
            return jsonify({
                "success": False,
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing admin API key",
                    "details": "Please provide valid X-Admin-API-Key header",
                    "timestamp": datetime.now().isoformat() + "Z"
                }
            }), 401

        # Validate API key
        if api_key != ADMIN_API_KEY:
            return jsonify({
                "success": False,
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing admin API key",
                    "details": "Please provide valid X-Admin-API-Key header",
                    "timestamp": datetime.now().isoformat() + "Z"
                }
            }), 401

        return f(*args, **kwargs)

    return decorated_function


@lstm_api.route('/api/lstm/admin/train', methods=['POST'])
@require_admin_api_key
def train_model():
    """
    Admin endpoint to train LSTM model for a stock.

    Request Body:
    {
        "stock_symbol": "RELIANCE.NS",
        "train_start": "2019-01-01",
        "train_end": "auto",
        "time_steps": 60,
        "epochs": 25,
        "batch_size": 32,
        "force_retrain": false
    }

    Returns:
        JSON response with training results
    """
    try:
        # Get request data
        data = request.get_json()

        if not data:
            return jsonify(LSTMValidators.create_error_response(
                "INVALID_REQUEST",
                "Request body is required",
                "Please provide JSON request body"
            ))

        # Validate request
        is_valid, errors = LSTMValidators.validate_training_request(data)
        if not is_valid:
            return jsonify(LSTMValidators.create_validation_error_response(errors))

        # Extract parameters with defaults
        stock_symbol = data.get('stock_symbol')
        train_start = data.get('train_start', '2019-01-01')
        train_end = data.get('train_end', 'auto')
        time_steps = data.get('time_steps', 60)
        epochs = data.get('epochs', 25)
        batch_size = data.get('batch_size', 32)
        force_retrain = data.get('force_retrain', False)

        # Sanitize stock symbol
        stock_symbol = LSTMValidators.sanitize_stock_symbol(stock_symbol)

        # Train model
        result = training_service.train_model(
            stock_symbol=stock_symbol,
            train_start=train_start,
            train_end=train_end,
            time_steps=time_steps,
            epochs=epochs,
            batch_size=batch_size,
            force_retrain=force_retrain
        )

        return jsonify(result), 200

    except ValueError as e:
        # Check if error is a dict (custom error format)
        error_data = str(e)
        try:
            import ast
            error_dict = ast.literal_eval(error_data)
            if isinstance(error_dict, dict) and 'code' in error_dict:
                # Handle MODEL_EXISTS error
                if error_dict['code'] == 'MODEL_EXISTS':
                    return jsonify({
                        "success": False,
                        "error": {
                            **error_dict,
                            "timestamp": datetime.now().isoformat() + "Z"
                        }
                    }), 409
        except:
            pass

        # Handle validation errors
        return jsonify(LSTMValidators.create_error_response(
            "INVALID_STOCK_SYMBOL",
            str(e),
            "Please provide a valid stock symbol from Yahoo Finance"
        )), 400

    except Exception as e:
        # Log the error
        print(f"Training error: {str(e)}")
        traceback.print_exc()

        # Return error response
        return jsonify(LSTMValidators.create_error_response(
            "TRAINING_FAILED",
            "Model training failed",
            str(e),
            500
        ))


@lstm_api.route('/api/lstm/predict', methods=['POST'])
def predict():
    """
    User endpoint to get stock predictions.

    Request Body:
    {
        "stock_symbol": "RELIANCE.NS"
    }

    Returns:
        JSON response with predictions
    """
    try:
        # Get request data
        data = request.get_json()

        if not data:
            return jsonify(LSTMValidators.create_error_response(
                "INVALID_REQUEST",
                "Request body is required",
                "Please provide JSON request body"
            ))

        # Validate request
        is_valid, errors = LSTMValidators.validate_prediction_request(data)
        if not is_valid:
            return jsonify(LSTMValidators.create_validation_error_response(errors))

        # Extract stock symbol
        stock_symbol = data.get('stock_symbol')

        # Sanitize stock symbol
        stock_symbol = LSTMValidators.sanitize_stock_symbol(stock_symbol)

        # Make predictions
        result = prediction_service.predict(stock_symbol)

        return jsonify(result), 200

    except ValueError as e:
        # Check if error is a dict (custom error format)
        error_data = str(e)
        try:
            import ast
            error_dict = ast.literal_eval(error_data)
            if isinstance(error_dict, dict) and 'code' in error_dict:
                # Handle MODEL_NOT_FOUND error
                if error_dict['code'] == 'MODEL_NOT_FOUND':
                    return jsonify({
                        "success": False,
                        "error": {
                            **error_dict,
                            "timestamp": datetime.now().isoformat() + "Z"
                        }
                    }), 404
                # Handle DATA_FETCH_FAILED error
                elif error_dict['code'] == 'DATA_FETCH_FAILED':
                    return jsonify({
                        "success": False,
                        "error": {
                            **error_dict,
                            "timestamp": datetime.now().isoformat() + "Z"
                        }
                    }), 503
        except:
            pass

        # Generic error
        return jsonify(LSTMValidators.create_error_response(
            "PREDICTION_ERROR",
            str(e),
            "Failed to generate predictions"
        )), 400

    except Exception as e:
        # Log the error
        print(f"Prediction error: {str(e)}")
        traceback.print_exc()

        # Return error response
        return jsonify(LSTMValidators.create_error_response(
            "PREDICTION_FAILED",
            "Failed to generate predictions",
            str(e),
            500
        ))


@lstm_api.route('/api/lstm/models', methods=['GET'])
@require_admin_api_key
def list_models():
    """
    Admin endpoint to list all trained models.

    Returns:
        JSON response with list of trained models
    """
    try:
        # Get list of all models
        models = LSTMFileManager.list_all_models(MODEL_DIR)

        # Get metadata for each model
        models_info = []
        for stock_symbol in models:
            try:
                metadata = training_service.get_model_info(stock_symbol)
                file_sizes = LSTMFileManager.get_model_size(stock_symbol, MODEL_DIR, SCALER_DIR)

                models_info.append({
                    "stock_symbol": stock_symbol,
                    "trained_at": metadata.get("training_info", {}).get("trained_at"),
                    "model_performance": metadata.get("model_performance", {}),
                    "file_size_mb": file_sizes.get("total_size_mb")
                })
            except:
                # If metadata not found, just add basic info
                models_info.append({
                    "stock_symbol": stock_symbol,
                    "trained_at": None,
                    "model_performance": {},
                    "file_size_mb": 0
                })

        # Get total disk usage
        disk_usage = LSTMFileManager.get_disk_usage(MODEL_DIR, SCALER_DIR, METADATA_DIR)

        return jsonify({
            "success": True,
            "data": {
                "total_models": len(models),
                "models": models_info,
                "disk_usage": disk_usage
            }
        }), 200

    except Exception as e:
        # Log the error
        print(f"List models error: {str(e)}")
        traceback.print_exc()

        # Return error response
        return jsonify(LSTMValidators.create_error_response(
            "LIST_MODELS_FAILED",
            "Failed to list models",
            str(e),
            500
        ))


@lstm_api.route('/api/lstm/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.

    Returns:
        JSON response with health status
    """
    return jsonify({
        "success": True,
        "message": "LSTM API is running",
        "timestamp": datetime.now().isoformat() + "Z",
        "endpoints": {
            "train": "/api/lstm/admin/train (POST, requires X-Admin-API-Key)",
            "predict": "/api/lstm/predict (POST)",
            "list_models": "/api/lstm/models (GET, requires X-Admin-API-Key)",
            "health": "/api/lstm/health (GET)"
        }
    }), 200
