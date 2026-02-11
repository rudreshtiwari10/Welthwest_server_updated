"""Feature pipeline -- orchestrates all feature computation for a stock."""
import pandas as pd
import logging
from typing import Optional, Tuple, List

from ai_screener.features.technical.momentum import MomentumFeatures
from ai_screener.features.technical.volume import VolumeFeatures
from ai_screener.features.fundamental.earnings import EarningsFeatures
from ai_screener.features.alternative.insider_signals import InsiderSignals
from ai_screener.features.alternative.promoter_pledging import PromoterPledgingScorer
from ai_screener.features.alternative.bulk_block_deals import BulkBlockDealAnalyzer
from ai_screener.features.anomaly import AnomalyFeatures

logger = logging.getLogger(__name__)


class FeaturePipeline:
    """Orchestrates feature computation across all feature groups."""

    def compute_features(
        self,
        price_df: pd.DataFrame,
        earnings_data: Optional[dict] = None,
        insider_transactions: Optional[list] = None,
        pledging_data: Optional[dict] = None,
        bulk_block_deals: Optional[list] = None,
        fii_dii_data: Optional[list] = None,
        delivery_data: Optional[dict] = None,
        fno_oi_data: Optional[dict] = None,
        current_price: float = 0.0,
        market_cap: float = 0.0,
        timeframe: str = "1d",
    ) -> Tuple[dict, List[dict]]:
        """Compute all features for a single Indian stock.

        Returns
        -------
        (features_dict, anomaly_records)
        """
        all_features = {}

        # 1. Technical features
        try:
            if len(price_df) >= 60:
                momentum = MomentumFeatures.compute_all(price_df, timeframe=timeframe)
                all_features.update({f"tech_{k}": v for k, v in momentum.items()})

                volume = VolumeFeatures.compute_all(price_df, timeframe=timeframe)
                all_features.update({f"vol_{k}": v for k, v in volume.items()})
        except Exception as e:
            logger.error(f"Technical feature computation failed: {e}")

        # 2. Fundamental features
        try:
            earnings = EarningsFeatures.compute_all(price_df, earnings_data)
            all_features.update({f"fund_{k}": v for k, v in earnings.items()})
        except Exception as e:
            logger.error(f"Fundamental feature computation failed: {e}")

        # 3. Insider signals
        try:
            if insider_transactions:
                insider = InsiderSignals.compute_all(insider_transactions, current_price, market_cap)
                all_features.update({f"insider_{k}": v for k, v in insider.items()})
        except Exception as e:
            logger.error(f"Insider feature computation failed: {e}")

        # 4. Promoter pledging (India-specific)
        try:
            if pledging_data:
                pledge_features = PromoterPledgingScorer.compute_features(pledging_data)
                all_features.update({f"india_pledge_{k}": v for k, v in pledge_features.items()})
        except Exception as e:
            logger.error(f"Pledging feature computation failed: {e}")

        # 5. Bulk/Block deals
        try:
            if bulk_block_deals:
                deal_features = BulkBlockDealAnalyzer.compute_features(
                    bulk_block_deals, current_price=current_price
                )
                all_features.update({f"india_deal_{k}": v for k, v in deal_features.items()})
        except Exception as e:
            logger.error(f"Bulk/block deal feature computation failed: {e}")

        # 6. FII/DII flows
        try:
            if fii_dii_data:
                fii_net = sum(d.get("net_value", 0) for d in fii_dii_data if "FII" in d.get("category", "").upper())
                dii_net = sum(d.get("net_value", 0) for d in fii_dii_data if "DII" in d.get("category", "").upper())
                all_features["india_fii_net_flow"] = fii_net
                all_features["india_dii_net_flow"] = dii_net
                all_features["india_fii_dii_ratio"] = fii_net / dii_net if dii_net != 0 else 0.0
                all_features["india_dii_absorption"] = 1.0 if (fii_net < 0 and dii_net > abs(fii_net) * 0.8) else 0.0
        except Exception as e:
            logger.error(f"FII/DII feature computation failed: {e}")

        # 7. Delivery volume
        try:
            if delivery_data:
                delivery_pct = delivery_data.get("delivery_pct", 0)
                all_features["india_delivery_pct"] = float(delivery_pct) if delivery_pct else 0.0
                all_features["india_high_delivery"] = 1.0 if float(delivery_pct or 0) > 60 else 0.0
        except Exception as e:
            logger.error(f"Delivery data feature computation failed: {e}")

        # 8. F&O OI signals
        try:
            if fno_oi_data:
                all_features["india_pcr_oi"] = fno_oi_data.get("pcr_oi", 0)
                pcr = fno_oi_data.get("pcr_oi", 1.0)
                all_features["india_pcr_signal"] = 1.0 if pcr > 1.2 else (-1.0 if pcr < 0.7 else 0.0)
        except Exception as e:
            logger.error(f"F&O OI feature computation failed: {e}")

        # 9. Meta-features
        all_features.update(self._compute_meta_features(all_features))

        # 10. Anomaly detection (runs after all other features are computed)
        anomaly_records: List[dict] = []
        try:
            all_features, anomaly_records = AnomalyFeatures.compute(
                price_df, all_features, timeframe=timeframe,
            )
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")

        return all_features, anomaly_records

    def _compute_meta_features(self, features: dict) -> dict:
        meta = {}

        mom_acc = features.get("tech_momentum_acceleration", 0)
        vol_ratio = features.get("vol_volume_ratio_10", 1)
        meta["meta_momentum_volume_convergence"] = float(mom_acc > 0 and vol_ratio > 1.2)

        roc_10 = features.get("tech_roc_10", 0)
        insider_activity = features.get("insider_insider_activity", 0)
        rsi_14 = features.get("tech_rsi_14", 50)
        if insider_activity > 0.4 and 30 < rsi_14 < 60:
            meta["meta_insider_momentum_alignment"] = 1.0
        else:
            meta["meta_insider_momentum_alignment"] = 0.0

        bullish_count = 0
        if features.get("tech_macd_crossover", 0) > 0:
            bullish_count += 1
        if features.get("tech_rsi_bullish_divergence", 0) > 0:
            bullish_count += 1
        if features.get("vol_obv_price_divergence", 0) and features.get("vol_obv_price_divergence", 0) > 0.5:
            bullish_count += 1
        if features.get("insider_cluster_buy_signal", 0) > 0:
            bullish_count += 1
        if features.get("fund_in_pead_window", 0) > 0 and features.get("fund_positive_surprise", 0) > 0:
            bullish_count += 1
        meta["meta_bullish_signal_count"] = bullish_count

        return meta
