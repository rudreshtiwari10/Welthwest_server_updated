"""
Batch Training Script for Multiple Stocks
Train LSTM models for multiple stocks in sequence
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict
import pandas as pd

# Import the main training script
from train_lstm_model import (
    TrainingConfig, DataFetcher, FeatureEngineering, DataPreparation,
    LSTMModelBuilder, LSTMTrainer, ModelEvaluator, ModelSaver,
    TENSORFLOW_AVAILABLE
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# BATCH TRAINING CONFIGURATION
# ============================================================================

class BatchTrainingConfig:
    """Configuration for batch training multiple stocks"""

    # List of stocks to train
    TICKERS = [
        'RELIANCE.NS',
        'TCS.NS',
        'HDFCBANK.NS',
        'INFY.NS',
        'ICICIBANK.NS',
        'WIPRO.NS',
        'SBIN.NS',
        'BHARTIARTL.NS',
        'ITC.NS',
        'KOTAKBANK.NS'
    ]

    # Training parameters (will be applied to all stocks)
    COMMON_CONFIG = {
        'period': '5y',
        'sequence_length': 60,
        'prediction_horizon': 5,
        'epochs': 100,
        'batch_size': 32,
        'learning_rate': 0.001
    }

    # Save batch results
    SAVE_BATCH_SUMMARY = True
    BATCH_SUMMARY_FILE = 'batch_training_summary.csv'


# ============================================================================
# BATCH TRAINER
# ============================================================================

class BatchTrainer:
    """Train multiple stocks in sequence"""

    def __init__(self, tickers: List[str], common_config: Dict):
        self.tickers = tickers
        self.common_config = common_config
        self.results = []

    def train_all(self):
        """Train models for all tickers"""
        print("=" * 80)
        print("BATCH LSTM MODEL TRAINING")
        print("=" * 80)
        print(f"\nTraining {len(self.tickers)} stocks:")
        for ticker in self.tickers:
            print(f"  - {ticker}")
        print("")

        if not TENSORFLOW_AVAILABLE:
            logger.error("TensorFlow is not installed. Cannot proceed.")
            return

        total = len(self.tickers)
        for idx, ticker in enumerate(self.tickers, 1):
            print(f"\n{'='*80}")
            print(f"TRAINING STOCK {idx}/{total}: {ticker}")
            print(f"{'='*80}\n")

            try:
                result = self._train_single_stock(ticker)
                self.results.append(result)
                self._print_result(ticker, result)

            except Exception as e:
                logger.error(f"Failed to train {ticker}: {str(e)}")
                self.results.append({
                    'ticker': ticker,
                    'status': 'failed',
                    'error': str(e)
                })

        # Print summary
        self._print_summary()

        # Save summary
        if BatchTrainingConfig.SAVE_BATCH_SUMMARY:
            self._save_summary()

    def _train_single_stock(self, ticker: str) -> Dict:
        """Train model for a single stock"""
        start_time = datetime.now()

        # Update configuration
        TrainingConfig.TICKER = ticker
        TrainingConfig.PERIOD = self.common_config['period']
        TrainingConfig.SEQUENCE_LENGTH = self.common_config['sequence_length']
        TrainingConfig.PREDICTION_HORIZON = self.common_config['prediction_horizon']
        TrainingConfig.EPOCHS = self.common_config['epochs']
        TrainingConfig.BATCH_SIZE = self.common_config['batch_size']
        TrainingConfig.LEARNING_RATE = self.common_config['learning_rate']

        # Update model name
        TrainingConfig.MODEL_NAME = f'lstm_{ticker.replace(".", "_")}_{datetime.now().strftime("%Y%m%d")}'

        try:
            # 1. Fetch data
            fetcher = DataFetcher(TrainingConfig)
            df = fetcher.fetch_data()

            # 2. Feature engineering
            feature_eng = FeatureEngineering(TrainingConfig)
            df_features = feature_eng.create_features(df)

            # 3. Prepare data
            prep = DataPreparation(TrainingConfig)
            X, y, scaler = prep.prepare_data(df_features)

            # 4. Train/test split
            from sklearn.model_selection import train_test_split
            import numpy as np

            split_idx = int(len(X) * (1 - TrainingConfig.TEST_SIZE))
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            X_train, X_val, y_train, y_val = train_test_split(
                X_train, y_train,
                test_size=TrainingConfig.VALIDATION_SPLIT,
                random_state=TrainingConfig.RANDOM_SEED
            )

            # 5. Build model
            builder = LSTMModelBuilder(TrainingConfig)
            model = builder.build_model(input_shape=(X_train.shape[1], X_train.shape[2]))

            # 6. Train model
            trainer = LSTMTrainer(TrainingConfig)
            model = trainer.train(model, X_train, y_train, X_val, y_val)

            # 7. Evaluate
            evaluator = ModelEvaluator(TrainingConfig)
            metrics = evaluator.evaluate(model, X_test, y_test, scaler)

            # 8. Save model
            saver = ModelSaver(TrainingConfig)
            saver.save_all(model, scaler, trainer.history, metrics, prep.feature_columns)

            end_time = datetime.now()
            training_time = (end_time - start_time).total_seconds()

            return {
                'ticker': ticker,
                'status': 'success',
                'metrics': metrics,
                'training_time_seconds': training_time,
                'samples': len(X),
                'features': len(prep.feature_columns),
                'model_path': f"{TrainingConfig.MODEL_DIR}/{TrainingConfig.MODEL_NAME}.h5"
            }

        except Exception as e:
            return {
                'ticker': ticker,
                'status': 'failed',
                'error': str(e)
            }

    def _print_result(self, ticker: str, result: Dict):
        """Print individual training result"""
        print(f"\n{'─'*80}")
        print(f"RESULT FOR {ticker}")
        print(f"{'─'*80}")

        if result['status'] == 'success':
            metrics = result['metrics']
            print(f"✓ Training successful")
            print(f"  RMSE: {metrics['rmse']:.2f}")
            print(f"  MAPE: {metrics['mape']:.2f}%")
            print(f"  Directional Accuracy: {metrics['directional_accuracy']:.2f}%")
            print(f"  Training Time: {result['training_time_seconds']:.1f}s")
            print(f"  Samples: {result['samples']}")
            print(f"  Features: {result['features']}")
        else:
            print(f"✗ Training failed")
            print(f"  Error: {result.get('error', 'Unknown error')}")

    def _print_summary(self):
        """Print overall batch training summary"""
        print("\n" + "=" * 80)
        print("BATCH TRAINING SUMMARY")
        print("=" * 80)

        successful = [r for r in self.results if r['status'] == 'success']
        failed = [r for r in self.results if r['status'] == 'failed']

        print(f"\nTotal Stocks: {len(self.results)}")
        print(f"Successful: {len(successful)} ({len(successful)/len(self.results)*100:.1f}%)")
        print(f"Failed: {len(failed)} ({len(failed)/len(self.results)*100:.1f}%)")

        if successful:
            print("\n" + "─" * 80)
            print("SUCCESSFUL MODELS")
            print("─" * 80)
            print(f"{'Ticker':<15} {'RMSE':<10} {'MAPE':<10} {'Dir.Acc.':<12} {'Time(s)':<10}")
            print("─" * 80)

            for r in successful:
                m = r['metrics']
                print(f"{r['ticker']:<15} {m['rmse']:<10.2f} {m['mape']:<10.2f}% {m['directional_accuracy']:<12.2f}% {r['training_time_seconds']:<10.1f}")

            # Average metrics
            avg_rmse = sum(r['metrics']['rmse'] for r in successful) / len(successful)
            avg_mape = sum(r['metrics']['mape'] for r in successful) / len(successful)
            avg_acc = sum(r['metrics']['directional_accuracy'] for r in successful) / len(successful)
            total_time = sum(r['training_time_seconds'] for r in successful)

            print("─" * 80)
            print(f"{'AVERAGE':<15} {avg_rmse:<10.2f} {avg_mape:<10.2f}% {avg_acc:<12.2f}% {total_time:<10.1f}")

        if failed:
            print("\n" + "─" * 80)
            print("FAILED MODELS")
            print("─" * 80)
            for r in failed:
                print(f"✗ {r['ticker']}: {r.get('error', 'Unknown error')}")

        print("\n" + "=" * 80)

    def _save_summary(self):
        """Save batch training summary to CSV"""
        try:
            rows = []
            for r in self.results:
                row = {
                    'ticker': r['ticker'],
                    'status': r['status'],
                    'timestamp': datetime.now().isoformat()
                }

                if r['status'] == 'success':
                    row.update({
                        'rmse': r['metrics']['rmse'],
                        'mae': r['metrics']['mae'],
                        'mape': r['metrics']['mape'],
                        'directional_accuracy': r['metrics']['directional_accuracy'],
                        'training_time_seconds': r['training_time_seconds'],
                        'samples': r['samples'],
                        'features': r['features'],
                        'model_path': r['model_path']
                    })
                else:
                    row['error'] = r.get('error', 'Unknown')

                rows.append(row)

            df = pd.DataFrame(rows)
            df.to_csv(BatchTrainingConfig.BATCH_SUMMARY_FILE, index=False)
            logger.info(f"✓ Batch summary saved to {BatchTrainingConfig.BATCH_SUMMARY_FILE}")

        except Exception as e:
            logger.error(f"Failed to save batch summary: {str(e)}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run batch training"""

    # Create batch trainer
    trainer = BatchTrainer(
        tickers=BatchTrainingConfig.TICKERS,
        common_config=BatchTrainingConfig.COMMON_CONFIG
    )

    # Train all
    trainer.train_all()

    print("\n✓ Batch training complete!")


if __name__ == '__main__':
    main()
