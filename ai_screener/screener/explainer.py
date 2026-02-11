"""Generate human-readable explanations for screening results."""
from typing import Optional


class SignalExplainer:
    """Convert features and signals into natural language explanations."""

    FEATURE_DESCRIPTIONS_DAILY = {
        "tech_rsi_14": "14-day RSI",
        "tech_macd_crossover": "MACD bullish crossover",
        "tech_rsi_bullish_divergence": "RSI bullish divergence",
        "tech_momentum_acceleration": "momentum acceleration",
        "vol_obv_price_divergence": "OBV-price divergence (accumulation)",
        "vol_volume_ratio_10": "10-day volume surge",
        "vol_up_down_volume_ratio": "up/down volume ratio",
        "fund_in_pead_window": "post-earnings drift window",
        "fund_positive_surprise": "positive earnings surprise",
        "insider_cluster_buy_signal": "insider/promoter cluster buying",
        "insider_c_suite_buying": "promoter/MD buying",
        "meta_bullish_signal_count": "multiple bullish signals",
        "meta_momentum_volume_convergence": "momentum-volume convergence",
        "meta_insider_momentum_alignment": "insider + technical alignment",
        "india_pledge_risk_score": "promoter pledging risk",
        "india_fii_net_flow": "FII net flow",
        "india_dii_net_flow": "DII net flow",
        "india_dii_absorption": "DII absorbing FII selling (bottoming signal)",
        "india_delivery_pct": "delivery volume %",
        "india_pcr_signal": "PCR signal (oversold/overbought)",
        "india_deal_institutional_buy_count": "institutional block/bulk buying",
        # Anomaly feature descriptions
        "anomaly_volume_spike": "extreme volume spike",
        "anomaly_volume_dryup": "volume dry-up (illiquidity)",
        "anomaly_gap_up": "gap-up shock",
        "anomaly_gap_down": "gap-down shock",
        "anomaly_flash_crash": "flash crash",
        "anomaly_flash_pump": "flash pump",
        "anomaly_vol_spike": "volatility regime spike",
        "anomaly_parabolic_up": "parabolic blow-off move",
        "anomaly_buying_climax": "buying climax (exhaustion)",
        "anomaly_selling_climax": "selling climax (capitulation)",
        "anomaly_smart_money_divergence": "smart-money divergence",
    }

    # Backward-compatible alias
    FEATURE_DESCRIPTIONS = FEATURE_DESCRIPTIONS_DAILY

    @staticmethod
    def get_feature_description(feature: str, timeframe: str = "1d") -> str:
        """Return a timeframe-aware human-readable label for a feature key."""
        base = SignalExplainer.FEATURE_DESCRIPTIONS_DAILY.get(feature)
        if base is None:
            return feature
        if timeframe == "1d":
            return base
        # Replace "day" with "bar" and append timeframe suffix for intraday
        tf_label = timeframe.upper()  # "1H" or "15M"
        label = base.replace("-day ", "-bar ")
        return f"{label} ({tf_label})"

    def generate_explanation(
        self,
        symbol: str,
        top_signals: list[dict],
        regime: str,
        composite_score: dict,
        timeframe: str = "1d",
        anomaly_records: Optional[list] = None,
    ) -> str:
        parts = []

        regime_text = {
            "bull_low_vol": "In the current low-volatility uptrend",
            "bull_high_vol": "Despite elevated volatility in this uptrend",
            "bear_low_vol": "In this cautious downtrend environment",
            "bear_high_vol": "In this high-volatility selloff",
            "sideways": "In the current range-bound market",
        }.get(regime, "In current market conditions")

        parts.append(f"{regime_text}, {symbol} scores {composite_score['overall_score']:.0f}/100.")

        bullish = [s for s in top_signals if s.get("direction") == "bullish"][:3]
        if bullish:
            signal_names = [
                self.get_feature_description(s["feature"], timeframe)
                for s in bullish
            ]
            if len(signal_names) == 1:
                parts.append(f"Key driver: {signal_names[0]}.")
            else:
                parts.append(f"Key drivers: {', '.join(signal_names[:-1])} and {signal_names[-1]}.")

        if composite_score["risk_score"] < 40:
            parts.append("Elevated risk -- position sizing recommended.")
        elif composite_score["risk_score"] > 80:
            parts.append("Low risk profile supports conviction.")

        # Append anomaly alert if present
        if anomaly_records:
            tf_label = timeframe.upper()
            names = [a["name"] for a in anomaly_records[:2]]
            severity_max = "high"
            for a in anomaly_records:
                if a.get("severity") == "critical":
                    severity_max = "critical"
                    break
            parts.append(
                f"ALERT: Anomaly detected on {tf_label} timeframe: "
                f"{' and '.join(names)}; treat current move as {severity_max}-risk."
            )

        return " ".join(parts)

    def extract_top_signals(self, features: dict, top_n: int = 5) -> list[dict]:
        """Extract top signals from feature dict for explanation."""
        signal_features = [
            ("tech_macd_crossover", "bullish"),
            ("tech_rsi_bullish_divergence", "bullish"),
            ("tech_momentum_acceleration", "bullish"),
            ("vol_obv_price_divergence", "bullish"),
            ("vol_volume_ratio_10", "bullish"),
            ("insider_cluster_buy_signal", "bullish"),
            ("insider_c_suite_buying", "bullish"),
            ("meta_momentum_volume_convergence", "bullish"),
            ("meta_insider_momentum_alignment", "bullish"),
            ("meta_bullish_signal_count", "bullish"),
        ]

        signals = []
        for feature_key, direction in signal_features:
            val = features.get(feature_key, 0)
            if val and val > 0:
                signals.append({
                    "feature": feature_key,
                    "value": float(val),
                    "direction": direction,
                })

        # Also check bearish signals
        rsi = features.get("tech_rsi_14", 50)
        if rsi > 75:
            signals.append({"feature": "tech_rsi_14", "value": rsi, "direction": "bearish"})

        pledge = features.get("india_pledge_pledge_risk_score", 0)
        if pledge > 50:
            signals.append({"feature": "india_pledge_risk_score", "value": pledge, "direction": "bearish"})

        signals.sort(key=lambda x: abs(x.get("value", 0)), reverse=True)
        return signals[:top_n]
