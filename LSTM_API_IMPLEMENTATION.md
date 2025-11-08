# LSTM Stock Prediction API - Implementation Guide

## Overview

This document describes the complete LSTM Stock Prediction API implementation based on the `LSTM_STOCK_PREDICTION_SPEC.md` specification. The system provides two main endpoints:

1. **Admin Training Endpoint** - Train LSTM models for specific stocks
2. **User Prediction Endpoint** - Get 3-day price predictions for trained stocks

## Architecture

The implementation follows a modular architecture with clear separation of concerns:

```
lstm_model/
├── models/          # Trained .keras model files
├── scalers/         # StandardScaler .pkl files
└── metadata/        # Model metadata JSON files

models/
└── lstm_stock_model.py       # LSTM architecture

services/
├── lstm_data_service.py      # Data fetching/preprocessing
├── lstm_training_service.py  # Model training logic
└── lstm_prediction_service.py # Prediction logic

utils/
├── lstm_validators.py        # Input validation
└── lstm_file_manager.py      # File operations

routes/
└── lstm_api_routes.py        # API endpoints
```

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /api/lstm/health`

**Description:** Check if LSTM API is running

**Response:**
```json
{
  "success": true,
  "message": "LSTM API is running",
  "timestamp": "2025-11-06T...",
  "endpoints": {
    "train": "/api/lstm/admin/train (POST, requires X-Admin-API-Key)",
    "predict": "/api/lstm/predict (POST)",
    "list_models": "/api/lstm/models (GET, requires X-Admin-API-Key)",
    "health": "/api/lstm/health (GET)"
  }
}
```

### 2. Train Model (Admin Only)

**Endpoint:** `POST /api/lstm/admin/train`

**Authentication:** Required (X-Admin-API-Key header)

**Request Headers:**
```
Content-Type: application/json
X-Admin-API-Key: your-admin-key-here
```

**Request Body:**
```json
{
  "stock_symbol": "RELIANCE.NS",
  "train_start": "2019-01-01",
  "train_end": "auto",
  "time_steps": 60,
  "epochs": 25,
  "batch_size": 32,
  "force_retrain": false
}
```

**Parameters:**
- `stock_symbol` (required): Stock ticker symbol (e.g., "RELIANCE.NS", "TCS.NS")
- `train_start` (optional): Training start date (default: "2019-01-01")
- `train_end` (optional): Training end date (default: "auto" - yesterday)
- `time_steps` (optional): Number of days for prediction window (default: 60)
- `epochs` (optional): Training epochs (default: 25)
- `batch_size` (optional): Batch size (default: 32)
- `force_retrain` (optional): Force retrain if model exists (default: false)

**Success Response (200):**
```json
{
  "success": true,
  "message": "Model trained successfully",
  "data": {
    "stock_symbol": "RELIANCE.NS",
    "training_completed_at": "2025-11-06T...",
    "training_duration_seconds": 420,
    "model_performance": {
      "mae": 12.45,
      "rmse": 18.32,
      "r2": 0.9234,
      "mape": 2.15
    },
    "training_data": {
      "start_date": "2019-01-01",
      "end_date": "2025-11-05",
      "total_days": 1734,
      "training_samples": 1647,
      "test_samples": 87
    },
    "model_files": {
      "model_path": "./lstm_model/models/lstm_reliance_ns.keras",
      "scaler_path": "./lstm_model/scalers/scaler_reliance_ns.pkl",
      "metadata_path": "./lstm_model/metadata/reliance_ns.json"
    },
    "last_training_price": 2845.50
  }
}
```

**Error Responses:**
- **401 Unauthorized** - Invalid or missing API key
- **400 Bad Request** - Invalid input parameters
- **409 Conflict** - Model already exists (use force_retrain: true)
- **500 Internal Server Error** - Training failed

### 3. Get Predictions

**Endpoint:** `POST /api/lstm/predict`

**Authentication:** None (public endpoint)

**Request Body:**
```json
{
  "stock_symbol": "RELIANCE.NS"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "Predictions generated successfully",
  "data": {
    "stock_symbol": "RELIANCE.NS",
    "prediction_generated_at": "2025-11-06T...",
    "last_actual_price": {
      "date": "2025-11-05",
      "close_price": 2845.50
    },
    "predictions": [
      {
        "day": 1,
        "date": "2025-11-06",
        "predicted_close_price": 2858.75,
        "change_from_last": 13.25,
        "change_percentage": 0.47,
        "confidence": "high",
        "trend": "up"
      },
      {
        "day": 2,
        "date": "2025-11-07",
        "predicted_close_price": 2872.40,
        "change_from_last": 26.90,
        "change_percentage": 0.95,
        "confidence": "medium",
        "trend": "up"
      },
      {
        "day": 3,
        "date": "2025-11-08",
        "predicted_close_price": 2865.20,
        "change_from_last": 19.70,
        "change_percentage": 0.69,
        "confidence": "low",
        "trend": "up"
      }
    ],
    "model_info": {
      "trained_on": "2025-11-01T...",
      "training_period": "2019-01-01 to 2025-10-31",
      "model_performance": {
        "mae": 12.45,
        "rmse": 18.32,
        "r2": 0.9234,
        "mape": 2.15
      },
      "time_steps_used": 60
    },
    "disclaimer": "Predictions are based on historical data and should not be considered as financial advice. Stock markets are subject to high volatility and risks."
  }
}
```

**Error Responses:**
- **400 Bad Request** - Missing or invalid stock symbol
- **404 Not Found** - Model not trained for this stock
- **503 Service Unavailable** - Unable to fetch latest data

### 4. List All Models (Admin Only)

**Endpoint:** `GET /api/lstm/models`

**Authentication:** Required (X-Admin-API-Key header)

**Response:**
```json
{
  "success": true,
  "data": {
    "total_models": 3,
    "models": [
      {
        "stock_symbol": "RELIANCE.NS",
        "trained_at": "2025-11-01T...",
        "model_performance": {
          "mae": 12.45,
          "rmse": 18.32,
          "r2": 0.9234,
          "mape": 2.15
        },
        "file_size_mb": 8.5
      }
    ],
    "disk_usage": {
      "models_size_mb": 25.4,
      "scalers_size_mb": 0.02,
      "metadata_size_mb": 0.01,
      "total_size_mb": 25.43
    }
  }
}
```

## Environment Variables

Add these variables to your `.env` file:

```bash
# ============================================
# LSTM STOCK PREDICTION CONFIGURATION
# ============================================

# Admin API Key (CHANGE THIS!)
LSTM_ADMIN_API_KEY=your-secure-admin-key-here-change-this

# Model Storage Directories
LSTM_MODEL_DIR=./lstm_model/models
LSTM_SCALER_DIR=./lstm_model/scalers
LSTM_METADATA_DIR=./lstm_model/metadata

# Training Configuration (Optional - has defaults)
LSTM_TIME_STEPS=60
LSTM_FORECAST_DAYS=3
LSTM_TRAINING_EPOCHS=25
LSTM_BATCH_SIZE=32
LSTM_TRAIN_TEST_SPLIT=0.95

# Data Configuration
LSTM_DATA_START_YEAR=2019-01-01
LSTM_DATA_SOURCE=yahoo_finance

# Rate Limiting
LSTM_RATE_LIMIT_PER_MINUTE=10
LSTM_ADMIN_RATE_LIMIT_PER_HOUR=5
```

## Testing the API

### Using cURL

**1. Check Health:**
```bash
curl -X GET http://localhost:8000/api/lstm/health
```

**2. Train a Model:**
```bash
curl -X POST http://localhost:8000/api/lstm/admin/train \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: your-admin-key-here" \
  -d '{
    "stock_symbol": "RELIANCE.NS",
    "train_start": "2019-01-01",
    "epochs": 25
  }'
```

**3. Get Predictions:**
```bash
curl -X POST http://localhost:8000/api/lstm/predict \
  -H "Content-Type: application/json" \
  -d '{
    "stock_symbol": "RELIANCE.NS"
  }'
```

**4. List All Models:**
```bash
curl -X GET http://localhost:8000/api/lstm/models \
  -H "X-Admin-API-Key: your-admin-key-here"
```

### Using Python

```python
import requests

BASE_URL = "http://localhost:8000"
ADMIN_KEY = "your-admin-key-here"

# Train a model
train_response = requests.post(
    f"{BASE_URL}/api/lstm/admin/train",
    headers={
        "Content-Type": "application/json",
        "X-Admin-API-Key": ADMIN_KEY
    },
    json={
        "stock_symbol": "TCS.NS",
        "train_start": "2019-01-01",
        "epochs": 25
    }
)
print(train_response.json())

# Get predictions
predict_response = requests.post(
    f"{BASE_URL}/api/lstm/predict",
    headers={"Content-Type": "application/json"},
    json={"stock_symbol": "TCS.NS"}
)
print(predict_response.json())
```

## Model Architecture

The LSTM model uses the following architecture:

```
Input: (60, 1) - 60 days of closing prices
    ↓
LSTM(128 units, return_sequences=True)
    ↓
Dropout(0.2)
    ↓
LSTM(64 units, return_sequences=True)
    ↓
Dropout(0.2)
    ↓
LSTM(32 units, return_sequences=False)
    ↓
Dropout(0.2)
    ↓
Dense(64 units, ReLU activation)
    ↓
Dropout(0.3)
    ↓
Dense(1 unit) - Predicted price
```

**Optimizer:** Adam (learning_rate=0.001)
**Loss Function:** MAE (Mean Absolute Error)
**Metrics:** RMSE (Root Mean Squared Error)

## Data Flow

### Training Flow:
1. Validate input parameters
2. Check admin API key
3. Fetch historical data from Yahoo Finance
4. Clean and preprocess data
5. Create training sequences (60-day windows)
6. Scale data using StandardScaler
7. Build and compile LSTM model
8. Train model with validation split
9. Evaluate on test set
10. Save model, scaler, and metadata
11. Return training results

### Prediction Flow:
1. Validate stock symbol
2. Check if model exists
3. Load model and scaler from disk
4. Fetch latest 60 days of data
5. Preprocess and scale data
6. Make iterative predictions (3 days)
7. Inverse transform predictions
8. Calculate changes and trends
9. Return predictions with metadata

## File Storage

**Model Files:**
- Location: `./lstm_model/models/`
- Format: `lstm_{symbol}.keras`
- Example: `lstm_reliance_ns.keras`

**Scaler Files:**
- Location: `./lstm_model/scalers/`
- Format: `scaler_{symbol}.pkl`
- Example: `scaler_reliance_ns.pkl`

**Metadata Files:**
- Location: `./lstm_model/metadata/`
- Format: `{symbol}.json`
- Example: `reliance_ns.json`

## Error Handling

All endpoints return standardized error responses:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable error message",
    "details": "Additional context or solution",
    "timestamp": "2025-11-06T..."
  }
}
```

Common error codes:
- `UNAUTHORIZED` - Invalid or missing API key
- `VALIDATION_ERROR` - Invalid input parameters
- `MODEL_EXISTS` - Model already trained (use force_retrain)
- `MODEL_NOT_FOUND` - Model not trained for this stock
- `TRAINING_FAILED` - Training process failed
- `PREDICTION_FAILED` - Prediction generation failed
- `DATA_FETCH_FAILED` - Unable to fetch stock data

## Important Notes

1. **Completely Separate Implementation**: This LSTM API is completely independent from any old LSTM implementations in the codebase. All endpoints use the `/api/lstm/` prefix.

2. **Admin Security**: The admin API key must be set in environment variables. Never commit the actual key to version control.

3. **Training Time**: Training can take 5-10 minutes depending on the data size and epochs. The endpoint has appropriate timeouts.

4. **Prediction Caching**: Models and scalers are cached in memory for faster predictions. Clear cache if you retrain a model.

5. **Weekend Handling**: The system automatically skips weekends when calculating prediction dates.

6. **Data Source**: Uses Yahoo Finance API. Ensure yfinance is installed: `pip install yfinance`

7. **Model Retraining**: Retrain models monthly with latest data for best accuracy.

## Troubleshooting

**Issue: "Model not found"**
- Solution: Train the model first using the admin endpoint

**Issue: "Data fetch failed"**
- Solution: Check internet connection and Yahoo Finance availability

**Issue: "Training takes too long"**
- Solution: Reduce epochs or use a smaller date range

**Issue: "Predictions are inaccurate"**
- Solution: Retrain model with more recent data

## Dependencies

Ensure these packages are installed:

```
tensorflow>=2.13.0
keras>=2.13.0
numpy>=1.24.0
pandas>=2.0.0
yfinance>=0.2.28
scikit-learn>=1.3.0
flask>=2.3.0
```

## Next Steps

1. Set the `LSTM_ADMIN_API_KEY` in your `.env` file
2. Start the Flask server
3. Test the health endpoint
4. Train your first model
5. Get predictions!

## Support

For issues or questions, check the logs or refer to the LSTM_STOCK_PREDICTION_SPEC.md file.
