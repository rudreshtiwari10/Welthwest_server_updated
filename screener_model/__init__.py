"""
Multi-Timeframe Quantitative Stock Screener Module with DUAL Scoring (LONG + SHORT)

Components:
- MTFRegimeDetector: 4-state HMM market regime detection with SHORT interpretation
- MTFIndicatorCalculator: Multi-timeframe technical indicators
- PatternDetector: Candle and chart pattern detection
- RiskRewardEngine: SL/TP calculation and trade quality
- ScoringEngine: 0-100 stock scoring system with DUAL scoring (LONG + SHORT)

SHORT/Selling Components:
- BreakdownDetector: Detects resistance breakdowns, new lows, bearish patterns
- NewLowsDetector: Detects new period lows and cascade targets
- ResistanceFader: Identifies fade opportunities at resistance
- SellingSignalAggregator: Combines all SHORT signals into a comprehensive score
"""

from .mtf_regime_detector import MTFRegimeDetector
from .mtf_indicator_calculator import MTFIndicatorCalculator
from .pattern_detector import PatternDetector
from .risk_reward_engine import RiskRewardEngine
from .scoring_engine import ScoringEngine

# SHORT/Selling modules
from .breakdown_detector import BreakdownDetector
from .new_lows_detector import NewLowsDetector
from .resistance_fader import ResistanceFader
from .selling_signal_aggregator import SellingSignalAggregator

__all__ = [
    # Core modules
    'MTFRegimeDetector',
    'MTFIndicatorCalculator',
    'PatternDetector',
    'RiskRewardEngine',
    'ScoringEngine',
    # SHORT/Selling modules
    'BreakdownDetector',
    'NewLowsDetector',
    'ResistanceFader',
    'SellingSignalAggregator'
]
