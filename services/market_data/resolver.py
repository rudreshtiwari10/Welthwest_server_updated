"""
Symbol resolver — free-text query → ranked SymbolMatch candidates.

Replaces the blind `.NS` auto-suffix heuristic with a proper ranked match.
Source of truth: services/nse_symbols.py's get_nse_symbol_map() which already
loads the full NSE equity list (~2000 symbols) with aliases.

Matching strategy (in order of confidence):
  1. Exact ticker match            → 1.00
  2. Exact alias/name match        → 0.98
  3. Prefix match on ticker        → 0.90
  4. Prefix match on company name  → 0.85
  5. Substring match on any key    → 0.70
  6. Difflib fuzzy ratio (>= 0.6)  → 0.50–0.80

Results are deduplicated by ticker and capped at `limit`.

This module is standalone — call `resolve_symbol(query)` from anywhere.
The Phase 2 agent will use this as its `disambiguate_symbol` tool.
"""

import difflib
import logging
from typing import Optional

from services.market_data.base import SymbolMatch

logger = logging.getLogger(__name__)


# ---- Lazy symbol index -----------------------------------------------------

_index: Optional[dict[str, str]] = None


def _get_index() -> dict[str, str]:
    """Return the NSE symbol map (uppercase key → ticker.NS). Lazily built."""
    global _index
    if _index is None:
        try:
            from services.nse_symbols import get_nse_symbol_map
            _index = get_nse_symbol_map() or {}
        except Exception as e:
            logger.warning("resolver: failed to load NSE symbol map: %s", e)
            _index = {}
    return _index


def refresh_index() -> int:
    """Force rebuild of the resolver's symbol index. Returns new size."""
    global _index
    _index = None
    return len(_get_index())


# ---- Core resolve functions ------------------------------------------------


def _ticker_from_yf(yf_symbol: str) -> str:
    """Strip trailing exchange suffix — 'RELIANCE.NS' → 'RELIANCE'."""
    for suffix in (".NS", ".BO", ".NSE", ".BSE"):
        if yf_symbol.endswith(suffix):
            return yf_symbol[: -len(suffix)]
    return yf_symbol


def _match(
    query: str,
    limit: int = 5,
) -> list[SymbolMatch]:
    """Internal ranked matcher — returns candidates sorted by confidence."""
    q = (query or "").strip().upper()
    if not q:
        return []

    index = _get_index()
    if not index:
        # No index available — fall back to blind normalization so callers
        # don't receive empty results when resolver data is missing.
        return [
            SymbolMatch(
                symbol=q,
                name=q,
                exchange="NSE",
                confidence=0.3,
            )
        ]

    # keys are NAME/ALIAS/TICKER (uppercase); values are ticker.NS strings.
    # Invert so we can iterate by ticker.
    by_ticker: dict[str, list[str]] = {}
    for k, v in index.items():
        ticker = _ticker_from_yf(v)
        by_ticker.setdefault(ticker, []).append(k)

    results: dict[str, SymbolMatch] = {}

    def _add(ticker: str, name: str, confidence: float):
        prev = results.get(ticker)
        if prev is None or confidence > prev.confidence:
            results[ticker] = SymbolMatch(
                symbol=ticker,
                name=name,
                exchange="NSE",
                confidence=confidence,
            )

    # 1. Exact ticker match
    if q in by_ticker:
        _add(q, q, 1.00)

    # 2. Exact alias/name match
    if q in index:
        ticker = _ticker_from_yf(index[q])
        _add(ticker, q, 0.98)

    # 3 & 4. Prefix matches
    for key, yf_sym in index.items():
        ticker = _ticker_from_yf(yf_sym)
        if key.startswith(q):
            conf = 0.90 if key == ticker else 0.85
            _add(ticker, key, conf)

    # 5. Substring match (cheap)
    if len(results) < limit:
        for key, yf_sym in index.items():
            if q in key and not key.startswith(q):
                ticker = _ticker_from_yf(yf_sym)
                _add(ticker, key, 0.70)
                if len(results) >= limit * 2:
                    break

    # 6. Fuzzy fallback (only if still short on results)
    if len(results) < limit:
        names = list(index.keys())
        close = difflib.get_close_matches(q, names, n=limit * 2, cutoff=0.6)
        for name in close:
            ticker = _ticker_from_yf(index[name])
            ratio = difflib.SequenceMatcher(None, q, name).ratio()
            _add(ticker, name, max(0.50, min(0.80, ratio)))

    ranked = sorted(
        results.values(), key=lambda m: m.confidence, reverse=True
    )
    return ranked[:limit]


# ---- Public API ------------------------------------------------------------


def resolve_symbol(query: str, limit: int = 5) -> list[SymbolMatch]:
    """
    Resolve a free-text query to ranked ticker candidates.

        >>> resolve_symbol("reliance")
        [SymbolMatch(symbol='RELIANCE', ..., confidence=0.98)]

        >>> resolve_symbol("hdfc")
        [SymbolMatch(symbol='HDFCBANK', ...), SymbolMatch(symbol='HDFCLIFE', ...)]
    """
    return _match(query, limit=limit)


def resolve_best(query: str) -> Optional[SymbolMatch]:
    """Return the single best candidate, or None if nothing matches."""
    matches = resolve_symbol(query, limit=1)
    return matches[0] if matches else None


def is_ambiguous(query: str, threshold: float = 0.1) -> bool:
    """
    True if the top match is within `threshold` confidence of the runner-up.
    Used by the agent to decide whether to ask the user for disambiguation.
    """
    matches = resolve_symbol(query, limit=2)
    if len(matches) < 2:
        return False
    return (matches[0].confidence - matches[1].confidence) < threshold
