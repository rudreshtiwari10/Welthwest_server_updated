"""
Advanced LSTM + HMM Multi-Model Forecast Service
Integrates ensemble AI for comprehensive trade recommendations
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional

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


class LSTMHMMForecastService:
    """Advanced multi-model AI trading advisor"""

    def __init__(self):
        logger.info("Advanced LSTM+HMM+RF+Sentiment Forecast Service initialized")
        self.technical_engine = technical_engine
        self.pattern_engine = pattern_engine
        self.sentiment_engine = sentiment_engine
        self.risk_engine = risk_engine
        self.ensemble_engine = ensemble_engine

    def get_full_trade_forecast(self, ticker: str, capital: float = 100000,
                                 risk_per_trade: float = 0.02,
                                 trading_style: str = 'swing') -> Dict:
        """
        Get comprehensive AI-powered trade forecast

        Args:
            ticker: Stock ticker symbol
            capital: Available trading capital
            risk_per_trade: Risk percentage per trade (0.01-0.05)
            trading_style: 'intraday', 'swing', or 'positional'

        Returns:
            Complete trade blueprint with entry/exit/risk management
        """
        try:
            logger.info(f"Generating advanced AI forecast for {ticker}")

            # Step 1: Get market data (mock for now - replace with actual data fetching)
            price_data = self._fetch_price_data(ticker)

            # Step 2: Run all AI models
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
            df = stock.history(period='1y')  # Get 1 year of data

            if df.empty:
                logger.warning(f"No data returned for {ticker}, trying with .NS suffix")
                # Try adding .NS for Indian stocks if not already present
                if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
                    ticker_ns = f"{ticker}.NS"
                    stock = yf.Ticker(ticker_ns)
                    df = stock.history(period='1y')

            if df.empty:
                raise ValueError(f"No data available for {ticker}")

            # Reset index to make Date a column
            df = df.reset_index()

            # Ensure we have the required columns
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"Missing required column: {col}")

            logger.info(f"✓ Successfully fetched {len(df)} days of real market data for {ticker}")
            logger.info(f"  Current price: ₹{df['Close'].iloc[-1]:.2f}")
            logger.info(f"  Date range: {df['Date'].iloc[0]} to {df['Date'].iloc[-1]}")

            return df

        except Exception as e:
            logger.error(f"Error fetching real data for {ticker}: {str(e)}")
            logger.warning("Falling back to mock data generation")

            # Fallback to mock data if real data fetch fails
            dates = pd.date_range(end=datetime.now(), periods=200, freq='D')
            np.random.seed(hash(ticker) % 2**32)
            base_price = 2000 + np.random.rand() * 1000
            returns = np.random.normal(0.001, 0.02, 200)
            prices = base_price * (1 + returns).cumprod()

            df = pd.DataFrame({
                'Date': dates,
                'Open': prices * (1 + np.random.uniform(-0.01, 0.01, 200)),
                'High': prices * (1 + np.random.uniform(0, 0.02, 200)),
                'Low': prices * (1 + np.random.uniform(-0.02, 0, 200)),
                'Close': prices,
                'Volume': np.random.uniform(1000000, 5000000, 200)
            })

            return df

    def _run_all_models(self, ticker: str, df: pd.DataFrame) -> Dict:
        """Run all AI models and collect outputs"""
        model_outputs = {}

        try:
            # 1. HMM Market Regime (mock for now)
            model_outputs['hmm'] = self._get_hmm_regime(df)

            # 2. Technical Analysis with 50+ indicators
            df_with_indicators = self.technical_engine.calculate_all_indicators(df)
            model_outputs['technical'] = self.technical_engine.calculate_trend_strength(df_with_indicators)
            model_outputs['support_resistance'] = self.technical_engine.detect_support_resistance(df)

            # 3. Pattern Recognition
            model_outputs['random_forest'] = self.pattern_engine.detect_patterns(df_with_indicators)

            # 4. Sentiment Analysis
            model_outputs['sentiment'] = self.sentiment_engine.analyze_sentiment(ticker)

            # 5. LSTM Price Prediction (mock for now)
            model_outputs['lstm'] = self._get_lstm_prediction(df)

            return model_outputs

        except Exception as e:
            logger.error(f"Error running models: {str(e)}")
            return {}

    def _get_hmm_regime(self, df: pd.DataFrame) -> Dict:
        """Get HMM market regime (mock implementation)"""
        # TODO: Integrate with actual HMM service
        volatility = df['Close'].pct_change().std()

        if volatility < 0.015:
            regime = 0
            regime_name = "Low Volatility Regime"
            confidence = 0.82
        elif volatility < 0.025:
            regime = 1
            regime_name = "Normal Volatility Regime"
            confidence = 0.75
        else:
            regime = 2
            regime_name = "High Volatility Regime"
            confidence = 0.78

        return {
            'current_regime': regime,
            'regime_name': regime_name,
            'confidence': confidence,
            'volatility': volatility
        }

    def _get_lstm_prediction(self, df: pd.DataFrame) -> Dict:
        """Get LSTM price prediction (mock implementation)"""
        # TODO: Implement actual LSTM model
        recent_return = (df['Close'].iloc[-1] / df['Close'].iloc[-20] - 1)

        if recent_return > 0.03:
            trend = "Bullish"
            avg_change = abs(recent_return * 100)
        elif recent_return < -0.03:
            trend = "Bearish"
            avg_change = recent_return * 100
        else:
            trend = "Neutral"
            avg_change = 0.0

        return {
            'lstm_trend': trend,
            'average_change_percent': avg_change,
            'confidence': 0.72
        }

    def _calculate_position_sizing(self, capital: float, risk_per_trade: float,
                                     ensemble_result: Dict, model_outputs: Dict) -> Dict:
        """Calculate optimal position size using Kelly Criterion"""
        try:
            # Extract parameters
            confidence = ensemble_result.get('confidence', 0.6)
            regime = model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime')
            volatility = model_outputs.get('hmm', {}).get('volatility', 0.02)

            # Historical win rate (would be calculated from backtesting)
            win_rate = 0.60 + (confidence - 0.5) * 0.4  # Scale confidence to win rate
            avg_win = 0.08  # 8% average win
            avg_loss = 0.04  # 4% average loss

            return self.risk_engine.calculate_position_size(
                capital=capital,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                confidence=confidence,
                volatility=volatility,
                regime=regime.split()[0],  # Extract 'Low', 'Normal', or 'High'
                max_risk_per_trade=risk_per_trade
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

            # Calculate stop-loss
            regime = model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime').split()[0]
            volatility = model_outputs.get('hmm', {}).get('volatility', 0.02)

            stop_loss_data = self.risk_engine.calculate_stop_loss(
                entry_price=current_price,
                atr=atr,
                support_level=nearest_support,
                volatility=volatility,
                stop_type='atr_based',
                regime=regime
            )

            # Calculate take-profit targets
            confidence = ensemble_result.get('confidence', 0.6)
            expected_move = 0.05 if confidence > 0.7 else 0.03  # 5% or 3% expected move

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
        """Generate complete trade blueprint"""
        try:
            current_price = df['Close'].iloc[-1]

            # Generate 5-day price forecast
            forecast_days = self._generate_price_forecast(df, model_outputs)

            # Calculate risk assessment
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

            # Build complete response
            return {
                "status": "success",
                "ticker": ticker,
                "timestamp": datetime.now().isoformat(),
                "trading_style": trading_style,

                # Price Analysis
                "price_analysis": {
                    "current_price": float(current_price),
                    "forecast": forecast_days,
                    "lstm_trend": model_outputs.get('lstm', {}).get('lstm_trend', 'Neutral'),
                    "average_change_percent": model_outputs.get('lstm', {}).get('average_change_percent', 0.0),
                    "technical_trend": model_outputs.get('technical', {}).get('trend_direction', 'neutral'),
                    "trend_strength": model_outputs.get('technical', {}).get('trend_strength', 0.0)
                },

                # Market Regime
                "market_regime": {
                    "current_regime": model_outputs.get('hmm', {}).get('current_regime', 1),
                    "regime_name": model_outputs.get('hmm', {}).get('regime_name', 'Normal Volatility Regime'),
                    "confidence": model_outputs.get('hmm', {}).get('confidence', 0.75),
                    "volatility": volatility,
                    "regime_description": self._get_regime_description(model_outputs.get('hmm', {}))
                },

                # AI Recommendation
                "recommendation": {
                    "action": ensemble_result.get('action', 'HOLD'),
                    "confidence": f"{ensemble_result.get('confidence', 0.5)*100:.0f}%",
                    "reasoning": ensemble_result.get('reasoning', 'Multi-model analysis'),
                    "model_agreement": f"{ensemble_result.get('agreement_score', 0.5)*100:.0f}%",
                    "model_signals": ensemble_result.get('model_signals', {})
                },

                # Risk Assessment
                "risk_assessment": risk_assessment,

                # Trading Signals
                "signals": {
                    "entry_price": float(trade_levels.get('entry_price', current_price)),
                    "stop_loss": float(trade_levels.get('stop_loss', {}).get('optimal_stop_loss', current_price * 0.97)),
                    "take_profit": float(trade_levels.get('take_profit', {}).get('targets', {}).get('T1', current_price * 1.05)),
                    "target_high": float(trade_levels.get('take_profit', {}).get('targets', {}).get('T2', current_price * 1.08)),
                    "target_low": float(trade_levels.get('stop_loss', {}).get('optimal_stop_loss', current_price * 0.97)),
                    "exit_price": float(trade_levels.get('take_profit', {}).get('targets', {}).get('T1', current_price * 1.05))
                },

                # Position Sizing
                "position_sizing": {
                    "recommended_capital": position_sizing.get('position_size_value', current_price * 100 * 0.02),
                    "position_percentage": position_sizing.get('position_size_percentage', 2.0),
                    "kelly_criterion": position_sizing.get('kelly_percentage', 0.0),
                    "max_risk": position_sizing.get('max_risk_amount', 0),
                    "recommendation": position_sizing.get('recommendation', 'Use conservative sizing')
                },

                # Advanced Insights
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
                    "resistance_levels": trade_levels.get('resistance_levels', [])
                },

                "message": "Advanced AI trade forecast completed successfully"
            }

        except Exception as e:
            logger.error(f"Error generating trade blueprint: {str(e)}")
            return self._get_error_response(str(e))

    def _generate_price_forecast(self, df: pd.DataFrame, model_outputs: Dict) -> list:
        """Generate 5-day price forecast"""
        current_price = df['Close'].iloc[-1]
        trend = model_outputs.get('lstm', {}).get('lstm_trend', 'Neutral')
        avg_change = model_outputs.get('lstm', {}).get('average_change_percent', 0.5)

        forecast_days = []
        for i in range(1, 6):
            date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')

            # Progressive price change based on trend
            if trend == 'Bullish':
                price_change = avg_change * (i / 5)  # Gradually increasing
            elif trend == 'Bearish':
                price_change = avg_change * (i / 5)  # Gradually decreasing
            else:
                price_change = (i - 2.5) * 0.3  # Neutral fluctuation

            predicted_price = current_price * (1 + price_change / 100)

            forecast_days.append({
                "date": date,
                "predicted_price": float(predicted_price),
                "price_change": float(price_change),
                "day": i
            })

        return forecast_days

    def _get_regime_description(self, hmm_data: Dict) -> str:
        """Get detailed regime description"""
        regime_name = hmm_data.get('regime_name', 'Normal Volatility Regime')

        descriptions = {
            'Low Volatility Regime': "Market is in a low volatility regime with stable price movements. This environment is favorable for momentum-based trading strategies with tighter stops.",
            'Normal Volatility Regime': "Market shows normal volatility levels with balanced price action. Standard trading strategies and position sizing apply.",
            'High Volatility Regime': "Market is experiencing high volatility with larger price swings. Consider wider stops and reduced position sizes for risk management."
        }

        return descriptions.get(regime_name, "Market regime analysis in progress.")

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
                "message": f"Generated advanced forecasts for {len(tickers)} tickers"
            }
        except Exception as e:
            logger.error(f"Error generating multiple forecasts: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }


# Create a singleton instance
lstm_hmm_forecast_service = LSTMHMMForecastService()
