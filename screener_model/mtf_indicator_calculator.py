"""
Multi-Timeframe Indicator Calculator

Calculates technical indicators across multiple timeframes:
- 5-min: Scalping (15-60 min hold, 1:1.5-2.5 R:R)
- 15-min: Intraday swing (1-4 hours, 1:2-3 R:R)
- 1-hour: Short-term swing (1-5 days, 1:3-5 R:R)
- 1-day: Position trading (5-20 days, 1:4-7 R:R)

Indicator Categories:
1. Trend: EMA crossovers, VWAP deviation, Trend Quality Score
2. Momentum: RSI, Stochastic RSI, Rate-of-Change
3. Volatility: ATR, ATR Ratio, VCP detection
4. Volume: RVOL, CMF, Institutional Participation
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
from services.stock_service import get_historical_data, get_ohlc_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MTFIndicatorCalculator:
    """
    Multi-Timeframe Technical Indicator Calculator

    Supports 4 timeframes with specific configurations for each.
    """

    # Timeframe configurations
    TIMEFRAME_CONFIG = {
        '5m': {
            'name': 'Scalping',
            'hold_time': '15-60 minutes',
            'min_rr': 1.5,
            'max_rr': 2.5,
            'period_days': 5,
            'interval': '5m',
            'atr_multiplier': 1.0
        },
        '15m': {
            'name': 'Intraday Swing',
            'hold_time': '1-4 hours',
            'min_rr': 2.0,
            'max_rr': 3.0,
            'period_days': 10,
            'interval': '15m',
            'atr_multiplier': 1.2
        },
        '1h': {
            'name': 'Short-term Swing',
            'hold_time': '1-5 days',
            'min_rr': 3.0,
            'max_rr': 5.0,
            'period_days': 60,
            'interval': '1h',
            'atr_multiplier': 1.5
        },
        '1d': {
            'name': 'Position Trading',
            'hold_time': '5-20 days',
            'min_rr': 4.0,
            'max_rr': 7.0,
            'period_days': 365,
            'interval': '1d',
            'atr_multiplier': 2.0
        }
    }

    # EMA crossover configurations
    EMA_CROSSOVERS = [
        (9, 21, 'short_term'),      # Fast crossover
        (21, 55, 'medium_term'),    # Medium crossover
        (50, 200, 'golden_death'),  # Golden/Death cross
    ]

    def __init__(self, ticker: str, timeframe: str = '1d', pre_fetched_data: pd.DataFrame = None):
        """
        Initialize calculator for specific ticker and timeframe

        Args:
            ticker: Stock ticker symbol
            timeframe: One of '5m', '15m', '1h', '1d'
            pre_fetched_data: Optional pre-fetched DataFrame to avoid API calls
        """
        self.ticker = ticker
        self.timeframe = timeframe
        self.config = self.TIMEFRAME_CONFIG.get(timeframe, self.TIMEFRAME_CONFIG['1d'])
        self.df = None

        # Use pre-fetched data if provided, otherwise load from API
        if pre_fetched_data is not None and not pre_fetched_data.empty:
            self.df = pre_fetched_data.copy()
        else:
            self._load_data()

    def _load_data(self):
        """Load OHLCV data for the configured timeframe"""
        try:
            period_days = self.config['period_days']
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)

            # For intraday timeframes, use shorter period
            if self.timeframe in ['5m', '15m']:
                # yfinance limits intraday data to ~60 days
                start_date = end_date - timedelta(days=min(period_days, 59))

            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            self.df = get_ohlc_data(
                self.ticker,
                start_str,
                end_str,
                self.config['interval']
            )

            if self.df is None or self.df.empty:
                # Fallback to daily data
                logger.warning(f"No {self.timeframe} data, falling back to daily")
                self.df = get_historical_data(self.ticker, period="6mo")

        except Exception as e:
            logger.error(f"Error loading data for {self.ticker}: {str(e)}")
            self.df = pd.DataFrame()

    def calculate_trend_indicators(self) -> Dict[str, Any]:
        """
        Calculate trend indicators:
        - EMA crossovers (9/21, 21/55, 50/200)
        - VWAP deviation
        - Trend Quality Score (TQS)

        Returns:
            Dictionary with trend indicators
        """
        if self.df is None or self.df.empty:
            return self._empty_trend_result()

        try:
            df = self.df.copy()
            result = {
                'ema_crossovers': {},
                'vwap': {},
                'trend_quality_score': 0,
                'overall_trend': 'neutral',
                'trend_strength': 0
            }

            # Calculate EMAs
            ema_9 = df['Close'].ewm(span=9, adjust=False).mean()
            ema_21 = df['Close'].ewm(span=21, adjust=False).mean()
            ema_55 = df['Close'].ewm(span=55, adjust=False).mean()
            ema_50 = df['Close'].ewm(span=50, adjust=False).mean()
            ema_200 = df['Close'].ewm(span=200, adjust=False).mean()

            current_price = df['Close'].iloc[-1]

            # EMA Crossover Analysis
            # Short-term (9/21)
            ema_9_current = ema_9.iloc[-1]
            ema_21_current = ema_21.iloc[-1]
            short_term_bullish = ema_9_current > ema_21_current
            result['ema_crossovers']['9_21'] = {
                'ema_fast': round(float(ema_9_current), 2),
                'ema_slow': round(float(ema_21_current), 2),
                'bullish': short_term_bullish,
                'signal': 'bullish' if short_term_bullish else 'bearish'
            }

            # Medium-term (21/55)
            ema_55_current = ema_55.iloc[-1] if len(ema_55) > 55 else ema_21_current
            medium_term_bullish = ema_21_current > ema_55_current
            result['ema_crossovers']['21_55'] = {
                'ema_fast': round(float(ema_21_current), 2),
                'ema_slow': round(float(ema_55_current), 2),
                'bullish': medium_term_bullish,
                'signal': 'bullish' if medium_term_bullish else 'bearish'
            }

            # Golden/Death Cross (50/200)
            ema_50_current = ema_50.iloc[-1] if len(ema_50) > 50 else current_price
            ema_200_current = ema_200.iloc[-1] if len(ema_200) > 200 else ema_50_current
            golden_cross = ema_50_current > ema_200_current
            result['ema_crossovers']['50_200'] = {
                'ema_fast': round(float(ema_50_current), 2),
                'ema_slow': round(float(ema_200_current), 2),
                'bullish': golden_cross,
                'signal': 'golden_cross' if golden_cross else 'death_cross'
            }

            # VWAP Calculation
            vwap = self._calculate_vwap(df)
            vwap_current = vwap.iloc[-1] if len(vwap) > 0 else current_price
            vwap_deviation = ((current_price - vwap_current) / vwap_current) * 100

            result['vwap'] = {
                'value': round(float(vwap_current), 2),
                'deviation_pct': round(float(vwap_deviation), 2),
                'above_vwap': current_price > vwap_current,
                'signal': 'bullish' if current_price > vwap_current else 'bearish'
            }

            # Trend Quality Score (0-100)
            tqs = self._calculate_trend_quality_score(
                short_term_bullish, medium_term_bullish, golden_cross,
                current_price > vwap_current, vwap_deviation
            )
            result['trend_quality_score'] = tqs

            # Overall trend determination
            bullish_signals = sum([
                short_term_bullish,
                medium_term_bullish,
                golden_cross,
                current_price > vwap_current
            ])

            if bullish_signals >= 3:
                result['overall_trend'] = 'bullish'
                result['trend_strength'] = min(bullish_signals * 25, 100)
            elif bullish_signals <= 1:
                result['overall_trend'] = 'bearish'
                result['trend_strength'] = min((4 - bullish_signals) * 25, 100)
            else:
                result['overall_trend'] = 'neutral'
                result['trend_strength'] = 50

            return result

        except Exception as e:
            logger.error(f"Error calculating trend indicators: {str(e)}")
            return self._empty_trend_result()

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price"""
        try:
            typical_price = (df['High'] + df['Low'] + df['Close']) / 3
            volume = df['Volume'].fillna(0)

            if volume.sum() == 0:
                return typical_price

            cumulative_tp_vol = (typical_price * volume).cumsum()
            cumulative_vol = volume.cumsum().replace(0, 1)

            return cumulative_tp_vol / cumulative_vol
        except:
            return df['Close']

    def _calculate_trend_quality_score(self, short_bullish: bool, medium_bullish: bool,
                                       golden: bool, above_vwap: bool,
                                       vwap_dev: float) -> int:
        """Calculate Trend Quality Score (0-100)"""
        score = 0

        # EMA alignment (60 points max)
        if short_bullish:
            score += 20
        if medium_bullish:
            score += 20
        if golden:
            score += 20

        # VWAP position (25 points max)
        if above_vwap:
            score += 15
            # Bonus for strong deviation
            if vwap_dev > 1:
                score += 5
            if vwap_dev > 2:
                score += 5

        # Consistency bonus (15 points)
        aligned_count = sum([short_bullish, medium_bullish, golden])
        if aligned_count == 3:
            score += 15
        elif aligned_count == 0:
            score += 15  # Consistent bearish is also a signal

        return min(score, 100)

    def calculate_momentum_indicators(self) -> Dict[str, Any]:
        """
        Calculate momentum indicators:
        - RSI(14) with adaptive thresholds
        - Stochastic RSI
        - Rate-of-Change exhaustion

        Returns:
            Dictionary with momentum indicators
        """
        if self.df is None or self.df.empty:
            return self._empty_momentum_result()

        try:
            df = self.df.copy()
            result = {
                'rsi': {},
                'stochastic_rsi': {},
                'roc': {},
                'momentum_score': 0
            }

            # RSI(14)
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(50)

            rsi_current = float(rsi.iloc[-1])
            rsi_prev = float(rsi.iloc[-2]) if len(rsi) > 1 else rsi_current

            # Adaptive thresholds based on trend
            oversold_threshold = 30
            overbought_threshold = 70

            rsi_signal = 'neutral'
            if rsi_current < oversold_threshold:
                rsi_signal = 'oversold'
            elif rsi_current > overbought_threshold:
                rsi_signal = 'overbought'
            elif rsi_current > rsi_prev and rsi_current > 50:
                rsi_signal = 'bullish_momentum'
            elif rsi_current < rsi_prev and rsi_current < 50:
                rsi_signal = 'bearish_momentum'

            result['rsi'] = {
                'value': round(rsi_current, 2),
                'previous': round(rsi_prev, 2),
                'signal': rsi_signal,
                'oversold': rsi_current < oversold_threshold,
                'overbought': rsi_current > overbought_threshold,
                'divergence': self._check_rsi_divergence(df, rsi)
            }

            # Stochastic RSI
            rsi_series = rsi.dropna()
            if len(rsi_series) >= 14:
                rsi_min = rsi_series.rolling(window=14).min()
                rsi_max = rsi_series.rolling(window=14).max()
                stoch_rsi_k = ((rsi_series - rsi_min) / (rsi_max - rsi_min + 1e-10)) * 100
                stoch_rsi_d = stoch_rsi_k.rolling(window=3).mean()

                k_current = float(stoch_rsi_k.iloc[-1]) if not pd.isna(stoch_rsi_k.iloc[-1]) else 50
                d_current = float(stoch_rsi_d.iloc[-1]) if not pd.isna(stoch_rsi_d.iloc[-1]) else 50

                stoch_signal = 'neutral'
                if k_current < 20 and k_current > d_current:
                    stoch_signal = 'buy'
                elif k_current > 80 and k_current < d_current:
                    stoch_signal = 'sell'

                result['stochastic_rsi'] = {
                    'k': round(k_current, 2),
                    'd': round(d_current, 2),
                    'signal': stoch_signal,
                    'oversold': k_current < 20,
                    'overbought': k_current > 80
                }
            else:
                result['stochastic_rsi'] = {
                    'k': 50, 'd': 50, 'signal': 'neutral',
                    'oversold': False, 'overbought': False
                }

            # Rate of Change (ROC) - 12 period
            roc = ((df['Close'] - df['Close'].shift(12)) / df['Close'].shift(12)) * 100
            roc = roc.fillna(0)
            roc_current = float(roc.iloc[-1])

            roc_signal = 'neutral'
            if roc_current > 5:
                roc_signal = 'strong_bullish'
            elif roc_current > 0:
                roc_signal = 'bullish'
            elif roc_current < -5:
                roc_signal = 'strong_bearish'
            elif roc_current < 0:
                roc_signal = 'bearish'

            # Check for exhaustion
            roc_exhaustion = abs(roc_current) > 10

            result['roc'] = {
                'value': round(roc_current, 2),
                'signal': roc_signal,
                'exhaustion': roc_exhaustion
            }

            # Momentum Score (0-100)
            momentum_score = self._calculate_momentum_score(result)
            result['momentum_score'] = momentum_score

            return result

        except Exception as e:
            logger.error(f"Error calculating momentum indicators: {str(e)}")
            return self._empty_momentum_result()

    def _check_rsi_divergence(self, df: pd.DataFrame, rsi: pd.Series) -> str:
        """Check for RSI divergence"""
        try:
            if len(df) < 20:
                return 'none'

            # Compare last 20 periods
            price_trend = df['Close'].iloc[-20:].diff().sum()
            rsi_trend = rsi.iloc[-20:].diff().sum()

            if price_trend > 0 and rsi_trend < 0:
                return 'bearish_divergence'
            elif price_trend < 0 and rsi_trend > 0:
                return 'bullish_divergence'

            return 'none'
        except:
            return 'none'

    def _calculate_momentum_score(self, momentum_data: Dict) -> int:
        """Calculate overall momentum score"""
        score = 50  # Start neutral

        rsi = momentum_data.get('rsi', {})
        stoch = momentum_data.get('stochastic_rsi', {})
        roc = momentum_data.get('roc', {})

        # RSI contribution
        rsi_signal = rsi.get('signal', 'neutral')
        if rsi_signal in ['bullish_momentum', 'oversold']:
            score += 15
        elif rsi_signal in ['bearish_momentum', 'overbought']:
            score -= 15

        # Stochastic RSI contribution
        stoch_signal = stoch.get('signal', 'neutral')
        if stoch_signal == 'buy':
            score += 20
        elif stoch_signal == 'sell':
            score -= 20

        # ROC contribution
        roc_signal = roc.get('signal', 'neutral')
        if roc_signal == 'strong_bullish':
            score += 15
        elif roc_signal == 'bullish':
            score += 10
        elif roc_signal == 'strong_bearish':
            score -= 15
        elif roc_signal == 'bearish':
            score -= 10

        return max(0, min(100, score))

    def calculate_volatility_indicators(self) -> Dict[str, Any]:
        """
        Calculate volatility indicators:
        - ATR(14)
        - ATR Ratio (5/50) for VCP detection
        - Bollinger Band squeeze

        Returns:
            Dictionary with volatility indicators
        """
        if self.df is None or self.df.empty:
            return self._empty_volatility_result()

        try:
            df = self.df.copy()
            result = {
                'atr': {},
                'atr_ratio': {},
                'vcp': {},
                'bollinger_squeeze': {},
                'volatility_state': 'normal'
            }

            # ATR(14)
            high_low = df['High'] - df['Low']
            high_close = abs(df['High'] - df['Close'].shift(1))
            low_close = abs(df['Low'] - df['Close'].shift(1))
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr_14 = true_range.ewm(span=14, adjust=False).mean()

            atr_current = float(atr_14.iloc[-1])
            atr_pct = (atr_current / df['Close'].iloc[-1]) * 100

            result['atr'] = {
                'value': round(atr_current, 2),
                'percentage': round(atr_pct, 2),
                'multiplier': self.config['atr_multiplier']
            }

            # ATR Ratio (5/50) for VCP detection
            atr_5 = true_range.ewm(span=5, adjust=False).mean()
            atr_50 = true_range.ewm(span=50, adjust=False).mean()

            atr_5_current = float(atr_5.iloc[-1])
            atr_50_current = float(atr_50.iloc[-1]) if len(atr_50) > 50 else atr_5_current

            atr_ratio = atr_5_current / (atr_50_current + 1e-10)

            # VCP Detection (Volatility Contraction Pattern)
            vcp_detected = atr_ratio < 0.7  # Volatility contracting
            vcp_breakout_ready = atr_ratio < 0.5

            result['atr_ratio'] = {
                'ratio': round(atr_ratio, 3),
                'atr_5': round(atr_5_current, 2),
                'atr_50': round(atr_50_current, 2),
                'contracting': atr_ratio < 1.0,
                'expanding': atr_ratio > 1.0
            }

            result['vcp'] = {
                'detected': vcp_detected,
                'breakout_ready': vcp_breakout_ready,
                'strength': 'strong' if vcp_breakout_ready else 'moderate' if vcp_detected else 'none'
            }

            # Bollinger Band Squeeze
            sma_20 = df['Close'].rolling(window=20).mean()
            std_20 = df['Close'].rolling(window=20).std()
            bb_upper = sma_20 + (2 * std_20)
            bb_lower = sma_20 - (2 * std_20)

            bb_width = ((bb_upper - bb_lower) / sma_20) * 100
            bb_width_current = float(bb_width.iloc[-1]) if not pd.isna(bb_width.iloc[-1]) else 5
            bb_width_avg = float(bb_width.rolling(window=50).mean().iloc[-1]) if len(bb_width) > 50 else bb_width_current

            squeeze = bb_width_current < bb_width_avg * 0.8

            result['bollinger_squeeze'] = {
                'width': round(bb_width_current, 2),
                'avg_width': round(bb_width_avg, 2),
                'squeeze': squeeze,
                'upper': round(float(bb_upper.iloc[-1]), 2) if not pd.isna(bb_upper.iloc[-1]) else 0,
                'lower': round(float(bb_lower.iloc[-1]), 2) if not pd.isna(bb_lower.iloc[-1]) else 0,
                'middle': round(float(sma_20.iloc[-1]), 2) if not pd.isna(sma_20.iloc[-1]) else 0
            }

            # Overall volatility state
            if squeeze or vcp_breakout_ready:
                result['volatility_state'] = 'compression'
            elif atr_ratio > 1.5:
                result['volatility_state'] = 'expansion'
            elif atr_pct > 3:
                result['volatility_state'] = 'high'
            elif atr_pct < 1:
                result['volatility_state'] = 'low'
            else:
                result['volatility_state'] = 'normal'

            return result

        except Exception as e:
            logger.error(f"Error calculating volatility indicators: {str(e)}")
            return self._empty_volatility_result()

    def calculate_volume_indicators(self) -> Dict[str, Any]:
        """
        Calculate volume indicators:
        - RVOL (Relative Volume to 20-day avg)
        - CMF (Chaikin Money Flow)
        - Institutional Participation Proxy

        Returns:
            Dictionary with volume indicators
        """
        if self.df is None or self.df.empty or 'Volume' not in self.df.columns:
            return self._empty_volume_result()

        try:
            df = self.df.copy()
            result = {
                'rvol': {},
                'cmf': {},
                'institutional_proxy': {},
                'volume_score': 0
            }

            volume = df['Volume'].fillna(0)

            if volume.sum() == 0:
                return self._empty_volume_result()

            # RVOL (Relative Volume)
            vol_20_avg = volume.rolling(window=20).mean()
            rvol = volume / vol_20_avg.replace(0, 1)

            rvol_current = float(rvol.iloc[-1]) if not pd.isna(rvol.iloc[-1]) else 1.0

            rvol_signal = 'normal'
            if rvol_current > 2.0:
                rvol_signal = 'very_high'
            elif rvol_current > 1.5:
                rvol_signal = 'high'
            elif rvol_current < 0.5:
                rvol_signal = 'very_low'
            elif rvol_current < 0.7:
                rvol_signal = 'low'

            result['rvol'] = {
                'value': round(rvol_current, 2),
                'signal': rvol_signal,
                'above_average': rvol_current > 1.0
            }

            # CMF (Chaikin Money Flow) - 20 period
            mfm = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'] + 1e-10)
            mfv = mfm * volume
            cmf = mfv.rolling(window=20).sum() / volume.rolling(window=20).sum().replace(0, 1)

            cmf_current = float(cmf.iloc[-1]) if not pd.isna(cmf.iloc[-1]) else 0

            cmf_signal = 'neutral'
            if cmf_current > 0.1:
                cmf_signal = 'strong_accumulation'
            elif cmf_current > 0:
                cmf_signal = 'accumulation'
            elif cmf_current < -0.1:
                cmf_signal = 'strong_distribution'
            elif cmf_current < 0:
                cmf_signal = 'distribution'

            result['cmf'] = {
                'value': round(cmf_current, 3),
                'signal': cmf_signal,
                'bullish': cmf_current > 0
            }

            # Institutional Participation Proxy
            # Based on volume spikes with price movement
            price_change = df['Close'].pct_change()
            vol_change = volume.pct_change()

            # Look for high volume with price movement (institutional activity)
            inst_proxy = (abs(price_change) * vol_change).rolling(window=5).mean()
            inst_current = float(inst_proxy.iloc[-1]) if not pd.isna(inst_proxy.iloc[-1]) else 0

            high_inst_activity = rvol_current > 1.5 and abs(cmf_current) > 0.05

            result['institutional_proxy'] = {
                'activity_score': round(inst_current * 100, 2),
                'high_activity': high_inst_activity,
                'direction': 'buying' if cmf_current > 0 else 'selling' if cmf_current < 0 else 'neutral'
            }

            # Volume Score (0-100)
            volume_score = self._calculate_volume_score(result)
            result['volume_score'] = volume_score

            return result

        except Exception as e:
            logger.error(f"Error calculating volume indicators: {str(e)}")
            return self._empty_volume_result()

    def _calculate_volume_score(self, volume_data: Dict) -> int:
        """Calculate overall volume score for confirmation"""
        score = 50

        rvol = volume_data.get('rvol', {})
        cmf = volume_data.get('cmf', {})
        inst = volume_data.get('institutional_proxy', {})

        # RVOL contribution
        rvol_val = rvol.get('value', 1.0)
        if rvol_val > 2.0:
            score += 25
        elif rvol_val > 1.5:
            score += 15
        elif rvol_val > 1.0:
            score += 5
        elif rvol_val < 0.5:
            score -= 20

        # CMF contribution
        cmf_signal = cmf.get('signal', 'neutral')
        if cmf_signal == 'strong_accumulation':
            score += 20
        elif cmf_signal == 'accumulation':
            score += 10
        elif cmf_signal == 'strong_distribution':
            score -= 20
        elif cmf_signal == 'distribution':
            score -= 10

        # Institutional activity
        if inst.get('high_activity', False):
            score += 10

        return max(0, min(100, score))

    def get_all_indicators(self) -> Dict[str, Any]:
        """
        Get all indicators for the configured timeframe

        Returns:
            Complete dictionary with all indicator categories
        """
        return {
            'ticker': self.ticker,
            'timeframe': self.timeframe,
            'timeframe_config': self.config,
            'current_price': round(float(self.df['Close'].iloc[-1]), 2) if self.df is not None and not self.df.empty else 0,
            'trend': self.calculate_trend_indicators(),
            'momentum': self.calculate_momentum_indicators(),
            'volatility': self.calculate_volatility_indicators(),
            'volume': self.calculate_volume_indicators(),
            'timestamp': datetime.now().isoformat()
        }

    # Empty result templates
    def _empty_trend_result(self) -> Dict:
        return {
            'ema_crossovers': {},
            'vwap': {'value': 0, 'deviation_pct': 0, 'above_vwap': False, 'signal': 'neutral'},
            'trend_quality_score': 0,
            'overall_trend': 'neutral',
            'trend_strength': 0
        }

    def _empty_momentum_result(self) -> Dict:
        return {
            'rsi': {'value': 50, 'signal': 'neutral', 'oversold': False, 'overbought': False},
            'stochastic_rsi': {'k': 50, 'd': 50, 'signal': 'neutral'},
            'roc': {'value': 0, 'signal': 'neutral', 'exhaustion': False},
            'momentum_score': 50
        }

    def _empty_volatility_result(self) -> Dict:
        return {
            'atr': {'value': 0, 'percentage': 0},
            'atr_ratio': {'ratio': 1.0},
            'vcp': {'detected': False, 'breakout_ready': False},
            'bollinger_squeeze': {'squeeze': False},
            'volatility_state': 'unknown'
        }

    def _empty_volume_result(self) -> Dict:
        return {
            'rvol': {'value': 1.0, 'signal': 'normal', 'above_average': False},
            'cmf': {'value': 0, 'signal': 'neutral', 'bullish': False},
            'institutional_proxy': {'high_activity': False, 'direction': 'neutral'},
            'volume_score': 50
        }
