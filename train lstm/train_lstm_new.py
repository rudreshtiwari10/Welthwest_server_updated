"""
LSTM Stock Model Training Script (WITH FULL PROGRESS)
======================================================

This script trains LSTM models for stock price prediction.
Shows complete training progress including epochs and batches.

Edit the CONFIGURATION section below to customize your training.

Usage:
    python "train lstm/train_lstm_new.py"

Author: WelthWest Team
Date: 2025-11-06
"""

import sys
import os

# Add parent directory to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import time
import pickle
import json
from datetime import datetime
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# Import LSTM components
from services.lstm_data_service import LSTMDataService
from models.lstm_stock_model import build_lstm_model, get_model_summary

# ============================================
# CONFIGURATION - EDIT THIS SECTION
# ============================================

# Stock Configuration
STOCK_SYMBOLS = [
    # "INFY.NS",      # Reliance Industries
    # "TCS.NS",         # Tata Consultancy Services
    # "RELIANCE.NS",        # Infosys
    # "HDFCBANK.NS",    # HDFC Bank
    # "ICICIBANK.NS",   # ICICI Bank
    "SBIN.NS",        # State Bank of India
    # "BHARTIARTL.NS",  # Bharti Airtel
    # "ITC.NS",         # ITC Limited
    # "KOTAKBANK.NS",   # Kotak Mahindra Bank
    # "LT.NS",          # Larsen & Toubro
]

# Training Data Configuration
TRAIN_START_DATE = "2018-01-01"  # Start date for training data
TRAIN_END_DATE = "auto"          # End date ('auto' = yesterday)

# Model Hyperparameters
TIME_STEPS = 60          # Number of days to look back (default: 60)
FORECAST_DAYS = 3        # Number of days to predict (default: 3)
EPOCHS = 60           # Training epochs (more = better but slower)
BATCH_SIZE = 32         # Batch size for training (default: 32)
TRAIN_TEST_SPLIT = 0.85  # Train/test split ratio (0.95 = 95% train, 5% test)

# Training Options
FORCE_RETRAIN = True     # Retrain even if model exists (True/False)
SHOW_MODEL_SUMMARY = True  # Show LSTM architecture (True/False)

# Directory Configuration
# Use parent directory paths since script runs from 'train lstm' folder
MODEL_DIR = "../lstm_model/models"
SCALER_DIR = "../lstm_model/scalers"
METADATA_DIR = "../lstm_model/metadata"

# Summary Output
SAVE_TRAINING_SUMMARY = True          # Save training summary to CSV
SUMMARY_FILE = "lstm_training_summary.csv"

# ============================================
# DO NOT EDIT BELOW THIS LINE
# ============================================

class LSTMTrainerWithProgress:
    """LSTM Model Trainer with full progress display"""

    def __init__(self):
        self.training_results = []
        # Ensure directories exist
        os.makedirs(MODEL_DIR, exist_ok=True)
        os.makedirs(SCALER_DIR, exist_ok=True)
        os.makedirs(METADATA_DIR, exist_ok=True)

    def print_header(self):
        """Print training session header"""
        print("\n" + "="*80)
        print(" "*25 + "LSTM MODEL TRAINING SESSION")
        print("="*80)
        print(f"\nSession started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Number of stocks to train: {len(STOCK_SYMBOLS)}")
        print(f"Training period: {TRAIN_START_DATE} to {TRAIN_END_DATE}")
        print(f"Epochs: {EPOCHS} | Batch Size: {BATCH_SIZE} | Time Steps: {TIME_STEPS}")
        print("="*80 + "\n")

    def print_section(self, title):
        """Print section header"""
        print("\n" + "─"*80)
        print(f"▶ {title}")
        print("─"*80)

    def check_model_exists(self, stock_symbol):
        """Check if model already exists"""
        symbol_normalized = stock_symbol.replace(".", "_").lower()
        model_path = os.path.join(MODEL_DIR, f"lstm_{symbol_normalized}.keras")
        return os.path.exists(model_path)

    def train_single_stock(self, stock_symbol, index, total):
        """Train model for a single stock with full progress"""

        print("\n" + "="*80)
        print(f"[{index}/{total}] TRAINING: {stock_symbol}")
        print("="*80)

        # Normalize stock symbol for file naming
        symbol_normalized = stock_symbol.replace(".", "_").lower()

        # Check if model exists
        if not FORCE_RETRAIN and self.check_model_exists(stock_symbol):
            print(f"\n⚠️  Model already exists for {stock_symbol}")
            print("   Set FORCE_RETRAIN = True to retrain")
            return {
                'success': False,
                'stock_symbol': stock_symbol,
                'error': 'Model already exists. Set FORCE_RETRAIN=True to retrain.'
            }

        try:
            # Start timing
            start_time = time.time()

            # ========================================
            # STEP 1: Fetch Stock Data
            # ========================================
            self.print_section("STEP 1/7: Fetching Stock Data")
            print(f"   Symbol: {stock_symbol}")
            print(f"   Period: {TRAIN_START_DATE} to {TRAIN_END_DATE}")

            data = LSTMDataService.fetch_stock_data(stock_symbol, TRAIN_START_DATE, TRAIN_END_DATE)

            print(f"   ✅ Data fetched successfully!")
            print(f"   📊 Total records: {len(data)}")
            print(f"   📅 Date range: {data['date'].min()} to {data['date'].max()}")
            print(f"   💰 Price range: ₹{data['close'].min():.2f} - ₹{data['close'].max():.2f}")

            # ========================================
            # STEP 2: Prepare Training Data
            # ========================================
            self.print_section("STEP 2/7: Preparing Training Data")
            print(f"   Time steps: {TIME_STEPS}")
            print(f"   Train/Test split: {TRAIN_TEST_SPLIT} ({TRAIN_TEST_SPLIT*100:.0f}% train)")

            X_train, y_train, X_test, y_test, scaler, training_data_len = \
                LSTMDataService.prepare_training_data(data, time_steps=TIME_STEPS, train_split=TRAIN_TEST_SPLIT)

            print(f"   ✅ Training data prepared!")
            print(f"   📦 Training samples: {len(X_train)}")
            print(f"   📦 Test samples: {len(X_test) if len(X_test) > 0 else 0}")
            print(f"   📐 Input shape: {X_train.shape}")

            # ========================================
            # STEP 3: Build LSTM Model
            # ========================================
            self.print_section("STEP 3/7: Building LSTM Model Architecture")
            print(f"   Building model with {TIME_STEPS} time steps...\n")

            model = build_lstm_model(time_steps=TIME_STEPS)

            if SHOW_MODEL_SUMMARY:
                print("\n📋 LSTM Model Architecture:")
                print("-"*80)
                model.summary()
                print("-"*80)

            print(f"\n   ✅ Model built successfully!")
            print(f"   🧠 Total parameters: {model.count_params():,}")

            # ========================================
            # STEP 4: Train the Model
            # ========================================
            self.print_section("STEP 4/7: Training LSTM Model")
            print(f"   Epochs: {EPOCHS}")
            print(f"   Batch size: {BATCH_SIZE}")
            print(f"   Validation split: 10%")
            print(f"\n   🚀 Starting training (this will take several minutes)...\n")

            # Train with verbose=1 to show progress
            history = model.fit(
                X_train, y_train,
                epochs=EPOCHS,
                batch_size=BATCH_SIZE,
                validation_split=0.1,
                verbose=1  # Shows epoch progress
            )

            training_duration = time.time() - start_time

            print(f"\n   ✅ Training completed in {int(training_duration)} seconds!")
            print(f"   📉 Final training loss: {history.history['loss'][-1]:.4f}")
            print(f"   📉 Final validation loss: {history.history['val_loss'][-1]:.4f}")

            # ========================================
            # STEP 5: Evaluate Model
            # ========================================
            self.print_section("STEP 5/7: Evaluating Model Performance")

            if len(X_test) > 0:
                print("   Making predictions on test set...")
                test_predictions = model.predict(X_test, verbose=0)
                test_predictions = scaler.inverse_transform(test_predictions)

                # Calculate metrics
                mae = mean_absolute_error(y_test, test_predictions)
                rmse = np.sqrt(mean_squared_error(y_test, test_predictions))
                r2 = r2_score(y_test, test_predictions)
                mape = np.mean(np.abs((y_test - test_predictions) / y_test)) * 100

                print(f"\n   ✅ Model Performance Metrics:")
                print(f"      📊 MAE (Mean Absolute Error):  ₹{mae:.2f}")
                print(f"      📊 RMSE (Root Mean Squared Error): ₹{rmse:.2f}")
                print(f"      📊 R² Score: {r2:.4f} ({self._interpret_r2(r2)})")
                print(f"      📊 MAPE (Mean Abs % Error): {mape:.2f}%")
            else:
                # Use training metrics if no test data
                mae = history.history['loss'][-1]
                rmse = history.history['root_mean_squared_error'][-1]
                r2 = 0.0
                mape = 0.0
                print("   ⚠️  No test data available, using training metrics")

            # ========================================
            # STEP 6: Save Model & Files
            # ========================================
            self.print_section("STEP 6/7: Saving Model and Files")

            # Save model
            model_path = os.path.join(MODEL_DIR, f"lstm_{symbol_normalized}.keras")
            model.save(model_path)
            print(f"   💾 Model saved: {model_path}")

            # Save scaler
            scaler_path = os.path.join(SCALER_DIR, f"scaler_{symbol_normalized}.pkl")
            with open(scaler_path, 'wb') as f:
                pickle.dump(scaler, f)
            print(f"   💾 Scaler saved: {scaler_path}")

            # Save metadata
            metadata = self._create_metadata(
                stock_symbol, data, training_data_len, TIME_STEPS, EPOCHS,
                BATCH_SIZE, mae, rmse, r2, mape, model_path, scaler_path,
                training_duration
            )
            metadata_path = os.path.join(METADATA_DIR, f"{symbol_normalized}.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            print(f"   💾 Metadata saved: {metadata_path}")

            # ========================================
            # STEP 7: Summary
            # ========================================
            self.print_section("STEP 7/7: Training Summary")

            last_price = float(data['close'].iloc[-1])

            print(f"\n   ✅ Training Complete for {stock_symbol}")
            print(f"   ⏱️  Total Duration: {int(training_duration)} seconds ({int(training_duration/60)} min)")
            print(f"   💰 Last Training Price: ₹{last_price:.2f}")
            print(f"   📈 Training Samples: {len(X_train)}")
            print(f"   📉 Test Samples: {len(X_test) if len(X_test) > 0 else 0}")
            print(f"\n   🎯 Performance Summary:")
            print(f"      MAE:  ₹{mae:.2f}")
            print(f"      RMSE: ₹{rmse:.2f}")
            print(f"      R²:   {r2:.4f}")
            print(f"      MAPE: {mape:.2f}%")

            # Return success result
            return {
                'success': True,
                'data': {
                    'stock_symbol': stock_symbol,
                    'training_completed_at': datetime.now().isoformat() + "Z",
                    'training_duration_seconds': int(training_duration),
                    'model_performance': {
                        'mae': float(mae),
                        'rmse': float(rmse),
                        'r2': float(r2),
                        'mape': float(mape)
                    },
                    'training_data': {
                        'start_date': str(data['date'].iloc[0]),
                        'end_date': str(data['date'].iloc[-1]),
                        'total_days': len(data),
                        'training_samples': len(X_train),
                        'test_samples': len(X_test) if len(X_test) > 0 else 0
                    },
                    'model_files': {
                        'model_path': model_path,
                        'scaler_path': scaler_path,
                        'metadata_path': metadata_path
                    },
                    'last_training_price': last_price
                }
            }

        except Exception as e:
            print(f"\n❌ Training failed for {stock_symbol}")
            print(f"   Error: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                'success': False,
                'stock_symbol': stock_symbol,
                'error': f'{type(e).__name__}: {str(e)}'
            }

    def _interpret_r2(self, r2):
        """Interpret R² score"""
        if r2 >= 0.95:
            return "Excellent"
        elif r2 >= 0.90:
            return "Very Good"
        elif r2 >= 0.85:
            return "Good"
        elif r2 >= 0.80:
            return "Fair"
        else:
            return "Needs Improvement"

    def _create_metadata(self, stock_symbol, data, training_data_len, time_steps,
                         epochs, batch_size, mae, rmse, r2, mape, model_path,
                         scaler_path, training_duration):
        """Create metadata dictionary"""
        return {
            "stock_symbol": stock_symbol,
            "training_info": {
                "trained_at": datetime.now().isoformat() + "Z",
                "training_duration_seconds": int(training_duration),
                "training_start_date": str(data['date'].iloc[0]),
                "training_end_date": str(data['date'].iloc[-1]),
                "total_training_days": len(data),
                "training_samples": training_data_len - time_steps,
                "test_samples": len(data) - training_data_len
            },
            "model_config": {
                "time_steps": time_steps,
                "forecast_days": FORECAST_DAYS,
                "epochs": epochs,
                "batch_size": batch_size,
                "lstm_layers": [128, 64, 32],
                "dense_layers": [64, 1],
                "dropout_rate": [0.2, 0.2, 0.2, 0.3]
            },
            "model_performance": {
                "mae": float(mae),
                "rmse": float(rmse),
                "r2": float(r2),
                "mape": float(mape)
            },
            "last_training_price": float(data['close'].iloc[-1]),
            "model_files": {
                "model_path": model_path,
                "scaler_path": scaler_path
            },
            "version": "1.0",
            "created_by": "train_lstm_new.py",
            "last_updated": datetime.now().isoformat() + "Z"
        }

    def train_all_stocks(self):
        """Train models for all configured stocks"""
        self.print_header()

        total_stocks = len(STOCK_SYMBOLS)
        successful_trainings = 0
        failed_trainings = 0

        for index, stock_symbol in enumerate(STOCK_SYMBOLS, 1):
            # Train the model
            result = self.train_single_stock(stock_symbol, index, total_stocks)

            # Track results
            if result.get('success'):
                successful_trainings += 1
            else:
                failed_trainings += 1

            self.training_results.append(result)

            # Add separator between stocks
            if index < total_stocks:
                print("\n" + "█"*80 + "\n")

        # Print final summary
        self.print_final_summary(successful_trainings, failed_trainings)

        # Save summary to CSV if enabled
        if SAVE_TRAINING_SUMMARY:
            self.save_summary_to_csv()

    def print_final_summary(self, successful, failed):
        """Print final training summary"""
        total = successful + failed

        print("\n" + "="*80)
        print(" "*25 + "TRAINING SESSION SUMMARY")
        print("="*80)
        print(f"\nTotal stocks processed: {total}")
        print(f"✅ Successful trainings: {successful}")
        print(f"❌ Failed trainings: {failed}")
        print(f"Success rate: {(successful/total*100) if total > 0 else 0:.1f}%")

        # Show successful models
        if successful > 0:
            print("\n📊 Successfully Trained Models:")
            for result in self.training_results:
                if result.get('success'):
                    data = result['data']
                    print(f"   • {data['stock_symbol']} - "
                          f"MAE: ₹{data['model_performance']['mae']:.2f}, "
                          f"R²: {data['model_performance']['r2']:.4f}, "
                          f"Time: {data['training_duration_seconds']}s")

        # Show failed models
        if failed > 0:
            print("\n⚠️  Failed Trainings:")
            for result in self.training_results:
                if not result.get('success'):
                    print(f"   • {result['stock_symbol']} - {result['error']}")

        print(f"\nSession ended at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")

    def save_summary_to_csv(self):
        """Save training summary to CSV file"""
        try:
            summary_data = []

            for result in self.training_results:
                if result.get('success'):
                    data = result['data']
                    summary_data.append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'stock_symbol': data['stock_symbol'],
                        'status': 'SUCCESS',
                        'duration_seconds': data['training_duration_seconds'],
                        'mae': data['model_performance']['mae'],
                        'rmse': data['model_performance']['rmse'],
                        'r2': data['model_performance']['r2'],
                        'mape': data['model_performance']['mape'],
                        'training_samples': data['training_data']['training_samples'],
                        'test_samples': data['training_data']['test_samples'],
                        'train_start': TRAIN_START_DATE,
                        'train_end': TRAIN_END_DATE,
                        'epochs': EPOCHS,
                        'batch_size': BATCH_SIZE,
                        'time_steps': TIME_STEPS,
                        'error': ''
                    })
                else:
                    summary_data.append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'stock_symbol': result['stock_symbol'],
                        'status': 'FAILED',
                        'duration_seconds': 0,
                        'mae': 0,
                        'rmse': 0,
                        'r2': 0,
                        'mape': 0,
                        'training_samples': 0,
                        'test_samples': 0,
                        'train_start': TRAIN_START_DATE,
                        'train_end': TRAIN_END_DATE,
                        'epochs': EPOCHS,
                        'batch_size': BATCH_SIZE,
                        'time_steps': TIME_STEPS,
                        'error': result['error']
                    })

            # Create DataFrame and save to CSV
            df = pd.DataFrame(summary_data)

            # Append to existing file or create new
            if os.path.exists(SUMMARY_FILE):
                df.to_csv(SUMMARY_FILE, mode='a', header=False, index=False)
            else:
                df.to_csv(SUMMARY_FILE, index=False)

            print(f"\n💾 Training summary saved to: {SUMMARY_FILE}")

        except Exception as e:
            print(f"\n⚠️  Failed to save summary: {str(e)}")


def validate_configuration():
    """Validate configuration before training"""
    errors = []

    # Check if stock symbols are provided
    if not STOCK_SYMBOLS:
        errors.append("❌ No stock symbols configured. Add symbols to STOCK_SYMBOLS list.")

    # Check epochs
    if EPOCHS < 1 or EPOCHS > 100:
        errors.append("❌ EPOCHS must be between 1 and 100")

    # Check batch size
    if BATCH_SIZE < 1 or BATCH_SIZE > 256:
        errors.append("❌ BATCH_SIZE must be between 1 and 256")

    # Check time steps
    if TIME_STEPS < 10 or TIME_STEPS > 200:
        errors.append("❌ TIME_STEPS must be between 10 and 200")

    if errors:
        print("\n⚠️  Configuration Errors:")
        for error in errors:
            print(f"   {error}")
        print("\nPlease fix the configuration and try again.\n")
        return False

    return True


def main():
    """Main training function"""
    print("\n" + "="*80)
    print(" "*20 + "LSTM STOCK PREDICTION - MODEL TRAINING")
    print(" "*25 + "(WITH FULL PROGRESS)")
    print("="*80)

    # Validate configuration
    if not validate_configuration():
        return

    # Show configuration
    print("\n📋 Training Configuration:")
    print(f"   Stock Symbols: {', '.join(STOCK_SYMBOLS)}")
    print(f"   Training Period: {TRAIN_START_DATE} to {TRAIN_END_DATE}")
    print(f"   Epochs: {EPOCHS}")
    print(f"   Batch Size: {BATCH_SIZE}")
    print(f"   Time Steps: {TIME_STEPS}")
    print(f"   Force Retrain: {FORCE_RETRAIN}")
    print(f"   Show Model Summary: {SHOW_MODEL_SUMMARY}")
    print(f"   Model Directory: {MODEL_DIR}")

    # Confirm before proceeding
    print("\n⚠️  Note: Training will show full progress including:")
    print("   - Model architecture details")
    print("   - Epoch-by-epoch progress")
    print("   - Batch processing updates")
    print("   - Performance metrics")
    print("\n   Training typically takes 5-10 minutes per stock.")

    response = input("\nProceed with training? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("\n❌ Training cancelled by user.\n")
        return

    # Create trainer and start training
    trainer = LSTMTrainerWithProgress()

    try:
        trainer.train_all_stocks()
    except KeyboardInterrupt:
        print("\n\n⚠️  Training interrupted by user.")
        print("Partially trained models may still be saved.\n")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
