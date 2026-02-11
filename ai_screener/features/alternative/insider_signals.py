"""Insider trading signal detection.
Cluster buying is one of the strongest pre-momentum signals.
Promoter buying is particularly significant in Indian stocks.
"""
import pandas as pd
from datetime import datetime, timedelta


class InsiderSignals:
    """Detect insider buying/selling patterns that predict price movements."""

    @staticmethod
    def compute_all(
        transactions: list[dict],
        current_price: float,
        market_cap: float,
    ) -> dict:
        features = {}

        if not transactions:
            return {
                "insider_activity": 0,
                "cluster_buy_signal": 0.0,
                "insider_buy_value_30d": 0.0,
                "insider_sell_value_30d": 0.0,
                "insider_net_value_30d": 0.0,
                "insider_buy_count_30d": 0,
                "insider_sell_count_30d": 0,
                "unique_buyers_30d": 0,
            }

        df = pd.DataFrame(transactions)
        df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
        now = datetime.utcnow()

        mask_30d = df["filing_date"] >= (now - timedelta(days=30))
        recent = df[mask_30d]

        buy_keywords = ["buy", "purchase", "p"]
        sell_keywords = ["sell", "sale", "s"]

        buys = recent[recent["transaction_type"].str.lower().isin(buy_keywords)]
        sells = recent[recent["transaction_type"].str.lower().isin(sell_keywords)]

        features["insider_buy_count_30d"] = len(buys)
        features["insider_sell_count_30d"] = len(sells)
        features["insider_buy_value_30d"] = float(buys["value"].sum()) if len(buys) > 0 else 0.0
        features["insider_sell_value_30d"] = float(sells["value"].sum()) if len(sells) > 0 else 0.0
        features["insider_net_value_30d"] = features["insider_buy_value_30d"] - features["insider_sell_value_30d"]

        unique_buyers = buys["insider_name"].nunique() if len(buys) > 0 else 0
        features["unique_buyers_30d"] = unique_buyers

        # Cluster buy signal
        mask_14d = df["filing_date"] >= (now - timedelta(days=14))
        recent_14d_buys = df[mask_14d & df["transaction_type"].str.lower().isin(buy_keywords)]
        unique_buyers_14d = recent_14d_buys["insider_name"].nunique()

        cluster_score = 0.0
        if unique_buyers_14d >= 3:
            cluster_score = 1.0
        elif unique_buyers_14d == 2:
            cluster_score = 0.5
        features["cluster_buy_signal"] = cluster_score

        if market_cap > 0:
            features["insider_buy_pct_mktcap"] = features["insider_buy_value_30d"] / market_cap * 100

        # C-suite buying
        c_suite_titles = [
            "ceo", "cfo", "president", "chairman", "chief",
            "promoter", "managing director", "md", "director",
        ]
        if len(buys) > 0:
            c_suite_buys = buys[
                buys["insider_title"].str.lower().apply(
                    lambda x: any(t in str(x) for t in c_suite_titles)
                )
            ]
            features["c_suite_buying"] = 1.0 if len(c_suite_buys) > 0 else 0.0
        else:
            features["c_suite_buying"] = 0.0

        # Overall score
        activity_score = 0
        if features["cluster_buy_signal"] > 0:
            activity_score += 3
        if features.get("c_suite_buying", 0) > 0:
            activity_score += 2
        if features["insider_net_value_30d"] > 0:
            activity_score += 1
        features["insider_activity"] = min(activity_score, 5) / 5.0

        return features
