"""Promoter pledging risk scoring -- India-unique, high-signal feature.

Thresholds:
- <10% pledged: Low risk (GREEN)
- 10-30% pledged: Medium risk (YELLOW)
- 30-50% pledged: High risk (ORANGE)
- >50% pledged: Very high risk (RED)
"""


class PromoterPledgingScorer:
    """Score promoter pledging risk for Indian stocks."""

    @staticmethod
    def compute_features(pledging_data: dict, historical_pledging: list[dict] = None) -> dict:
        features = {}

        if not pledging_data:
            return {
                "pledge_pct": 0.0,
                "pledge_risk_score": 0.0,
                "pledge_trend": 0.0,
                "promoter_holding_pct": 0.0,
            }

        pledge_pct = pledging_data.get("pledged_pct", 0.0)
        promoter_pct = pledging_data.get("promoter_holding_pct", 0.0)

        features["pledge_pct"] = pledge_pct
        features["promoter_holding_pct"] = promoter_pct

        # Risk score: 0 (safe) to 100 (extreme risk)
        if pledge_pct <= 0:
            risk_score = 0.0
        elif pledge_pct <= 10:
            risk_score = pledge_pct * 2
        elif pledge_pct <= 30:
            risk_score = 20 + (pledge_pct - 10) * 2
        elif pledge_pct <= 50:
            risk_score = 60 + (pledge_pct - 30) * 1.5
        else:
            risk_score = min(100, 90 + (pledge_pct - 50) * 0.2)

        features["pledge_risk_score"] = round(risk_score, 2)

        # Trend
        if historical_pledging and len(historical_pledging) >= 2:
            prev_pledge = historical_pledging[-2].get("pledged_pct", 0)
            features["pledge_trend"] = pledge_pct - prev_pledge
        else:
            features["pledge_trend"] = 0.0

        # Critical flag
        if promoter_pct < 30 and pledge_pct > 30:
            features["pledge_critical_flag"] = 1.0
        else:
            features["pledge_critical_flag"] = 0.0

        return features
