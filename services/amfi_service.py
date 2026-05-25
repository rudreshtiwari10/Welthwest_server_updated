"""
amfi_service — daily NAV lookup using AMFI's public NAVAll.txt.

AMFI publishes a single semicolon-delimited file listing every Indian mutual-fund
scheme with its current NAV. We download it once per day, parse it into a typed
in-memory index, and provide lookup by scheme code or fuzzy name match.

File format (simplified):
    Open Ended Schemes(Equity Scheme - Multi Cap Fund)
    Aditya Birla Sun Life Mutual Fund

    Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
    118625;INF209KB1WL5;-;Aditya Birla Sun Life Multi-Cap Fund - Direct Plan - Growth;55.4321;05-May-2026

Lines that aren't scheme rows (AMC headers, category headers, blank) are state
trackers: we update the current AMC / category and tag every subsequent row.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import urllib.request

logger = logging.getLogger(__name__)

NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
TTL_SECONDS = 6 * 60 * 60  # 6 hours — NAV publishes once per day, but we refresh more
DOWNLOAD_TIMEOUT = 30
USER_AGENT = "WelthWest/1.0 (+https://welthwest.com)"


_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "fetched_at": 0.0,
    "by_code": {},          # int code -> scheme dict
    "all_schemes": [],      # list of scheme dicts (for screening)
    "name_index": [],       # list of (name_lower, code) for fuzzy match
}


# ---- Download + parse -------------------------------------------------------

def _download_nav_file() -> str:
    req = urllib.request.Request(NAV_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _parse_nav_text(text: str) -> Dict[str, Any]:
    """
    Walk the text line by line, keeping a state of current AMC + scheme category.
    Yield scheme rows as parsed dicts.
    """
    by_code: Dict[int, Dict[str, Any]] = {}
    all_schemes: List[Dict[str, Any]] = []
    current_category = ""
    current_amc = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("scheme code"):
            # Header row — skip
            continue

        # Category line: e.g. "Open Ended Schemes(Equity Scheme - Multi Cap Fund)"
        if "(" in line and line.endswith(")") and ";" not in line:
            current_category = line.split("(", 1)[1].rstrip(")").strip()
            continue

        # Data row?
        if ";" in line:
            parts = [p.strip() for p in line.split(";")]
            if len(parts) >= 6:
                code_raw = parts[0]
                if not code_raw.isdigit():
                    # Not a data row — could be a stray
                    continue
                code = int(code_raw)
                isin_div = parts[1] or ""
                isin_growth = parts[2] or ""
                name = parts[3]
                nav_raw = parts[4]
                date_raw = parts[5]

                try:
                    nav = float(nav_raw)
                except (TypeError, ValueError):
                    nav = None

                row = {
                    "code": code,
                    "name": name,
                    "isin_div": isin_div if isin_div != "-" else None,
                    "isin_growth": isin_growth if isin_growth != "-" else None,
                    "nav": nav,
                    "nav_date": date_raw,
                    "amc": current_amc,
                    "category": current_category,
                }
                by_code[code] = row
                all_schemes.append(row)
                continue

        # Otherwise treat the line as the current AMC name.
        # AMC names rarely contain semicolons or parentheses — last writer wins.
        if line and ";" not in line and "(" not in line:
            current_amc = line

    name_index = [(s["name"].lower(), s["code"]) for s in all_schemes]
    return {
        "by_code": by_code,
        "all_schemes": all_schemes,
        "name_index": name_index,
    }


def _ensure_loaded(force: bool = False) -> None:
    """Refresh cache if stale. Thread-safe."""
    with _cache_lock:
        age = time.time() - _cache["fetched_at"]
        if not force and _cache["all_schemes"] and age < TTL_SECONDS:
            return

        try:
            text = _download_nav_file()
            parsed = _parse_nav_text(text)
            _cache["by_code"] = parsed["by_code"]
            _cache["all_schemes"] = parsed["all_schemes"]
            _cache["name_index"] = parsed["name_index"]
            _cache["fetched_at"] = time.time()
            logger.info(
                "AMFI NAV file loaded: %d schemes",
                len(_cache["all_schemes"]),
            )
        except Exception as e:
            logger.error("AMFI NAV download failed: %s", e)
            # Keep stale cache rather than fail
            if not _cache["all_schemes"]:
                raise


# ---- Public API -------------------------------------------------------------

def lookup_by_code(code: int) -> Optional[Dict[str, Any]]:
    _ensure_loaded()
    return _cache["by_code"].get(int(code))


def search_by_name(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Fuzzy substring search. Returns up to `limit` schemes ranked by:
      1. Direct prefix match
      2. Substring containment
      3. Word-boundary match
    """
    _ensure_loaded()
    if not query:
        return []
    q = query.lower().strip()

    prefix_hits: List[Dict[str, Any]] = []
    contains_hits: List[Dict[str, Any]] = []

    for name_lower, code in _cache["name_index"]:
        if name_lower.startswith(q):
            prefix_hits.append(_cache["by_code"][code])
        elif q in name_lower:
            contains_hits.append(_cache["by_code"][code])
        if len(prefix_hits) >= limit:
            break

    out = prefix_hits[:limit]
    if len(out) < limit:
        out.extend(contains_hits[: limit - len(out)])
    return out


def filter_schemes(
    category_contains: Optional[str] = None,
    amc_contains: Optional[str] = None,
    name_contains: Optional[str] = None,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    _ensure_loaded()
    out = []
    cat_q = (category_contains or "").lower()
    amc_q = (amc_contains or "").lower()
    name_q = (name_contains or "").lower()

    for s in _cache["all_schemes"]:
        if cat_q and cat_q not in (s["category"] or "").lower():
            continue
        if amc_q and amc_q not in (s["amc"] or "").lower():
            continue
        if name_q and name_q not in (s["name"] or "").lower():
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


def status() -> Dict[str, Any]:
    return {
        "loaded": bool(_cache["all_schemes"]),
        "scheme_count": len(_cache["all_schemes"]),
        "fetched_at": _cache["fetched_at"],
        "age_seconds": time.time() - _cache["fetched_at"] if _cache["fetched_at"] else None,
    }
