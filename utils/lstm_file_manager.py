"""
LSTM File Manager Utility
Handles file operations for LSTM models
Based on LSTM_STOCK_PREDICTION_SPEC.md
"""

import os
import shutil
import json
from datetime import datetime


class LSTMFileManager:
    """Utility class for managing LSTM model files."""

    @staticmethod
    def ensure_directories(model_dir, scaler_dir, metadata_dir):
        """
        Ensure all required directories exist.

        Args:
            model_dir (str): Model directory path
            scaler_dir (str): Scaler directory path
            metadata_dir (str): Metadata directory path
        """
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(scaler_dir, exist_ok=True)
        os.makedirs(metadata_dir, exist_ok=True)

    @staticmethod
    def get_model_files(stock_symbol, model_dir, scaler_dir, metadata_dir):
        """
        Get file paths for a stock symbol.

        Args:
            stock_symbol (str): Stock ticker symbol
            model_dir (str): Model directory
            scaler_dir (str): Scaler directory
            metadata_dir (str): Metadata directory

        Returns:
            dict: Dictionary with file paths
        """
        symbol_normalized = stock_symbol.replace(".", "_").lower()

        return {
            "model_path": os.path.join(model_dir, f"lstm_{symbol_normalized}.keras"),
            "scaler_path": os.path.join(scaler_dir, f"scaler_{symbol_normalized}.pkl"),
            "metadata_path": os.path.join(metadata_dir, f"{symbol_normalized}.json")
        }

    @staticmethod
    def model_exists(stock_symbol, model_dir):
        """
        Check if model exists for a stock.

        Args:
            stock_symbol (str): Stock ticker symbol
            model_dir (str): Model directory

        Returns:
            bool: True if model exists, False otherwise
        """
        symbol_normalized = stock_symbol.replace(".", "_").lower()
        model_path = os.path.join(model_dir, f"lstm_{symbol_normalized}.keras")
        return os.path.exists(model_path)

    @staticmethod
    def delete_model(stock_symbol, model_dir, scaler_dir, metadata_dir):
        """
        Delete all files for a stock model.

        Args:
            stock_symbol (str): Stock ticker symbol
            model_dir (str): Model directory
            scaler_dir (str): Scaler directory
            metadata_dir (str): Metadata directory

        Returns:
            bool: True if deletion successful
        """
        files = LSTMFileManager.get_model_files(
            stock_symbol, model_dir, scaler_dir, metadata_dir
        )

        for file_path in files.values():
            if os.path.exists(file_path):
                os.remove(file_path)

        return True

    @staticmethod
    def list_all_models(model_dir):
        """
        List all trained models.

        Args:
            model_dir (str): Model directory

        Returns:
            list: List of stock symbols with trained models
        """
        models = []

        if os.path.exists(model_dir):
            for filename in os.listdir(model_dir):
                if filename.startswith("lstm_") and filename.endswith(".keras"):
                    symbol_normalized = filename.replace("lstm_", "").replace(".keras", "")
                    symbol = symbol_normalized.replace("_", ".").upper()
                    models.append(symbol)

        return sorted(models)

    @staticmethod
    def get_model_size(stock_symbol, model_dir, scaler_dir):
        """
        Get total size of model files.

        Args:
            stock_symbol (str): Stock ticker symbol
            model_dir (str): Model directory
            scaler_dir (str): Scaler directory

        Returns:
            dict: Dictionary with file sizes in MB
        """
        symbol_normalized = stock_symbol.replace(".", "_").lower()
        model_path = os.path.join(model_dir, f"lstm_{symbol_normalized}.keras")
        scaler_path = os.path.join(scaler_dir, f"scaler_{symbol_normalized}.pkl")

        model_size = os.path.getsize(model_path) / (1024 * 1024) if os.path.exists(model_path) else 0
        scaler_size = os.path.getsize(scaler_path) / (1024 * 1024) if os.path.exists(scaler_path) else 0

        return {
            "model_size_mb": round(model_size, 2),
            "scaler_size_mb": round(scaler_size, 4),
            "total_size_mb": round(model_size + scaler_size, 2)
        }

    @staticmethod
    def backup_model(stock_symbol, model_dir, scaler_dir, metadata_dir, backup_dir):
        """
        Create backup of model files.

        Args:
            stock_symbol (str): Stock ticker symbol
            model_dir (str): Model directory
            scaler_dir (str): Scaler directory
            metadata_dir (str): Metadata directory
            backup_dir (str): Backup directory

        Returns:
            dict: Backup information
        """
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        symbol_normalized = stock_symbol.replace(".", "_").lower()

        backup_folder = os.path.join(backup_dir, f"{symbol_normalized}_{timestamp}")
        os.makedirs(backup_folder, exist_ok=True)

        files = LSTMFileManager.get_model_files(
            stock_symbol, model_dir, scaler_dir, metadata_dir
        )

        backed_up_files = []
        for file_type, file_path in files.items():
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                backup_path = os.path.join(backup_folder, filename)
                shutil.copy2(file_path, backup_path)
                backed_up_files.append(file_type)

        return {
            "backup_path": backup_folder,
            "backed_up_files": backed_up_files,
            "timestamp": timestamp
        }

    @staticmethod
    def get_disk_usage(model_dir, scaler_dir, metadata_dir):
        """
        Get total disk usage for all models.

        Args:
            model_dir (str): Model directory
            scaler_dir (str): Scaler directory
            metadata_dir (str): Metadata directory

        Returns:
            dict: Disk usage information
        """
        def get_directory_size(directory):
            total_size = 0
            if os.path.exists(directory):
                for dirpath, dirnames, filenames in os.walk(directory):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        if os.path.exists(filepath):
                            total_size += os.path.getsize(filepath)
            return total_size / (1024 * 1024)  # Convert to MB

        model_size = get_directory_size(model_dir)
        scaler_size = get_directory_size(scaler_dir)
        metadata_size = get_directory_size(metadata_dir)

        return {
            "models_size_mb": round(model_size, 2),
            "scalers_size_mb": round(scaler_size, 2),
            "metadata_size_mb": round(metadata_size, 2),
            "total_size_mb": round(model_size + scaler_size + metadata_size, 2)
        }
