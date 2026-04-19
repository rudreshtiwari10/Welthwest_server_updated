"""
Abstract base class and data contracts for market data providers.

Every provider (yfinance, Upstox, Kite, etc.) implements MarketDataProvider.
Tools and services depend on this interface, never on a specific provider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


class MarketDataError(Exception):
    """Base exception for market data provider failures."""
    pass


class SymbolNotFoundError(MarketDataError):
    """Raised when a symbol cannot be resolved."""
    pass


class ProviderUnavailableError(MarketDataError):
    """Raised when the upstream provider is rate-limited or down."""
    pass


@dataclass
class Quote:
    """A point-in-time quote for an instrument."""
    symbol: str
    price: float
    currency: str = "INR"
    change: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    open: Optional[float] = None
    previous_close: Optional[float] = None
    timestamp: Optional[datetime] = None
    exchange: Optional[str] = None
    extras: dict = field(default_factory=dict)


@dataclass
class Candle:
    """A single OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class SymbolMatch:
    """A candidate result from symbol search."""
    symbol: str
    name: str
    exchange: str
    confidence: float = 1.0
    isin: Optional[str] = None
    sector: Optional[str] = None


@dataclass
class Fundamentals:
    """Fundamental metrics for an instrument. All fields optional — providers
    fill what they can."""
    symbol: str
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    eps: Optional[float] = None
    dividend_yield: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    debt_to_equity: Optional[float] = None
    book_value: Optional[float] = None
    face_value: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    extras: dict = field(default_factory=dict)


class MarketDataProvider(ABC):
    """
    Abstract contract every market data provider must implement.

    Providers should:
      - Raise SymbolNotFoundError for unknown symbols (not return None silently).
      - Raise ProviderUnavailableError on rate-limits / upstream outages.
      - Return typed dataclasses, never raw dicts from upstream APIs.
      - Be safe to instantiate cheaply (lazy-import heavy deps inside methods).
    """

    name: str = "abstract"

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """Return the latest available quote for a symbol."""
        raise NotImplementedError

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> list[Candle]:
        """
        Return OHLCV candles for a symbol.

        period:   "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"
        interval: "1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"
        """
        raise NotImplementedError

    @abstractmethod
    def search_symbols(self, query: str, limit: int = 5) -> list[SymbolMatch]:
        """Return ranked candidate matches for a free-text query."""
        raise NotImplementedError

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Return fundamental metrics for a symbol."""
        raise NotImplementedError

    # ---- Optional methods (providers may override; default raises) ----

    def get_index_quote(self, index: str) -> Quote:
        """Return a quote for an index (NIFTY, SENSEX, etc.)."""
        raise NotImplementedError(f"{self.name} does not support index quotes")

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        """Return dividends, splits, bonuses, etc."""
        raise NotImplementedError(f"{self.name} does not support corporate actions")

    def health_check(self) -> bool:
        """Return True if the provider is currently reachable."""
        try:
            self.get_quote("RELIANCE")
            return True
        except Exception:
            return False
