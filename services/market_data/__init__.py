"""
market_data — unified abstraction over stock/market data providers.

Public API:
    from services.market_data import MarketDataProvider, get_default_provider

The default provider currently wraps yfinance. Additional providers (Upstox,
Kite, etc.) can be added under providers/ and selected via get_provider(name).

This package is purely additive. Existing call sites in stock_service.py,
finance_orchestrator.py, etc. continue to work unchanged. Migration to the
abstraction happens incrementally.
"""

from services.market_data.base import (
    MarketDataProvider,
    Quote,
    Candle,
    SymbolMatch,
    Fundamentals,
    MarketDataError,
)
from services.market_data.cache import CachedMarketDataProvider
from services.market_data.router import RoutedMarketDataProvider


def get_default_provider() -> MarketDataProvider:
    """
    Returns the default market data provider.

    Composition (outer to inner):
        CachedMarketDataProvider
          └── RoutedMarketDataProvider
                ├── UpstoxProvider   (preferred — real-time NSE data)
                └── YFinanceProvider (fallback — always available)

    If Upstox is not authenticated, every call transparently falls through
    to yfinance. If Redis is unavailable, caching is a no-op. Each layer
    degrades gracefully and the full chain behaves like plain yfinance in
    the worst case.
    """
    from services.market_data.providers.upstox_provider import UpstoxProvider
    from services.market_data.providers.yfinance_provider import YFinanceProvider
    routed = RoutedMarketDataProvider([UpstoxProvider(), YFinanceProvider()])
    return CachedMarketDataProvider(routed)


def get_provider(name: str, *, cached: bool = True) -> MarketDataProvider:
    """Get a specific provider by name. Raises ValueError if unknown."""
    name = name.lower().strip()
    if name in ("yfinance", "yf"):
        from services.market_data.providers.yfinance_provider import YFinanceProvider
        inner = YFinanceProvider()
        return CachedMarketDataProvider(inner) if cached else inner
    if name in ("upstox",):
        from services.market_data.providers.upstox_provider import UpstoxProvider
        inner = UpstoxProvider()
        return CachedMarketDataProvider(inner) if cached else inner
    if name in ("default", "routed"):
        return get_default_provider()
    raise ValueError(f"Unknown market data provider: {name!r}")


__all__ = [
    "MarketDataProvider",
    "CachedMarketDataProvider",
    "RoutedMarketDataProvider",
    "Quote",
    "Candle",
    "SymbolMatch",
    "Fundamentals",
    "MarketDataError",
    "get_default_provider",
    "get_provider",
]
