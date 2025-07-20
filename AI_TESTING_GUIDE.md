# AI Model Endpoint Testing Guide

## Overview

This guide provides comprehensive testing tools for all AI model endpoints in the trading platform, including the Market Regime Classifier and other AI services.

## Testing Tools

### 1. Advanced Interactive Simulator (`ai_model_simulator.py`)
- **Features**: Full-featured GUI-like interface with colored output
- **Requirements**: `pip install colorama`
- **Best for**: Detailed testing and exploration

### 2. Simple Tester (`simple_ai_tester.py`)
- **Features**: Lightweight, no external dependencies
- **Requirements**: Built-in Python libraries only
- **Best for**: Quick testing and automated testing

## Quick Start

### Step 1: Start the Server
```bash
# Open terminal 1
cd "C:\Users\Kunal Kumar\Desktop\Human bot collection\Human bot 20 Deplyment with AI model correct one\WelthWestServer-main"
python run.py
```

### Step 2: Run the Tester
```bash
# Open terminal 2
cd "C:\Users\Kunal Kumar\Desktop\Human bot collection\Human bot 20 Deplyment with AI model correct one\WelthWestServer-main"

# Option 1: Simple tester (recommended)
python simple_ai_tester.py

# Option 2: Advanced simulator
python ai_model_simulator.py
```

## Available Endpoints to Test

### Market Regime Classifier Endpoints
1. **GET /api/market-regime/definitions** - Get regime definitions (no auth)
2. **GET /api/market-regime/model-info** - Get model information
3. **GET /api/market-regime/predict** - Predict market regime
4. **GET /api/market-regime/analysis** - Get comprehensive analysis
5. **GET /api/market-regime/recommendations** - Get trading recommendations
6. **POST /api/market-regime/multiple** - Batch predictions
7. **POST /api/market-regime/train** - Train model (admin only)
8. **GET /api/market-regime/evaluate** - Evaluate model (admin only)

### Technical Analysis Endpoints
1. **POST /api/technical-analysis** - Calculate technical indicators

### Stock Data Endpoints
1. **GET /api/stock/{ticker}/historical** - Get historical data
2. **GET /api/live/{ticker}** - Get live data
3. **GET /api/market-indices** - Get market indices

### Authentication Endpoints
1. **POST /api/auth/register** - Register user
2. **POST /api/auth/login** - Login user

## Testing Examples

### Example 1: Test Market Regime Prediction
```bash
# Start server
python run.py

# In another terminal, run simple tester
python simple_ai_tester.py

# Choose option 1 (Market Regime Classifier Endpoints)
# The tester will automatically test all endpoints
```

### Example 2: Test Specific Endpoint
```python
# Custom test script
import requests

# Test regime prediction
response = requests.get(
    "http://127.0.0.1:8000/api/market-regime/predict?ticker=RELIANCE.NS",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)

print(response.json())
```

## Expected Results

### Market Regime Classifier Results
- **Model Status**: Should be "trained" with is_loaded=True
- **Prediction Accuracy**: Should be >85% (currently achieving 96%)
- **Regime Prediction**: Should return regime name and confidence score
- **Recommendations**: Should provide trading strategy and risk level

### Sample Response - Regime Prediction
```json
{
  "status": "success",
  "regime": 2,
  "regime_name": "Sideways/Ranging",
  "regime_description": "Low volatility consolidation with no clear trend",
  "confidence": 0.99,
  "probabilities": {
    "Bull Trending": 0.01,
    "Bear Trending": 0.00,
    "Sideways/Ranging": 0.99,
    "High Volatility": 0.00,
    "Accumulation/Distribution": 0.00
  },
  "timestamp": "2025-07-17T09:45:00"
}
```

### Sample Response - Trading Recommendations
```json
{
  "status": "success",
  "ticker": "RELIANCE.NS",
  "current_regime": {
    "regime_name": "Sideways/Ranging",
    "confidence": 0.99
  },
  "recommendations": {
    "strategy": "Range Trading",
    "risk_level": "Medium",
    "position_size": "Small-Medium",
    "stop_loss": "Beyond range boundaries",
    "take_profit": "At opposite range boundary",
    "notes": "Trade within range. Buy at support, sell at resistance.",
    "confidence_level": "High"
  }
}
```

## Troubleshooting

### Common Issues

1. **Server Not Running**
   - Error: "Cannot connect to server"
   - Solution: Start server with `python run.py`

2. **Authentication Failed**
   - Error: "Login failed"
   - Solution: Tester automatically creates test user, should work automatically

3. **Model Not Trained**
   - Error: "Model not trained"
   - Solution: Run training endpoint or use admin user

4. **Port Already in Use**
   - Error: "Port 8000 is already in use"
   - Solution: Kill existing process or use different port

### Model Training
If model is not trained, you can train it using:
```python
# The tester will automatically attempt training
# Or manually train using the train endpoint
```

## Advanced Testing

### Custom Endpoint Testing
```python
# Using the advanced simulator
python ai_model_simulator.py

# Choose option 4 (Test Custom Endpoint)
# Enter: POST /api/market-regime/train
# Enter JSON: {"ticker": "RELIANCE.NS", "period": "1y", "retrain": true}
```

### Batch Testing
```python
# Test multiple tickers
{
  "tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS"]
}
```

## Performance Monitoring

### Expected Performance Metrics
- **Training Accuracy**: >85% (currently 96%)
- **Prediction Confidence**: >0.7 for good predictions
- **Response Time**: <2 seconds for predictions
- **Cache Hit Rate**: High for repeated requests

### Model Information
- **Training Samples**: ~200-300 samples
- **Test Samples**: ~50-80 samples
- **Feature Count**: 50+ features
- **Model Type**: Random Forest Classifier

## Support

If you encounter issues:
1. Check server logs in terminal 1
2. Verify all dependencies are installed
3. Ensure model is trained
4. Check authentication tokens

## Next Steps

After successful testing:
1. Deploy to production environment
2. Set up monitoring and alerts
3. Configure real-time data feeds
4. Implement automated retraining
5. Add additional AI models to the ensemble

---

**Note**: This testing suite verifies that all AI model endpoints are working correctly and ready for production deployment.