# LSTM Stock Prediction API - Quick Start Guide

## Step 1: Configure Environment Variables

1. Open your `.env` file
2. Add the LSTM configuration variables from `LSTM_ENV_VARIABLES.txt`
3. **IMPORTANT:** Set a secure admin API key:

```bash
LSTM_ADMIN_API_KEY=my-secure-admin-key-123
```

## Step 2: Install Dependencies

Make sure you have all required packages:

```bash
pip install tensorflow keras numpy pandas yfinance scikit-learn
```

Or if you have a requirements.txt:

```bash
pip install -r requirements.txt
```

## Step 3: Start the Server

Start your Flask server:

```bash
python app.py
```

Or:

```bash
python run.py
```

The server should start and you'll see:
```
LSTM API routes initialized
```

## Step 4: Test the Health Endpoint

Check if the LSTM API is running:

```bash
curl http://localhost:8000/api/lstm/health
```

Expected response:
```json
{
  "success": true,
  "message": "LSTM API is running",
  "endpoints": {
    "train": "/api/lstm/admin/train (POST, requires X-Admin-API-Key)",
    "predict": "/api/lstm/predict (POST)",
    "list_models": "/api/lstm/models (GET, requires X-Admin-API-Key)",
    "health": "/api/lstm/health (GET)"
  }
}
```

## Step 5: Train Your First Model

Train a model for Reliance Industries (RELIANCE.NS):

```bash
curl -X POST http://localhost:8000/api/lstm/admin/train \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: my-secure-admin-key-123" \
  -d '{
    "stock_symbol": "RELIANCE.NS",
    "train_start": "2020-01-01",
    "epochs": 16
  }'
```

**Note:** Training will take 5-10 minutes. You'll see console output showing progress.

Expected response (after training completes):
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
    ...
  }
}
```

## Step 6: Get Predictions

Once training is complete, get 3-day predictions:

```bash
curl -X POST http://localhost:8000/api/lstm/predict \
  -H "Content-Type: application/json" \
  -d '{
    "stock_symbol": "RELIANCE.NS"
  }'
```

Expected response:
```json
{
  "success": true,
  "message": "Predictions generated successfully",
  "data": {
    "stock_symbol": "RELIANCE.NS",
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
    "disclaimer": "Predictions are based on historical data..."
  }
}
```

## Step 7: List All Trained Models

Check which models you have trained:

```bash
curl -X GET http://localhost:8000/api/lstm/models \
  -H "X-Admin-API-Key: my-secure-admin-key-123"
```

Expected response:
```json
{
  "success": true,
  "data": {
    "total_models": 1,
    "models": [
      {
        "stock_symbol": "RELIANCE.NS",
        "trained_at": "2025-11-06T...",
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
      "total_size_mb": 8.51
    }
  }
}
```

## Step 8: Train More Models

Train models for other stocks:

### TCS (Tata Consultancy Services)
```bash
curl -X POST http://localhost:8000/api/lstm/admin/train \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: my-secure-admin-key-123" \
  -d '{
    "stock_symbol": "TCS.NS",
    "train_start": "2020-01-01",
    "epochs": 16
  }'
```

### INFY (Infosys)
```bash
curl -X POST http://localhost:8000/api/lstm/admin/train \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: my-secure-admin-key-123" \
  -d '{
    "stock_symbol": "INFY.NS",
    "train_start": "2020-01-01",
    "epochs": 16
  }'
```

### HDFCBANK (HDFC Bank)
```bash
curl -X POST http://localhost:8000/api/lstm/admin/train \
  -H "Content-Type: application/json" \
  -H "X-Admin-API-Key: my-secure-admin-key-123" \
  -d '{
    "stock_symbol": "HDFCBANK.NS",
    "train_start": "2020-01-01",
    "epochs": 16
  }'
```

## Python Testing Script

Create a file `test_lstm_api.py`:

```python
import requests
import json
import time

BASE_URL = "http://localhost:8000"
ADMIN_KEY = "my-secure-admin-key-123"

def test_health():
    """Test health endpoint"""
    print("\n1. Testing Health Endpoint...")
    response = requests.get(f"{BASE_URL}/api/lstm/health")
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def train_model(stock_symbol):
    """Train a model"""
    print(f"\n2. Training Model for {stock_symbol}...")
    print("This will take 5-10 minutes...")

    response = requests.post(
        f"{BASE_URL}/api/lstm/admin/train",
        headers={
            "Content-Type": "application/json",
            "X-Admin-API-Key": ADMIN_KEY
        },
        json={
            "stock_symbol": stock_symbol,
            "train_start": "2020-01-01",
            "epochs": 16
        }
    )
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def get_predictions(stock_symbol):
    """Get predictions"""
    print(f"\n3. Getting Predictions for {stock_symbol}...")

    response = requests.post(
        f"{BASE_URL}/api/lstm/predict",
        headers={"Content-Type": "application/json"},
        json={"stock_symbol": stock_symbol}
    )
    print(f"Status: {response.status_code}")
    result = response.json()

    if result.get("success"):
        print(f"\nLast Actual Price: ₹{result['data']['last_actual_price']['close_price']}")
        print("\nPredictions:")
        for pred in result['data']['predictions']:
            print(f"  Day {pred['day']} ({pred['date']}): "
                  f"₹{pred['predicted_close_price']} "
                  f"({pred['trend']} {pred['change_percentage']}%, "
                  f"confidence: {pred['confidence']})")
    else:
        print(json.dumps(result, indent=2))

def list_models():
    """List all trained models"""
    print("\n4. Listing All Models...")

    response = requests.get(
        f"{BASE_URL}/api/lstm/models",
        headers={"X-Admin-API-Key": ADMIN_KEY}
    )
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    # Test health
    test_health()

    # Train model (uncomment to train)
    # train_model("RELIANCE.NS")

    # Get predictions
    get_predictions("RELIANCE.NS")

    # List models
    list_models()
```

Run the script:
```bash
python test_lstm_api.py
```

## Common Issues and Solutions

### Issue: "Model not found"
**Solution:** Train the model first using the admin endpoint

### Issue: "Invalid or missing admin API key"
**Solution:** Check that X-Admin-API-Key header matches your .env LSTM_ADMIN_API_KEY

### Issue: "No data returned for stock"
**Solution:** Use valid Yahoo Finance symbols (e.g., RELIANCE.NS, TCS.NS, AAPL for US stocks)

### Issue: Training is slow
**Solution:**
- Reduce epochs (try 10-15 instead of 25)
- Use shorter date range (e.g., start from 2022)
- This is normal - ML training takes time!

### Issue: ModuleNotFoundError
**Solution:** Install missing packages:
```bash
pip install tensorflow keras numpy pandas yfinance scikit-learn
```

## File Locations

After training, check these directories:

- **Models:** `./lstm_model/models/lstm_reliance_ns.keras`
- **Scalers:** `./lstm_model/scalers/scaler_reliance_ns.pkl`
- **Metadata:** `./lstm_model/metadata/reliance_ns.json`

## Next Steps

1. **Integrate with Frontend:** Use the prediction endpoint in your frontend application
2. **Add More Stocks:** Train models for your most-used stocks
3. **Schedule Retraining:** Set up monthly retraining for fresh data
4. **Monitor Performance:** Check model accuracy metrics
5. **Scale Up:** Consider GPU for faster training of many models

## Tips for Best Results

1. **Training Data:** Use at least 3-5 years of historical data
2. **Retraining:** Retrain models monthly with latest data
3. **Epochs:** 16-25 epochs usually sufficient, more doesn't always help
4. **Stock Selection:** Works best on liquid, actively traded stocks
5. **Interpretation:** Use predictions as indicators, not absolute truth

## Support

For detailed API documentation, see `LSTM_API_IMPLEMENTATION.md`
For specification details, see `LSTM_STOCK_PREDICTION_SPEC.md`

Happy predicting! 🚀📈
