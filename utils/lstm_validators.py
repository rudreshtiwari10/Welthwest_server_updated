"""
LSTM Validators Utility
Input validation for LSTM API endpoints
Based on LSTM_STOCK_PREDICTION_SPEC.md
"""

import re
from datetime import datetime


class LSTMValidators:
    """Utility class for input validation."""

    @staticmethod
    def validate_stock_symbol(stock_symbol):
        """
        Validate stock symbol format.

        Args:
            stock_symbol (str): Stock ticker symbol

        Returns:
            tuple: (is_valid, error_message)
        """
        if not stock_symbol:
            return False, "Stock symbol is required"

        if not isinstance(stock_symbol, str):
            return False, "Stock symbol must be a string"

        # Check length
        if len(stock_symbol) < 1 or len(stock_symbol) > 20:
            return False, "Stock symbol must be between 1 and 20 characters"

        # Check format (alphanumeric and dots only)
        if not re.match(r'^[A-Za-z0-9.]+$', stock_symbol):
            return False, "Stock symbol can only contain letters, numbers, and dots"

        return True, None

    @staticmethod
    def validate_date(date_string, field_name="date"):
        """
        Validate date format.

        Args:
            date_string (str): Date string in YYYY-MM-DD format
            field_name (str): Name of the field for error messages

        Returns:
            tuple: (is_valid, error_message)
        """
        if date_string == "auto":
            return True, None

        if not date_string:
            return False, f"{field_name} is required"

        try:
            datetime.strptime(date_string, '%Y-%m-%d')
            return True, None
        except ValueError:
            return False, f"{field_name} must be in YYYY-MM-DD format"

    @staticmethod
    def validate_time_steps(time_steps):
        """
        Validate time_steps parameter.

        Args:
            time_steps (int): Number of time steps

        Returns:
            tuple: (is_valid, error_message)
        """
        if not isinstance(time_steps, int):
            return False, "time_steps must be an integer"

        if time_steps < 10 or time_steps > 200:
            return False, "time_steps must be between 10 and 200"

        return True, None

    @staticmethod
    def validate_epochs(epochs):
        """
        Validate epochs parameter.

        Args:
            epochs (int): Number of training epochs

        Returns:
            tuple: (is_valid, error_message)
        """
        if not isinstance(epochs, int):
            return False, "epochs must be an integer"

        if epochs < 1 or epochs > 100:
            return False, "epochs must be between 1 and 100"

        return True, None

    @staticmethod
    def validate_batch_size(batch_size):
        """
        Validate batch_size parameter.

        Args:
            batch_size (int): Training batch size

        Returns:
            tuple: (is_valid, error_message)
        """
        if not isinstance(batch_size, int):
            return False, "batch_size must be an integer"

        if batch_size < 1 or batch_size > 256:
            return False, "batch_size must be between 1 and 256"

        return True, None

    @staticmethod
    def validate_training_request(request_data):
        """
        Validate training request data.

        Args:
            request_data (dict): Request data

        Returns:
            tuple: (is_valid, errors_dict)
        """
        errors = {}

        # Validate stock_symbol (required)
        if 'stock_symbol' not in request_data:
            errors['stock_symbol'] = "stock_symbol is required"
        else:
            is_valid, error = LSTMValidators.validate_stock_symbol(
                request_data['stock_symbol']
            )
            if not is_valid:
                errors['stock_symbol'] = error

        # Validate train_start (optional)
        if 'train_start' in request_data:
            is_valid, error = LSTMValidators.validate_date(
                request_data['train_start'], 'train_start'
            )
            if not is_valid:
                errors['train_start'] = error

        # Validate train_end (optional)
        if 'train_end' in request_data:
            is_valid, error = LSTMValidators.validate_date(
                request_data['train_end'], 'train_end'
            )
            if not is_valid:
                errors['train_end'] = error

        # Validate time_steps (optional)
        if 'time_steps' in request_data:
            is_valid, error = LSTMValidators.validate_time_steps(
                request_data['time_steps']
            )
            if not is_valid:
                errors['time_steps'] = error

        # Validate epochs (optional)
        if 'epochs' in request_data:
            is_valid, error = LSTMValidators.validate_epochs(
                request_data['epochs']
            )
            if not is_valid:
                errors['epochs'] = error

        # Validate batch_size (optional)
        if 'batch_size' in request_data:
            is_valid, error = LSTMValidators.validate_batch_size(
                request_data['batch_size']
            )
            if not is_valid:
                errors['batch_size'] = error

        # Validate force_retrain (optional)
        if 'force_retrain' in request_data:
            if not isinstance(request_data['force_retrain'], bool):
                errors['force_retrain'] = "force_retrain must be a boolean"

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def validate_prediction_request(request_data):
        """
        Validate prediction request data.

        Args:
            request_data (dict): Request data

        Returns:
            tuple: (is_valid, errors_dict)
        """
        errors = {}

        # Validate stock_symbol (required)
        if 'stock_symbol' not in request_data:
            errors['stock_symbol'] = "stock_symbol is required"
        else:
            is_valid, error = LSTMValidators.validate_stock_symbol(
                request_data['stock_symbol']
            )
            if not is_valid:
                errors['stock_symbol'] = error

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def sanitize_stock_symbol(stock_symbol):
        """
        Sanitize stock symbol (remove potentially dangerous characters).

        Args:
            stock_symbol (str): Stock ticker symbol

        Returns:
            str: Sanitized stock symbol
        """
        if not stock_symbol:
            return ""

        # Remove any characters that aren't alphanumeric or dots
        sanitized = re.sub(r'[^A-Za-z0-9.]', '', stock_symbol)

        # Convert to uppercase and strip
        sanitized = sanitized.upper().strip()

        return sanitized

    @staticmethod
    def create_error_response(code, message, details=None, status_code=400):
        """
        Create standardized error response.

        Args:
            code (str): Error code
            message (str): Error message
            details (str): Additional details
            status_code (int): HTTP status code

        Returns:
            tuple: (response_dict, status_code)
        """
        error_response = {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or "",
                "timestamp": datetime.now().isoformat() + "Z"
            }
        }

        return error_response, status_code

    @staticmethod
    def create_validation_error_response(errors):
        """
        Create validation error response.

        Args:
            errors (dict): Dictionary of validation errors

        Returns:
            tuple: (response_dict, status_code)
        """
        error_response = {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": errors,
                "timestamp": datetime.now().isoformat() + "Z"
            }
        }

        return error_response, 400
