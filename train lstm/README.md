# LSTM Model Training - Quick Guide

This folder contains everything you need to train LSTM stock prediction models.

## Files

- **`train_lstm_new.py`** - Main training script (standalone, easy to use)
- **`training_config.py`** - Configuration file with all settings
- **`TRAINING_QUICK_REFERENCE.md`** - Quick reference guide

## Quick Start

### Method 1: Edit Configuration Directly

1. Open `train_lstm_new.py`
2. Edit the `CONFIGURATION` section at the top:

```python
# Stock Configuration
STOCK_SYMBOLS = [
    "RELIANCE.NS",      # Add your stocks here
]

# Training Settings
EPOCHS = 16              # Number of training epochs
BATCH_SIZE = 32         # Batch size
TIME_STEPS = 60         # Days to look back
TRAIN_START_DATE = "2020-01-01"  # Start date
```

3. Run the training:

```bash
python "train lstm/train_lstm_new.py"
```

### Method 2: Use Configuration File

1. Edit `training_config.py` to customize settings
2. Import and use in your own scripts
3. Useful for managing multiple training configurations

## Training Your First Model

### Step 1: Choose Your Stocks

Indian stocks (NSE):
```python
STOCK_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
]
```

US stocks:
```python
STOCK_SYMBOLS = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
]
```

### Step 2: Configure Training

**Quick Test** (for testing setup):
```python
EPOCHS = 10
TRAIN_START_DATE = "2022-01-01"
STOCK_SYMBOLS = ["RELIANCE.NS"]  # Just one stock
```

**Standard Training** (recommended):
```python
EPOCHS = 16
TRAIN_START_DATE = "2020-01-01"
TIME_STEPS = 60
```

**Production Quality** (best accuracy):
```python
EPOCHS = 25
TRAIN_START_DATE = "2019-01-01"
TIME_STEPS = 60
```

### Step 3: Run Training

```bash
cd "C:\Users\Kunal Kumar\Desktop\WelthWest\Trials\WelthWest_payment\Welthwest_server_updated"
python "train lstm/train_lstm_new.py"
```

The script will:
- ✅ Show configuration summary
- ✅ Ask for confirmation
- ✅ Train each stock (5-10 min per stock)
- ✅ Show progress and results
- ✅ Save models automatically
- ✅ Generate training summary CSV

## Training Output

### Console Output

```
================================================================================
                    LSTM MODEL TRAINING SESSION
================================================================================

Session started at: 2025-11-06 14:30:00
Number of stocks to train: 1
Training period: 2020-01-01 to auto
Epochs: 16 | Batch Size: 32 | Time Steps: 60
================================================================================

--------------------------------------------------------------------------------
[1/1] Training: RELIANCE.NS
--------------------------------------------------------------------------------
Fetching training data for RELIANCE.NS...
✅ Data fetched successfully!
   Total records: 1234
Preparing training data...
✅ Training data prepared: (1174, 60, 1)
Building LSTM model...
Training model with 16 epochs...
✅ Training complete!

✅ Training successful for RELIANCE.NS
   Duration: 382 seconds
   Model Performance:
      MAE:  12.45
      RMSE: 18.32
      R²:   0.9234
      MAPE: 2.15%
   Training Samples: 1174
   Test Samples: 60
   Last Training Price: ₹2845.50
```

### Files Created

After training, you'll find:

```
lstm_model/
├── models/
│   └── lstm_reliance_ns.keras          (5-10 MB)
├── scalers/
│   └── scaler_reliance_ns.pkl          (few KB)
└── metadata/
    └── reliance_ns.json                (metadata)

lstm_training_summary.csv               (training log)
```

## Configuration Options

### Stock Symbols

```python
# Single stock
STOCK_SYMBOLS = ["RELIANCE.NS"]

# Multiple stocks
STOCK_SYMBOLS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
]

# Use preset lists (from training_config.py)
from training_config import INDIAN_BANKING
STOCK_SYMBOLS = INDIAN_BANKING
```

### Training Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `EPOCHS` | 16 | 1-100 | Training iterations (more = better but slower) |
| `BATCH_SIZE` | 32 | 1-256 | Batch size (higher = faster, more memory) |
| `TIME_STEPS` | 60 | 10-200 | Days to look back (60 = 2 months) |
| `TRAIN_START_DATE` | "2020-01-01" | Any date | Start of training data |
| `TRAIN_END_DATE` | "auto" | Date or "auto" | End of training data (auto = yesterday) |

### Training Options

```python
FORCE_RETRAIN = True     # Retrain even if model exists
VERBOSE_TRAINING = True  # Show detailed progress
SAVE_TRAINING_SUMMARY = True  # Save CSV summary
```

## Understanding Model Performance

### Metrics Explained

**MAE (Mean Absolute Error)**
- Average prediction error in rupees
- Lower is better
- Example: MAE of 12.45 means average error of ₹12.45

**RMSE (Root Mean Squared Error)**
- Similar to MAE but penalizes large errors more
- Lower is better

**R² (R-squared)**
- Measures how well model fits data
- Range: 0 to 1
- 0.9+ = Excellent
- 0.8-0.9 = Good
- <0.8 = May need improvement

**MAPE (Mean Absolute Percentage Error)**
- Percentage error
- Lower is better
- Example: 2.15% means average 2.15% error

### What's Good Performance?

For stock prediction:
- R² > 0.85 = Very good
- MAPE < 5% = Good accuracy
- MAE < 3% of stock price = Acceptable

Example:
```
Stock price: ₹2000
MAE: 40 (2% of price) ✅ Good
MAPE: 3.5% ✅ Good
R²: 0.89 ✅ Very good
```

## Training Tips

### 1. Start Small

Begin with one stock to test:
```python
STOCK_SYMBOLS = ["RELIANCE.NS"]
EPOCHS = 10  # Quick test
```

### 2. Increase Gradually

Once satisfied, add more:
```python
STOCK_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
EPOCHS = 16  # Standard
```

### 3. Production Training

For best accuracy:
```python
STOCK_SYMBOLS = [...your list...]
EPOCHS = 25
TRAIN_START_DATE = "2019-01-01"  # 5+ years of data
```

### 4. Batch Training

Training multiple stocks takes time:
- 1 stock: ~5-10 minutes
- 10 stocks: ~50-100 minutes
- Run overnight for large batches

### 5. Retraining Schedule

- **Weekly**: Active trading stocks
- **Monthly**: Most stocks (recommended)
- **Quarterly**: Stable, long-term stocks

Set `FORCE_RETRAIN = True` to retrain existing models.

## Troubleshooting

### "No data available for stock XYZ"

**Problem:** Invalid stock symbol or no data
**Solution:**
- Check symbol format (Indian stocks need `.NS` suffix)
- Verify stock is actively traded
- Try different date range

### "Insufficient data points"

**Problem:** Not enough historical data
**Solution:**
- Use earlier start date: `TRAIN_START_DATE = "2019-01-01"`
- Reduce TIME_STEPS: `TIME_STEPS = 30`

### "Training is very slow"

**Problem:** Large dataset or many epochs
**Solution:**
- Reduce epochs: `EPOCHS = 10`
- Increase batch size: `BATCH_SIZE = 64`
- Use GPU if available
- Reduce training period

### "Out of memory error"

**Problem:** Not enough RAM
**Solution:**
- Reduce batch size: `BATCH_SIZE = 16`
- Train fewer stocks at once
- Close other applications

### "Model already exists"

**Problem:** Model trained previously
**Solution:**
- Set `FORCE_RETRAIN = True` to retrain
- Or set `FORCE_RETRAIN = False` to skip

## Advanced Usage

### Custom Training Script

```python
from services.lstm_training_service import LSTMTrainingService

# Initialize service
trainer = LSTMTrainingService(
    model_dir="./lstm_model/models",
    scaler_dir="./lstm_model/scalers",
    metadata_dir="./lstm_model/metadata"
)

# Train a model
result = trainer.train_model(
    stock_symbol="RELIANCE.NS",
    train_start="2020-01-01",
    train_end="auto",
    time_steps=60,
    epochs=16,
    batch_size=32,
    force_retrain=True
)

print(result)
```

### Batch Training from CSV

Create `stocks_to_train.csv`:
```csv
symbol,epochs,start_date
RELIANCE.NS,16,2020-01-01
TCS.NS,16,2020-01-01
INFY.NS,16,2020-01-01
```

Then train from file:
```python
import pandas as pd

df = pd.read_csv('stocks_to_train.csv')
for _, row in df.iterrows():
    # Train each stock...
```

## Next Steps

After training models:

1. **Test Predictions**
   ```bash
   curl -X POST http://localhost:8000/api/lstm/predict \
     -H "Content-Type: application/json" \
     -d '{"stock_symbol": "RELIANCE.NS"}'
   ```

2. **Check Model List**
   ```bash
   curl -X GET http://localhost:8000/api/lstm/models \
     -H "X-Admin-API-Key: your-key"
   ```

3. **Integrate with Frontend**
   - Use `/api/lstm/predict` endpoint
   - Display predictions to users
   - Show confidence levels

4. **Schedule Retraining**
   - Set up cron job for monthly retraining
   - Monitor model performance
   - Update models with fresh data

## Summary CSV

Training summary is saved to `lstm_training_summary.csv`:

| Column | Description |
|--------|-------------|
| timestamp | When training completed |
| stock_symbol | Stock symbol |
| status | SUCCESS or FAILED |
| duration_seconds | Training time |
| mae | Mean Absolute Error |
| rmse | Root Mean Squared Error |
| r2 | R-squared score |
| mape | Mean Absolute Percentage Error |
| training_samples | Number of training samples |
| epochs | Epochs used |
| error | Error message if failed |

Use this to track training history and model performance over time.

## Support

For more information:
- **API Documentation**: `../LSTM_API_IMPLEMENTATION.md`
- **Quick Start**: `../LSTM_QUICK_START.md`
- **Specification**: `../LSTM_STOCK_PREDICTION_SPEC.md`

Happy training! 🚀📈
