"""
RoutedMarketDataProvider — tries providers in order and falls back.

Given a preferred provider (e.g., Upstox) and a fallback (e.g., yfinance),
every method call is attempted on the preferred provider first. If it raises
ProviderUnavailableError (auth not ready, rate-limited, upstream 5xx), the
call is retried on the fallback transparently.

SymbolNotFoundError is NOT fallback-triggering — if the preferred provider
definitively says "no such symbol", we trust it and raise immediately.
"""

import logging
from typing import Callable

from services.market_data.base import (
    Candle,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    ProviderUnavailableError,
    Quote,
    SymbolMatch,
    SymbolNotFoundError,
)

logger = logging.getLogger(__name__)


class RoutedMarketDataProvider(MarketDataProvider):
    """Chain of MarketDataProviders with automatic failover."""

    def __init__(self, providers: list[MarketDataProvider]):
        if not providers:
            raise ValueError("RoutedMarketDataProvider needs at least one provider")
        self._providers = providers
        self.name = "routed:" + "+".join(p.name for p in providers)

    def _try_chain(self, method_name: str, *args, **kwargs):
        last_err: Exception | None = None
        for provider in self._providers:
            try:
                return getattr(provider, method_name)(*args, **kwargs)
            except SymbolNotFoundError:
                # Definitive negative — don't keep retrying.
                raise
            except ProviderUnavailableError as e:
                logger.debug(
                    "provider %s unavailable for %s(%s, %s): %s",
                    provider.name, method_name, args, kwargs, e,
                )
                last_err = e
                continue
            except NotImplementedError as e:
                last_err = e
                continue
            except Exception as e:
                logger.warning(
                    "provider %s raised unexpected error on %s: %s",
                    provider.name, method_name, e,
                )
                last_err = e
                continue

        raise ProviderUnavailableError(
            f"All providers exhausted for {method_name}"
        ) from last_err

    # ---- MarketDataProvider interface ----

    def get_quote(self, symbol: str) -> Quote:
        return self._try_chain("get_quote", symbol)

    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> list[Candle]:
        return self._try_chain(
            "get_history", symbol, period=period, interval=interval
        )

    def search_symbols(self, query: str, limit: int = 5) -> list[SymbolMatch]:
        # Search is additive — collect from all providers, de-dup by symbol.
        seen: dict[str, SymbolMatch] = {}
        for provider in self._providers:
            try:
                for match in provider.search_symbols(query, limit=limit):
                    if match.symbol not in seen:
                        seen[match.symbol] = match
                        if len(seen) >= limit:
                            return list(seen.values())
            except Exception as e:
                logger.debug(
                    "provider %s search_symbols failed: %s", provider.name, e
                )
                continue
        return list(seen.values())

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        return self._try_chain("get_fundamentals", symbol)

    def get_index_quote(self, index: str) -> Quote:
        return self._try_chain("get_index_quote", index)

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        return self._try_chain("get_corporate_actions", symbol)

    def get_financials(
        self,
        symbol: str,
        statement: str = "income",
        period: str = "quarterly",
        num_periods: int = 4,
    ) -> dict:
        return self._try_chain(
            "get_financials", symbol, statement, period, num_periods
        )

    def health_check(self) -> bool:
        return any(p.health_check() for p in self._providers)
