"""Volume-based features -- critical for detecting accumulation before breakouts."""
import pandas as pd
import numpy as np


class VolumeFeatures:
    """Volume analysis for detecting smart money accumulation/distribution."""

    @staticmethod
    def compute_all(df: pd.DataFrame, timeframe: str = "1d") -> dict:
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values.astype(float)

        features = {}

        # Volume trend
        for period in [5, 10, 20]:
            if len(volume) >= period * 2:
                recent_avg = np.mean(volume[-period:])
                prior_avg = np.mean(volume[-period * 2 : -period])
                features[f"volume_ratio_{period}"] = float(recent_avg / prior_avg if prior_avg > 0 else 1.0)

        # OBV trend
        obv = VolumeFeatures._obv(close, volume)
        features["obv_slope_10"] = VolumeFeatures._slope(obv, 10)
        features["obv_slope_20"] = VolumeFeatures._slope(obv, 20)

        # OBV divergence from price
        if len(close) >= 20:
            price_slope = VolumeFeatures._slope(close, 20)
            obv_slope = VolumeFeatures._slope(obv, 20)
            features["obv_price_divergence"] = float(obv_slope - price_slope)

        # Accumulation/Distribution
        ad = VolumeFeatures._ad_line(high, low, close, volume)
        features["ad_slope_10"] = VolumeFeatures._slope(ad, 10)

        # Money Flow Index
        features["mfi_14"] = VolumeFeatures._mfi(high, low, close, volume, 14)

        # Chaikin Money Flow
        features["cmf_20"] = VolumeFeatures._cmf(high, low, close, volume, 20)

        # Relative Volume
        if len(volume) >= 20:
            avg20 = np.mean(volume[-20:])
            features["relative_volume"] = float(volume[-1] / avg20 if avg20 > 0 else 1.0)

        # Volume concentration
        if len(volume) >= 60:
            vol_90th = np.percentile(volume[-60:], 90)
            recent_big_days = int(np.sum(volume[-10:] > vol_90th))
            features["volume_concentration_10d"] = float(recent_big_days)

        # Up vs down volume ratio
        if len(close) >= 21:
            returns = np.diff(close[-21:])
            vol_slice = volume[-20:]
            up_vol = float(np.sum(vol_slice[returns > 0]))
            down_vol = float(np.sum(vol_slice[returns < 0]))
            features["up_down_volume_ratio"] = up_vol / down_vol if down_vol > 0 else 2.0

        return features

    @staticmethod
    def _obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        obv = np.zeros_like(volume)
        obv[0] = volume[0]
        for i in range(1, len(close)):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]
        return obv

    @staticmethod
    def _ad_line(high, low, close, volume) -> np.ndarray:
        denom = high - low
        denom = np.where(denom == 0, 1, denom)
        clv = ((close - low) - (high - close)) / denom
        clv = np.where(high == low, 0, clv)
        return np.cumsum(clv * volume)

    @staticmethod
    def _mfi(high, low, close, volume, period=14) -> float:
        if len(close) < period + 1:
            return 50.0
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        tp_diff = np.diff(typical_price[-(period + 1) :])
        pos_flow = float(np.sum(money_flow[-period:][tp_diff > 0]))
        neg_flow = float(np.sum(money_flow[-period:][tp_diff <= 0]))
        if neg_flow == 0:
            return 100.0
        mfr = pos_flow / neg_flow
        return float(100 - (100 / (1 + mfr)))

    @staticmethod
    def _cmf(high, low, close, volume, period=20) -> float:
        if len(close) < period:
            return 0.0
        h = high[-period:]
        l = low[-period:]
        c = close[-period:]
        denom = h - l
        denom = np.where(denom == 0, 1, denom)
        clv = ((c - l) - (h - c)) / denom
        clv = np.where(h == l, 0, clv)
        vol_sum = float(np.sum(volume[-period:]))
        return float(np.sum(clv * volume[-period:]) / vol_sum) if vol_sum > 0 else 0.0

    @staticmethod
    def _slope(series: np.ndarray, period: int) -> float:
        if len(series) < period:
            return 0.0
        y = series[-period:]
        x = np.arange(period)
        if np.std(y) == 0:
            return 0.0
        slope = np.polyfit(x, y, 1)[0]
        mean_abs = float(np.mean(np.abs(y)))
        return float(slope / mean_abs) if mean_abs > 0 else 0.0
