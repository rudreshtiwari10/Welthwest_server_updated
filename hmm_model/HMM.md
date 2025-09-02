# HMM Market Regime Model Documentation

## Overview

The HMM (Hidden Markov Model) Market Regime Classifier is a specialized model for identifying market regimes using statistical patterns in price movements. This model is completely separate from the main market regime classifier and focuses purely on Hidden Markov Model techniques.

## Model Architecture

### Core Components
- **Model Type**: Gaussian Hidden Markov Model
- **States**: 3 hidden states representing different volatility regimes
- **Features**: Log returns, rolling volatility, volume changes
- **Algorithm**: Viterbi algorithm for state decoding
- **Training**: Expectation-Maximization algorithm

### Regime Definitions

| State | Name | Description | Characteristics |
|-------|------|-------------|-----------------|
| 0 | Low Volatility Regime | Stable market conditions | Small price movements, consistent trends |
| 1 | Medium Volatility Regime | Normal market conditions | Regular price movements, typical behavior |
| 2 | High Volatility Regime | Turbulent market conditions | Large price movements, crisis periods |

## API Endpoints

### 1. HMM Regime Prediction

**Endpoint**: `/api/hmm_model/predict`  
**Methods**: `GET`, `POST`  
**Authentication**: Not required

#### Input Fields

**GET Request:**
```
?ticker=RELIANCE.NS
```

**POST Request:**
```json
{
  "ticker": "RELIANCE.NS"
}
```

#### Input Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ticker` | string | Yes | "RELIANCE.NS" | Stock ticker symbol |

#### Response Format
```json
{
  "status": "success",
  "regime": 1,
  "regime_name": "Medium Volatility Regime",
  "regime_description": "Normal market conditions with moderate volatility",
  "confidence": 0.75,
  "current_probabilities": {
    "state_0": 0.15,
    "state_1": 0.75,
    "state_2": 0.10
  },
  "next_state_probabilities": {
    "state_0": 0.20,
    "state_1": 0.65,
    "state_2": 0.15
  },
  "state_sequence": [1, 1, 0, 1, 1, 1, 2, 1, 1, 1],
  "model_score": -245.67,
  "timestamp": "2025-01-01T12:00:00"
}
```

### 2. HMM Regime Analysis

**Endpoint**: `/api/hmm_model/analysis`  
**Method**: `GET`  
**Authentication**: Not required

#### Input Fields
```
?ticker=RELIANCE.NS&period=6mo
```

#### Input Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ticker` | string | Yes | "RELIANCE.NS" | Stock ticker symbol |
| `period` | string | No | "6mo" | Analysis period (3mo, 6mo, 1y, 2y) |

#### Response Format
```json
{
  "status": "success",
  "regime_persistence": {
    "state_0": {
      "average_duration": 5.2,
      "max_duration": 15,
      "num_periods": 8
    },
    "state_1": {
      "average_duration": 12.5,
      "max_duration": 35,
      "num_periods": 12
    },
    "state_2": {
      "average_duration": 3.1,
      "max_duration": 8,
      "num_periods": 6
    }
  },
  "transition_matrix": [
    [0.65, 0.30, 0.05],
    [0.25, 0.60, 0.15],
    [0.40, 0.45, 0.15]
  ],
  "observed_transitions": [
    [62.5, 32.5, 5.0],
    [23.8, 61.9, 14.3],
    [38.5, 46.2, 15.3]
  ],
  "state_distribution": {
    "state_0": 45,
    "state_1": 89,
    "state_2": 26
  },
  "analysis_period": "6mo",
  "total_periods": 160
}
```

### 3. Train HMM Model

**Endpoint**: `/api/hmm_model/train`  
**Method**: `POST`  
**Authentication**: Required (Admin only)

#### Input Fields
```json
{
  "ticker": "RELIANCE.NS",
  "period": "2y",
  "retrain": false
}
```

#### Input Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ticker` | string | Yes | "RELIANCE.NS" | Stock ticker for training |
| `period` | string | No | "2y" | Training period (1y, 2y, 5y, max) |
| `retrain` | boolean | No | false | Force retrain existing model |

#### Response Format
```json
{
  "status": "success",
  "model_score": -1245.67,
  "log_likelihood": -1245.67,
  "transition_matrix": [
    [0.65, 0.30, 0.05],
    [0.25, 0.60, 0.15],
    [0.40, 0.45, 0.15]
  ],
  "means": [
    [-0.002],
    [0.001],
    [0.005]
  ],
  "covariances": [
    [[0.0001]],
    [[0.0004]],
    [[0.0016]]
  ],
  "state_distribution": {
    "state_0": {
      "count": 234,
      "percentage": 32.5
    },
    "state_1": {
      "count": 345,
      "percentage": 47.9
    },
    "state_2": {
      "count": 141,
      "percentage": 19.6
    }
  },
  "training_samples": 720,
  "n_components": 3
}
```

### 4. Multiple Ticker Predictions

**Endpoint**: `/api/hmm_model/multiple`  
**Method**: `POST`  
**Authentication**: Required

#### Input Fields
```json
{
  "tickers": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFC.NS"]
}
```

#### Input Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `tickers` | array | Yes | ["RELIANCE.NS"] | List of ticker symbols |

#### Response Format
```json
{
  "status": "success",
  "predictions": {
    "RELIANCE.NS": {
      "status": "success",
      "regime": 1,
      "regime_name": "Medium Volatility Regime",
      "confidence": 0.75
    },
    "TCS.NS": {
      "status": "success",
      "regime": 0,
      "regime_name": "Low Volatility Regime", 
      "confidence": 0.82
    }
  },
  "processed_tickers": 4,
  "total_tickers": 4,
  "timestamp": "2025-01-01T12:00:00",
  "errors": []
}
```

### 5. HMM Model Information

**Endpoint**: `/api/hmm_model/model-info`  
**Method**: `GET`  
**Authentication**: Required

#### Input Fields
No input parameters required.

#### Response Format
```json
{
  "status": "success",
  "model_type": "Hidden Markov Model",
  "n_components": 3,
  "covariance_type": "full",
  "is_trained": true,
  "regime_definitions": {
    "0": {
      "name": "Low Volatility Regime",
      "description": "Stable market conditions with low volatility and predictable returns",
      "characteristics": "Small price movements, consistent trends"
    },
    "1": {
      "name": "Medium Volatility Regime",
      "description": "Normal market conditions with moderate volatility",
      "characteristics": "Regular price movements, typical market behavior"
    },
    "2": {
      "name": "High Volatility Regime", 
      "description": "Turbulent market conditions with high volatility and large price swings",
      "characteristics": "Large price movements, unpredictable behavior, crisis periods"
    }
  },
  "transition_matrix": [
    [0.65, 0.30, 0.05],
    [0.25, 0.60, 0.15],
    [0.40, 0.45, 0.15]
  ],
  "means": [
    [-0.002],
    [0.001], 
    [0.005]
  ],
  "covariances": [
    [[0.0001]],
    [[0.0004]],
    [[0.0016]]
  ]
}
```

### 6. Evaluate HMM Model

**Endpoint**: `/api/hmm_model/evaluate`  
**Method**: `GET`  
**Authentication**: Required (Admin only)

#### Input Fields
```
?ticker=RELIANCE.NS&test_period=6mo
```

#### Input Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ticker` | string | Yes | "RELIANCE.NS" | Stock ticker for evaluation |
| `test_period` | string | No | "6mo" | Evaluation period (3mo, 6mo, 1y) |

#### Response Format
```json
{
  "status": "success",
  "model_score": -456.78,
  "log_likelihood": -456.78,
  "stability_ratio": 0.85,
  "state_changes": 24,
  "total_periods": 160,
  "state_distribution": {
    "state_0": {
      "count": 52,
      "percentage": 32.5
    },
    "state_1": {
      "count": 76,
      "percentage": 47.5
    },
    "state_2": {
      "count": 32,
      "percentage": 20.0
    }
  },
  "evaluation_period": "6mo"
}
```

## Testing the HMM Model

### Test Files Provided

1. **`test_hmm_endpoints.py`** - Python script for testing all endpoints
2. **`test_hmm_frontend.html`** - HTML interface for interactive testing

### Quick Test Commands

```bash
# Test basic prediction
curl "http://localhost:5000/api/hmm_model/predict?ticker=RELIANCE.NS"

# Test with POST
curl -X POST "http://localhost:5000/api/hmm_model/predict" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "RELIANCE.NS"}'

# Test analysis
curl "http://localhost:5000/api/hmm_model/analysis?ticker=RELIANCE.NS&period=6mo"
```

## Model Features

### Input Features Used
- **Log Returns**: `log(price_t / price_{t-1})`
- **Rolling Volatility**: 5-day rolling standard deviation of returns
- **Volume Changes**: `log(volume_t / volume_{t-1})` (if available)

### Model Configuration
- **Components**: 3 hidden states
- **Covariance Type**: Full covariance matrices
- **Maximum Iterations**: 100
- **Algorithm**: Viterbi decoding
- **Scaling**: StandardScaler normalization

### Performance Metrics
- **Model Score**: Log-likelihood of the data
- **Stability Ratio**: Measure of regime persistence
- **State Probabilities**: Forward-backward algorithm probabilities
- **Transition Analysis**: Regime switching patterns

## Error Handling

### Common Error Responses

```json
{
  "status": "error",
  "message": "Model not trained"
}
```

```json
{
  "status": "error", 
  "message": "No data available"
}
```

```json
{
  "status": "error",
  "message": "Insufficient data for prediction"
}
```

### HTTP Status Codes
- **200**: Success
- **400**: Bad request (invalid parameters)
- **401**: Unauthorized (missing/invalid JWT)
- **403**: Forbidden (admin required)
- **500**: Internal server error

## Implementation Details

### File Structure
```
hmm_model/
├── __init__.py          # Package initialization
├── hmm_classifier.py    # Core HMM implementation
├── hmm_service.py       # Service layer with caching
└── HMM.md              # This documentation
```

### Dependencies
- `hmmlearn`: Hidden Markov Model implementation
- `sklearn`: Data preprocessing and scaling
- `pandas`: Data manipulation
- `numpy`: Numerical computations
- `yfinance`: Stock data fetching

### Caching Strategy
- **Prediction Cache**: 5 minutes TTL
- **Analysis Cache**: 10 minutes TTL
- **Cache Keys**: `hmm_predict_{ticker}`, `hmm_persistence_{ticker}_{period}`

## Usage Examples

### Basic Usage
```python
from hmm_model import hmm_service

# Get regime prediction
result = hmm_service.predict_regime("RELIANCE.NS")
print(f"Current regime: {result['regime_name']}")

# Analyze regime persistence
analysis = hmm_service.analyze_regime_persistence("RELIANCE.NS", "6mo")
print(f"Average duration in state 1: {analysis['regime_persistence']['state_1']['average_duration']} days")
```

### Advanced Usage
```python
# Train new model
train_result = hmm_service.train_model("RELIANCE.NS", period="2y", retrain=True)

# Get multiple predictions
tickers = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
predictions = hmm_service.get_multiple_regime_predictions(tickers)

# Evaluate model performance
evaluation = hmm_service.evaluate_model("RELIANCE.NS", "6mo")
```

---

**Note**: The HMM model operates independently from the main market regime classifier and provides a different perspective on market regimes based on statistical modeling of price movements and volatility patterns.