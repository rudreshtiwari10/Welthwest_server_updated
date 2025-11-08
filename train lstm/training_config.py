"""
LSTM Training Configuration File
=================================

Edit this file to configure your LSTM model training.
This configuration is used by train_lstm_new.py

You can create multiple configuration files for different training scenarios.
Example: training_config_aggressive.py, training_config_conservative.py
"""

# ============================================
# STOCK SELECTION
# ============================================

# List of stock symbols to train
# Format: "SYMBOL.EXCHANGE" (e.g., "RELIANCE.NS" for Indian stocks, "AAPL" for US stocks)

# Indian Stocks (NSE)
INDIAN_NIFTY50 = [
    "RELIANCE.NS",      # Reliance Industries
    "TCS.NS",           # Tata Consultancy Services
    "HDFCBANK.NS",      # HDFC Bank
    "INFY.NS",          # Infosys
    "ICICIBANK.NS",     # ICICI Bank
    "HINDUNILVR.NS",    # Hindustan Unilever
    "SBIN.NS",          # State Bank of India
    "BHARTIARTL.NS",    # Bharti Airtel
    "ITC.NS",           # ITC Limited
    "KOTAKBANK.NS",     # Kotak Mahindra Bank
]

INDIAN_BANKING = [
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "INDUSINDBK.NS",
]

INDIAN_IT = [
    "TCS.NS",
    "INFY.NS",
    "WIPRO.NS",
    "HCLTECH.NS",
    "TECHM.NS",
]

INDIAN_PHARMA = [
    "SUNPHARMA.NS",
    "DRREDDY.NS",
    "CIPLA.NS",
    "DIVISLAB.NS",
]

# US Stocks (NASDAQ/NYSE)
US_TECH = [
    "AAPL",    # Apple
    "MSFT",    # Microsoft
    "GOOGL",   # Alphabet
    "AMZN",    # Amazon
    "META",    # Meta (Facebook)
    "NVDA",    # NVIDIA
    "TSLA",    # Tesla
]

US_FINANCE = [
    "JPM",     # JPMorgan Chase
    "BAC",     # Bank of America
    "WFC",     # Wells Fargo
    "GS",      # Goldman Sachs
]

# Select which stocks to train (choose one of the above lists or create your own)
STOCK_SYMBOLS = [
    "RELIANCE.NS",
    # Add more symbols here...
]

# You can also use predefined lists:
# STOCK_SYMBOLS = INDIAN_NIFTY50
# STOCK_SYMBOLS = INDIAN_BANKING
# STOCK_SYMBOLS = INDIAN_IT
# STOCK_SYMBOLS = US_TECH

# ============================================
# TRAINING DATA PERIOD
# ============================================

# Start date for training data
# More historical data generally improves model accuracy
# Recommended: At least 3-5 years of data
TRAIN_START_DATE = "2020-01-01"  # Format: YYYY-MM-DD

# End date for training data
# Use "auto" for yesterday's date (recommended for latest data)
# Or specify exact date like "2025-11-05"
TRAIN_END_DATE = "auto"

# ============================================
# MODEL HYPERPARAMETERS
# ============================================

# Number of days the model looks back to make predictions
# Default: 60 days
# Range: 10-200
# Lower values: Faster training, may miss long-term patterns
# Higher values: Slower training, captures longer trends
TIME_STEPS = 60

# Number of days to predict into the future
# Default: 3 days
# Note: Accuracy decreases significantly beyond 3 days
FORECAST_DAYS = 3

# Number of training epochs
# Default: 16-25
# Range: 1-100
# Lower values: Faster training, may underfit
# Higher values: Better training, but longer time and risk of overfitting
# Recommended: 16 for quick tests, 25 for production
EPOCHS = 16

# Training batch size
# Default: 32
# Range: 1-256
# Lower values: More memory efficient, slower, noisier training
# Higher values: Faster training, requires more memory
BATCH_SIZE = 32

# Train-test split ratio
# Default: 0.95 (95% for training, 5% for testing)
# Range: 0.8-0.99
TRAIN_TEST_SPLIT = 0.95

# ============================================
# TRAINING OPTIONS
# ============================================

# Force retrain even if model already exists
# True: Always retrain (overwrites existing models)
# False: Skip training if model exists
FORCE_RETRAIN = True

# Show detailed training progress
# True: Shows epoch-by-epoch progress
# False: Silent training (faster for batch jobs)
VERBOSE_TRAINING = True

# ============================================
# DIRECTORY CONFIGURATION
# ============================================

# Directories for storing model files
# Leave as default unless you have specific requirements
MODEL_DIR = "./lstm_model/models"
SCALER_DIR = "./lstm_model/scalers"
METADATA_DIR = "./lstm_model/metadata"

# ============================================
# OUTPUT OPTIONS
# ============================================

# Save training summary to CSV file
SAVE_TRAINING_SUMMARY = True

# CSV filename for training summary
SUMMARY_FILE = "lstm_training_summary.csv"

# ============================================
# PRESET CONFIGURATIONS
# ============================================

# Uncomment one of these to use preset configurations

# Quick Test Configuration (fast training for testing)
"""
EPOCHS = 10
BATCH_SIZE = 64
TRAIN_START_DATE = "2022-01-01"
STOCK_SYMBOLS = ["RELIANCE.NS"]
"""

# Standard Configuration (balanced speed and accuracy)
"""
EPOCHS = 16
BATCH_SIZE = 32
TRAIN_START_DATE = "2020-01-01"
TIME_STEPS = 60
"""

# Production Configuration (best accuracy, slower)
"""
EPOCHS = 25
BATCH_SIZE = 32
TRAIN_START_DATE = "2019-01-01"
TIME_STEPS = 60
FORCE_RETRAIN = False
"""

# Aggressive Configuration (more data, more training)
"""
EPOCHS = 30
BATCH_SIZE = 32
TRAIN_START_DATE = "2018-01-01"
TIME_STEPS = 90
"""

# ============================================
# VALIDATION RULES
# ============================================

# Do not edit this section
def validate_config():
    """Validate configuration values"""
    errors = []

    if not STOCK_SYMBOLS:
        errors.append("STOCK_SYMBOLS cannot be empty")

    if EPOCHS < 1 or EPOCHS > 100:
        errors.append("EPOCHS must be between 1 and 100")

    if BATCH_SIZE < 1 or BATCH_SIZE > 256:
        errors.append("BATCH_SIZE must be between 1 and 256")

    if TIME_STEPS < 10 or TIME_STEPS > 200:
        errors.append("TIME_STEPS must be between 10 and 200")

    if TRAIN_TEST_SPLIT < 0.8 or TRAIN_TEST_SPLIT > 0.99:
        errors.append("TRAIN_TEST_SPLIT must be between 0.8 and 0.99")

    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

    return True

# ============================================
# NOTES AND TIPS
# ============================================

"""
TRAINING TIPS:

1. Start Small:
   - Begin with 1-2 stocks to test your setup
   - Use EPOCHS=10 for quick tests
   - Once satisfied, scale up to more stocks

2. Data Quality:
   - Use at least 3 years of historical data
   - More data usually means better predictions
   - Very old data may not be relevant for current market

3. Epochs:
   - 10 epochs: Quick test
   - 16 epochs: Good balance
   - 25+ epochs: Production quality
   - More doesn't always mean better (overfitting risk)

4. Time Steps:
   - 60 days: Standard, works well for most stocks
   - 30 days: For volatile stocks with short-term patterns
   - 90+ days: For stable stocks with long-term trends

5. Batch Training:
   - Training multiple stocks takes time (5-10 min per stock)
   - Run overnight for large batches
   - Use FORCE_RETRAIN=False to avoid retraining existing models

6. Retraining:
   - Retrain monthly for best accuracy
   - Market conditions change, models need fresh data
   - Set up a cron job for automated monthly retraining

7. Performance Metrics:
   - MAE (Mean Absolute Error): Lower is better
   - RMSE (Root Mean Squared Error): Lower is better
   - R² (R-squared): Closer to 1.0 is better (0.9+ is excellent)
   - MAPE (Mean Absolute Percentage Error): Lower is better

8. Stock Selection:
   - Liquid stocks: Better predictions (high trading volume)
   - Stable stocks: More predictable patterns
   - Avoid penny stocks: Too volatile for LSTM

TROUBLESHOOTING:

- "No data available": Check stock symbol format (add .NS for Indian stocks)
- "Insufficient data": Increase training period or reduce TIME_STEPS
- Training too slow: Reduce EPOCHS or use GPU
- Poor accuracy: Try more data, more epochs, or different TIME_STEPS
- Out of memory: Reduce BATCH_SIZE
"""
