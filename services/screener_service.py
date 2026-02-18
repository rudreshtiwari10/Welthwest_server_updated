"""
Stock Screener Engine - Rule-based stock filtering and ranking

Features:
- Screen stocks from NIFTY50, NIFTY100, S&P500
- Apply technical indicator filters
- Custom scoring algorithms
- Parallel processing for performance
- Cached results

Example Screening Rules:
- RSI < 30 (oversold stocks)
- Price > SMA50 (uptrend stocks)
- MACD crossover (momentum stocks)
- High volume stocks
- Bollinger Band breakouts
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Callable
import logging
from datetime import datetime, timedelta
# yfinance not directly used — screener operates via indicator_engine
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from services.indicators_service import indicator_engine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Stock universe definitions
NIFTY_50 = [
    'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS',
    'HINDUNILVR.NS', 'ITC.NS', 'SBIN.NS', 'BHARTIARTL.NS', 'KOTAKBANK.NS',
    'LT.NS', 'AXISBANK.NS', 'ASIANPAINT.NS', 'MARUTI.NS', 'TITAN.NS',
    'BAJFINANCE.NS', 'HCLTECH.NS', 'WIPRO.NS', 'ULTRACEMCO.NS', 'NESTLEIND.NS',
    'SUNPHARMA.NS', 'ONGC.NS', 'NTPC.NS', 'POWERGRID.NS', 'M&M.NS',
    'TATASTEEL.NS', 'JSWSTEEL.NS', 'TECHM.NS', 'ADANIENT.NS', 'COALINDIA.NS',
    'INDUSINDBK.NS', 'BAJAJFINSV.NS', 'HINDALCO.NS', 'TATAMOTORS.NS', 'GRASIM.NS',
    'DIVISLAB.NS', 'DRREDDY.NS', 'CIPLA.NS', 'EICHERMOT.NS', 'HEROMOTOCO.NS',
    'BRITANNIA.NS', 'APOLLOHOSP.NS', 'BPCL.NS', 'TATACONSUM.NS', 'UPL.NS',
    'ADANIPORTS.NS', 'SHREECEM.NS', 'BAJAJ-AUTO.NS', 'SBILIFE.NS', 'HDFCLIFE.NS'
]

NIFTY_100 = NIFTY_50 + [
    'PIDILITIND.NS', 'GODREJCP.NS', 'BOSCHLTD.NS', 'HAVELLS.NS', 'DABUR.NS',
    'MARICO.NS', 'BERGEPAINT.NS', 'AMBUJACEM.NS', 'SIEMENS.NS', 'DLF.NS',
    'GAIL.NS', 'IOC.NS', 'INDIGO.NS', 'VEDL.NS', 'PNB.NS',
    'BANKBARODA.NS', 'SAIL.NS', 'NMDC.NS', 'ZEEL.NS', 'IRCTC.NS',
    'TATAPOWER.NS', 'ADANIGREEN.NS', 'MUTHOOTFIN.NS', 'TORNTPHARM.NS', 'BIOCON.NS',
    'LUPIN.NS', 'CONCOR.NS', 'PETRONET.NS', 'RECLTD.NS', 'CHOLAFIN.NS',
    'MCDOWELL-N.NS', 'PAGEIND.NS', 'PEL.NS', 'BATAINDIA.NS', 'GODREJPROP.NS',
    'MOTHERSON.NS', 'LTIM.NS', 'OFSS.NS', 'MINDTREE.NS', 'PERSISTENT.NS',
    'COFORGE.NS', 'LALPATHLAB.NS', 'DMART.NS', 'NAUKRI.NS', 'ZOMATO.NS',
    'PAYTM.NS', 'POLICYBZR.NS', 'SBICARD.NS', 'ICICIPRULI.NS', 'BANDHANBNK.NS'
]

SP500_TOP_50 = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B', 'UNH', 'JNJ',
    'V', 'XOM', 'WMT', 'JPM', 'PG', 'MA', 'CVX', 'HD', 'ABBV', 'MRK',
    'KO', 'COST', 'PEP', 'AVGO', 'ADBE', 'TMO', 'MCD', 'CSCO', 'ACN', 'LLY',
    'NFLX', 'ABT', 'NKE', 'DHR', 'TXN', 'PM', 'VZ', 'CRM', 'INTC', 'NEE',
    'WFC', 'BMY', 'ORCL', 'QCOM', 'AMD', 'HON', 'UNP', 'UPS', 'RTX', 'COP'
]


class StockScreener:
    """
    Advanced stock screening engine with rule-based filtering
    """

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(minutes=30)
        self.indicator_engine = indicator_engine

    def get_universe(self, universe: str = 'NIFTY50') -> List[str]:
        """
        Get stock universe

        Args:
            universe: 'NIFTY50', 'NIFTY100', or 'SP500'

        Returns:
            List of stock symbols
        """
        universes = {
            'NIFTY50': NIFTY_50,
            'NIFTY100': NIFTY_100,
            'SP500': SP500_TOP_50
        }
        return universes.get(universe.upper(), NIFTY_50)

    def fetch_stock_data(self, symbol: str, period: str = '6mo') -> Optional[Dict[str, Any]]:
        """
        Fetch stock data and indicators

        Args:
            symbol: Stock symbol
            period: Data period

        Returns:
            Dictionary with stock data and indicators, or None if error
        """
        try:
            # Check cache first
            cache_key = f"{symbol}_{period}"
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                if datetime.now() - cached_time < self.cache_duration:
                    return cached_data

            # Fetch indicators
            indicators = self.indicator_engine.calculate_all_indicators(symbol, period)

            if 'error' in indicators:
                logger.warning(f"Error fetching data for {symbol}: {indicators['error']}")
                return None

            # Cache result
            self.cache[cache_key] = (indicators, datetime.now())
            return indicators

        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {str(e)}")
            return None

    def apply_rules(self, stock_data: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply screening rules to stock data

        Args:
            stock_data: Stock data with indicators
            rules: Dictionary of screening rules

        Returns:
            Dictionary with match status, score, and details
        """
        if not stock_data or 'error' in stock_data:
            return {
                'match': False,
                'score': 0,
                'reasons': ['Data unavailable']
            }

        matches = []
        score = 0
        reasons = []

        indicators = stock_data.get('indicators', {})

        # RSI Rules
        if 'rsi_oversold' in rules and rules['rsi_oversold']:
            rsi_value = indicators.get('rsi', {}).get('value', 50)
            if rsi_value < 30:
                matches.append('rsi_oversold')
                score += 20
                reasons.append(f'RSI oversold ({rsi_value:.1f})')

        if 'rsi_overbought' in rules and rules['rsi_overbought']:
            rsi_value = indicators.get('rsi', {}).get('value', 50)
            if rsi_value > 70:
                matches.append('rsi_overbought')
                score += 20
                reasons.append(f'RSI overbought ({rsi_value:.1f})')

        # Trend Rules
        if 'uptrend' in rules and rules['uptrend']:
            trend = indicators.get('trend_analysis', {}).get('overall_trend', 'neutral')
            if trend == 'bullish':
                matches.append('uptrend')
                score += 25
                reasons.append('Bullish trend')

        if 'downtrend' in rules and rules['downtrend']:
            trend = indicators.get('trend_analysis', {}).get('overall_trend', 'neutral')
            if trend == 'bearish':
                matches.append('downtrend')
                score += 25
                reasons.append('Bearish trend')

        # MACD Rules
        if 'macd_bullish' in rules and rules['macd_bullish']:
            macd_trend = indicators.get('macd', {}).get('trend', 'neutral')
            if macd_trend == 'bullish':
                matches.append('macd_bullish')
                score += 20
                reasons.append('MACD bullish')

        if 'macd_bearish' in rules and rules['macd_bearish']:
            macd_trend = indicators.get('macd', {}).get('trend', 'neutral')
            if macd_trend == 'bearish':
                matches.append('macd_bearish')
                score += 20
                reasons.append('MACD bearish')

        # Bollinger Bands Rules
        if 'bb_oversold' in rules and rules['bb_oversold']:
            bb_signal = indicators.get('bollinger_bands', {}).get('signal', 'neutral')
            if bb_signal == 'oversold':
                matches.append('bb_oversold')
                score += 15
                reasons.append('Near lower Bollinger Band')

        if 'bb_overbought' in rules and rules['bb_overbought']:
            bb_signal = indicators.get('bollinger_bands', {}).get('signal', 'neutral')
            if bb_signal == 'overbought':
                matches.append('bb_overbought')
                score += 15
                reasons.append('Near upper Bollinger Band')

        # Price above/below moving averages
        if 'price_above_sma50' in rules and rules['price_above_sma50']:
            price = stock_data.get('current_price', 0)
            sma_50 = indicators.get('moving_averages', {}).get('sma_50', 0)
            if price > sma_50:
                matches.append('price_above_sma50')
                score += 15
                reasons.append('Price above SMA50')

        if 'price_below_sma50' in rules and rules['price_below_sma50']:
            price = stock_data.get('current_price', 0)
            sma_50 = indicators.get('moving_averages', {}).get('sma_50', 0)
            if price < sma_50:
                matches.append('price_below_sma50')
                score += 15
                reasons.append('Price below SMA50')

        # Determine if stock passes screening
        match = len(matches) > 0
        if not match:
            reasons = ['Does not meet any criteria']

        return {
            'match': match,
            'score': min(score, 100),  # Cap at 100
            'matched_rules': matches,
            'reasons': reasons
        }

    def screen_stocks(self, universe: str = 'NIFTY50', rules: Dict[str, Any] = None,
                     top_n: int = 10, period: str = '6mo') -> List[Dict[str, Any]]:
        """
        Screen stocks based on rules

        Args:
            universe: Stock universe to screen
            rules: Screening rules
            top_n: Number of top stocks to return
            period: Data period for analysis

        Returns:
            List of stocks that match criteria, sorted by score
        """
        if rules is None:
            rules = {'rsi_oversold': True, 'uptrend': True}

        logger.info(f"Screening {universe} with rules: {rules}")

        # Get stock universe
        symbols = self.get_universe(universe)
        results = []

        # Process stocks in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_stock_data, symbol, period): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    stock_data = future.result()
                    if stock_data:
                        # Apply rules
                        rule_result = self.apply_rules(stock_data, rules)

                        if rule_result['match']:
                            results.append({
                                'symbol': symbol,
                                'score': rule_result['score'],
                                'current_price': stock_data.get('current_price'),
                                'rsi': stock_data.get('indicators', {}).get('rsi', {}).get('value'),
                                'trend': stock_data.get('indicators', {}).get('trend_analysis', {}).get('overall_trend'),
                                'macd_trend': stock_data.get('indicators', {}).get('macd', {}).get('trend'),
                                'matched_rules': rule_result['matched_rules'],
                                'reasons': rule_result['reasons'],
                                'indicators': stock_data.get('indicators', {})
                            })
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {str(e)}")

        # Sort by score and return top N
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_n]

    def get_predefined_screens(self) -> Dict[str, Dict[str, Any]]:
        """
        Get predefined screening strategies

        Returns:
            Dictionary of predefined screen configurations
        """
        return {
            'oversold_bounce': {
                'name': 'Oversold Bounce Candidates',
                'description': 'Stocks that are oversold and may bounce back',
                'rules': {
                    'rsi_oversold': True,
                    'bb_oversold': True
                }
            },
            'strong_uptrend': {
                'name': 'Strong Uptrend Stocks',
                'description': 'Stocks in confirmed uptrend',
                'rules': {
                    'uptrend': True,
                    'price_above_sma50': True,
                    'macd_bullish': True
                }
            },
            'momentum_breakout': {
                'name': 'Momentum Breakout',
                'description': 'Stocks showing strong momentum',
                'rules': {
                    'macd_bullish': True,
                    'price_above_sma50': True
                }
            },
            'overbought_reversal': {
                'name': 'Overbought Reversal Candidates',
                'description': 'Potentially overbought stocks that may reverse',
                'rules': {
                    'rsi_overbought': True,
                    'bb_overbought': True
                }
            },
            'downtrend_short': {
                'name': 'Downtrend Short Candidates',
                'description': 'Stocks in confirmed downtrend',
                'rules': {
                    'downtrend': True,
                    'price_below_sma50': True,
                    'macd_bearish': True
                }
            }
        }

    def run_predefined_screen(self, screen_name: str, universe: str = 'NIFTY50',
                             top_n: int = 10, period: str = '6mo') -> Dict[str, Any]:
        """
        Run a predefined screening strategy

        Args:
            screen_name: Name of predefined screen
            universe: Stock universe
            top_n: Number of results
            period: Data period

        Returns:
            Screening results with metadata
        """
        screens = self.get_predefined_screens()

        if screen_name not in screens:
            return {
                'error': f'Unknown screen: {screen_name}',
                'available_screens': list(screens.keys())
            }

        screen_config = screens[screen_name]
        results = self.screen_stocks(
            universe=universe,
            rules=screen_config['rules'],
            top_n=top_n,
            period=period
        )

        return {
            'screen_name': screen_name,
            'description': screen_config['description'],
            'universe': universe,
            'rules': screen_config['rules'],
            'total_matches': len(results),
            'timestamp': datetime.now().isoformat(),
            'results': results
        }


# Singleton instance
stock_screener = StockScreener()


# Helper functions
def screen_stocks(universe: str = 'NIFTY50', rules: Dict[str, Any] = None,
                 top_n: int = 10) -> List[Dict[str, Any]]:
    """Screen stocks with custom rules"""
    return stock_screener.screen_stocks(universe, rules, top_n)


def run_screen(screen_name: str, universe: str = 'NIFTY50', top_n: int = 10) -> Dict[str, Any]:
    """Run a predefined screen"""
    return stock_screener.run_predefined_screen(screen_name, universe, top_n)


def get_available_screens() -> Dict[str, Dict[str, Any]]:
    """Get list of available predefined screens"""
    return stock_screener.get_predefined_screens()
