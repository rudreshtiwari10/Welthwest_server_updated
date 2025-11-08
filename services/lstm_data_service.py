"""
LSTM Data Service
Handles data fetching and preprocessing for LSTM stock prediction
Based on LSTM_STOCK_PREDICTION_SPEC.md
"""

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta


class LSTMDataService:
    """Service for fetching and preprocessing stock data."""

    @staticmethod
    def fetch_stock_data(stock_symbol, start_date, end_date=None):
        """
        Fetch stock data from Yahoo Finance.

        Args:
            stock_symbol (str): Stock ticker symbol (e.g., "RELIANCE.NS")
            start_date (str): Start date in YYYY-MM-DD format
            end_date (str): End date in YYYY-MM-DD format (optional, defaults to today)

        Returns:
            pd.DataFrame: Stock data with cleaned columns

        Raises:
            ValueError: If no data is returned or data is invalid
        """
        try:
            # If end_date is 'auto' or None, use yesterday's date
            if end_date is None or end_date == 'auto':
                end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

            # Download data from Yahoo Finance
            data = yf.download(stock_symbol, start=start_date, end=end_date, progress=False)

            # Check if data is empty
            if data.empty:
                raise ValueError(f"No data returned for {stock_symbol}. Check symbol or date range.")

            # Reset index to make Date a column
            data = data.reset_index()

            # Fix column names
            data = LSTMDataService._clean_column_names(data)

            # Validate required columns
            required_columns = ['date', 'close']
            missing_columns = [col for col in required_columns if col not in data.columns]
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")

            return data

        except Exception as e:
            raise ValueError(f"Error fetching stock data: {str(e)}")

    @staticmethod
    def _clean_column_names(data):
        """
        Clean and standardize column names.

        Args:
            data (pd.DataFrame): Raw data from Yahoo Finance

        Returns:
            pd.DataFrame: Data with cleaned column names
        """
        # Handle MultiIndex columns
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = ['_'.join(map(str, col)).strip('_').lower()
                            if isinstance(col, tuple) else str(col).lower()
                            for col in data.columns]
        else:
            data.columns = [str(col).lower().strip() for col in data.columns]

        # Remove ticker suffix from column names
        new_columns = {}
        for col in data.columns:
            clean_col = col.split('_')[0] if '_' in col and col != 'date' else col
            new_columns[col] = clean_col
        data.rename(columns=new_columns, inplace=True)

        return data

    @staticmethod
    def prepare_training_data(data, time_steps=60, train_split=0.95):
        """
        Prepare training data with sequences.

        Args:
            data (pd.DataFrame): Stock data with 'close' column
            time_steps (int): Number of time steps for sequences (default: 60)
            train_split (float): Train-test split ratio (default: 0.95)

        Returns:
            tuple: (X_train, y_train, X_test, y_test, scaler, training_data_len)

        Raises:
            ValueError: If insufficient data points
        """
        # Extract close prices
        stock_close = data[['close']].copy()
        dataset = stock_close.values

        # Check minimum data requirement
        if len(dataset) < time_steps + 1:
            raise ValueError(f"Insufficient data. Need at least {time_steps + 1} days, got {len(dataset)}")

        # Calculate training data length
        training_data_len = int(np.ceil(len(dataset) * train_split))

        # Scale the data
        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(dataset)

        # Create training sequences
        training_data = scaled_data[:training_data_len]
        X_train, y_train = [], []

        for i in range(time_steps, len(training_data)):
            X_train.append(training_data[i - time_steps:i, 0])
            y_train.append(training_data[i, 0])

        X_train, y_train = np.array(X_train), np.array(y_train)
        X_train = np.reshape(X_train, (X_train.shape[0], X_train.shape[1], 1))

        # Create test sequences
        test_data = scaled_data[training_data_len - time_steps:]
        X_test, y_test = [], dataset[training_data_len:]

        for i in range(time_steps, len(test_data)):
            X_test.append(test_data[i - time_steps:i, 0])

        X_test = np.array(X_test)
        if len(X_test) > 0:
            X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))

        return X_train, y_train, X_test, y_test, scaler, training_data_len

    @staticmethod
    def fetch_latest_data(stock_symbol, days=60):
        """
        Fetch latest stock data for prediction.

        Args:
            stock_symbol (str): Stock ticker symbol
            days (int): Number of days to fetch (default: 60)

        Returns:
            pd.DataFrame: Latest stock data

        Raises:
            ValueError: If data fetch fails
        """
        try:
            # Use yfinance to get recent data
            ticker = yf.Ticker(stock_symbol)
            data = ticker.history(period=f'{days}d')

            if data.empty:
                raise ValueError(f"No recent data available for {stock_symbol}")

            # Reset index and clean column names
            data = data.reset_index()
            data = LSTMDataService._clean_column_names(data)

            return data

        except Exception as e:
            raise ValueError(f"Error fetching latest data: {str(e)}")

    @staticmethod
    def prepare_prediction_input(data, scaler, time_steps=60):
        """
        Prepare input data for prediction.

        Args:
            data (pd.DataFrame): Recent stock data
            scaler: Fitted StandardScaler
            time_steps (int): Number of time steps (default: 60)

        Returns:
            np.array: Scaled and reshaped input for prediction

        Raises:
            ValueError: If insufficient data
        """
        # Extract close prices
        close_prices = data[['close']].tail(time_steps).values

        if len(close_prices) < time_steps:
            raise ValueError(f"Insufficient data. Need {time_steps} days, got {len(close_prices)}")

        # Scale the data
        scaled_data = scaler.transform(close_prices)

        # Reshape for prediction
        forecast_input = scaled_data.reshape(1, time_steps, 1)

        return forecast_input, scaled_data

    @staticmethod
    def get_next_trading_dates(last_date, num_days=3):
        """
        Get next trading dates (skip weekends).

        Args:
            last_date: Last actual trading date
            num_days (int): Number of days to predict (default: 3)

        Returns:
            list: List of next trading dates
        """
        prediction_dates = []
        current_date = pd.to_datetime(last_date)

        for _ in range(num_days):
            # Add one day
            next_date = current_date + timedelta(days=1)

            # Skip weekends (Saturday=5, Sunday=6)
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)

            prediction_dates.append(next_date)
            current_date = next_date

        return prediction_dates
