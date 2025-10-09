# LSTM Training - Quick Reference Card

## Installation
```bash
pip install -r requirements_training.txt
```

## Train Single Stock
```bash
python train_lstm_model.py
```

## Train Multiple Stocks
```bash
python train_multiple_stocks.py
```

## Change Stock Ticker
Edit `train_lstm_model.py`:
```python
TICKER = 'TCS.NS'  # Change this line
```

## Common Indian Stock Tickers
| Company | Ticker |
|---------|--------|
| Reliance Industries | RELIANCE.NS |
| TCS | TCS.NS |
| HDFC Bank | HDFCBANK.NS |
| Infosys | INFY.NS |
| ICICI Bank | ICICIBANK.NS |
| Wipro | WIPRO.NS |
| State Bank of India | SBIN.NS |
| Bharti Airtel | BHARTIARTL.NS |
| ITC | ITC.NS |
| Kotak Bank | KOTAKBANK.NS |

## Key Parameters Quick Change

### Data Period
```python
PERIOD = '5y'  # '1y', '2y', '5y', '10y', 'max'
```

### Training Duration
```python
EPOCHS = 100      # More = better, but slower
BATCH_SIZE = 32   # Larger = faster, but may overfit
```

### Model Size
```python
# Small model (fast)
LSTM_LAYERS = [
    {'units': 64, ...},
    {'units': 32, ...}
]

# Large model (accurate)
LSTM_LAYERS = [
    {'units': 256, ...},
    {'units': 128, ...},
    {'units': 64, ...}
]
```

### Prediction Range
```python
SEQUENCE_LENGTH = 60      # Days to look back
PREDICTION_HORIZON = 5    # Days to predict
```

## APIs Used

### 1. Yahoo Finance (yfinance)
```python
DATA_SOURCE = 'yfinance'
# No API key needed
# Free unlimited access
```

**API Endpoints:**
- Historical Data: `yf.Ticker(symbol).history(period='5y')`
- Real-time Data: `yf.Ticker(symbol).info`
- Multiple Stocks: `yf.download(['RELIANCE.NS', 'TCS.NS'])`

### 2. Alpha Vantage (Optional)
```python
DATA_SOURCE = 'alphavantage'
ALPHA_VANTAGE_API_KEY = 'YOUR_KEY'
```

**API Endpoint:**
```
https://www.alphavantage.co/query
  ?function=TIME_SERIES_DAILY
  &symbol=RELIANCE.NS
  &apikey=YOUR_KEY
  &outputsize=full
```

**Get Free API Key:** https://www.alphavantage.co/support/#api-key
**Limit:** 5 calls/minute, 500 calls/day (free tier)

## Data Fetching Examples

### Yahoo Finance
```python
import yfinance as yf

# Single stock
ticker = yf.Ticker('RELIANCE.NS')
df = ticker.history(period='5y')

# Date range
df = ticker.history(start='2020-01-01', end='2025-12-31')

# Multiple stocks
df = yf.download(['RELIANCE.NS', 'TCS.NS'], period='1y')
```

### Alpha Vantage
```python
import requests

url = f'https://www.alphavantage.co/query'
params = {
    'function': 'TIME_SERIES_DAILY',
    'symbol': 'RELIANCE.NS',
    'apikey': 'YOUR_KEY',
    'outputsize': 'full'
}

response = requests.get(url, params=params)
data = response.json()
```

## Technical Indicators API

All indicators are calculated automatically using:
```python
from lstm_model.technical_analysis_engine import technical_engine

df_with_indicators = technical_engine.calculate_all_indicators(df)
```

**Indicators Added:**
- 50+ technical indicators
- Price-based: SMA, EMA
- Momentum: RSI, MACD, Stochastic
- Volatility: Bollinger, ATR
- Volume: OBV, MFI
- Advanced: Ichimoku, Aroon

## Output Files

### Model Files
```
models/lstm/lstm_RELIANCE_NS_20251009.h5         # Trained model
models/lstm/lstm_RELIANCE_NS_20251009_scaler.pkl # Feature scaler
models/lstm/lstm_RELIANCE_NS_20251009_metadata.json  # Metadata
```

### Batch Training
```
batch_training_summary.csv  # Results for all stocks
```

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| No data | Check ticker symbol, add .NS for Indian stocks |
| Out of memory | Reduce BATCH_SIZE or LSTM units |
| Training slow | Increase BATCH_SIZE or reduce EPOCHS |
| Poor accuracy | More data, more epochs, tune hyperparameters |
| Import error | `pip install tensorflow yfinance pandas` |

## Performance Targets

| Metric | Target |
|--------|--------|
| MAPE | < 10% (Excellent), < 20% (Good) |
| Directional Accuracy | > 65% (Good), > 75% (Excellent) |
| Training Time | 10-20 min per stock (100 epochs) |

## Load Trained Model
```python
from tensorflow.keras.models import load_model
import pickle

# Load model
model = load_model('models/lstm/lstm_RELIANCE_NS_20251009.h5')

# Load scaler
with open('models/lstm/lstm_RELIANCE_NS_20251009_scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

# Make prediction
prediction = model.predict(X_new)
```

## Training Pipeline Flow
```
1. Fetch Data (yfinance/alphavantage)
   ↓
2. Feature Engineering (50+ indicators)
   ↓
3. Data Preparation (sequences, normalization)
   ↓
4. Train/Validation/Test Split
   ↓
5. Build LSTM Model
   ↓
6. Train with Callbacks
   ↓
7. Evaluate Performance
   ↓
8. Save Model + Metadata
```

## Common Configurations

### Quick Test
```python
PERIOD = '1y'
EPOCHS = 20
BATCH_SIZE = 64
```

### Production
```python
PERIOD = '5y'
EPOCHS = 100
BATCH_SIZE = 32
```

### High Accuracy
```python
PERIOD = '10y'
EPOCHS = 150
BATCH_SIZE = 32
LSTM_LAYERS = [256, 128, 64]
```

## Need Help?
1. Check LSTM_TRAINING_GUIDE.md for detailed documentation
2. Review IMPLEMENTATION_SUMMARY.md for system overview
3. Check training_configs/ for example configurations
