"""Earnings momentum and Post-Earnings Announcement Drift (PEAD) signals."""
import pandas as pd
from datetime import datetime
from typing import Optional


class EarningsFeatures:
    """Detect earnings momentum and PEAD opportunities."""

    @staticmethod
    def compute_all(
        price_df: pd.DataFrame,
        earnings_data: Optional[dict] = None,
        analyst_estimates: Optional[dict] = None,
    ) -> dict:
        features = {}

        if earnings_data:
            actual = earnings_data.get("actual_eps")
            estimate = earnings_data.get("consensus_eps")
            if actual is not None and estimate is not None and estimate != 0:
                features["sue"] = (actual - estimate) / abs(estimate)
                features["earnings_surprise_pct"] = ((actual - estimate) / abs(estimate)) * 100
                features["positive_surprise"] = 1.0 if actual > estimate else 0.0

            report_date = earnings_data.get("report_date")
            if report_date:
                if isinstance(report_date, str):
                    try:
                        report_date = datetime.fromisoformat(report_date)
                    except ValueError:
                        report_date = None
                if report_date:
                    days_since = (datetime.utcnow() - report_date).days
                    features["days_since_earnings"] = days_since
                    features["in_pead_window"] = 1.0 if 1 <= days_since <= 30 else 0.0
                    features["pead_early"] = 1.0 if 1 <= days_since <= 10 else 0.0

            features["consecutive_beats"] = earnings_data.get("consecutive_beats", 0)
            features["eps_growth_yoy"] = earnings_data.get("eps_growth_yoy", 0.0)

        if analyst_estimates:
            features["eps_revision_1m"] = analyst_estimates.get("eps_revision_1m", 0.0)
            features["revenue_revision_1m"] = analyst_estimates.get("revenue_revision_1m", 0.0)

            next_earnings = analyst_estimates.get("next_earnings_date")
            if next_earnings:
                days_to = (pd.Timestamp(next_earnings) - pd.Timestamp.utcnow()).days
                features["days_to_earnings"] = max(0, days_to)
                features["pre_earnings_window"] = 1.0 if 0 < days_to <= 14 else 0.0

        return features
