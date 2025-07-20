# Market Regime Classifier Documentation

## Overview

The Market Regime Classifier is a Random Forest-based ensemble model designed to detect and classify market conditions into 5 distinct regimes. This implementation targets 85% accuracy and includes real-time adaptation capabilities for your AI trading platform.

## Market Regimes

The classifier identifies 5 market states:

### 1. Bull Trending (0)
- **Description**: Strong upward momentum with sustained buying pressure
- **Characteristics**: 
  - Positive average returns (> 0.2%)
  - Strong positive momentum (> 5%)
  - High trend strength (> 0.6)
  - Controlled volatility (< 3%)
  - RSI not overbought (< 80)
- **Trading Strategy**: Long/Buy positions with trend following

### 2. Bear Trending (1)
- **Description**: Strong downward momentum with sustained selling pressure
- **Characteristics**:
  - Negative average returns (< -0.2%)
  - Strong negative momentum (< -5%)
  - High trend strength (> 0.6)
  - Controlled volatility (< 3%)
  - RSI not oversold (> 20)
- **Trading Strategy**: Short/Sell positions with trend following

### 3. Sideways/Ranging (2)
- **Description**: Low volatility consolidation with no clear trend
- **Characteristics**:
  - Weak trend strength
  - Low volatility
  - Decreasing volume
  - Neutral momentum
- **Trading Strategy**: Range trading - buy support, sell resistance

### 4. High Volatility (3)
- **Description**: Large price swings with uncertain direction
- **Characteristics**:
  - High volatility (> 4%)
  - High momentum (> 10% either direction)
  - High return variability
- **Trading Strategy**: Reduced position sizes, tight stops

### 5. Accumulation/Distribution (4)
- **Description**: Transitional phase with smart money activity
- **Characteristics**:
  - Above average volume (> 1.2x)
  - Building momentum (2-5%)
  - Medium volatility (1.5-3.5%)
- **Trading Strategy**: Gradual accumulation, watch for breakouts

## Features Used

The classifier uses 50+ features derived from:

### Price-based Features
- Returns (1, 5, 10, 20 day)
- Log returns
- Price momentum indicators

### Volatility Features
- Rolling volatility (5, 10, 20 day)
- Volatility ratios
- Average True Range (ATR)

### Volume Features
- Volume moving averages
- Volume ratios
- Volume momentum

### Technical Indicators
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- Moving Averages (SMA, EMA)
- ADX (Average Directional Index)

### Market Structure
- Higher highs/Lower lows detection
- Breakout strength
- Trend strength indicators

## Installation

1. **Install required dependencies**:
```bash
pip install scikit-learn==1.0.2 yfinance==0.1.63 ta==0.7.0 schedule==1.1.0
```

2. **Import the services**:
```python
from services.market_regime_classifier import MarketRegimeClassifier
from services.market_regime_service import MarketRegimeService
```

## Usage

### 1. Basic Usage

```python
# Initialize the classifier
classifier = MarketRegimeClassifier()

# Train the model
training_result = classifier.train_model("RELIANCE.NS", period="2y")
print(f"Training accuracy: {training_result['accuracy']:.4f}")

# Predict current regime
prediction = classifier.predict_regime("RELIANCE.NS")
print(f"Current regime: {prediction['regime_name']}")
print(f"Confidence: {prediction['confidence']:.4f}")
```

### 2. Service Layer Usage

```python
# Initialize the service
service = MarketRegimeService()

# Get regime prediction with caching
result = service.predict_regime("RELIANCE.NS")

# Get comprehensive analysis
analysis = service.get_regime_analysis("RELIANCE.NS")

# Get trading recommendations
recommendations = service.get_regime_recommendations("RELIANCE.NS")
```

### 3. Multiple Ticker Predictions

```python
tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
results = service.get_multiple_regime_predictions(tickers)

for ticker, prediction in results['predictions'].items():
    if prediction["status"] == "success":
        print(f"{ticker}: {prediction['regime_name']} ({prediction['confidence']:.3f})")
```

## API Endpoints

### Authentication Required
All endpoints require JWT authentication except `/api/market-regime/definitions`.

### Available Endpoints

#### 1. Train Model (Admin Only)
```
POST /api/market-regime/train
```
**Body**:
```json
{
  "ticker": "RELIANCE.NS",
  "period": "2y",
  "retrain": false
}
```

#### 2. Predict Regime
```
GET /api/market-regime/predict?ticker=RELIANCE.NS
```

#### 3. Get Analysis
```
GET /api/market-regime/analysis?ticker=RELIANCE.NS
```

#### 4. Get Recommendations
```
GET /api/market-regime/recommendations?ticker=RELIANCE.NS
```

#### 5. Multiple Predictions
```
POST /api/market-regime/multiple
```
**Body**:
```json
{
  "tickers": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
}
```

#### 6. Model Information
```
GET /api/market-regime/model-info
```

#### 7. Evaluate Model (Admin Only)
```
GET /api/market-regime/evaluate?ticker=RELIANCE.NS
```

#### 8. Get Regime Definitions (No Auth)
```
GET /api/market-regime/definitions
```

## Real-time Adaptation

The system includes automatic adaptation mechanisms:

### 1. Scheduled Retraining
- **Daily**: Full model retraining at 6 PM (after market close)
- **Hourly**: Incremental updates with recent data during market hours

### 2. Manual Retraining
```python
# Retrain with recent data
classifier.retrain_with_recent_data("RELIANCE.NS", days_back=30)

# Full retraining
service.train_model("RELIANCE.NS", period="2y", retrain=True)
```

### 3. Caching Strategy
- **Regime predictions**: Cached for 15 minutes
- **Model training results**: Cached for 24 hours
- **Model evaluations**: Cached for 6 hours

## Performance Evaluation

### Accuracy Metrics
- **Target**: 85% accuracy
- **Cross-validation**: 5-fold CV for robust evaluation
- **Per-regime accuracy**: Individual regime classification accuracy

### Evaluation Methods
```python
# Evaluate model performance
evaluation = classifier.evaluate_model("RELIANCE.NS", test_period="6mo")
print(f"Overall accuracy: {evaluation['accuracy']:.4f}")

# Per-regime accuracy
for regime, accuracy in evaluation['regime_accuracy'].items():
    print(f"{regime}: {accuracy:.4f}")
```

## Testing

Run the comprehensive test suite:

```bash
python test_market_regime.py
```

The test suite covers:
1. Data pipeline integration
2. Feature preparation and regime labeling
3. Model training and prediction
4. Service layer functionality
5. API endpoint simulation

## Integration with Existing System

### 1. Data Sources
- **Primary**: Yahoo Finance API (15-minute delay)
- **Backup**: Upstox API integration
- **Caching**: Redis-based caching for performance

### 2. Feature Integration
- Leverages existing technical analysis indicators
- Compatible with current stock service architecture
- Integrates with subscription middleware

### 3. AI Model Ecosystem
- Part of larger AI trading platform
- Designed to work with LSTM predictors and XGBoost optimizers
- Provides regime context for other models

## Monitoring and Maintenance

### 1. Performance Monitoring
- Track prediction accuracy over time
- Monitor regime distribution changes
- Alert on model degradation

### 2. Data Quality Checks
- Validate input data completeness
- Check for data anomalies
- Handle missing data gracefully

### 3. Model Versioning
- Save model snapshots
- Track training parameters
- Enable rollback capabilities

## Troubleshooting

### Common Issues

#### 1. Model Not Trained
```python
# Check model status
model_info = service.get_model_info()
if model_info['status'] == 'not_trained':
    # Train the model
    service.train_model("RELIANCE.NS", period="2y")
```

#### 2. Insufficient Data
- Ensure minimum 100 data points for training
- Use longer periods for training (recommended: 2y)
- Handle missing data with forward/backward fill

#### 3. Low Accuracy
- Retrain with more recent data
- Adjust feature engineering parameters
- Consider ensemble with other models

#### 4. Slow Predictions
- Check cache configuration
- Verify data fetching performance
- Consider batch predictions for multiple tickers

## Future Enhancements

### 1. Online Learning
- Implement incremental learning algorithms
- Real-time model updates
- Adaptive feature selection

### 2. Additional Features
- Sentiment analysis integration
- News-based features
- Inter-market correlations

### 3. Advanced Techniques
- Deep learning regime detection
- Ensemble methods
- Regime transition modeling

## License and Support

This implementation is part of your AI trading platform. For support and customization, refer to the development team.

---

**Note**: This classifier is designed for educational and research purposes. Always validate predictions with additional analysis before making trading decisions.