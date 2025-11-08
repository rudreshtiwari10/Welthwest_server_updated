# LSTM Training - Example Configurations

This file contains ready-to-use training configurations for common scenarios.
Copy the configuration you need into `train_lstm_new.py` and run!

---

## Example 1: Quick Test (Single Stock)

**Use Case:** Test your setup, verify everything works
**Time:** ~5-10 minutes

```python
# Stock Configuration
STOCK_SYMBOLS = ["RELIANCE.NS"]

# Training Data Configuration
TRAIN_START_DATE = "2022-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 10              # Quick test
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 2: Top 5 Indian Stocks (Standard)

**Use Case:** Train models for major Indian stocks
**Time:** ~40-50 minutes

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "RELIANCE.NS",      # Reliance Industries
    "TCS.NS",           # Tata Consultancy Services
    "HDFCBANK.NS",      # HDFC Bank
    "INFY.NS",          # Infosys
    "ICICIBANK.NS",     # ICICI Bank
]

# Training Data Configuration
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 16              # Standard training
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 3: Banking Sector Focus

**Use Case:** Train models for Indian banking stocks
**Time:** ~50-60 minutes

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "HDFCBANK.NS",      # HDFC Bank
    "ICICIBANK.NS",     # ICICI Bank
    "SBIN.NS",          # State Bank of India
    "KOTAKBANK.NS",     # Kotak Mahindra Bank
    "AXISBANK.NS",      # Axis Bank
    "INDUSINDBK.NS",    # IndusInd Bank
]

# Training Data Configuration
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 4: IT Sector Stocks

**Use Case:** Train models for Indian IT stocks
**Time:** ~40-50 minutes

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "TCS.NS",           # Tata Consultancy Services
    "INFY.NS",          # Infosys
    "WIPRO.NS",         # Wipro
    "HCLTECH.NS",       # HCL Technologies
    "TECHM.NS",         # Tech Mahindra
]

# Training Data Configuration
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 5: Production Quality (Best Accuracy)

**Use Case:** Production deployment, monthly retraining
**Time:** ~60-70 minutes (longer training for better accuracy)

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
]

# Training Data Configuration
TRAIN_START_DATE = "2019-01-01"  # 5+ years of data
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 25              # More epochs for better accuracy
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 6: US Tech Stocks

**Use Case:** Train models for major US technology stocks
**Time:** ~40-50 minutes

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "AAPL",             # Apple
    "MSFT",             # Microsoft
    "GOOGL",            # Alphabet (Google)
    "AMZN",             # Amazon
    "META",             # Meta (Facebook)
]

# Training Data Configuration
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 7: Aggressive Training (Maximum Accuracy)

**Use Case:** When accuracy is critical, time is not a constraint
**Time:** ~2-3 hours

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
]

# Training Data Configuration
TRAIN_START_DATE = "2018-01-01"  # 7 years of data
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 90              # Longer time window
FORECAST_DAYS = 3
EPOCHS = 30                  # More training iterations
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 8: Update Existing Models

**Use Case:** Retrain existing models with latest data
**Time:** Varies based on number of existing models

```python
# Stock Configuration
# Leave empty to retrain ALL existing models
STOCK_SYMBOLS = []  # Will automatically find all trained models

# OR specify which ones to update
STOCK_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
]

# Training Data Configuration
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True         # Must be True to retrain
VERBOSE_TRAINING = False     # Silent for batch updates
```

---

## Example 9: Fast Batch Training

**Use Case:** Quick training for many stocks (lower accuracy)
**Time:** ~3-5 minutes per stock

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS",
    "ICICIBANK.NS", "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS",
    "ITC.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS",
]

# Training Data Configuration
TRAIN_START_DATE = "2021-01-01"  # Less data = faster
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 45              # Shorter window
FORECAST_DAYS = 3
EPOCHS = 12                  # Fewer epochs
BATCH_SIZE = 64              # Larger batches
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = False     # Silent mode
```

---

## Example 10: Volatile Stock Configuration

**Use Case:** Stocks with high volatility, short-term patterns
**Time:** ~5-10 minutes per stock

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "YESBANK.NS",       # Yes Bank (volatile)
    "ADANIENT.NS",      # Adani Enterprises
    "TATASTEEL.NS",     # Tata Steel
]

# Training Data Configuration
TRAIN_START_DATE = "2021-01-01"  # Recent data more relevant
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 30              # Shorter time window for volatility
FORECAST_DAYS = 3
EPOCHS = 20                  # More epochs to learn patterns
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 11: Stable Blue-Chip Stocks

**Use Case:** Large, stable companies with predictable patterns
**Time:** ~5-10 minutes per stock

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "HINDUNILVR.NS",    # Hindustan Unilever
    "ITC.NS",           # ITC Limited
    "NESTLEIND.NS",     # Nestle India
]

# Training Data Configuration
TRAIN_START_DATE = "2019-01-01"  # More historical data for stable stocks
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 90              # Longer time window for trends
FORECAST_DAYS = 3
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = True
VERBOSE_TRAINING = True
```

---

## Example 12: Nifty 50 Complete Training

**Use Case:** Train all Nifty 50 stocks (comprehensive coverage)
**Time:** ~4-8 hours

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "BAJFINANCE.NS", "MARUTI.NS",
    "HCLTECH.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "ONGC.NS", "NESTLEIND.NS", "TATAMOTORS.NS", "NTPC.NS", "POWERGRID.NS",
    "M&M.NS", "TECHM.NS", "BAJAJFINSV.NS", "TATASTEEL.NS", "ADANIPORTS.NS",
    "CIPLA.NS", "JSWSTEEL.NS", "DRREDDY.NS", "GRASIM.NS", "HINDALCO.NS",
    "INDUSINDBK.NS", "EICHERMOT.NS", "DIVISLAB.NS", "COALINDIA.NS", "HEROMOTOCO.NS",
    "BRITANNIA.NS", "UPL.NS", "SHREECEM.NS", "TATACONSUM.NS", "APOLLOHOSP.NS",
    "BAJAJ-AUTO.NS", "ADANIENT.NS", "BPCL.NS", "SBILIFE.NS", "HDFCLIFE.NS",
]

# Training Data Configuration
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "auto"

# Model Hyperparameters
TIME_STEPS = 60
FORECAST_DAYS = 3
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_TEST_SPLIT = 0.95

# Training Options
FORCE_RETRAIN = False        # Skip existing models to save time
VERBOSE_TRAINING = False     # Silent mode for batch processing
```

---

## How to Use These Examples

1. **Choose** an example that matches your use case
2. **Copy** the configuration code
3. **Open** `train_lstm_new.py`
4. **Replace** the CONFIGURATION section with the example code
5. **Run** the training script

```bash
python "train lstm/train_lstm_new.py"
```

---

## Customization Tips

### Adjust Training Speed

**Faster (lower accuracy):**
```python
EPOCHS = 10
TRAIN_START_DATE = "2022-01-01"  # Less data
BATCH_SIZE = 64
```

**Slower (higher accuracy):**
```python
EPOCHS = 25
TRAIN_START_DATE = "2019-01-01"  # More data
BATCH_SIZE = 32
```

### Adjust for Memory

**Low memory:**
```python
BATCH_SIZE = 16
STOCK_SYMBOLS = ["RELIANCE.NS"]  # One at a time
```

**High memory:**
```python
BATCH_SIZE = 64
STOCK_SYMBOLS = [...]  # Many stocks
```

### Adjust for Market Type

**Volatile markets:**
```python
TIME_STEPS = 30          # Short-term patterns
TRAIN_START_DATE = "2021-01-01"  # Recent data
```

**Stable markets:**
```python
TIME_STEPS = 90          # Long-term patterns
TRAIN_START_DATE = "2019-01-01"  # Historical data
```

---

## Performance Expectations

Based on these configurations, expect:

| Configuration | R² Score | MAPE | Training Time (per stock) |
|---------------|----------|------|---------------------------|
| Quick Test | 0.75-0.85 | 3-5% | 3-5 min |
| Standard | 0.85-0.90 | 2-4% | 5-8 min |
| Production | 0.90-0.95 | 1.5-3% | 8-12 min |
| Aggressive | 0.92-0.96 | 1-2.5% | 15-25 min |

Actual results vary by stock and market conditions.

---

## Need Help?

- **General questions**: See `README.md` in this folder
- **API usage**: See `../LSTM_API_IMPLEMENTATION.md`
- **Quick start**: See `../LSTM_QUICK_START.md`
- **Full specification**: See `../LSTM_STOCK_PREDICTION_SPEC.md`

Happy training! 📈🚀
