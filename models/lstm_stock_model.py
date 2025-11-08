"""
LSTM Stock Model Architecture
Based on LSTM_STOCK_PREDICTION_SPEC.md
"""

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout


def build_lstm_model(time_steps=60):
    """
    Build LSTM model architecture as per specification.

    Architecture:
    - LSTM Layer 1: 128 units, return_sequences=True
    - Dropout: 0.2
    - LSTM Layer 2: 64 units, return_sequences=True
    - Dropout: 0.2
    - LSTM Layer 3: 32 units, return_sequences=False
    - Dropout: 0.2
    - Dense Layer 1: 64 units, activation='relu'
    - Dropout: 0.3
    - Dense Layer 2: 1 unit (output)

    Args:
        time_steps (int): Number of time steps (default: 60)

    Returns:
        keras.Model: Compiled LSTM model
    """
    model = Sequential([
        LSTM(128, return_sequences=True, input_shape=(time_steps, 1)),
        Dropout(0.2),
        LSTM(64, return_sequences=True),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(64, activation="relu"),
        Dropout(0.3),
        Dense(1)
    ])

    # Compile with Adam optimizer and MAE loss
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss="mae",
        metrics=[keras.metrics.RootMeanSquaredError()]
    )

    return model


def get_model_summary(model):
    """
    Get model summary as string.

    Args:
        model: Keras model

    Returns:
        str: Model summary
    """
    from io import StringIO
    import sys

    stream = StringIO()
    model.summary(print_fn=lambda x: stream.write(x + '\n'))
    summary_string = stream.getvalue()
    stream.close()

    return summary_string
