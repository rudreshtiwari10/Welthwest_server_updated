"""Central configuration for the WelthWest AI Screener."""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache

# ── Multi-timeframe configuration ─────────────────────────────────────
VALID_TIMEFRAMES = ["1d", "1h", "15m"]

TIMEFRAME_CONFIG = {
    "1d": {
        "bars_per_day": 1,
        "max_history_days": 365,
        "annualization": 252,
        "min_bars": 60,
    },
    "1h": {
        "bars_per_day": 7,
        "max_history_days": 60,
        "annualization": 1764,
        "min_bars": 60,
    },
    "15m": {
        "bars_per_day": 26,
        "max_history_days": 60,
        "annualization": 6552,
        "min_bars": 60,
    },
}

# Features that require long history and must be skipped on intraday timeframes
INTRADAY_SKIP_FEATURES = [
    "ma50_vs_ma200",
    "ma_cross_proximity",
    "momentum_percentile_10",
    "momentum_percentile_21",
    "price_vs_ma_200",
]

# ── Anomaly Detection Thresholds ─────────────────────────────────────
ANOMALY_THRESHOLDS = {
    # 3.1 Extreme Volume Spike
    "VOLUME_SPIKE_EXTREME_THRESHOLD": 3.0,
    # 3.2 Volume Dry-Up
    "VOLUME_DRYUP_THRESHOLD": 0.4,
    # 3.3 Price Gap
    "GAP_UP_THRESHOLD": 3.0,   # percent
    "GAP_DOWN_THRESHOLD": 3.0,  # percent
    # 3.4 Flash Crash / Pump (per-timeframe)
    "FLASH_CRASH_THRESHOLD": {"1d": -2.0, "1h": -3.0, "15m": -5.0},
    "FLASH_PUMP_THRESHOLD": {"1d": 2.0, "1h": 3.0, "15m": 5.0},
    # 3.5 Volatility Regime Spike
    "VOL_SPIKE_Z_THRESHOLD": 2.5,
    "VOL_SPIKE_WINDOW": 20,
    # 3.6 Parabolic Move / Blow-Off Top
    "PARABOLIC_ROC_THRESHOLD": 15.0,  # percent
    # 3.7 Buying / Selling Climax
    "CLIMAX_RSI_HIGH": 80,
    "CLIMAX_RSI_LOW": 25,
    "CLIMAX_VOL_RATIO": 2.5,
    "CLIMAX_STALL_PCT": 0.5,
    # 3.9 Wide Spread / Liquidity Risk
    "SPREAD_THRESHOLD": 1.0,  # percent
}


class Settings(BaseSettings):
    # App
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # Indian Market
    primary_exchange: str = Field(default="NSE")
    yfinance_suffix: str = Field(default=".NS")
    default_currency: str = Field(default="INR")
    market_timezone: str = Field(default="Asia/Kolkata")
    market_open_time: str = Field(default="09:15")
    market_close_time: str = Field(default="15:30")

    # Universe
    screener_universe: str = Field(default="NIFTY500")
    screener_universe_size: int = Field(default=500)

    # Model / Screening
    prediction_horizon_days: int = Field(default=10)
    lookback_window_days: int = Field(default=252)
    min_history_days: int = Field(default=60)
    top_n_stocks: int = Field(default=50)
    min_market_cap_inr: float = Field(default=500_00_00_000)
    min_avg_volume: int = Field(default=50_000)

    # Regime Detection
    hmm_n_states: int = Field(default=5)
    regime_lookback_days: int = Field(default=504)
    regime_index_symbol: str = Field(default="^NSEI")
    regime_vix_symbol: str = Field(default="^INDIAVIX")

    # India-Specific Thresholds
    max_promoter_pledge_pct: float = Field(default=50.0)
    fii_dii_lookback_days: int = Field(default=30)
    circuit_limit_filter: bool = Field(default=True)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def nifty50_symbols(self) -> list[str]:
        """Top NIFTY 50 symbols."""
        return [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
            "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT", "MARUTI",
            "HCLTECH", "SUNPHARMA", "TATAMOTORS", "TITAN", "NTPC",
            "WIPRO", "ULTRACEMCO", "POWERGRID", "NESTLEIND", "TATASTEEL",
            "TECHM", "JSWSTEEL", "ADANIENT", "ADANIPORTS",
            "BAJAJFINSV", "ONGC", "COALINDIA", "HINDALCO", "GRASIM",
            "DIVISLAB", "DRREDDY", "BPCL", "CIPLA", "EICHERMOT",
            "HEROMOTOCO", "APOLLOHOSP", "TATACONSUM", "SBILIFE", "INDUSINDBK",
            "BRITANNIA", "HDFCLIFE", "LTIM", "SHRIRAMFIN",
        ]

    @property
    def yf_nifty50_symbols(self) -> list[str]:
        return [f"{s}{self.yfinance_suffix}" for s in self.nifty50_symbols]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
