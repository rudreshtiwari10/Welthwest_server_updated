"""SUPPLEMENTARY data provider: Direct NSE APIs for India-specific signals.
Adds data NOT available in yfinance: FII/DII flows, promoter pledging,
bulk/block deals, circuit limits, delivery volume, F&O OI data.
"""
import httpx
import time
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class NSEDirectProvider:
    """NSE direct API provider for India-specific supplementary data."""

    NSE_BASE = "https://www.nseindia.com/api"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }

    def __init__(self):
        self._cookies: Optional[dict] = None
        self._cookie_time: Optional[float] = None

    def _get_client(self) -> httpx.Client:
        client = httpx.Client(timeout=30, headers=self.HEADERS)
        now = time.time()
        if not self._cookies or (now - (self._cookie_time or 0)) > 300:
            try:
                resp = client.get("https://www.nseindia.com")
                self._cookies = dict(resp.cookies)
                self._cookie_time = now
            except Exception as e:
                logger.warning(f"NSE cookie refresh failed: {e}")
                return client
        client.cookies.update(self._cookies)
        return client

    def fetch_fii_dii_data(self, target_date: Optional[date] = None) -> list[dict]:
        """Fetch FII/DII daily activity data. Values in INR Crores."""
        try:
            client = self._get_client()
            resp = client.get(f"{self.NSE_BASE}/fiidiiTradeReact")
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for entry in data:
                    results.append({
                        "date": str(target_date or date.today()),
                        "category": entry.get("category", ""),
                        "buy_value": float(entry.get("buyValue", 0)),
                        "sell_value": float(entry.get("sellValue", 0)),
                        "net_value": float(entry.get("netValue", 0)),
                        "segment": "cash",
                    })
                return results
            return []
        except Exception as e:
            logger.error(f"FII/DII fetch failed: {e}")
            return []

    def fetch_bulk_block_deals(self, target_date: Optional[date] = None) -> list[dict]:
        """Fetch today's bulk and block deals from NSE."""
        try:
            client = self._get_client()
            deals = []

            resp = client.get(f"{self.NSE_BASE}/snapshot/bulk-deal")
            if resp.status_code == 200:
                for deal in resp.json().get("data", []):
                    deals.append({
                        "date": str(target_date or date.today()),
                        "symbol": deal.get("symbol", ""),
                        "deal_type": "BULK",
                        "client_name": deal.get("clientName", ""),
                        "transaction_type": deal.get("buySell", ""),
                        "quantity": int(deal.get("quantity", 0)),
                        "price": float(deal.get("avgPrice", 0)),
                    })

            resp = client.get(f"{self.NSE_BASE}/snapshot/block-deal")
            if resp.status_code == 200:
                for deal in resp.json().get("data", []):
                    deals.append({
                        "date": str(target_date or date.today()),
                        "symbol": deal.get("symbol", ""),
                        "deal_type": "BLOCK",
                        "client_name": deal.get("clientName", ""),
                        "transaction_type": deal.get("buySell", ""),
                        "quantity": int(deal.get("quantity", 0)),
                        "price": float(deal.get("avgPrice", 0)),
                    })
            return deals
        except Exception as e:
            logger.error(f"Bulk/block deal fetch failed: {e}")
            return []

    def health_check(self) -> bool:
        try:
            client = self._get_client()
            resp = client.get(f"{self.NSE_BASE}/allIndices")
            return resp.status_code == 200
        except Exception:
            return False
