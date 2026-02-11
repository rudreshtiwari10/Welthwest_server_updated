"""Bulk and block deal analysis -- institutional transaction signals.

Block deals: Minimum 5 lakh shares or INR 10 crore value.
Bulk deals: >0.5% of equity shares traded in a single day by one entity.
"""


class BulkBlockDealAnalyzer:
    """Analyze bulk and block deals for institutional flow signals."""

    INSTITUTIONAL_KEYWORDS = [
        "mutual fund", "insurance", "pension", "sovereign", "bank",
        "capital", "investments", "asset management", "securities",
        "fii", "fpi", "dii", "goldman", "morgan", "jpmorgan",
        "blackrock", "vanguard", "hdfc", "icici", "sbi", "kotak",
        "axis", "nippon", "birla", "uti", "lic", "gic",
    ]

    @staticmethod
    def compute_features(
        deals: list[dict],
        lookback_days: int = 30,
        current_price: float = 0.0,
    ) -> dict:
        features = {}

        if not deals:
            return {
                "bulk_block_activity": 0,
                "institutional_buy_count": 0,
                "institutional_sell_count": 0,
                "net_institutional_flow": 0.0,
            }

        buy_deals = [d for d in deals if d.get("transaction_type", "").upper() == "BUY"]
        sell_deals = [d for d in deals if d.get("transaction_type", "").upper() == "SELL"]

        features["total_deal_count"] = len(deals)
        features["buy_deal_count"] = len(buy_deals)
        features["sell_deal_count"] = len(sell_deals)

        inst_buys = [d for d in buy_deals if BulkBlockDealAnalyzer._is_institutional(d)]
        inst_sells = [d for d in sell_deals if BulkBlockDealAnalyzer._is_institutional(d)]

        features["institutional_buy_count"] = len(inst_buys)
        features["institutional_sell_count"] = len(inst_sells)

        buy_value = sum(d.get("quantity", 0) * d.get("price", 0) for d in inst_buys)
        sell_value = sum(d.get("quantity", 0) * d.get("price", 0) for d in inst_sells)
        features["net_institutional_flow"] = buy_value - sell_value

        if current_price > 0 and buy_deals:
            avg_buy_price = sum(d.get("price", 0) for d in buy_deals) / len(buy_deals)
            features["deal_premium_pct"] = (avg_buy_price / current_price - 1) * 100

        block_deals = [d for d in deals if d.get("deal_type") == "BLOCK"]
        features["block_deal_count"] = len(block_deals)

        activity = min(len(deals), 5) / 5.0
        features["bulk_block_activity"] = activity

        return features

    @staticmethod
    def _is_institutional(deal: dict) -> bool:
        name = deal.get("client_name", "").lower()
        return any(kw in name for kw in BulkBlockDealAnalyzer.INSTITUTIONAL_KEYWORDS)
