"""Composite scoring system -- combines model predictions with regime-aware weighting."""
import numpy as np


# Regime adjustment parameters
REGIME_ADJUSTMENTS = {
    "bull_low_vol": {
        "momentum_weight": 1.3,
        "quality_weight": 0.8,
        "volatility_penalty": 0.5,
        "description": "Low volatility uptrend -- momentum strategies work best",
    },
    "bull_high_vol": {
        "momentum_weight": 1.0,
        "quality_weight": 1.2,
        "volatility_penalty": 1.0,
        "description": "Volatile uptrend -- favor quality momentum",
    },
    "bear_low_vol": {
        "momentum_weight": 0.5,
        "quality_weight": 1.5,
        "volatility_penalty": 1.5,
        "description": "Grinding downtrend -- be very selective, favor defensive quality",
    },
    "bear_high_vol": {
        "momentum_weight": 0.3,
        "quality_weight": 1.5,
        "volatility_penalty": 2.0,
        "description": "Crash/panic mode -- capital preservation, screen for bottoming patterns",
    },
    "sideways": {
        "momentum_weight": 0.8,
        "quality_weight": 1.0,
        "volatility_penalty": 1.0,
        "description": "Range-bound market -- mean reversion may outperform momentum",
    },
}


class CompositeScorer:
    """Compute regime-adjusted composite scores for screening."""

    def compute_score(
        self,
        momentum_probability: float,
        crash_probability: float,
        features: dict,
        regime_adjustments: dict,
        anomaly_records: list = None,
    ) -> dict:
        momentum_weight = regime_adjustments.get("momentum_weight", 1.0)
        vol_penalty = regime_adjustments.get("volatility_penalty", 1.0)

        momentum_raw = momentum_probability * 100

        bullish_count = features.get("meta_bullish_signal_count", 0)
        confluence_bonus = min(bullish_count * 5, 20)

        momentum_score = min(100, momentum_raw * momentum_weight + confluence_bonus)

        risk_score = (1 - crash_probability) * 100
        vol_ratio = features.get("vol_volume_ratio_10", 1.0)
        if vol_ratio > 3.0:
            risk_score *= 1 - 0.1 * vol_penalty

        # Light anomaly risk adjustment
        if anomaly_records:
            has_critical = any(a.get("severity") == "critical" for a in anomaly_records)
            has_high = any(a.get("severity") == "high" for a in anomaly_records)
            if has_critical:
                risk_score = max(0, risk_score - 10)
            elif has_high:
                risk_score = max(0, risk_score - 5)

        overall_score = momentum_score * 0.6 + risk_score * 0.3 + confluence_bonus * 0.1

        overall_score = max(0, min(100, overall_score))
        momentum_score = max(0, min(100, momentum_score))
        risk_score = max(0, min(100, risk_score))

        return {
            "overall_score": round(overall_score, 2),
            "momentum_score": round(momentum_score, 2),
            "risk_score": round(risk_score, 2),
            "confluence_bonus": confluence_bonus,
        }

    @staticmethod
    def heuristic_momentum_probability(features: dict) -> float:
        """Compute momentum probability from features using a rule-based heuristic.
        Used when no trained ML model is available.
        """
        score = 0.5  # baseline

        rsi = features.get("tech_rsi_14", 50)
        if 40 <= rsi <= 60:
            score += 0.05
        elif rsi < 30:
            score += 0.10  # oversold bounce
        elif rsi > 70:
            score -= 0.05

        if features.get("tech_macd_crossover", 0) > 0:
            score += 0.10
        if features.get("tech_rsi_bullish_divergence", 0) > 0:
            score += 0.08

        mom_acc = features.get("tech_momentum_acceleration", 0)
        if mom_acc and mom_acc > 0:
            score += min(0.10, mom_acc * 2)

        obv_div = features.get("vol_obv_price_divergence", 0)
        if obv_div and obv_div > 0:
            score += 0.07

        vol_ratio = features.get("vol_volume_ratio_10", 1)
        if vol_ratio and vol_ratio > 1.3:
            score += 0.05

        if features.get("insider_cluster_buy_signal", 0) > 0:
            score += 0.10
        if features.get("insider_c_suite_buying", 0) > 0:
            score += 0.05

        roc_5 = features.get("tech_roc_5", 0)
        if roc_5 and roc_5 > 3:
            score += 0.05
        elif roc_5 and roc_5 < -5:
            score -= 0.05

        price_vs_ma50 = features.get("tech_price_vs_ma_50", 0)
        if price_vs_ma50 and -5 < price_vs_ma50 < 5:
            score += 0.03

        return max(0.0, min(1.0, score))

    @staticmethod
    def heuristic_crash_probability(features: dict) -> float:
        """Estimate crash probability from features."""
        risk = 0.1  # baseline low risk

        rsi = features.get("tech_rsi_14", 50)
        if rsi > 80:
            risk += 0.15
        elif rsi > 70:
            risk += 0.05

        vol_ratio = features.get("vol_volume_ratio_10", 1)
        if vol_ratio and vol_ratio > 3:
            risk += 0.10

        roc_5 = features.get("tech_roc_5", 0)
        if roc_5 and roc_5 < -10:
            risk += 0.15
        elif roc_5 and roc_5 < -5:
            risk += 0.05

        pledge_risk = features.get("india_pledge_pledge_risk_score", 0)
        if pledge_risk > 60:
            risk += 0.15

        return max(0.0, min(1.0, risk))
