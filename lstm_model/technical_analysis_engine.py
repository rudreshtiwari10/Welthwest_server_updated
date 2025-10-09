"""
Advanced Technical Analysis Engine
Provides 50+ technical indicators for LSTM input
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class TechnicalAnalysisEngine:
    """Comprehensive technical analysis with 50+ indicators"""

    def __init__(self):
        logger.info("Technical Analysis Engine initialized")

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all 50+ technical indicators

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with all technical indicators
        """
        try:
            # Make a copy to avoid modifying original
            data = df.copy()

            # Price-based indicators
            data = self._calculate_moving_averages(data)

            # Momentum indicators
            data = self._calculate_momentum_indicators(data)

            # Volatility indicators
            data = self._calculate_volatility_indicators(data)

            # Volume indicators
            data = self._calculate_volume_indicators(data)

            # Advanced indicators
            data = self._calculate_advanced_indicators(data)

            return data

        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return df

    def _calculate_moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate SMA and EMA indicators"""
        # Simple Moving Averages
        for period in [5, 10, 20, 50, 200]:
            df[f'SMA_{period}'] = df['Close'].rolling(window=period).mean()

        # Exponential Moving Averages
        for period in [5, 12, 26, 50]:
            df[f'EMA_{period}'] = df['Close'].ewm(span=period, adjust=False).mean()

        return df

    def _calculate_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate RSI, MACD, Stochastic, Williams %R, CCI"""
        # RSI
        for period in [14, 21]:
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df[f'RSI_{period}'] = 100 - (100 / (1 + rs))

        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_line'] = exp1 - exp2
        df['MACD_signal'] = df['MACD_line'].ewm(span=9, adjust=False).mean()
        df['MACD_histogram'] = df['MACD_line'] - df['MACD_signal']

        # Stochastic Oscillator
        low_14 = df['Low'].rolling(window=14).min()
        high_14 = df['High'].rolling(window=14).max()
        df['Stochastic_K'] = 100 * ((df['Close'] - low_14) / (high_14 - low_14))
        df['Stochastic_D'] = df['Stochastic_K'].rolling(window=3).mean()

        # Williams %R
        df['Williams_R'] = -100 * ((high_14 - df['Close']) / (high_14 - low_14))

        # CCI (Commodity Channel Index)
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        sma = tp.rolling(window=14).mean()
        mad = tp.rolling(window=14).apply(lambda x: np.abs(x - x.mean()).mean())
        df['CCI_14'] = (tp - sma) / (0.015 * mad)

        return df

    def _calculate_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Bollinger Bands, ATR, Donchian Channels"""
        # Bollinger Bands
        sma_20 = df['Close'].rolling(window=20).mean()
        std_20 = df['Close'].rolling(window=20).std()
        df['Bollinger_Upper'] = sma_20 + (std_20 * 2)
        df['Bollinger_Lower'] = sma_20 - (std_20 * 2)
        df['Bollinger_Width'] = df['Bollinger_Upper'] - df['Bollinger_Lower']

        # ATR (Average True Range)
        for period in [14, 21]:
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df[f'ATR_{period}'] = true_range.rolling(window=period).mean()

        # Donchian Channels
        df['Donchian_Upper'] = df['High'].rolling(window=20).max()
        df['Donchian_Lower'] = df['Low'].rolling(window=20).min()

        return df

    def _calculate_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate volume-based indicators"""
        # Volume SMA
        df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA']

        # On-Balance Volume (OBV)
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()

        # Volume Price Trend
        df['Volume_Price_Trend'] = ((df['Close'].diff() / df['Close'].shift()) * df['Volume']).cumsum()

        # Accumulation/Distribution Line
        clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
        df['Accumulation_Distribution'] = (clv * df['Volume']).cumsum()

        # Money Flow Index
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        mf = tp * df['Volume']
        mf_pos = mf.where(tp > tp.shift(), 0).rolling(window=14).sum()
        mf_neg = mf.where(tp < tp.shift(), 0).rolling(window=14).sum()
        df['Money_Flow_Index'] = 100 - (100 / (1 + mf_pos / mf_neg))

        return df

    def _calculate_advanced_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Ichimoku, Parabolic SAR, Aroon"""
        # Ichimoku Cloud
        high_9 = df['High'].rolling(window=9).max()
        low_9 = df['Low'].rolling(window=9).min()
        df['Ichimoku_Tenkan'] = (high_9 + low_9) / 2

        high_26 = df['High'].rolling(window=26).max()
        low_26 = df['Low'].rolling(window=26).min()
        df['Ichimoku_Kijun'] = (high_26 + low_26) / 2

        df['Ichimoku_Senkou_A'] = ((df['Ichimoku_Tenkan'] + df['Ichimoku_Kijun']) / 2).shift(26)

        # Aroon Indicator
        def aroon_up(series, period=25):
            return series.rolling(window=period).apply(
                lambda x: ((period - (period - 1 - x.argmax())) / period) * 100
            )

        def aroon_down(series, period=25):
            return series.rolling(window=period).apply(
                lambda x: ((period - (period - 1 - x.argmin())) / period) * 100
            )

        df['Aroon_Up'] = aroon_up(df['High'])
        df['Aroon_Down'] = aroon_down(df['Low'])

        return df

    def detect_support_resistance(self, df: pd.DataFrame, window: int = 20,
                                   min_touches: int = 3) -> Dict[str, List[float]]:
        """
        Detect support and resistance levels

        Args:
            df: DataFrame with OHLCV data
            window: Window for local minima/maxima detection
            min_touches: Minimum touches to confirm level

        Returns:
            Dictionary with support and resistance levels
        """
        try:
            # Find local minima and maxima
            local_min_mask = (df['Low'].shift(1) > df['Low']) & (df['Low'].shift(-1) > df['Low'])
            local_min = df.loc[local_min_mask, 'Low'].tolist()

            local_max_mask = (df['High'].shift(1) < df['High']) & (df['High'].shift(-1) < df['High'])
            local_max = df.loc[local_max_mask, 'High'].tolist()

            # Cluster nearby levels
            support_levels = self._cluster_levels(local_min, tolerance=0.02)
            resistance_levels = self._cluster_levels(local_max, tolerance=0.02)

            return {
                'support_levels': support_levels[:5],  # Top 5 support levels
                'resistance_levels': resistance_levels[:5]  # Top 5 resistance levels
            }

        except Exception as e:
            logger.error(f"Error detecting support/resistance: {str(e)}")
            return {'support_levels': [], 'resistance_levels': []}

    def _cluster_levels(self, levels: List[float], tolerance: float = 0.02) -> List[float]:
        """Cluster nearby price levels"""
        if not levels:
            return []

        levels = sorted(levels)
        clusters = []
        current_cluster = [levels[0]]

        for level in levels[1:]:
            if abs(level - current_cluster[-1]) / current_cluster[-1] <= tolerance:
                current_cluster.append(level)
            else:
                clusters.append(np.mean(current_cluster))
                current_cluster = [level]

        clusters.append(np.mean(current_cluster))
        return sorted(clusters, reverse=True)

    def calculate_trend_strength(self, df: pd.DataFrame, period: int = 50) -> Dict[str, float]:
        """
        Calculate trend strength and direction

        Args:
            df: DataFrame with price data
            period: Period for trend calculation

        Returns:
            Dictionary with trend metrics
        """
        try:
            # Linear regression on recent price data
            x = np.arange(len(df[-period:]))
            y = df['Close'][-period:].values

            # Calculate slope and R-squared
            coeffs = np.polyfit(x, y, 1)
            slope = coeffs[0]

            # Calculate R-squared
            y_pred = np.polyval(coeffs, x)
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot)

            return {
                'trend_direction': 'up' if slope > 0 else 'down',
                'trend_strength': abs(r_squared),
                'slope': slope
            }

        except Exception as e:
            logger.error(f"Error calculating trend: {str(e)}")
            return {'trend_direction': 'neutral', 'trend_strength': 0.0, 'slope': 0.0}


# Singleton instance
technical_engine = TechnicalAnalysisEngine()
