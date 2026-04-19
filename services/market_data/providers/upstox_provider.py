"""
Upstox-backed MarketDataProvider.

Wraps the existing services/upstox_service.py helpers behind the
MarketDataProvider interface. Upstox is preferred over yfinance for Indian
equities when available because:
  - real-time quotes (yfinance is 15-min delayed for NSE)
  - native NSE/BSE support (no .NS suffix hacks)
  - higher reliability under load

Auth-gated: if no Upstox access token is configured, every method raises
ProviderUnavailableError so the router layer can fall back to yfinance.
"""

import logging
from datetime import datetime
from typing import Optional

from services.market_data.base import (
    Candle,
    Fundamentals,
    MarketDataProvider,
    ProviderUnavailableError,
    Quote,
    SymbolMatch,
    SymbolNotFoundError,
)

logger = logging.getLogger(__name__)


def _is_upstox_ready() -> bool:
    """Cheap check: does the Upstox API instance have an access token loaded?"""
    try:
        from services.upstox_service import upstox_api
        return bool(getattr(upstox_api, "access_token", None))
    except Exception:
        return False


class UpstoxProvider(MarketDataProvider):
    """MarketDataProvider backed by Upstox v2 API."""

    name = "upstox"

    def _require_ready(self) -> None:
        if not _is_upstox_ready():
            raise ProviderUnavailableError(
                "Upstox provider is not authenticated"
            )

    def get_quote(self, symbol: str) -> Quote:
        self._require_ready()
        try:
            from services.upstox_service import get_upstox_live_data
            data = get_upstox_live_data([symbol])
        except Exception as e:
            logger.debug("upstox get_quote call failed for %s: %s", symbol, e)
            raise ProviderUnavailableError(
                f"Could not fetch quote for {symbol!r}"
            ) from e

        row = data.get(symbol) if isinstance(data, dict) else None
        if not row or not row.get("price"):
            raise SymbolNotFoundError(f"No Upstox data for symbol {symbol!r}")

        try:
            timestamp = datetime.strptime(
                row.get("timestamp", ""), "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            timestamp = datetime.utcnow()

        return Quote(
            symbol=symbol.upper(),
            price=float(row.get("price") or 0),
            currency="INR",
            change=_maybe_float(row.get("change")),
            change_percent=_maybe_float(row.get("percentChange")),
            volume=_maybe_int(row.get("volume")),
            day_high=_maybe_float(row.get("dayHigh")),
            day_low=_maybe_float(row.get("dayLow")),
            open=_maybe_float(row.get("open")),
            previous_close=_maybe_float(row.get("previousClose")),
            timestamp=timestamp,
            exchange="NSE",
            extras={"source": "upstox"},
        )

    def get_history(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> list[Candle]:
        self._require_ready()
        # Map MarketDataProvider interval vocab → Upstox vocab.
        upstox_interval = _map_interval(interval)
        upstox_period = _map_period(period)

        try:
            from services.upstox_service import get_upstox_historical_data
            df = get_upstox_historical_data(
                symbol, period=upstox_period, interval=upstox_interval
            )
        except Exception as e:
            logger.debug("upstox get_history call failed for %s: %s", symbol, e)
            raise ProviderUnavailableError(
                f"Could not fetch history for {symbol!r}"
            ) from e

        if df is None or len(df) == 0:
            raise SymbolNotFoundError(f"No Upstox history for {symbol!r}")

        candles: list[Candle] = []
        for ts, row in df.iterrows():
            try:
                ts_dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
            except Exception:
                try:
                    ts_dt = datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
            try:
                candles.append(
                    Candle(
                        timestamp=ts_dt,
                        open=float(row.get("Open", row.get("open", 0))),
                        high=float(row.get("High", row.get("high", 0))),
                        low=float(row.get("Low", row.get("low", 0))),
                        close=float(row.get("Close", row.get("close", 0))),
                        volume=int(row.get("Volume", row.get("volume", 0)) or 0),
                    )
                )
            except Exception:
                continue
        return candles

    def search_symbols(self, query: str, limit: int = 5) -> list[SymbolMatch]:
        # Upstox has no free-text search; delegate to the shared resolver
        # when Phase 1.4 is wired up. For now return empty so the router
        # falls through to yfinance.search_symbols or the resolver directly.
        return []

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        # Upstox does not expose fundamentals; force fallback.
        raise ProviderUnavailableError(
            "Upstox does not provide fundamentals"
        )

    def get_index_quote(self, index: str) -> Quote:
        self._require_ready()
        try:
            from services.upstox_service import get_upstox_market_indices
            indices = get_upstox_market_indices()
        except Exception as e:
            logger.debug("upstox indices fetch failed: %s", e)
            raise ProviderUnavailableError(
                f"Could not fetch index {index!r}"
            ) from e

        key = index.strip().upper()
        aliases = {
            "NIFTY": "NIFTY 50",
            "NIFTY50": "NIFTY 50",
            "BANKNIFTY": "NIFTY BANK",
            "NIFTY BANK": "NIFTY BANK",
            "SENSEX": "BSE SENSEX",
        }
        lookup_key = aliases.get(key, key)
        row = indices.get(lookup_key) if isinstance(indices, dict) else None
        if not row:
            raise SymbolNotFoundError(f"Unknown index {index!r}")

        return Quote(
            symbol=key,
            price=float(row.get("price") or row.get("last_price") or 0),
            currency="INR",
            change=_maybe_float(row.get("change") or row.get("net_change")),
            change_percent=_maybe_float(
                row.get("percentChange") or row.get("percent_change")
            ),
            timestamp=datetime.utcnow(),
            exchange="NSE",
            extras={"source": "upstox"},
        )

    def health_check(self) -> bool:
        if not _is_upstox_ready():
            return False
        try:
            self.get_quote("RELIANCE")
            return True
        except Exception:
            return False


# ---- helpers ---------------------------------------------------------------


def _maybe_float(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _maybe_int(v) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def _map_interval(interval: str) -> str:
    """Map MarketDataProvider interval → Upstox interval vocab."""
    m = {
        "1m": "1minute",
        "5m": "5minute",
        "15m": "15minute",
        "30m": "30minute",
        "1h": "60minute",
        "1d": "1day",
        "1wk": "1week",
        "1mo": "1month",
    }
    return m.get(interval, "1day")


def _map_period(period: str) -> str:
    """Map MarketDataProvider period → Upstox period vocab (best effort)."""
    m = {
        "1d": "1d",
        "5d": "1mo",
        "1mo": "1mo",
        "3mo": "1y",
        "6mo": "1y",
        "1y": "1y",
        "2y": "1y",
        "5y": "1y",
        "max": "1y",
    }
    return m.get(period, "1y")
