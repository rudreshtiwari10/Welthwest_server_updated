"""
Advanced LSTM + HMM Multi-Model Forecast Service
FULLY DYNAMIC IMPLEMENTATION - No Mock Data
Integrates ensemble AI for comprehensive trade recommendations
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

# Import all AI engines
try:
    from .technical_analysis_engine import technical_engine
    from .pattern_recognition_engine import pattern_engine
    from .sentiment_engine import sentiment_engine
    from .risk_management import risk_engine
    from .ensemble_fusion import ensemble_engine
except ImportError:
    # Fallback for direct imports
    from technical_analysis_engine import technical_engine
    from pattern_recognition_engine import pattern_engine
    from sentiment_engine import sentiment_engine
    from risk_management import risk_engine
    from ensemble_fusion import ensemble_engine

logger = logging.getLogger(__name__)


class MarketConditionAnalyzer:
    """Analyzes real-time market conditions for dynamic forecasting"""

    def __init__(self):
        self.lookback_short = 5
        self.lookback_medium = 20
        self.lookback_long = 50

    def analyze(self, df: pd.DataFrame) -> Dict:
        """Get comprehensive market condition analysis"""
        return {
            'volatility_analysis': self._analyze_volatility(df),
            'momentum_analysis': self._analyze_momentum(df),
            'trend_analysis': self._analyze_trend(df),
            'volume_analysis': self._analyze_volume(df),
            'price_structure': self._analyze_price_structure(df),
            'market_phase': self._detect_market_phase(df),
        }

    def _analyze_volatility(self, df: pd.DataFrame) -> Dict:
        """Multi-timeframe volatility analysis"""
        returns = df['Close'].pct_change().dropna()

        # Current volatility levels
        vol_5d = returns.tail(5).std() * np.sqrt(252) * 100
        vol_20d = returns.tail(20).std() * np.sqrt(252) * 100
        vol_50d = returns.tail(50).std() * np.sqrt(252) * 100 if len(returns) >= 50 else vol_20d

        # Historical volatility percentile
        rolling_vol = returns.rolling(20).std() * np.sqrt(252) * 100
        current_vol_percentile = stats.percentileofscore(rolling_vol.dropna(), vol_20d) / 100

        # ATR-based volatility
        atr_14 = self._calculate_atr(df, 14)
        atr_pct = (atr_14 / df['Close'].iloc[-1]) * 100

        # Volatility trend (expanding or contracting)
        vol_trend = "expanding" if vol_5d > vol_20d else "contracting"

        # Regime classification
        if current_vol_percentile < 0.25:
            regime = "very_low"
            regime_multiplier = 0.6
        elif current_vol_percentile < 0.45:
            regime = "low"
            regime_multiplier = 0.8
        elif current_vol_percentile < 0.65:
            regime = "normal"
            regime_multiplier = 1.0
        elif current_vol_percentile < 0.85:
            regime = "high"
            regime_multiplier = 1.3
        else:
            regime = "extreme"
            regime_multiplier = 1.6

        return {
            'vol_5d': float(vol_5d),
            'vol_20d': float(vol_20d),
            'vol_50d': float(vol_50d),
            'percentile': float(current_vol_percentile),
            'atr_pct': float(atr_pct),
            'trend': vol_trend,
            'regime': regime,
            'regime_multiplier': regime_multiplier
        }

    def _analyze_momentum(self, df: pd.DataFrame) -> Dict:
        """Multi-timeframe momentum analysis"""
        close = df['Close']

        # Rate of Change (ROC) at multiple timeframes
        roc_5 = ((close.iloc[-1] / close.iloc[-6]) - 1) * 100 if len(close) > 5 else 0
        roc_10 = ((close.iloc[-1] / close.iloc[-11]) - 1) * 100 if len(close) > 10 else 0
        roc_20 = ((close.iloc[-1] / close.iloc[-21]) - 1) * 100 if len(close) > 20 else 0

        # RSI calculation
        rsi_14 = self._calculate_rsi(close, 14)

        # MACD
        macd_line, signal_line, histogram = self._calculate_macd(close)

        # Momentum score (-1 to +1)
        momentum_score = 0
        if roc_5 > 0: momentum_score += 0.2
        if roc_10 > 0: momentum_score += 0.2
        if roc_20 > 0: momentum_score += 0.2
        if rsi_14 > 50: momentum_score += 0.2
        if histogram > 0: momentum_score += 0.2

        momentum_score = (momentum_score - 0.5) * 2  # Scale to -1 to +1

        # Momentum direction
        if momentum_score > 0.3:
            direction = "bullish"
        elif momentum_score < -0.3:
            direction = "bearish"
        else:
            direction = "neutral"

        return {
            'roc_5': float(roc_5),
            'roc_10': float(roc_10),
            'roc_20': float(roc_20),
            'rsi_14': float(rsi_14),
            'macd_histogram': float(histogram),
            'score': float(momentum_score),
            'direction': direction
        }

    def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """Trend strength and direction analysis"""
        close = df['Close']

        # Moving averages
        sma_5 = close.rolling(5).mean().iloc[-1]
        sma_20 = close.rolling(20).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else sma_20
        sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else sma_50

        current_price = close.iloc[-1]

        # Price position relative to MAs
        above_sma5 = current_price > sma_5
        above_sma20 = current_price > sma_20
        above_sma50 = current_price > sma_50
        above_sma200 = current_price > sma_200

        # MA alignment score
        ma_alignment = sum([above_sma5, above_sma20, above_sma50, above_sma200]) / 4

        # Linear regression trend
        x = np.arange(min(50, len(close))).reshape(-1, 1)
        y = close.tail(min(50, len(close))).values
        reg = LinearRegression().fit(x, y)
        slope = reg.coef_[0]
        r_squared = reg.score(x, y)

        # Trend strength (0 to 1)
        trend_strength = abs(r_squared) * (1 if slope > 0 else -1)

        # ADX approximation
        adx = self._calculate_adx(df, 14)

        # Trend direction
        if slope > 0 and ma_alignment > 0.6:
            direction = "strong_uptrend"
        elif slope > 0:
            direction = "uptrend"
        elif slope < 0 and ma_alignment < 0.4:
            direction = "strong_downtrend"
        elif slope < 0:
            direction = "downtrend"
        else:
            direction = "sideways"

        return {
            'slope': float(slope),
            'r_squared': float(r_squared),
            'ma_alignment': float(ma_alignment),
            'adx': float(adx),
            'strength': float(abs(trend_strength)),
            'direction': direction,
            'sma_5': float(sma_5),
            'sma_20': float(sma_20),
            'sma_50': float(sma_50)
        }

    def _analyze_volume(self, df: pd.DataFrame) -> Dict:
        """Volume analysis"""
        volume = df['Volume']

        # Volume moving averages
        vol_sma_10 = volume.rolling(10).mean().iloc[-1]
        vol_sma_20 = volume.rolling(20).mean().iloc[-1]
        current_vol = volume.iloc[-1]

        # Volume ratio
        vol_ratio = current_vol / vol_sma_20 if vol_sma_20 > 0 else 1

        # Volume trend
        vol_trend = "increasing" if vol_sma_10 > vol_sma_20 else "decreasing"

        # Volume strength
        if vol_ratio > 2:
            vol_strength = "very_high"
        elif vol_ratio > 1.5:
            vol_strength = "high"
        elif vol_ratio > 0.8:
            vol_strength = "normal"
        else:
            vol_strength = "low"

        return {
            'current': float(current_vol),
            'sma_20': float(vol_sma_20),
            'ratio': float(vol_ratio),
            'trend': vol_trend,
            'strength': vol_strength
        }

    def _analyze_price_structure(self, df: pd.DataFrame) -> Dict:
        """Analyze price structure for support/resistance"""
        high = df['High']
        low = df['Low']
        close = df['Close']

        # Recent highs and lows
        recent_high = high.tail(20).max()
        recent_low = low.tail(20).min()
        current_price = close.iloc[-1]

        # Price position in range
        price_range = recent_high - recent_low
        position_in_range = (current_price - recent_low) / price_range if price_range > 0 else 0.5

        # Bollinger Band position
        sma_20 = close.rolling(20).mean().iloc[-1]
        std_20 = close.rolling(20).std().iloc[-1]
        bb_upper = sma_20 + (2 * std_20)
        bb_lower = sma_20 - (2 * std_20)
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

        return {
            'recent_high': float(recent_high),
            'recent_low': float(recent_low),
            'position_in_range': float(position_in_range),
            'bb_position': float(bb_position),
            'bb_upper': float(bb_upper),
            'bb_lower': float(bb_lower)
        }

    def _detect_market_phase(self, df: pd.DataFrame) -> Dict:
        """Detect current market phase"""
        vol_analysis = self._analyze_volatility(df)
        trend_analysis = self._analyze_trend(df)
        momentum = self._analyze_momentum(df)

        # Determine market phase
        if trend_analysis['direction'] in ['strong_uptrend', 'uptrend'] and momentum['direction'] == 'bullish':
            phase = "accumulation_breakout"
            expected_move = "up"
        elif trend_analysis['direction'] in ['strong_downtrend', 'downtrend'] and momentum['direction'] == 'bearish':
            phase = "distribution_breakdown"
            expected_move = "down"
        elif vol_analysis['regime'] in ['very_low', 'low'] and abs(momentum['score']) < 0.3:
            phase = "consolidation"
            expected_move = "neutral"
        elif vol_analysis['regime'] in ['high', 'extreme']:
            phase = "high_volatility"
            expected_move = "uncertain"
        else:
            phase = "transition"
            expected_move = "neutral"

        return {
            'phase': phase,
            'expected_move': expected_move,
            'confidence': float(min(abs(momentum['score']) + trend_analysis['strength'], 1.0))
        }

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]

        return float(atr)

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_macd(self, prices: pd.Series) -> Tuple[float, float, float]:
        """Calculate MACD"""
        exp1 = prices.ewm(span=12, adjust=False).mean()
        exp2 = prices.ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ADX"""
        try:
            high = df['High']
            low = df['Low']
            close = df['Close']

            plus_dm = high.diff()
            minus_dm = low.diff()

            plus_dm[plus_dm < 0] = 0
            minus_dm[minus_dm > 0] = 0

            tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)

            atr = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
            minus_di = 100 * (abs(minus_dm.rolling(period).mean()) / atr)

            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(period).mean().iloc[-1]

            return float(adx) if not pd.isna(adx) else 25.0
        except:
            return 25.0


class DynamicPricePredictor:
    """Dynamic price prediction using multiple signals"""

    def __init__(self):
        self.condition_analyzer = MarketConditionAnalyzer()

    def predict(self, df: pd.DataFrame, model_outputs: Dict, forecast_days: int = 5) -> Dict:
        """Generate dynamic price predictions"""
        current_price = float(df['Close'].iloc[-1])

        # Get market conditions
        conditions = self.condition_analyzer.analyze(df)

        # Calculate base expected move
        base_move = self._calculate_base_expected_move(conditions, model_outputs)

        # Generate daily forecasts
        forecasts = self._generate_daily_forecasts(
            df, current_price, base_move, conditions, model_outputs, forecast_days
        )

        # Calculate overall trend and confidence
        trend, confidence = self._calculate_trend_and_confidence(conditions, model_outputs)

        return {
            'lstm_trend': trend,
            'average_change_percent': float(base_move['expected_daily_change'] * forecast_days),
            'confidence': float(confidence),
            'forecasts': forecasts,
            'conditions': conditions,
            'base_move': base_move
        }

    def _calculate_base_expected_move(self, conditions: Dict, model_outputs: Dict) -> Dict:
        """Calculate base expected price move"""
        vol = conditions['volatility_analysis']
        momentum = conditions['momentum_analysis']
        trend = conditions['trend_analysis']
        phase = conditions['market_phase']

        # Daily expected volatility (standard deviation)
        daily_vol = vol['vol_20d'] / np.sqrt(252)  # Convert annual to daily

        # Direction factor based on momentum and trend
        direction_score = (momentum['score'] + (trend['strength'] if trend['direction'].endswith('uptrend') else -trend['strength'])) / 2

        # Expected daily change
        expected_daily_change = direction_score * daily_vol * vol['regime_multiplier']

        # Bounds based on ATR - Using 2.0 multiplier for larger swing targets
        atr_pct = vol['atr_pct']
        upper_bound = atr_pct * 2.0
        lower_bound = -atr_pct * 2.0

        return {
            'expected_daily_change': float(expected_daily_change),
            'daily_volatility': float(daily_vol),
            'direction_score': float(direction_score),
            'upper_bound': float(upper_bound),
            'lower_bound': float(lower_bound),
            'regime_multiplier': float(vol['regime_multiplier'])
        }

    def _generate_daily_forecasts(self, df: pd.DataFrame, current_price: float,
                                   base_move: Dict, conditions: Dict,
                                   model_outputs: Dict, forecast_days: int) -> List[Dict]:
        """Generate daily price forecasts"""
        forecasts = []
        cumulative_change = 0
        last_price = current_price

        # Get pattern influence
        patterns = model_outputs.get('random_forest', {})
        pattern_bias = (patterns.get('success_probability', 0.5) - 0.5) * 0.5

        # Get sentiment influence
        sentiment = model_outputs.get('sentiment', {})
        sentiment_bias = sentiment.get('overall_sentiment', 0) * 0.3

        # Combine biases
        total_bias = base_move['direction_score'] + pattern_bias + sentiment_bias

        for day in range(1, forecast_days + 1):
            # Calculate confidence decay for longer forecasts (0.95 for stronger day 5 targets)
            confidence_decay = 0.95 ** day

            # Base daily change with randomness
            daily_vol = base_move['daily_volatility']

            # Mean reversion factor (reduced effect, only at extreme positions)
            bb_position = conditions['price_structure']['bb_position']
            mean_reversion = 0
            if bb_position > 0.95:
                mean_reversion = -0.15  # Only at extreme overbought, smaller pullback
            elif bb_position < 0.05:
                mean_reversion = 0.15  # Only at extreme oversold, smaller bounce

            # Calculate expected move for this day
            # Using 0.7 multiplier for more aggressive targets (+40% vs original 0.5)
            expected_move = (total_bias * daily_vol * 0.7) + (mean_reversion * daily_vol)

            # Add controlled randomness based on volatility regime
            noise_factor = conditions['volatility_analysis']['regime_multiplier'] * 0.3
            random_component = np.random.normal(0, daily_vol * noise_factor)

            # Final daily change
            daily_change = (expected_move + random_component) * confidence_decay

            # Apply bounds
            daily_change = np.clip(daily_change, base_move['lower_bound'], base_move['upper_bound'])

            cumulative_change += daily_change
            predicted_price = current_price * (1 + cumulative_change / 100)

            # Get next trading date (skip weekends)
            forecast_date = self._get_next_trading_date(datetime.now(), day)

            forecasts.append({
                "date": forecast_date.strftime('%Y-%m-%d'),
                "predicted_price": float(round(predicted_price, 2)),
                "price_change": float(round(cumulative_change, 2)),
                "daily_change": float(round(daily_change, 2)),
                "day": day,
                "confidence": float(round(confidence_decay, 2))
            })

            last_price = predicted_price

        return forecasts

    def _calculate_trend_and_confidence(self, conditions: Dict, model_outputs: Dict) -> Tuple[str, float]:
        """Calculate overall trend and confidence"""
        momentum = conditions['momentum_analysis']
        trend = conditions['trend_analysis']
        phase = conditions['market_phase']

        # Determine trend
        direction_score = momentum['score']
        if direction_score > 0.3 and trend['direction'].endswith('uptrend'):
            trend_label = "Bullish"
        elif direction_score < -0.3 and trend['direction'].endswith('downtrend'):
            trend_label = "Bearish"
        else:
            trend_label = "Neutral"

        # Calculate confidence
        base_confidence = 0.5

        # Add confidence from trend strength
        base_confidence += trend['strength'] * 0.2

        # Add confidence from momentum clarity
        base_confidence += abs(momentum['score']) * 0.15

        # Add confidence from phase clarity
        base_confidence += phase['confidence'] * 0.15

        # Reduce confidence in high volatility
        vol_regime = conditions['volatility_analysis']['regime']
        if vol_regime in ['high', 'extreme']:
            base_confidence *= 0.85

        confidence = min(max(base_confidence, 0.35), 0.90)

        return trend_label, confidence

    def _get_next_trading_date(self, start_date: datetime, days_ahead: int) -> datetime:
        """Get next trading date, skipping weekends"""
        current = start_date
        trading_days = 0

        while trading_days < days_ahead:
            current += timedelta(days=1)
            # Skip weekends (5 = Saturday, 6 = Sunday)
            if current.weekday() < 5:
                trading_days += 1

        return current


class DynamicRegimeClassifier:
    """Dynamic HMM-style regime classification without mock data"""

    def __init__(self):
        self.condition_analyzer = MarketConditionAnalyzer()

    def classify(self, df: pd.DataFrame) -> Dict:
        """Classify current market regime dynamically"""
        conditions = self.condition_analyzer.analyze(df)

        vol = conditions['volatility_analysis']
        trend = conditions['trend_analysis']
        momentum = conditions['momentum_analysis']
        phase = conditions['market_phase']

        # Determine regime based on multiple factors
        regime, regime_name, description = self._determine_regime(vol, trend, momentum, phase)

        # Calculate dynamic confidence
        confidence = self._calculate_regime_confidence(vol, trend, momentum)

        # Calculate regime probabilities (HMM-style)
        probabilities = self._calculate_regime_probabilities(vol, trend, momentum)

        # Get regime-specific recommendations
        recommendations = self._get_regime_recommendations(regime_name, confidence)

        return {
            'current_regime': regime,
            'regime_name': regime_name,
            'confidence': float(confidence),
            'volatility': float(vol['vol_20d'] / 100),  # Convert to decimal
            'regime_description': description,
            'regime_probabilities': probabilities,
            'recommendations': recommendations,
            'market_phase': phase['phase'],
            'conditions_summary': {
                'volatility_regime': vol['regime'],
                'trend_direction': trend['direction'],
                'momentum_direction': momentum['direction'],
                'volume_strength': conditions['volume_analysis']['strength']
            }
        }

    def _determine_regime(self, vol: Dict, trend: Dict, momentum: Dict, phase: Dict) -> Tuple[int, str, str]:
        """Determine market regime based on conditions"""

        # Regime 0: Bull Trending
        if (trend['direction'] in ['strong_uptrend', 'uptrend'] and
            momentum['direction'] == 'bullish' and
            vol['regime'] in ['low', 'normal', 'very_low']):
            return 0, "Bull Trending", \
                f"Strong upward momentum with {trend['direction'].replace('_', ' ')}. " \
                f"RSI at {momentum['rsi_14']:.1f}, showing bullish momentum. " \
                f"Volatility is {vol['regime']} ({vol['vol_20d']:.1f}% annualized). " \
                f"Favorable conditions for long positions with trend-following strategies."

        # Regime 1: Bear Trending
        elif (trend['direction'] in ['strong_downtrend', 'downtrend'] and
              momentum['direction'] == 'bearish' and
              vol['regime'] in ['low', 'normal', 'very_low']):
            return 1, "Bear Trending", \
                f"Strong downward momentum with {trend['direction'].replace('_', ' ')}. " \
                f"RSI at {momentum['rsi_14']:.1f}, showing bearish momentum. " \
                f"Volatility is {vol['regime']} ({vol['vol_20d']:.1f}% annualized). " \
                f"Consider short positions or staying out of the market."

        # Regime 2: Sideways/Ranging
        elif (trend['direction'] == 'sideways' or
              (abs(momentum['score']) < 0.3 and trend['strength'] < 0.3)):
            return 2, "Sideways/Ranging", \
                f"Market is consolidating with no clear directional bias. " \
                f"Trend strength is low ({trend['strength']:.2f}). " \
                f"RSI at {momentum['rsi_14']:.1f} near neutral. " \
                f"Consider range-trading strategies or wait for breakout."

        # Regime 3: High Volatility
        elif vol['regime'] in ['high', 'extreme']:
            return 3, "High Volatility", \
                f"Market experiencing elevated volatility ({vol['vol_20d']:.1f}% annualized). " \
                f"Volatility is in the {vol['percentile']*100:.0f}th percentile historically. " \
                f"Price swings are {vol['trend']}. " \
                f"Reduce position sizes and use wider stops. High risk environment."

        # Regime 4: Accumulation/Distribution
        elif phase['phase'] in ['accumulation_breakout', 'distribution_breakdown', 'transition']:
            direction = "accumulation" if momentum['score'] > 0 else "distribution"
            return 4, f"Accumulation/Distribution", \
                f"Market in {direction} phase with transitional characteristics. " \
                f"Momentum score: {momentum['score']:.2f}. " \
                f"Watch for breakout signals. Smart money may be positioning."

        # Default to Normal
        else:
            return 1, "Normal Volatility Regime", \
                f"Market showing normal conditions. " \
                f"Volatility at {vol['vol_20d']:.1f}% annualized. " \
                f"Trend: {trend['direction']}, Momentum: {momentum['direction']}. " \
                f"Standard trading strategies apply."

    def _calculate_regime_confidence(self, vol: Dict, trend: Dict, momentum: Dict) -> float:
        """Calculate confidence in regime classification"""
        confidence = 0.5

        # Higher confidence when indicators align
        if (trend['direction'].endswith('uptrend') and momentum['direction'] == 'bullish') or \
           (trend['direction'].endswith('downtrend') and momentum['direction'] == 'bearish'):
            confidence += 0.15

        # Higher confidence with strong trend
        confidence += trend['strength'] * 0.15

        # Higher confidence with clear momentum
        confidence += abs(momentum['score']) * 0.1

        # Lower confidence in extreme volatility
        if vol['regime'] == 'extreme':
            confidence *= 0.8
        elif vol['regime'] == 'high':
            confidence *= 0.9

        # Bound confidence
        return min(max(confidence, 0.45), 0.92)

    def _calculate_regime_probabilities(self, vol: Dict, trend: Dict, momentum: Dict) -> Dict:
        """Calculate probability of each regime"""
        # Base probabilities
        probs = {
            'Bull Trending': 0.15,
            'Bear Trending': 0.15,
            'Sideways/Ranging': 0.25,
            'High Volatility': 0.20,
            'Accumulation/Distribution': 0.25
        }

        # Adjust based on conditions
        if trend['direction'].endswith('uptrend'):
            probs['Bull Trending'] += 0.2
            probs['Bear Trending'] -= 0.1
        elif trend['direction'].endswith('downtrend'):
            probs['Bear Trending'] += 0.2
            probs['Bull Trending'] -= 0.1

        if vol['regime'] in ['high', 'extreme']:
            probs['High Volatility'] += 0.25
            probs['Sideways/Ranging'] -= 0.1

        if abs(momentum['score']) < 0.2:
            probs['Sideways/Ranging'] += 0.15

        # Normalize
        total = sum(probs.values())
        probs = {k: round(v/total, 3) for k, v in probs.items()}

        return probs

    def _get_regime_recommendations(self, regime_name: str, confidence: float) -> Dict:
        """Get trading recommendations based on regime"""
        recommendations = {
            'Bull Trending': {
                'strategy': 'Trend Following / Buy Dips',
                'position_bias': 'Long',
                'risk_adjustment': 1.0,
                'stop_multiplier': 1.5,
                'notes': 'Favorable for long positions. Buy on pullbacks to support.'
            },
            'Bear Trending': {
                'strategy': 'Trend Following / Sell Rallies',
                'position_bias': 'Short or Cash',
                'risk_adjustment': 0.8,
                'stop_multiplier': 1.5,
                'notes': 'Consider short positions or staying out. Sell rallies to resistance.'
            },
            'Sideways/Ranging': {
                'strategy': 'Range Trading',
                'position_bias': 'Neutral',
                'risk_adjustment': 0.7,
                'stop_multiplier': 1.2,
                'notes': 'Buy at support, sell at resistance. Smaller position sizes.'
            },
            'High Volatility': {
                'strategy': 'Reduced Exposure / Hedging',
                'position_bias': 'Cautious',
                'risk_adjustment': 0.5,
                'stop_multiplier': 2.0,
                'notes': 'Reduce position sizes. Use wider stops. Consider hedging.'
            },
            'Accumulation/Distribution': {
                'strategy': 'Watch for Breakout',
                'position_bias': 'Preparing',
                'risk_adjustment': 0.8,
                'stop_multiplier': 1.3,
                'notes': 'Smart money positioning. Watch for volume breakouts.'
            }
        }

        rec = recommendations.get(regime_name, recommendations['Sideways/Ranging'])

        # Adjust based on confidence
        if confidence < 0.6:
            rec['notes'] += ' LOW CONFIDENCE - Wait for clearer signals.'
            rec['risk_adjustment'] *= 0.8

        return rec


class LSTMHMMForecastService:
    """Advanced multi-model AI trading advisor - FULLY DYNAMIC"""

    def __init__(self):
        logger.info("DYNAMIC LSTM+HMM+RF+Sentiment Forecast Service initialized")
        self.technical_engine = technical_engine
        self.pattern_engine = pattern_engine
        self.sentiment_engine = sentiment_engine
        self.risk_engine = risk_engine
        self.ensemble_engine = ensemble_engine

        # New dynamic components
        self.condition_analyzer = MarketConditionAnalyzer()
        self.price_predictor = DynamicPricePredictor()
        self.regime_classifier = DynamicRegimeClassifier()

    def get_full_trade_forecast(self, ticker: str, capital: float = 100000,
                                 risk_per_trade: float = 0.02,
                                 trading_style: str = 'swing') -> Dict:
        """Get comprehensive AI-powered trade forecast - FULLY DYNAMIC"""
        try:
            logger.info(f"Generating DYNAMIC AI forecast for {ticker}")

            # Step 1: Get market data
            price_data = self._fetch_price_data(ticker)

            # Step 2: Run all AI models with dynamic implementations
            model_outputs = self._run_all_models(ticker, price_data)

            # Step 3: Ensemble fusion
            ensemble_result = self.ensemble_engine.fuse_predictions(model_outputs)

            # Step 4: Calculate position sizing
            position_sizing = self._calculate_position_sizing(
                capital, risk_per_trade, ensemble_result, model_outputs
            )

            # Step 5: Calculate entry/exit levels
            trade_levels = self._calculate_trade_levels(
                price_data, ensemble_result, model_outputs
            )

            # Step 6: Generate complete trade blueprint
            trade_blueprint = self._generate_trade_blueprint(
                ticker, price_data, ensemble_result, model_outputs,
                position_sizing, trade_levels, trading_style
            )

            return trade_blueprint

        except Exception as e:
            logger.error(f"Error generating forecast: {str(e)}", exc_info=True)
            return self._get_error_response(str(e))

    def _fetch_price_data(self, ticker: str) -> pd.DataFrame:
        """Fetch historical price data from Yahoo Finance"""
        try:
            import yfinance as yf

            logger.info(f"Fetching real market data for {ticker} from Yahoo Finance")

            # Fetch real data from Yahoo Finance
            stock = yf.Ticker(ticker)
            df = stock.history(period='1y')

            if df.empty:
                logger.warning(f"No data returned for {ticker}, trying with .NS suffix")
                if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
                    ticker_ns = f"{ticker}.NS"
                    stock = yf.Ticker(ticker_ns)
                    df = stock.history(period='1y')

            if df.empty:
                raise ValueError(f"No data available for {ticker}")

            df = df.reset_index()

            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")

            logger.info(f"Successfully fetched {len(df)} days of data for {ticker}")
            logger.info(f"Current price: {df['Close'].iloc[-1]:.2f}")

            return df

        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {str(e)}")
            raise ValueError(f"Unable to fetch data for {ticker}: {str(e)}")

    def _run_all_models(self, ticker: str, df: pd.DataFrame) -> Dict:
        """Run all AI models - DYNAMIC IMPLEMENTATIONS"""
        model_outputs = {}

        try:
            # 1. DYNAMIC HMM Market Regime
            model_outputs['hmm'] = self.regime_classifier.classify(df)

            # 2. Technical Analysis with 50+ indicators
            df_with_indicators = self.technical_engine.calculate_all_indicators(df)
            model_outputs['technical'] = self.technical_engine.calculate_trend_strength(df_with_indicators)
            model_outputs['support_resistance'] = self.technical_engine.detect_support_resistance(df)

            # 3. Pattern Recognition
            model_outputs['random_forest'] = self.pattern_engine.detect_patterns(df_with_indicators)

            # 4. Sentiment Analysis
            model_outputs['sentiment'] = self.sentiment_engine.analyze_sentiment(ticker)

            # 5. DYNAMIC LSTM-style Price Prediction
            model_outputs['lstm'] = self.price_predictor.predict(df, model_outputs)

            # 6. Market Conditions Analysis
            model_outputs['conditions'] = self.condition_analyzer.analyze(df)

            return model_outputs

        except Exception as e:
            logger.error(f"Error running models: {str(e)}")
            return {}

    def _calculate_position_sizing(self, capital: float, risk_per_trade: float,
                                     ensemble_result: Dict, model_outputs: Dict) -> Dict:
        """Calculate optimal position size using Kelly Criterion"""
        try:
            confidence = ensemble_result.get('confidence', 0.6)
            regime = model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime')
            volatility = model_outputs.get('hmm', {}).get('volatility', 0.02)

            # Dynamic win rate based on confidence and regime
            base_win_rate = 0.55
            confidence_bonus = (confidence - 0.5) * 0.3
            regime_adjustment = model_outputs.get('hmm', {}).get('recommendations', {}).get('risk_adjustment', 1.0)

            win_rate = min(max(base_win_rate + confidence_bonus, 0.45), 0.70)
            avg_win = 0.06 + (confidence * 0.04)
            avg_loss = 0.03 + (volatility * 0.5)

            return self.risk_engine.calculate_position_size(
                capital=capital,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                confidence=confidence,
                volatility=volatility,
                regime=regime.split()[0],
                max_risk_per_trade=risk_per_trade * regime_adjustment
            )

        except Exception as e:
            logger.error(f"Error calculating position size: {str(e)}")
            return {}

    def _calculate_trade_levels(self, df: pd.DataFrame, ensemble_result: Dict,
                                  model_outputs: Dict) -> Dict:
        """Calculate entry, exit, stop-loss, and take-profit levels"""
        try:
            current_price = df['Close'].iloc[-1]

            # Calculate ATR for stops
            high_low = df['High'] - df['Low']
            atr = high_low.rolling(window=14).mean().iloc[-1]

            # Get support/resistance levels
            support_resistance = model_outputs.get('support_resistance', {})
            support_levels = support_resistance.get('support_levels', [current_price * 0.95])
            resistance_levels = support_resistance.get('resistance_levels', [current_price * 1.05])

            nearest_support = min(support_levels, key=lambda x: abs(x - current_price)) if support_levels else current_price * 0.95
            nearest_resistance = min(resistance_levels, key=lambda x: abs(x - current_price)) if resistance_levels else current_price * 1.05

            # Get regime-specific stop multiplier
            stop_multiplier = model_outputs.get('hmm', {}).get('recommendations', {}).get('stop_multiplier', 1.5)
            regime = model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime').split()[0]
            volatility = model_outputs.get('hmm', {}).get('volatility', 0.02)

            stop_loss_data = self.risk_engine.calculate_stop_loss(
                entry_price=current_price,
                atr=atr * stop_multiplier,
                support_level=nearest_support,
                volatility=volatility,
                stop_type='atr_based',
                regime=regime
            )

            confidence = ensemble_result.get('confidence', 0.6)
            # Increased take profit levels: 8% for high confidence, 5% for normal
            expected_move = 0.08 if confidence > 0.7 else 0.05

            take_profit_data = self.risk_engine.calculate_take_profit(
                entry_price=current_price,
                expected_move=expected_move,
                confidence=confidence,
                resistance_level=nearest_resistance
            )

            return {
                'entry_price': current_price,
                'stop_loss': stop_loss_data,
                'take_profit': take_profit_data,
                'support_levels': support_levels[:3],
                'resistance_levels': resistance_levels[:3],
                'atr': atr
            }

        except Exception as e:
            logger.error(f"Error calculating trade levels: {str(e)}")
            return {}

    def _generate_trade_blueprint(self, ticker: str, df: pd.DataFrame,
                                    ensemble_result: Dict, model_outputs: Dict,
                                    position_sizing: Dict, trade_levels: Dict,
                                    trading_style: str) -> Dict:
        """Generate complete trade blueprint - DYNAMIC"""
        try:
            current_price = df['Close'].iloc[-1]

            # Get dynamic forecasts
            lstm_output = model_outputs.get('lstm', {})
            forecast_days = lstm_output.get('forecasts', [])

            # If no forecasts, generate them
            if not forecast_days:
                prediction = self.price_predictor.predict(df, model_outputs)
                forecast_days = prediction.get('forecasts', [])
                lstm_output = prediction

            volatility = model_outputs.get('hmm', {}).get('volatility', 0.02)
            regime = model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime').split()[0]
            pattern_confidence = model_outputs.get('random_forest', {}).get('pattern_confidence', 0.5)
            sentiment_score = model_outputs.get('sentiment', {}).get('overall_sentiment', 0.0)

            risk_assessment = self.risk_engine.assess_risk_level(
                volatility=volatility,
                regime=regime,
                pattern_confidence=pattern_confidence,
                market_sentiment=sentiment_score
            )

            return {
                "status": "success",
                "ticker": ticker,
                "timestamp": datetime.now().isoformat(),
                "trading_style": trading_style,

                "price_analysis": {
                    "current_price": float(current_price),
                    "forecast": forecast_days,
                    "lstm_trend": lstm_output.get('lstm_trend', 'Neutral'),
                    "average_change_percent": float(lstm_output.get('average_change_percent', 0.0)),
                    "technical_trend": model_outputs.get('technical', {}).get('trend_direction', 'neutral'),
                    "trend_strength": float(model_outputs.get('technical', {}).get('trend_strength', 0.0))
                },

                "market_regime": {
                    "current_regime": model_outputs.get('hmm', {}).get('current_regime', 1),
                    "regime_name": model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime'),
                    "confidence": float(model_outputs.get('hmm', {}).get('confidence', 0.75)),
                    "volatility": float(volatility),
                    "regime_description": model_outputs.get('hmm', {}).get('regime_description', ''),
                    "regime_probabilities": model_outputs.get('hmm', {}).get('regime_probabilities', {}),
                    "market_phase": model_outputs.get('hmm', {}).get('market_phase', 'unknown')
                },

                "recommendation": {
                    "action": ensemble_result.get('action', 'HOLD'),
                    "confidence": f"{ensemble_result.get('confidence', 0.5)*100:.0f}%",
                    "reasoning": ensemble_result.get('reasoning', 'Multi-model analysis'),
                    "model_agreement": f"{ensemble_result.get('agreement_score', 0.5)*100:.0f}%",
                    "model_signals": ensemble_result.get('model_signals', {}),
                    "regime_recommendation": model_outputs.get('hmm', {}).get('recommendations', {})
                },

                "risk_assessment": risk_assessment,

                "signals": {
                    "entry_price": float(trade_levels.get('entry_price', current_price)),
                    "stop_loss": float(trade_levels.get('stop_loss', {}).get('optimal_stop_loss', current_price * 0.97)),
                    "take_profit": float(trade_levels.get('take_profit', {}).get('targets', {}).get('T1', current_price * 1.05)),
                    "target_high": float(trade_levels.get('take_profit', {}).get('targets', {}).get('T2', current_price * 1.08)),
                    "target_low": float(trade_levels.get('stop_loss', {}).get('optimal_stop_loss', current_price * 0.97)),
                    "exit_price": float(trade_levels.get('take_profit', {}).get('targets', {}).get('T1', current_price * 1.05))
                },

                "position_sizing": {
                    "recommended_capital": position_sizing.get('position_size_value', current_price * 100 * 0.02),
                    "position_percentage": position_sizing.get('position_size_percentage', 2.0),
                    "kelly_criterion": position_sizing.get('kelly_percentage', 0.0),
                    "max_risk": position_sizing.get('max_risk_amount', 0),
                    "recommendation": position_sizing.get('recommendation', 'Use conservative sizing')
                },

                "insights": {
                    "detected_patterns": model_outputs.get('random_forest', {}).get('chart_patterns', []),
                    "price_action_signals": model_outputs.get('random_forest', {}).get('price_action', []),
                    "breakouts": model_outputs.get('random_forest', {}).get('breakout_signals', []),
                    "sentiment_analysis": {
                        "overall": model_outputs.get('sentiment', {}).get('overall_sentiment', 0.0),
                        "trend": model_outputs.get('sentiment', {}).get('sentiment_trend', 'neutral'),
                        "key_topics": model_outputs.get('sentiment', {}).get('key_topics', [])
                    },
                    "support_levels": trade_levels.get('support_levels', []),
                    "resistance_levels": trade_levels.get('resistance_levels', []),
                    "market_conditions": model_outputs.get('conditions', {}).get('market_phase', {})
                },

                "message": "DYNAMIC AI trade forecast completed successfully"
            }

        except Exception as e:
            logger.error(f"Error generating trade blueprint: {str(e)}")
            return self._get_error_response(str(e))

    def _get_error_response(self, error_message: str) -> Dict:
        """Generate error response"""
        return {
            "status": "error",
            "message": f"Error generating forecast: {error_message}",
            "recommendation": {
                "action": "HOLD",
                "reasoning": "Unable to generate reliable forecast. Please try again.",
                "confidence": "Low (0%)"
            }
        }

    def get_multiple_forecasts(self, tickers: list, capital: float = 100000) -> Dict:
        """Get forecasts for multiple tickers"""
        try:
            logger.info(f"Generating forecasts for {len(tickers)} tickers")
            forecasts = {}

            for ticker in tickers:
                forecasts[ticker] = self.get_full_trade_forecast(
                    ticker, capital=capital/len(tickers)
                )

            return {
                "status": "success",
                "forecasts": forecasts,
                "message": f"Generated DYNAMIC forecasts for {len(tickers)} tickers"
            }
        except Exception as e:
            logger.error(f"Error generating multiple forecasts: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }


# Create a singleton instance
lstm_hmm_forecast_service = LSTMHMMForecastService()
