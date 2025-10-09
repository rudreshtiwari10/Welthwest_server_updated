# LSTM Model Training Guide

## Overview
Complete training pipeline for LSTM-based stock price prediction with 50+ technical indicators, configurable architecture, and comprehensive evaluation.

## Quick Start

### 1. Install Dependencies
```bash
pip install tensorflow yfinance pandas numpy scikit-learn matplotlib
```

### 2. Basic Training
```bash
python train_lstm_model.py
```

This will train an LSTM model for RELIANCE.NS with default settings.

### 3. Customize Training
Edit the `TrainingConfig` class in `train_lstm_model.py`:

```python
class TrainingConfig:
    TICKER = 'TCS.NS'          # Change stock ticker
    PERIOD = '5y'               # Change data period
    EPOCHS = 100                # Change training epochs
    BATCH_SIZE = 32             # Change batch size
    # ... more parameters
```

## Configuration Parameters

### Data Parameters
```python
# Stock Selection
TICKER = 'TCS.NS'          # Stock ticker symbol
DATA_SOURCE = 'yfinance'        # Data source ('yfinance' or 'alphavantage')

# Date Range
USE_PERIOD = True               # Use period instead of dates
PERIOD = '5y'                   # '1y', '2y', '5y', '10y', 'max'
# OR
START_DATE = '2020-01-01'
END_DATE = '2025-12-31'
```

### Model Architecture
```python
# Sequence Configuration
SEQUENCE_LENGTH = 60            # Days to look back (60 = ~3 months)
PREDICTION_HORIZON = 5          # Predict next N days

# LSTM Layers (3-layer architecture)
LSTM_LAYERS = [
    {'units': 128, 'return_sequences': True, 'dropout': 0.2},
    {'units': 64, 'return_sequences': True, 'dropout': 0.2},
    {'units': 32, 'return_sequences': False, 'dropout': 0.3}
]

# Dense Layers
DENSE_LAYERS = [
    {'units': 16, 'activation': 'relu', 'dropout': 0.3},
    {'units': PREDICTION_HORIZON, 'activation': 'linear'}
]
```

### Training Parameters
```python
BATCH_SIZE = 32                 # Training batch size
EPOCHS = 100                    # Maximum training epochs
VALIDATION_SPLIT = 0.2          # 20% for validation
LEARNING_RATE = 0.001          # Initial learning rate
OPTIMIZER = 'adam'              # 'adam', 'rmsprop', 'sgd'
LOSS = 'mse'                    # 'mse', 'mae', 'huber'
```

### Features Configuration
```python
USE_TECHNICAL_INDICATORS = True  # Use 50+ technical indicators
USE_PRICE_FEATURES = True        # OHLC data
USE_VOLUME_FEATURES = True       # Volume indicators
USE_RETURNS = True               # Price returns
USE_LOG_RETURNS = True           # Log returns
NORMALIZE_DATA = True            # MinMax normalization
```

### Callbacks
```python
# Early Stopping
USE_EARLY_STOPPING = True
EARLY_STOPPING_PATIENCE = 15     # Stop if no improvement for N epochs
EARLY_STOPPING_MIN_DELTA = 0.0001

# Learning Rate Reduction
USE_REDUCE_LR = True
REDUCE_LR_PATIENCE = 5
REDUCE_LR_FACTOR = 0.5
REDUCE_LR_MIN_LR = 1e-7

# Model Checkpointing
USE_MODEL_CHECKPOINT = True
CHECKPOINT_SAVE_BEST_ONLY = True
```

## Using Configuration Files

Pre-configured JSON files for different stocks:

### Train with Config File
```python
import json

# Load configuration
with open('training_configs/config_reliance.json', 'r') as f:
    config = json.load(f)

# Update TrainingConfig from JSON
TrainingConfig.TICKER = config['data']['ticker']
TrainingConfig.EPOCHS = config['training']['epochs']
# ... update other parameters

# Run training
main()
```

### Available Configs
1. **config_reliance.json** - Default configuration for RELIANCE.NS
2. **config_tcs.json** - Optimized for TCS.NS
3. **config_bank.json** - Optimized for banking stocks (larger model)

## Data Sources

### 1. Yahoo Finance (Default)
```python
DATA_SOURCE = 'yfinance'
TICKER = 'RELIANCE.NS'
```

**Advantages:**
- Free, no API key needed
- Extensive historical data
- Real-time quotes
- Wide coverage of Indian stocks

**Indian Stock Tickers:**
- `RELIANCE.NS` - Reliance Industries
- `TCS.NS` - Tata Consultancy Services
- `HDFCBANK.NS` - HDFC Bank
- `INFY.NS` - Infosys
- `ICICIBANK.NS` - ICICI Bank

### 2. Alpha Vantage
```python
DATA_SOURCE = 'alphavantage'
ALPHA_VANTAGE_API_KEY = 'YOUR_KEY_HERE'
```

**Get API Key:**
https://www.alphavantage.co/support/#api-key

## Technical Indicators Used

The training pipeline automatically calculates 50+ technical indicators:

### Price-Based
- SMA: 5, 10, 20, 50, 200
- EMA: 5, 12, 26, 50

### Momentum
- RSI: 14, 21
- MACD (line, signal, histogram)
- Stochastic Oscillator (K, D)
- Williams %R
- CCI (Commodity Channel Index)

### Volatility
- Bollinger Bands (upper, lower, width)
- ATR: 14, 21
- Donchian Channels

### Volume
- Volume SMA & Ratio
- OBV (On-Balance Volume)
- Volume Price Trend
- Accumulation/Distribution
- Money Flow Index

### Advanced
- Ichimoku Cloud (Tenkan, Kijun, Senkou A)
- Parabolic SAR
- Aroon Indicator

## Training Output

### Files Created
```
models/lstm/
├── lstm_RELIANCE_NS_20251009.h5              # Trained model
├── lstm_RELIANCE_NS_20251009_scaler.pkl      # Feature scaler
├── lstm_RELIANCE_NS_20251009_metadata.json   # Model metadata
├── lstm_RELIANCE_NS_20251009_history.pkl     # Training history
└── lstm_RELIANCE_NS_20251009_checkpoint.h5   # Best checkpoint
```

### Metadata Format
```json
{
  "ticker": "RELIANCE.NS",
  "sequence_length": 60,
  "prediction_horizon": 5,
  "features": ["Open", "High", "Low", "Close", "Volume", ...],
  "metrics": {
    "mae": 45.32,
    "rmse": 67.89,
    "mape": 2.34,
    "directional_accuracy": 72.45
  },
  "training_date": "2025-10-09T12:00:00",
  "config": {...}
}
```

## Model Evaluation Metrics

### 1. MAE (Mean Absolute Error)
Average absolute difference between predicted and actual prices.
- **Lower is better**
- Measured in price units (e.g., ₹45.32)

### 2. RMSE (Root Mean Squared Error)
Standard deviation of prediction errors.
- **Lower is better**
- Penalizes large errors more than MAE

### 3. MAPE (Mean Absolute Percentage Error)
Average percentage error.
- **Lower is better**
- **Good:** < 10%
- **Acceptable:** 10-20%
- **Poor:** > 20%

### 4. Directional Accuracy
Percentage of correct price direction predictions.
- **Higher is better**
- **Good:** > 65%
- **Excellent:** > 75%

## Training Best Practices

### 1. Data Quality
- Use at least 2-3 years of historical data
- More data = better generalization
- 5 years recommended for stable models

### 2. Sequence Length
- **Short (20-30):** Day trading, quick patterns
- **Medium (60-90):** Swing trading (recommended)
- **Long (120+):** Long-term trends

### 3. Batch Size
- **Small (16-32):** Better generalization, slower training
- **Large (64-128):** Faster training, may overfit

### 4. Epochs
- Start with 100 epochs
- Use early stopping to prevent overfitting
- Monitor validation loss

### 5. Learning Rate
- **High (0.01):** Fast convergence, may overshoot
- **Medium (0.001):** Balanced (recommended)
- **Low (0.0001):** Slow but stable

### 6. Preventing Overfitting
- Use dropout (0.2-0.3)
- Enable early stopping
- Use validation data
- Don't train too long

## Example Training Sessions

### 1. Quick Test (Fast Training)
```python
TICKER = 'RELIANCE.NS'
PERIOD = '1y'
EPOCHS = 20
BATCH_SIZE = 64
SEQUENCE_LENGTH = 30
```

### 2. Production Model (Recommended)
```python
TICKER = 'RELIANCE.NS'
PERIOD = '5y'
EPOCHS = 100
BATCH_SIZE = 32
SEQUENCE_LENGTH = 60
USE_EARLY_STOPPING = True
```

### 3. Large-Cap Bank Stock
```python
TICKER = 'HDFCBANK.NS'
PERIOD = '5y'
EPOCHS = 150
BATCH_SIZE = 64
SEQUENCE_LENGTH = 90
LSTM_LAYERS = [
    {'units': 256, ...},
    {'units': 128, ...},
    {'units': 64, ...}
]
```

### 4. IT Sector Stock
```python
TICKER = 'TCS.NS'
PERIOD = '5y'
EPOCHS = 100
BATCH_SIZE = 32
LEARNING_RATE = 0.001
```

## Troubleshooting

### Issue: "No module named 'tensorflow'"
```bash
pip install tensorflow
```

### Issue: "No data returned for ticker"
- Check ticker symbol (must include .NS for Indian stocks)
- Verify internet connection
- Try different data source

### Issue: "Out of memory"
- Reduce batch size
- Reduce LSTM units
- Reduce sequence length
- Set GPU_MEMORY_LIMIT

### Issue: "Model not improving"
- Increase epochs
- Adjust learning rate
- Try different optimizer
- Add more features
- Check data quality

### Issue: "Training too slow"
- Increase batch size
- Reduce sequence length
- Use GPU (if available)
- Reduce number of features

## GPU Acceleration

### TensorFlow GPU Setup
```bash
# Install CUDA-enabled TensorFlow
pip install tensorflow-gpu

# Verify GPU
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

### Set GPU Memory Limit
```python
GPU_MEMORY_LIMIT = 4096  # MB
```

## Advanced Usage

### Custom Model Architecture
```python
# 4-layer deep LSTM
LSTM_LAYERS = [
    {'units': 256, 'return_sequences': True, 'dropout': 0.2},
    {'units': 128, 'return_sequences': True, 'dropout': 0.2},
    {'units': 64, 'return_sequences': True, 'dropout': 0.2},
    {'units': 32, 'return_sequences': False, 'dropout': 0.3}
]
```

### Multiple Prediction Horizons
```python
# Predict next 10 days
PREDICTION_HORIZON = 10
DENSE_LAYERS[-1]['units'] = 10
```

### Custom Loss Function
```python
# Huber loss (robust to outliers)
LOSS = 'huber'

# Or custom
from tensorflow.keras.losses import Huber
LOSS = Huber(delta=1.0)
```

## Loading Trained Model

```python
from tensorflow.keras.models import load_model
import pickle

# Load model
model = load_model('models/lstm/lstm_RELIANCE_NS_20251009.h5')

# Load scaler
with open('models/lstm/lstm_RELIANCE_NS_20251009_scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

# Load metadata
with open('models/lstm/lstm_RELIANCE_NS_20251009_metadata.json', 'r') as f:
    metadata = json.load(f)

# Make predictions
predictions = model.predict(X_new)
```

## Integration with Forecast Service

After training, integrate with the forecast service:

```python
# In lstm_model/lstm_service.py
from tensorflow.keras.models import load_model

class LSTMService:
    def load_trained_model(self, ticker):
        model_path = f'models/lstm/lstm_{ticker.replace(".", "_")}_latest.h5'
        self.model = load_model(model_path)
        # Load scaler and metadata
        ...
```

## Next Steps

1. **Train your first model:** Run with default settings
2. **Evaluate results:** Check metrics and plots
3. **Optimize:** Adjust hyperparameters based on performance
4. **Deploy:** Integrate trained model with forecast service
5. **Monitor:** Track real-world prediction accuracy
6. **Retrain:** Update model monthly with new data

## Support

For issues or questions:
- Check troubleshooting section
- Review configuration examples
- Verify data source connectivity
- Check TensorFlow installation

## Performance Benchmarks

Expected performance for well-trained models:

| Metric | Good | Excellent |
|--------|------|-----------|
| MAPE | < 10% | < 5% |
| Directional Accuracy | > 65% | > 75% |
| Training Time (100 epochs) | 10-20 min | 5-10 min |

*Varies by stock volatility, data size, and hardware*
