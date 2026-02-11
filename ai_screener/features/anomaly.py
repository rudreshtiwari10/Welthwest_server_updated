"""Anomaly detection features for the AI Screener.

Computes anomaly flags per stock per timeframe and returns both
feature keys (for scoring) and structured anomaly records (for the API).

Each anomaly now scans a recent window of bars (not just the last bar)
and records *when* the anomaly was detected: bar_index, timestamp, bars_ago.
"""
import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple

from ai_screener.config.settings import ANOMALY_THRESHOLDS

logger = logging.getLogger(__name__)

# How many recent bars each anomaly scanner should inspect
_SCAN_WINDOW = 60


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """Compute the rolling z-score of a series."""
    rolling_mean = series.rolling(window).mean()
    rolling_std = series.rolling(window).std(ddof=0)
    return (series - rolling_mean) / rolling_std.replace(0, np.nan)


def _make_record(
    code: str,
    name: str,
    severity: str,
    timeframe: str,
    window_bars: int,
    current_value: float,
    threshold: float,
    supporting: List[str],
    bar_index: int,
    timestamp: str,
    bars_ago: int,
) -> dict:
    return {
        "code": code,
        "name": name,
        "severity": severity,
        "timeframe": timeframe,
        "window_bars": window_bars,
        "bar_index": bar_index,
        "timestamp": timestamp,
        "bars_ago": bars_ago,
        "details": {
            "current_value": round(current_value, 4),
            "threshold": round(threshold, 4),
            "supporting_features": supporting,
        },
    }


def _ts_at(df: pd.DataFrame, idx: int) -> str:
    """Return the ISO-8601 timestamp string for a positional index in *df*."""
    try:
        ts = df["timestamp"].iloc[idx]
        if hasattr(ts, "isoformat"):
            return ts.isoformat()
        return str(ts)
    except Exception:
        return ""


def _last_true(mask: np.ndarray, offset: int) -> int:
    """Return the absolute bar index of the last True in *mask*.

    *offset* is the starting position of *mask* inside the full DataFrame.
    Returns -1 if nothing is True.
    """
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return -1
    return int(indices[-1]) + offset


class AnomalyFeatures:
    """Compute anomaly detection features from OHLCV data and existing features."""

    @staticmethod
    def compute(
        df: pd.DataFrame,
        features: dict,
        timeframe: str = "1d",
    ) -> Tuple[Dict, List[Dict]]:
        """Return (updated_features_dict, anomaly_records_list).

        Each anomaly scanner inspects the most recent *_SCAN_WINDOW* bars and
        records the last bar where the trigger condition held, along with
        bar_index / timestamp / bars_ago metadata.
        """
        anomalies: List[dict] = []

        if df.empty or len(df) < 20:
            return features, anomalies

        n = len(df)
        close = df["close"].values.astype(float)
        opn = df["open"].values.astype(float)
        volume = df["volume"].values.astype(float)

        T = ANOMALY_THRESHOLDS
        scan_start = max(0, n - _SCAN_WINDOW)

        # ── helpers to build series over the full df ──────────────────────

        # Volume ratio series (10-bar)
        vol_series_10 = pd.Series(volume)
        vol_ratio_10_series = (
            vol_series_10.rolling(10).mean()
            / vol_series_10.rolling(20).mean().shift(10)
        ).values
        # fix any inf/nan
        vol_ratio_10_series = np.where(
            np.isfinite(vol_ratio_10_series), vol_ratio_10_series, 1.0
        )

        # Volume ratio series (20-bar)
        vol_ratio_20_series = (
            vol_series_10.rolling(20).mean()
            / vol_series_10.rolling(40).mean().shift(20)
        ).values
        vol_ratio_20_series = np.where(
            np.isfinite(vol_ratio_20_series), vol_ratio_20_series, 1.0
        )

        # Gap % series (open_t vs close_{t-1})
        gap_pct_series = np.zeros(n)
        gap_pct_series[1:] = (opn[1:] - close[:-1]) / np.where(close[:-1] != 0, close[:-1], 1.0) * 100

        # Bar return series (close - open) / open
        bar_ret_series = np.where(opn != 0, (close - opn) / opn * 100, 0.0)

        # RSI-14 series (simple Wilder smoothing)
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0).rolling(14).mean().values
        loss = (-delta.clip(upper=0)).rolling(14).mean().values
        rs = np.where(loss != 0, gain / loss, 100.0)
        rsi_14_series = 100.0 - 100.0 / (1.0 + rs)

        # ROC-10 series
        roc_10_series = np.zeros(n)
        roc_10_series[10:] = (close[10:] / np.where(close[:-10] != 0, close[:-10], 1.0) - 1) * 100

        # ROC-5 series
        roc_5_series = np.zeros(n)
        roc_5_series[5:] = (close[5:] / np.where(close[:-5] != 0, close[:-5], 1.0) - 1) * 100

        # ── 3.1 Extreme Volume Spike ──────────────────────────────────────
        try:
            threshold = T["VOLUME_SPIKE_EXTREME_THRESHOLD"]
            recent = vol_ratio_10_series[scan_start:]
            mask = recent >= threshold
            idx = _last_true(mask, scan_start)
            if idx >= 0:
                val = float(vol_ratio_10_series[idx])
                features["anomaly_volume_spike"] = 1.0
                severity = "critical" if val >= 5.0 else "high"
                anomalies.append(_make_record(
                    "VOLUME_SPIKE_EXTREME", "Extreme Volume Spike", severity,
                    timeframe, 10, val, threshold,
                    ["vol_volume_ratio_10", "vol_relative_volume"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_volume_spike"] = 0.0
        except Exception as e:
            logger.debug(f"Volume spike anomaly failed: {e}")
            features["anomaly_volume_spike"] = 0.0

        # ── 3.2 Volume Dry-Up ─────────────────────────────────────────────
        try:
            threshold = T["VOLUME_DRYUP_THRESHOLD"]
            recent = vol_ratio_20_series[scan_start:]
            mask = recent <= threshold
            idx = _last_true(mask, scan_start)
            if idx >= 0:
                val = float(vol_ratio_20_series[idx])
                features["anomaly_volume_dryup"] = 1.0
                anomalies.append(_make_record(
                    "VOLUME_DRYUP", "Volume Dry-Up (Illiquidity Risk)", "medium",
                    timeframe, 20, val, threshold,
                    ["vol_volume_ratio_20"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_volume_dryup"] = 0.0
        except Exception as e:
            logger.debug(f"Volume dryup anomaly failed: {e}")
            features["anomaly_volume_dryup"] = 0.0

        # ── 3.3 Price Gap Up / Down ───────────────────────────────────────
        try:
            gap_up_thresh = T["GAP_UP_THRESHOLD"]
            gap_down_thresh = T["GAP_DOWN_THRESHOLD"]
            recent_gap = gap_pct_series[scan_start:]

            # Gap up
            mask_up = recent_gap >= gap_up_thresh
            idx = _last_true(mask_up, scan_start)
            if idx >= 0:
                val = float(gap_pct_series[idx])
                features["anomaly_gap_up"] = 1.0
                severity = "high" if val >= 5.0 else "medium"
                anomalies.append(_make_record(
                    "GAP_UP", "Gap Up Shock", severity,
                    timeframe, 1, val, gap_up_thresh,
                    ["open", "prev_close"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_gap_up"] = 0.0

            # Gap down
            mask_down = recent_gap <= -gap_down_thresh
            idx = _last_true(mask_down, scan_start)
            if idx >= 0:
                val = float(gap_pct_series[idx])
                features["anomaly_gap_down"] = 1.0
                severity = "high" if val <= -5.0 else "medium"
                anomalies.append(_make_record(
                    "GAP_DOWN", "Gap Down Shock", severity,
                    timeframe, 1, val, -gap_down_thresh,
                    ["open", "prev_close"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_gap_down"] = 0.0
        except Exception as e:
            logger.debug(f"Gap anomaly failed: {e}")
            features["anomaly_gap_up"] = 0.0
            features["anomaly_gap_down"] = 0.0

        # ── 3.4 Flash Crash / Flash Pump ──────────────────────────────────
        try:
            crash_thresh = T["FLASH_CRASH_THRESHOLD"].get(timeframe, -3.0)
            pump_thresh = T["FLASH_PUMP_THRESHOLD"].get(timeframe, 3.0)
            recent_ret = bar_ret_series[scan_start:]

            # Flash crash
            mask_crash = recent_ret <= crash_thresh
            idx = _last_true(mask_crash, scan_start)
            if idx >= 0:
                val = float(bar_ret_series[idx])
                features["anomaly_flash_crash"] = 1.0
                severity = "critical" if val <= crash_thresh * 2 else "high"
                anomalies.append(_make_record(
                    "FLASH_CRASH", "Flash Crash (Single Bar)", severity,
                    timeframe, 1, val, crash_thresh,
                    ["bar_return"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_flash_crash"] = 0.0

            # Flash pump
            mask_pump = recent_ret >= pump_thresh
            idx = _last_true(mask_pump, scan_start)
            if idx >= 0:
                val = float(bar_ret_series[idx])
                features["anomaly_flash_pump"] = 1.0
                anomalies.append(_make_record(
                    "FLASH_PUMP", "Flash Pump (Single Bar)", "high",
                    timeframe, 1, val, pump_thresh,
                    ["bar_return"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_flash_pump"] = 0.0
        except Exception as e:
            logger.debug(f"Flash crash/pump anomaly failed: {e}")
            features["anomaly_flash_crash"] = 0.0
            features["anomaly_flash_pump"] = 0.0

        # ── 3.5 Volatility Regime Spike ───────────────────────────────────
        try:
            window = T["VOL_SPIKE_WINDOW"]
            z_thresh = T["VOL_SPIKE_Z_THRESHOLD"]
            if n > window + 10:
                returns = pd.Series(close).pct_change().dropna()
                vol_rolling = returns.rolling(window).std()
                vol_z = rolling_zscore(vol_rolling, window * 3).values

                # scan recent window (aligned to returns which is 1 shorter)
                scan_s = max(0, len(vol_z) - _SCAN_WINDOW)
                recent_z = vol_z[scan_s:]
                mask = np.array([v >= z_thresh if np.isfinite(v) else False for v in recent_z])
                rel_idx = _last_true(mask, 0)
                if rel_idx >= 0:
                    # map back to df index: returns series is offset by 1 from df
                    abs_idx = scan_s + rel_idx + 1
                    abs_idx = min(abs_idx, n - 1)
                    val = float(vol_z[scan_s + rel_idx]) if np.isfinite(vol_z[scan_s + rel_idx]) else 0.0
                    features["anomaly_vol_spike"] = 1.0
                    anomalies.append(_make_record(
                        "VOLATILITY_SPIKE", "Volatility Regime Spike", "high",
                        timeframe, window, val, z_thresh,
                        ["rolling_volatility"],
                        bar_index=abs_idx, timestamp=_ts_at(df, abs_idx), bars_ago=n - 1 - abs_idx,
                    ))
                else:
                    features["anomaly_vol_spike"] = 0.0
            else:
                features["anomaly_vol_spike"] = 0.0
        except Exception as e:
            logger.debug(f"Volatility spike anomaly failed: {e}")
            features["anomaly_vol_spike"] = 0.0

        # ── 3.6 Parabolic Move / Blow-Off Top ────────────────────────────
        try:
            parabolic_thresh = T["PARABOLIC_ROC_THRESHOLD"]
            recent_roc = roc_10_series[scan_start:]
            recent_rsi = rsi_14_series[scan_start:]
            recent_vol = vol_ratio_10_series[scan_start:]

            mask = (recent_roc >= parabolic_thresh) & (recent_rsi >= 75) & (recent_vol >= 2.0)
            idx = _last_true(mask, scan_start)
            if idx >= 0:
                val = float(roc_10_series[idx])
                features["anomaly_parabolic_up"] = 1.0
                anomalies.append(_make_record(
                    "PARABOLIC_MOVE_UP", "Parabolic Move / Blow-Off Top", "high",
                    timeframe, 10, val, parabolic_thresh,
                    ["tech_roc_10", "tech_rsi_14", "vol_volume_ratio_10"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_parabolic_up"] = 0.0
        except Exception as e:
            logger.debug(f"Parabolic anomaly failed: {e}")
            features["anomaly_parabolic_up"] = 0.0

        # ── 3.7 Buying / Selling Climax ───────────────────────────────────
        try:
            climax_vol = T["CLIMAX_VOL_RATIO"]
            stall = T["CLIMAX_STALL_PCT"]
            recent_rsi = rsi_14_series[scan_start:]
            recent_vol = vol_ratio_10_series[scan_start:]
            recent_roc5 = roc_5_series[scan_start:]
            recent_bar = bar_ret_series[scan_start:]

            # Buying climax
            mask_buy = (
                (recent_rsi >= T["CLIMAX_RSI_HIGH"])
                & (recent_vol >= climax_vol)
                & (recent_roc5 > 0)
                & (recent_bar < stall)
            )
            idx = _last_true(mask_buy, scan_start)
            if idx >= 0:
                val = float(rsi_14_series[idx])
                features["anomaly_buying_climax"] = 1.0
                anomalies.append(_make_record(
                    "BUYING_CLIMAX", "Buying Climax (Exhaustion)", "high",
                    timeframe, 5, val, float(T["CLIMAX_RSI_HIGH"]),
                    ["tech_rsi_14", "vol_volume_ratio_10", "tech_roc_5"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_buying_climax"] = 0.0

            # Selling climax
            mask_sell = (
                (recent_rsi <= T["CLIMAX_RSI_LOW"])
                & (recent_vol >= climax_vol)
                & (recent_roc5 < 0)
                & (recent_bar > -stall)
            )
            idx = _last_true(mask_sell, scan_start)
            if idx >= 0:
                val = float(rsi_14_series[idx])
                features["anomaly_selling_climax"] = 1.0
                anomalies.append(_make_record(
                    "SELLING_CLIMAX", "Selling Climax (Capitulation)", "high",
                    timeframe, 5, val, float(T["CLIMAX_RSI_LOW"]),
                    ["tech_rsi_14", "vol_volume_ratio_10", "tech_roc_5"],
                    bar_index=idx, timestamp=_ts_at(df, idx), bars_ago=n - 1 - idx,
                ))
            else:
                features["anomaly_selling_climax"] = 0.0
        except Exception as e:
            logger.debug(f"Climax anomaly failed: {e}")
            features["anomaly_buying_climax"] = 0.0
            features["anomaly_selling_climax"] = 0.0

        # ── 3.8 Smart Money Divergence (Meta-Anomaly) ─────────────────────
        # This one uses pre-computed scalar features so we keep last-bar logic
        # but still emit the timing metadata pointing to the latest bar.
        try:
            rsi_div = features.get("tech_rsi_bullish_divergence", 0.0) or 0.0
            obv_div = features.get("vol_obv_price_divergence", 0.0) or 0.0
            rsi_14_val = features.get("tech_rsi_14", 50.0) or 50.0

            if rsi_div == 1.0 and obv_div > 0:
                features["anomaly_smart_money_divergence"] = 1.0
                anomalies.append(_make_record(
                    "SMART_MONEY_DIVERGENCE_BULL", "Smart Money Accumulation", "medium",
                    timeframe, 20, obv_div, 0.0,
                    ["tech_rsi_bullish_divergence", "vol_obv_price_divergence"],
                    bar_index=n - 1, timestamp=_ts_at(df, n - 1), bars_ago=0,
                ))
            elif obv_div < 0 and rsi_14_val > 60:
                features["anomaly_smart_money_divergence"] = -1.0
                anomalies.append(_make_record(
                    "SMART_MONEY_DIVERGENCE_BEAR", "Smart Money Distribution", "medium",
                    timeframe, 20, obv_div, 0.0,
                    ["vol_obv_price_divergence", "tech_rsi_14"],
                    bar_index=n - 1, timestamp=_ts_at(df, n - 1), bars_ago=0,
                ))
            else:
                features["anomaly_smart_money_divergence"] = 0.0
        except Exception as e:
            logger.debug(f"Smart money divergence anomaly failed: {e}")
            features["anomaly_smart_money_divergence"] = 0.0

        return features, anomalies
