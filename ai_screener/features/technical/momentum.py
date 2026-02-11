"""Momentum-based technical features for pre-momentum detection."""
import pandas as pd
import numpy as np


class MomentumFeatures:
    """Compute momentum indicators optimized for 1-4 week prediction."""

    @staticmethod
    def compute_all(df: pd.DataFrame, timeframe: str = "1d") -> dict:
        """Compute all momentum features from OHLCV DataFrame.

        Args:
            df: DataFrame with columns [timestamp, open, high, low, close, volume]
                sorted by timestamp ascending, minimum 60 rows.
            timeframe: "1d", "1h", or "15m". Intraday skips long-period features.
        Returns:
            Dict of feature_name: value (latest values only)
        """
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        is_daily = timeframe == "1d"

        features = {}

        # RSI at multiple timeframes
        for period in [5, 14, 21]:
            features[f"rsi_{period}"] = MomentumFeatures._rsi(close, period)

        # RSI divergence
        features["rsi_bullish_divergence"] = MomentumFeatures._rsi_divergence(close, 14)

        # MACD
        macd, signal, hist = MomentumFeatures._macd(close)
        features["macd_value"] = macd
        features["macd_signal"] = signal
        features["macd_histogram"] = hist
        prev_hist = MomentumFeatures._macd(close[:-1])[2] if len(close) > 1 else 0
        features["macd_crossover"] = 1.0 if hist > 0 and prev_hist <= 0 else 0.0

        # Rate of Change
        for period in [5, 10, 21, 63]:
            if len(close) > period:
                features[f"roc_{period}"] = (close[-1] / close[-period] - 1) * 100

        # Momentum percentile — needs 252+ bars, daily only
        if is_daily:
            for period in [10, 21]:
                if len(close) > period + 252:
                    returns = pd.Series(close).pct_change(period).dropna()
                    current = returns.iloc[-1]
                    features[f"momentum_percentile_{period}"] = (returns < current).mean() * 100

        # Williams %R
        for period in [14, 28]:
            if len(close) >= period:
                highest_high = max(high[-period:])
                lowest_low = min(low[-period:])
                if highest_high != lowest_low:
                    features[f"williams_r_{period}"] = (
                        (highest_high - close[-1]) / (highest_high - lowest_low) * -100
                    )

        # Stochastic
        features.update(MomentumFeatures._stochastic(high, low, close, 14, 3))

        # Momentum acceleration
        if len(close) > 21:
            mom_10 = pd.Series(close).pct_change(10)
            features["momentum_acceleration"] = float(mom_10.iloc[-1] - mom_10.iloc[-6])

        # Price vs moving averages — skip MA-200 on intraday
        ma_periods = [10, 20, 50, 200] if is_daily else [10, 20, 50]
        for period in ma_periods:
            if len(close) >= period:
                ma = np.mean(close[-period:])
                features[f"price_vs_ma_{period}"] = (close[-1] / ma - 1) * 100

        # MA50 vs MA200 — daily only
        if is_daily and len(close) >= 200:
            ma50 = np.mean(close[-50:])
            ma200 = np.mean(close[-200:])
            features["ma50_vs_ma200"] = (ma50 / ma200 - 1) * 100
            features["ma_cross_proximity"] = abs(ma50 - ma200) / ma200 * 100

        return features

    @staticmethod
    def _rsi(close: np.ndarray, period: int = 14) -> float:
        if len(close) < period + 1:
            return 50.0
        deltas = np.diff(close[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains) if np.any(gains) else 0.001
        avg_loss = np.mean(losses) if np.any(losses) else 0.001
        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))

    @staticmethod
    def _rsi_divergence(close: np.ndarray, period: int = 14, lookback: int = 20) -> float:
        if len(close) < lookback + period:
            return 0.0
        rsi_values = []
        for i in range(lookback):
            end_idx = len(close) - lookback + i + 1
            rsi_values.append(MomentumFeatures._rsi(close[:end_idx], period))
        price_window = close[-lookback:]
        if len(price_window) <= 5:
            return 0.0
        price_at_end = price_window[-1]
        price_min = np.min(price_window[:-5])
        rsi_at_end = rsi_values[-1]
        min_idx = int(np.argmin(price_window[:-5]))
        rsi_at_price_min = rsi_values[min_idx] if min_idx < len(rsi_values) else rsi_values[0]
        if price_at_end <= price_min * 1.02 and rsi_at_end > rsi_at_price_min:
            return 1.0
        return 0.0

    @staticmethod
    def _macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
        if len(close) < slow + signal:
            return 0.0, 0.0, 0.0
        series = pd.Series(close)
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])

    @staticmethod
    def _stochastic(high, low, close, k_period=14, d_period=3) -> dict:
        if len(close) < k_period + d_period:
            return {"stoch_k": 50.0, "stoch_d": 50.0}
        k_values = []
        for i in range(d_period):
            offset = -(d_period - i) if i < d_period - 1 else None
            end = len(close) + (offset if offset else 0)
            start = max(0, end - k_period)
            hh = max(high[start:end])
            ll = min(low[start:end])
            if hh != ll:
                k_values.append((close[end - 1] - ll) / (hh - ll) * 100)
            else:
                k_values.append(50.0)
        return {"stoch_k": k_values[-1], "stoch_d": float(np.mean(k_values))}
