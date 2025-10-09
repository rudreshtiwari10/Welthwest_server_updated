"""
Standalone LSTM Training Script
Trains the LSTM model without running the server
"""
import os
import sys

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

print("=" * 70)
print("LSTM Model Training - Standalone")
print("=" * 70)

# Import after setting environment
from lstm_model import lstm_service

def train_lstm(ticker="RVNL.NS", period="2y", epochs=50, batch_size=20):
    """Train LSTM model"""
    print(f"\nTraining Configuration:")
    print(f"  Ticker: {ticker}")
    print(f"  Period: {period}")
    print(f"  Epochs: {epochs}")
    print(f"  Batch Size: {batch_size}")
    print("\n" + "=" * 70)
    print("Starting training... This will take 5-10 minutes.")
    print("Please do not interrupt the process.")
    print("=" * 70 + "\n")

    result = lstm_service.train_model(
        ticker=ticker,
        period=period,
        epochs=epochs,
        batch_size=batch_size,
        retrain=True
    )

    print("\n" + "=" * 70)
    if result.get("status") == "success":
        print("✓ LSTM Model Training Completed Successfully!")
        print("=" * 70)
        print(f"\nTraining Results:")
        print(f"  Training Loss: {result.get('training_loss', 0):.6f}")
        print(f"  Validation Loss: {result.get('validation_loss', 0):.6f}")
        print(f"  Mean Absolute Error: {result.get('mean_absolute_error', 0):.6f}")
        print(f"  Epochs Trained: {result.get('epochs_trained', 0)}")
        print(f"  Training Samples: {result.get('training_samples', 0)}")
        print(f"\nModel Configuration:")
        print(f"  Lookback Period: {result.get('lookback_period', 0)} days")
        print(f"  Forecast Days: {result.get('forecast_days', 0)}")
        print("\n✓ Model saved successfully!")
        print("✓ You can now use the LSTM prediction endpoints")
    else:
        print("✗ LSTM Model Training Failed")
        print("=" * 70)
        print(f"Error: {result.get('message', 'Unknown error')}")
        return False

    print("\n" + "=" * 70)
    return True

if __name__ == "__main__":
    # Parse command line arguments
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RVNL.NS"
    period = sys.argv[2] if len(sys.argv) > 2 else "2y"
    epochs = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    batch_size = int(sys.argv[4]) if len(sys.argv) > 4 else 20

    success = train_lstm(ticker, period, epochs, batch_size)

    if success:
        print("\n✓ All done! Start your server and test the predictions.")
        sys.exit(0)
    else:
        print("\n✗ Training failed. Check the error messages above.")
        sys.exit(1)
