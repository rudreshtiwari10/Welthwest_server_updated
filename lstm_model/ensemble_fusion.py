"""
Multi-Model Ensemble Fusion System
Combines HMM, LSTM, Random Forest, Sentiment, and Technical Analysis
"""
import numpy as np
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EnsembleFusionEngine:
    """Weighted ensemble combining multiple AI models"""

    def __init__(self):
        logger.info("Ensemble Fusion Engine initialized")

        # Research-based optimal weights
        self.model_weights = {
            'hmm': 0.35,        # Highest weight - regime analysis is foundational
            'lstm': 0.25,       # Price prediction weight
            'random_forest': 0.20,  # Pattern recognition weight
            'sentiment': 0.10,  # Sentiment analysis weight
            'technical': 0.10   # Technical indicators weight
        }

        self.performance_history = {model: [] for model in self.model_weights.keys()}

    def fuse_predictions(self, model_outputs: Dict[str, Dict]) -> Dict:
        """
        Fuse predictions from all models using weighted ensemble

        Args:
            model_outputs: Dictionary containing outputs from each model
                {
                    'hmm': {...},
                    'lstm': {...},
                    'random_forest': {...},
                    'sentiment': {...},
                    'technical': {...}
                }

        Returns:
            Fused prediction with confidence scores
        """
        try:
            # Extract signals and confidences from each model
            signals = self._extract_signals(model_outputs)
            confidences = self._extract_confidences(model_outputs)

            # Calculate weighted ensemble signal
            raw_signal = sum(
                self.model_weights[model] * signals[model] * confidences[model]
                for model in self.model_weights.keys()
                if model in signals and model in confidences
            )

            # Calculate confidence-weighted normalization
            weighted_confidence = sum(
                self.model_weights[model] * confidences[model]
                for model in self.model_weights.keys()
                if model in confidences
            )

            final_signal = raw_signal / weighted_confidence if weighted_confidence > 0 else 0

            # Calculate ensemble confidence
            ensemble_confidence = self._calculate_ensemble_confidence(
                signals, confidences, model_outputs
            )

            # Determine trading action
            action = self._signal_to_action(final_signal, ensemble_confidence)

            # Calculate agreement score
            agreement_score = self._calculate_agreement(signals)

            return {
                'final_signal': float(final_signal),
                'action': action,
                'confidence': float(ensemble_confidence),
                'agreement_score': float(agreement_score),
                'model_signals': {k: float(v) for k, v in signals.items()},
                'model_confidences': {k: float(v) for k, v in confidences.items()},
                'model_weights': {k: float(v) for k, v in self.model_weights.items()},
                'reasoning': self._generate_reasoning(model_outputs, action, ensemble_confidence)
            }

        except Exception as e:
            logger.error(f"Error in ensemble fusion: {str(e)}")
            return {
                'final_signal': 0.0,
                'action': 'HOLD',
                'confidence': 0.5,
                'agreement_score': 0.5,
                'model_signals': {},
                'model_confidences': {},
                'model_weights': self.model_weights,
                'reasoning': 'Unable to generate ensemble prediction'
            }

    def _extract_signals(self, model_outputs: Dict) -> Dict[str, float]:
        """Extract trading signals from each model (-1 to +1)"""
        signals = {}

        # HMM signal (regime-based)
        if 'hmm' in model_outputs and model_outputs['hmm']:
            regime = model_outputs['hmm'].get('current_regime', 1)
            if regime == 0:  # Low volatility
                signals['hmm'] = 0.5  # Moderately bullish
            elif regime == 1:  # Normal volatility
                signals['hmm'] = 0.0  # Neutral
            else:  # High volatility
                signals['hmm'] = -0.3  # Slightly bearish

        # LSTM signal (price prediction)
        if 'lstm' in model_outputs and model_outputs['lstm']:
            trend = model_outputs['lstm'].get('lstm_trend', 'Neutral')
            avg_change = model_outputs['lstm'].get('average_change_percent', 0)
            if trend == 'Bullish':
                signals['lstm'] = min(avg_change / 10.0, 1.0)
            elif trend == 'Bearish':
                signals['lstm'] = max(avg_change / 10.0, -1.0)
            else:
                signals['lstm'] = 0.0

        # Random Forest signal (pattern-based)
        if 'random_forest' in model_outputs and model_outputs['random_forest']:
            success_prob = model_outputs['random_forest'].get('success_probability', 0.5)
            signals['random_forest'] = (success_prob - 0.5) * 2  # Scale to -1 to +1

        # Sentiment signal
        if 'sentiment' in model_outputs and model_outputs['sentiment']:
            sentiment_score = model_outputs['sentiment'].get('overall_sentiment', 0.0)
            signals['sentiment'] = sentiment_score

        # Technical signal
        if 'technical' in model_outputs and model_outputs['technical']:
            trend_direction = model_outputs['technical'].get('trend_direction', 'neutral')
            trend_strength = model_outputs['technical'].get('trend_strength', 0.0)
            if trend_direction == 'up':
                signals['technical'] = trend_strength
            elif trend_direction == 'down':
                signals['technical'] = -trend_strength
            else:
                signals['technical'] = 0.0

        return signals

    def _extract_confidences(self, model_outputs: Dict) -> Dict[str, float]:
        """Extract confidence scores from each model"""
        confidences = {}

        if 'hmm' in model_outputs and model_outputs['hmm']:
            confidences['hmm'] = model_outputs['hmm'].get('confidence', 0.5)

        if 'lstm' in model_outputs and model_outputs['lstm']:
            confidences['lstm'] = 0.7  # Default LSTM confidence

        if 'random_forest' in model_outputs and model_outputs['random_forest']:
            confidences['random_forest'] = model_outputs['random_forest'].get('pattern_confidence', 0.5)

        if 'sentiment' in model_outputs and model_outputs['sentiment']:
            confidences['sentiment'] = model_outputs['sentiment'].get('confidence', 0.5)

        if 'technical' in model_outputs and model_outputs['technical']:
            confidences['technical'] = model_outputs['technical'].get('trend_strength', 0.5)

        return confidences

    def _calculate_ensemble_confidence(self, signals: Dict, confidences: Dict,
                                        model_outputs: Dict) -> float:
        """
        Calculate multi-dimensional ensemble confidence

        Components:
        1. Model Agreement Score
        2. Prediction Variance Score
        3. Historical Performance Score
        4. Regime Alignment Score
        """
        # 1. Model Agreement Score
        agreement_score = self._calculate_agreement(signals)

        # 2. Prediction Variance Score (lower variance = higher confidence)
        signal_values = list(signals.values())
        if len(signal_values) > 1:
            variance = np.std(signal_values)
            mean = np.mean(signal_values)
            variance_score = 1 - (variance / abs(mean)) if mean != 0 else 0.5
            variance_score = np.clip(variance_score, 0, 1)
        else:
            variance_score = 0.5

        # 3. Historical Performance Score (placeholder - would use actual performance)
        historical_score = 0.75  # Assume 75% accuracy

        # 4. Regime Alignment Score
        if 'hmm' in model_outputs and model_outputs['hmm']:
            regime_alignment = model_outputs['hmm'].get('confidence', 0.5)
        else:
            regime_alignment = 0.5

        # Weighted combination
        ensemble_confidence = (
            agreement_score * 0.30 +
            variance_score * 0.25 +
            historical_score * 0.25 +
            regime_alignment * 0.20
        )

        return float(np.clip(ensemble_confidence, 0, 1))

    def _calculate_agreement(self, signals: Dict[str, float]) -> float:
        """Calculate how many models agree on direction"""
        if not signals:
            return 0.5

        signal_values = list(signals.values())
        positive_count = sum(1 for s in signal_values if s > 0.1)
        negative_count = sum(1 for s in signal_values if s < -0.1)
        total = len(signal_values)

        # Agreement is the proportion agreeing with the majority
        agreement = max(positive_count, negative_count) / total if total > 0 else 0.5

        return float(agreement)

    def _signal_to_action(self, signal: float, confidence: float) -> str:
        """Convert numerical signal to trading action"""
        # Require minimum confidence for any action
        if confidence < 0.55:
            return 'HOLD'

        # Strong signals with high confidence
        if signal > 0.3 and confidence > 0.70:
            return 'STRONG BUY'
        elif signal > 0.1 and confidence > 0.60:
            return 'BUY'
        elif signal < -0.3 and confidence > 0.70:
            return 'STRONG SELL'
        elif signal < -0.1 and confidence > 0.60:
            return 'SELL'
        else:
            return 'HOLD'

    def _generate_reasoning(self, model_outputs: Dict, action: str, confidence: float) -> str:
        """Generate human-readable reasoning for the recommendation"""
        reasons = []

        # HMM reasoning
        if 'hmm' in model_outputs and model_outputs['hmm']:
            regime_name = model_outputs['hmm'].get('regime_name', 'Unknown')
            reasons.append(f"Market is in {regime_name}")

        # LSTM reasoning
        if 'lstm' in model_outputs and model_outputs['lstm']:
            trend = model_outputs['lstm'].get('lstm_trend', 'Neutral')
            reasons.append(f"LSTM predicts {trend} trend")

        # Pattern reasoning
        if 'random_forest' in model_outputs and model_outputs['random_forest']:
            patterns = model_outputs['random_forest'].get('chart_patterns', [])
            if patterns:
                reasons.append(f"Detected patterns: {', '.join(patterns[:2])}")

        # Sentiment reasoning
        if 'sentiment' in model_outputs and model_outputs['sentiment']:
            sentiment_trend = model_outputs['sentiment'].get('sentiment_trend', 'neutral')
            reasons.append(f"Market sentiment is {sentiment_trend}")

        # Combine reasoning
        base_reasoning = ". ".join(reasons) if reasons else "Based on multi-model analysis"

        # Add confidence qualifier
        confidence_desc = "high" if confidence > 0.75 else "moderate" if confidence > 0.60 else "low"

        return f"{base_reasoning}. Recommendation confidence: {confidence_desc} ({confidence*100:.0f}%)."

    def update_model_weights(self, recent_performance: Dict[str, float]):
        """
        Dynamically adjust model weights based on recent performance

        Args:
            recent_performance: Dictionary of model accuracies {model: accuracy}
        """
        try:
            if not recent_performance:
                return

            # Calculate performance scores
            total_performance = sum(recent_performance.values())

            if total_performance == 0:
                return

            # Calculate new weights based on relative performance
            new_weights = {
                model: perf / total_performance
                for model, perf in recent_performance.items()
            }

            # Smooth weight transition (10% adjustment per update)
            alpha = 0.1
            for model in self.model_weights:
                if model in new_weights:
                    self.model_weights[model] = (
                        (1 - alpha) * self.model_weights[model] +
                        alpha * new_weights[model]
                    )

            logger.info(f"Updated model weights: {self.model_weights}")

        except Exception as e:
            logger.error(f"Error updating model weights: {str(e)}")


# Singleton instance
ensemble_engine = EnsembleFusionEngine()
