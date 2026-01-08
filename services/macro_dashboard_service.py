"""
Macro Dashboard Service

Provides macroeconomic indicators affecting SHORT opportunities in India:
- Interest Rates & Yields (RBI Repo, 10Y yields, rate differential)
- Currency & Flows (USD/INR, FII flows)
- Growth & Inflation (GDP, CPI)
- Volatility & Sentiment (VIX India, Global VIX, Put/Call)
- Oil & Commodities
- US Macro
- Technical Breadth
"""

import yfinance as yf
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import numpy as np
from functools import lru_cache
import threading
import time

logger = logging.getLogger(__name__)


class MacroDashboardService:
    """Service for fetching and analyzing macroeconomic indicators"""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes cache
        self.lock = threading.Lock()

        # Define indicator ranges for traffic light system
        self.indicator_ranges = {
            # Interest Rates
            'rbi_repo_rate': {'green': (5.5, 6.5), 'yellow': (6.5, 7.5), 'red_above': 7.5, 'red_below': 5.5},
            'india_10y_yield': {'green': (6.8, 7.2), 'yellow': (7.2, 7.8), 'red_above': 7.8, 'red_below': 6.8},
            'us_10y_yield': {'green': (4.0, 4.5), 'yellow': (4.5, 5.0), 'red_above': 5.0},
            'rate_differential': {'green': (1.5, 2.5), 'yellow_low': (1.0, 1.5), 'yellow_high': (2.5, 3.0), 'red_below': 1.0, 'red_above': 3.0},

            # Currency
            'usd_inr': {'green': (82.5, 83.5), 'yellow': (83.5, 84.5), 'red_above': 84.5},

            # FII Flows (in crores)
            'fii_daily': {'green': (-500, 2000), 'yellow': (-1000, -500), 'red_below': -1000},
            'fii_weekly': {'green': (-1000, 5000), 'yellow': (-5000, -1000), 'red_below': -5000},

            # VIX
            'vix_india': {'green': (12, 18), 'yellow': (18, 25), 'red_above': 25},
            'vix_global': {'green': (12, 20), 'yellow': (20, 30), 'red_above': 30},

            # MOVE Index
            'move_index': {'green': (100, 120), 'yellow': (120, 150), 'red_above': 150},

            # Inflation
            'inflation_headline': {'green': (2.0, 4.0), 'yellow': (4.0, 6.0), 'red_above': 6.0},
            'inflation_core': {'green': (2.5, 4.0), 'yellow': (4.0, 5.5), 'red_above': 5.5},

            # GDP
            'gdp_growth': {'green': (5.5, 7.0), 'yellow_low': (4.5, 5.5), 'yellow_high': (7.0, 8.0), 'red_below': 4.5, 'red_above': 8.0},

            # Oil
            'crude_oil': {'green': (70, 80), 'yellow': (80, 100), 'red_above': 100},

            # Put/Call Ratio
            'put_call_ratio': {'green': (0.7, 1.0), 'yellow': (1.0, 1.3), 'red_above': 1.3},
        }

    def _get_status(self, indicator: str, value: float) -> Dict[str, Any]:
        """Determine traffic light status for an indicator"""
        ranges = self.indicator_ranges.get(indicator, {})

        if not ranges:
            return {'light': 'gray', 'status': 'Unknown'}

        green = ranges.get('green')
        yellow = ranges.get('yellow')
        yellow_low = ranges.get('yellow_low')
        yellow_high = ranges.get('yellow_high')
        red_above = ranges.get('red_above')
        red_below = ranges.get('red_below')

        # Check red conditions first
        if red_above is not None and value > red_above:
            return {'light': 'red', 'status': 'CRITICAL'}
        if red_below is not None and value < red_below:
            return {'light': 'red', 'status': 'CRITICAL'}

        # Check yellow conditions
        if yellow and yellow[0] <= value <= yellow[1]:
            return {'light': 'yellow', 'status': 'Warning'}
        if yellow_low and yellow_low[0] <= value <= yellow_low[1]:
            return {'light': 'yellow', 'status': 'Warning'}
        if yellow_high and yellow_high[0] <= value <= yellow_high[1]:
            return {'light': 'yellow', 'status': 'Warning'}

        # Check green
        if green and green[0] <= value <= green[1]:
            return {'light': 'green', 'status': 'In Range'}

        # Default to yellow if none match
        return {'light': 'yellow', 'status': 'Monitor'}

    def _fetch_with_cache(self, key: str, fetch_func, ttl: int = None) -> Any:
        """Fetch data with caching"""
        ttl = ttl or self.cache_ttl
        now = time.time()

        with self.lock:
            if key in self.cache:
                cached_data, cached_time = self.cache[key]
                if now - cached_time < ttl:
                    return cached_data

        try:
            data = fetch_func()
            with self.lock:
                self.cache[key] = (data, now)
            return data
        except Exception as e:
            logger.error(f"Error fetching {key}: {e}")
            # Return cached data if available, even if stale
            with self.lock:
                if key in self.cache:
                    return self.cache[key][0]
            return None

    def _fetch_yahoo_data(self, ticker: str, period: str = '5d') -> Optional[Dict]:
        """Fetch data from Yahoo Finance"""
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period=period)
            if hist.empty:
                return None

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            return {
                'current': float(latest['Close']),
                'previous': float(prev['Close']),
                'change': float(latest['Close'] - prev['Close']),
                'change_pct': float((latest['Close'] - prev['Close']) / prev['Close'] * 100) if prev['Close'] != 0 else 0,
                'high': float(hist['High'].max()),
                'low': float(hist['Low'].min()),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")
            return None

    def get_interest_rates_section(self) -> Dict[str, Any]:
        """Get Interest Rates & Yields section data"""

        def fetch():
            # India 10Y yield proxy (using government bond ETF)
            india_10y = self._fetch_yahoo_data('^TNX')  # Using US 10Y as proxy for now
            india_10y_value = 7.15  # Simulated India 10Y yield

            # US 10Y yield
            us_10y = self._fetch_yahoo_data('^TNX')
            us_10y_value = us_10y['current'] if us_10y else 4.5

            # Rate differential
            rate_diff = india_10y_value - us_10y_value

            return {
                'rbi_repo_rate': {
                    'value': 6.5,
                    'unit': '%',
                    'display_name': 'RBI Repo Rate',
                    **self._get_status('rbi_repo_rate', 6.5),
                    'change': 0,
                    'trend': 'stable',
                    'next_review': 'Feb 7, 2026',
                    'impact_shorts': 'neutral',
                    'description': 'RBI policy rate - impacts borrowing costs'
                },
                'india_10y_yield': {
                    'value': india_10y_value,
                    'unit': '%',
                    'display_name': '10Y India Yield',
                    **self._get_status('india_10y_yield', india_10y_value),
                    'change': 0.12,
                    'trend': 'rising',
                    'impact_shorts': 'positive',
                    'description': 'Government bond yield - higher = stocks less attractive'
                },
                'us_10y_yield': {
                    'value': round(us_10y_value, 2),
                    'unit': '%',
                    'display_name': 'US 10Y Yield',
                    **self._get_status('us_10y_yield', us_10y_value),
                    'change': us_10y.get('change_pct', 0) if us_10y else 0,
                    'trend': 'rising' if us_10y and us_10y.get('change', 0) > 0 else 'falling',
                    'impact_shorts': 'positive' if us_10y_value > 4.5 else 'neutral',
                    'description': 'US rates affect global capital flows'
                },
                'rate_differential': {
                    'value': round(rate_diff, 2),
                    'unit': '%',
                    'display_name': 'Rate Differential',
                    **self._get_status('rate_differential', rate_diff),
                    'change': -0.05,
                    'trend': 'narrowing',
                    'critical_level': 1.5,
                    'impact_shorts': 'positive' if rate_diff < 2.0 else 'neutral',
                    'description': 'India-US spread - narrowing = FII outflow risk'
                }
            }

        return self._fetch_with_cache('interest_rates', fetch)

    def get_currency_flows_section(self) -> Dict[str, Any]:
        """Get Currency & Flows section data"""

        def fetch():
            # USD/INR
            usd_inr = self._fetch_yahoo_data('USDINR=X')
            usd_inr_value = usd_inr['current'] if usd_inr else 83.50

            # Simulated FII data (would come from NSDL in production)
            fii_daily = -1850  # Simulated
            fii_weekly = -4200  # Simulated

            return {
                'usd_inr': {
                    'value': round(usd_inr_value, 2),
                    'unit': '',
                    'display_name': 'USD/INR',
                    **self._get_status('usd_inr', usd_inr_value),
                    'change': usd_inr.get('change', 0) if usd_inr else 0,
                    'change_pct': usd_inr.get('change_pct', 0) if usd_inr else 0,
                    'trend': 'weakening' if usd_inr and usd_inr.get('change', 0) > 0 else 'stable',
                    'support': 83.00,
                    'resistance': 84.00,
                    'impact_shorts': 'positive' if usd_inr_value > 83.5 else 'neutral',
                    'description': 'Rupee strength - higher = weaker INR = shorts favorable'
                },
                'fii_daily': {
                    'value': fii_daily,
                    'unit': ' Cr',
                    'display_name': 'FII Flows (Today)',
                    **self._get_status('fii_daily', fii_daily),
                    'trend': 'selling' if fii_daily < 0 else 'buying',
                    'impact_shorts': 'positive' if fii_daily < -500 else 'neutral',
                    'description': 'Foreign institutional investor daily flow'
                },
                'fii_weekly': {
                    'value': fii_weekly,
                    'unit': ' Cr',
                    'display_name': 'FII Flows (Week)',
                    **self._get_status('fii_weekly', fii_weekly),
                    'trend': 'outflow' if fii_weekly < 0 else 'inflow',
                    'impact_shorts': 'positive' if fii_weekly < -2000 else 'neutral',
                    'description': 'Weekly cumulative FII flows'
                },
                'inr_trend': {
                    'value': 'Depreciating',
                    'display_name': 'INR Trend',
                    'light': 'yellow',
                    'status': 'Weakening',
                    'velocity_1d': 0.15,
                    'velocity_5d': 0.60,
                    'impact_shorts': 'positive',
                    'description': 'Rupee depreciation trend indicator'
                }
            }

        return self._fetch_with_cache('currency_flows', fetch)

    def get_growth_inflation_section(self) -> Dict[str, Any]:
        """Get Growth & Inflation section data"""

        def fetch():
            # Simulated macro data (would come from MOSPI in production)
            gdp_growth = 6.2
            inflation_headline = 5.8
            inflation_core = 6.5

            return {
                'gdp_growth': {
                    'value': gdp_growth,
                    'unit': '%',
                    'display_name': 'GDP Growth YoY',
                    **self._get_status('gdp_growth', gdp_growth),
                    'prev_quarter': 6.7,
                    'trend': 'slowing',
                    'forecast': 6.0,
                    'impact_shorts': 'positive' if gdp_growth < 6.0 else 'neutral',
                    'description': 'Economic growth rate - slowing = short favorable'
                },
                'inflation_headline': {
                    'value': inflation_headline,
                    'unit': '%',
                    'display_name': 'Inflation (Headline)',
                    **self._get_status('inflation_headline', inflation_headline),
                    'prev_month': 5.5,
                    'trend': 'rising',
                    'rbi_target': 4.0,
                    'rate_hike_probability': 65,
                    'impact_shorts': 'positive' if inflation_headline > 5.0 else 'neutral',
                    'description': 'CPI inflation - high = rate hikes = shorts favorable'
                },
                'inflation_core': {
                    'value': inflation_core,
                    'unit': '%',
                    'display_name': 'Core Inflation',
                    **self._get_status('inflation_core', inflation_core),
                    'trend': 'sticky',
                    'above_target_by': 2.5,
                    'impact_shorts': 'positive' if inflation_core > 5.0 else 'neutral',
                    'description': 'Core inflation (ex food/fuel) - sticky = more hikes'
                },
                'inflation_trend': {
                    'value': 'Rising',
                    'display_name': 'Inflation Momentum',
                    'light': 'red',
                    'status': 'Rising sharply',
                    'trend_3m': 0.6,
                    'trend_6m': 1.0,
                    'impact_shorts': 'positive',
                    'description': 'Inflation direction - rising = strong short bias'
                }
            }

        return self._fetch_with_cache('growth_inflation', fetch)

    def get_volatility_sentiment_section(self) -> Dict[str, Any]:
        """Get Volatility & Sentiment section data"""

        def fetch():
            # India VIX
            india_vix = self._fetch_yahoo_data('^INDIAVIX')
            india_vix_value = india_vix['current'] if india_vix else 18.5

            # Global VIX
            global_vix = self._fetch_yahoo_data('^VIX')
            global_vix_value = global_vix['current'] if global_vix else 16.0

            # Put/Call ratio (simulated)
            pcr = 0.92

            return {
                'vix_india': {
                    'value': round(india_vix_value, 2),
                    'unit': '',
                    'display_name': 'VIX (India)',
                    **self._get_status('vix_india', india_vix_value),
                    'change': india_vix.get('change', 0) if india_vix else 0,
                    'trend': 'rising' if india_vix and india_vix.get('change', 0) > 0 else 'falling',
                    'high_52w': 32.5,
                    'low_52w': 11.0,
                    'average': 17.5,
                    'impact_shorts': 'positive' if india_vix_value > 20 else 'neutral',
                    'description': 'Fear index - high VIX = shorts easier'
                },
                'vix_global': {
                    'value': round(global_vix_value, 2),
                    'unit': '',
                    'display_name': 'VIX (Global)',
                    **self._get_status('vix_global', global_vix_value),
                    'change': global_vix.get('change', 0) if global_vix else 0,
                    'trend': 'rising' if global_vix and global_vix.get('change', 0) > 0 else 'falling',
                    'spread_vs_india': round(india_vix_value - global_vix_value, 2),
                    'impact_shorts': 'positive' if global_vix_value > 22 else 'neutral',
                    'description': 'US VIX - global risk sentiment indicator'
                },
                'move_index': {
                    'value': 128,
                    'unit': '',
                    'display_name': 'MOVE Index',
                    **self._get_status('move_index', 128),
                    'trend': 'elevated',
                    'critical_level': 150,
                    'impact_shorts': 'positive' if 128 > 130 else 'neutral',
                    'description': 'Bond volatility - high = rate uncertainty'
                },
                'put_call_ratio': {
                    'value': pcr,
                    'unit': '',
                    'display_name': 'Put/Call Ratio',
                    **self._get_status('put_call_ratio', pcr),
                    'trend': 'rising',
                    'avg_5d': 0.85,
                    'impact_shorts': 'positive' if pcr > 1.0 else 'neutral',
                    'description': 'Options sentiment - >1 = more hedging/fear'
                }
            }

        return self._fetch_with_cache('volatility_sentiment', fetch)

    def get_oil_commodities_section(self) -> Dict[str, Any]:
        """Get Oil & Commodities section data"""

        def fetch():
            # Brent Crude
            brent = self._fetch_yahoo_data('BZ=F')
            brent_value = brent['current'] if brent else 78.0

            # Gold
            gold = self._fetch_yahoo_data('GC=F')
            gold_value = gold['current'] if gold else 2050.0

            # Calculate INR impact from oil
            oil_change_2m = 4.0  # Simulated
            inr_impact = oil_change_2m * 0.08  # ~₹0.8 per $10 oil

            return {
                'crude_oil': {
                    'value': round(brent_value, 2),
                    'unit': '/bbl',
                    'display_name': 'Brent Crude',
                    **self._get_status('crude_oil', brent_value),
                    'change': brent.get('change', 0) if brent else 0,
                    'change_pct': brent.get('change_pct', 0) if brent else 0,
                    'trend': 'rising' if brent and brent.get('change', 0) > 0 else 'falling',
                    'critical_level': 100,
                    'geopolitical_risk': 'Medium',
                    'impact_shorts': 'positive' if brent_value > 85 else 'neutral',
                    'description': 'Oil price - high = INR pressure = shorts favorable'
                },
                'oil_inr_impact': {
                    'value': round(inr_impact, 2),
                    'unit': ' INR',
                    'display_name': 'Oil Impact on INR',
                    'light': 'yellow' if inr_impact > 0.3 else 'green',
                    'status': 'Pressure' if inr_impact > 0.3 else 'Minimal',
                    'impact_shorts': 'positive' if inr_impact > 0.5 else 'neutral',
                    'description': 'Estimated INR pressure from oil prices'
                },
                'gold_price': {
                    'value': round(gold_value, 2),
                    'unit': '/oz',
                    'display_name': 'Gold Price',
                    'light': 'green' if gold_value < 2100 else 'yellow',
                    'status': 'Stable' if gold_value < 2100 else 'Elevated',
                    'change': gold.get('change', 0) if gold else 0,
                    'trend': 'rising' if gold and gold.get('change', 0) > 0 else 'stable',
                    'impact_shorts': 'positive' if gold_value > 2150 else 'neutral',
                    'description': 'Safe haven - spike = risk-off sentiment'
                }
            }

        return self._fetch_with_cache('oil_commodities', fetch)

    def get_us_macro_section(self) -> Dict[str, Any]:
        """Get US Macro section data"""

        def fetch():
            return {
                'us_gdp_growth': {
                    'value': 2.5,
                    'unit': '%',
                    'display_name': 'US GDP Growth',
                    'light': 'green',
                    'status': 'Moderate',
                    'trend': 'stable',
                    'impact_shorts': 'neutral',
                    'description': 'US economic growth - impacts global sentiment'
                },
                'us_unemployment': {
                    'value': 3.7,
                    'unit': '%',
                    'display_name': 'US Unemployment',
                    'light': 'green',
                    'status': 'Healthy',
                    'trend': 'stable',
                    'impact_shorts': 'neutral',
                    'description': 'US labor market health'
                },
                'us_inflation': {
                    'value': 3.4,
                    'unit': '%',
                    'display_name': 'US Inflation',
                    'light': 'yellow',
                    'status': 'Elevated',
                    'trend': 'sticky',
                    'impact_shorts': 'positive',
                    'description': 'US CPI - high = Fed hawkish = USD strong'
                },
                'fed_rate_risk': {
                    'value': 35,
                    'unit': '%',
                    'display_name': 'Fed Hike Probability',
                    'light': 'yellow',
                    'status': 'Monitor',
                    'current_rate': '4.25-4.50%',
                    'next_meeting': 'Feb 5, 2026',
                    'impact_shorts': 'positive' if 35 > 40 else 'neutral',
                    'description': 'Probability of Fed rate hike next meeting'
                }
            }

        return self._fetch_with_cache('us_macro', fetch)

    def get_market_breadth_section(self) -> Dict[str, Any]:
        """Get Technical Breadth section data"""

        def fetch():
            # Simulated breadth data
            advances = 18
            declines = 32
            ad_ratio = advances / declines if declines > 0 else 1

            return {
                'advance_decline': {
                    'value': f"{advances}:{declines}",
                    'display_name': 'Nifty Advance/Decline',
                    'light': 'yellow' if ad_ratio < 0.7 else 'green',
                    'status': 'Declining' if ad_ratio < 0.7 else 'Balanced',
                    'ratio': round(ad_ratio, 2),
                    'trend': 'deteriorating',
                    'days_declining': 3,
                    'impact_shorts': 'positive' if ad_ratio < 0.6 else 'neutral',
                    'description': 'Market breadth - weak = more stocks falling'
                },
                'sector_momentum': {
                    'value': '-2',
                    'display_name': 'Sector Momentum',
                    'light': 'yellow',
                    'status': 'Weak',
                    'sectors_up': ['REALTY', 'PVT BANKS'],
                    'sectors_down': ['IT', 'PHARMA', 'OIL'],
                    'impact_shorts': 'positive',
                    'description': 'Net sector momentum score'
                },
                'vix_trend': {
                    'value': 'Rising',
                    'display_name': 'VIX Trend',
                    'light': 'yellow',
                    'status': 'Rising',
                    'change_3d': 1.5,
                    'change_5d': 3.0,
                    'acceleration': 'positive',
                    'impact_shorts': 'positive',
                    'description': 'VIX direction - rising = fear building'
                }
            }

        return self._fetch_with_cache('market_breadth', fetch)

    def calculate_short_bias_score(self) -> Dict[str, Any]:
        """Calculate overall SHORT bias score from all indicators"""

        try:
            # Fetch all sections
            interest = self.get_interest_rates_section() or {}
            currency = self.get_currency_flows_section() or {}
            growth = self.get_growth_inflation_section() or {}
            volatility = self.get_volatility_sentiment_section() or {}
            oil = self.get_oil_commodities_section() or {}
            us_macro = self.get_us_macro_section() or {}
            breadth = self.get_market_breadth_section() or {}

            score = 0
            max_score = 20
            breakdown = []

            # Rate Hike Risk (max 3 points)
            inflation = growth.get('inflation_headline', {}).get('value', 4)
            if inflation > 6.0:
                score += 3
                breakdown.append({'factor': 'High Inflation', 'points': 3, 'reason': f'CPI at {inflation}%'})
            elif inflation > 5.0:
                score += 2
                breakdown.append({'factor': 'Elevated Inflation', 'points': 2, 'reason': f'CPI at {inflation}%'})

            # USD Strength / INR Weakness (max 3 points)
            usd_inr = currency.get('usd_inr', {}).get('value', 83)
            if usd_inr > 84.5:
                score += 3
                breakdown.append({'factor': 'INR Very Weak', 'points': 3, 'reason': f'USD/INR at {usd_inr}'})
            elif usd_inr > 83.5:
                score += 2
                breakdown.append({'factor': 'INR Weakening', 'points': 2, 'reason': f'USD/INR at {usd_inr}'})

            # FII Selling (max 3 points)
            fii_weekly = currency.get('fii_weekly', {}).get('value', 0)
            if fii_weekly < -5000:
                score += 3
                breakdown.append({'factor': 'Heavy FII Selling', 'points': 3, 'reason': f'Weekly outflow ₹{abs(fii_weekly)}Cr'})
            elif fii_weekly < -2000:
                score += 2
                breakdown.append({'factor': 'FII Outflow', 'points': 2, 'reason': f'Weekly outflow ₹{abs(fii_weekly)}Cr'})
            elif fii_weekly < -500:
                score += 1
                breakdown.append({'factor': 'Mild FII Selling', 'points': 1, 'reason': f'Weekly outflow ₹{abs(fii_weekly)}Cr'})

            # High Volatility (max 2 points)
            vix = volatility.get('vix_india', {}).get('value', 15)
            if vix > 25:
                score += 2
                breakdown.append({'factor': 'High VIX', 'points': 2, 'reason': f'VIX at {vix}'})
            elif vix > 20:
                score += 1
                breakdown.append({'factor': 'Elevated VIX', 'points': 1, 'reason': f'VIX at {vix}'})

            # Oil Prices (max 2 points)
            crude = oil.get('crude_oil', {}).get('value', 75)
            if crude > 100:
                score += 2
                breakdown.append({'factor': 'Oil Spike', 'points': 2, 'reason': f'Crude at ${crude}'})
            elif crude > 85:
                score += 1
                breakdown.append({'factor': 'Elevated Oil', 'points': 1, 'reason': f'Crude at ${crude}'})

            # Rate Differential (max 2 points)
            rate_diff = interest.get('rate_differential', {}).get('value', 2.0)
            if rate_diff < 1.0:
                score += 2
                breakdown.append({'factor': 'Rate Differential Critical', 'points': 2, 'reason': f'Spread at {rate_diff}%'})
            elif rate_diff < 1.5:
                score += 1
                breakdown.append({'factor': 'Rate Differential Narrowing', 'points': 1, 'reason': f'Spread at {rate_diff}%'})

            # Market Breadth (max 2 points)
            ad_ratio = breadth.get('advance_decline', {}).get('ratio', 1)
            if ad_ratio < 0.5:
                score += 2
                breakdown.append({'factor': 'Weak Breadth', 'points': 2, 'reason': f'A/D ratio at {ad_ratio}'})
            elif ad_ratio < 0.7:
                score += 1
                breakdown.append({'factor': 'Deteriorating Breadth', 'points': 1, 'reason': f'A/D ratio at {ad_ratio}'})

            # Fed Risk (max 3 points)
            fed_risk = us_macro.get('fed_rate_risk', {}).get('value', 30)
            if fed_risk > 60:
                score += 3
                breakdown.append({'factor': 'Fed Hawkish', 'points': 3, 'reason': f'{fed_risk}% hike probability'})
            elif fed_risk > 40:
                score += 1
                breakdown.append({'factor': 'Fed Uncertainty', 'points': 1, 'reason': f'{fed_risk}% hike probability'})

            # Determine bias level
            if score >= 14:
                bias_level = 'STRONG DOWNTREND'
                recommendation = 'STRONGLY FAVORABLE FOR SHORTS'
            elif score >= 10:
                bias_level = 'MODERATE DOWNTREND'
                recommendation = 'FAVORABLE FOR SHORTS'
            elif score >= 6:
                bias_level = 'MILD DOWNWARD BIAS'
                recommendation = 'CAUTIOUS SHORTS'
            else:
                bias_level = 'NEUTRAL/UPWARD'
                recommendation = 'SHORTS NOT FAVORABLE'

            return {
                'score': score,
                'max_score': max_score,
                'percentage': round(score / max_score * 100),
                'bias_level': bias_level,
                'recommendation': recommendation,
                'breakdown': breakdown,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error calculating short bias score: {e}")
            return {
                'score': 0,
                'max_score': 20,
                'percentage': 0,
                'bias_level': 'UNKNOWN',
                'recommendation': 'Unable to calculate',
                'breakdown': [],
                'error': str(e)
            }

    def get_full_dashboard(self) -> Dict[str, Any]:
        """Get complete macro dashboard data"""
        try:
            return {
                'status': 'success',
                'short_bias': self.calculate_short_bias_score(),
                'sections': {
                    'interest_rates': {
                        'title': 'Interest Rates & Yields',
                        'icon': '💰',
                        'data': self.get_interest_rates_section()
                    },
                    'currency_flows': {
                        'title': 'Currency & Flows',
                        'icon': '💱',
                        'data': self.get_currency_flows_section()
                    },
                    'growth_inflation': {
                        'title': 'Growth & Inflation',
                        'icon': '📈',
                        'data': self.get_growth_inflation_section()
                    },
                    'volatility_sentiment': {
                        'title': 'Volatility & Sentiment',
                        'icon': '😨',
                        'data': self.get_volatility_sentiment_section()
                    },
                    'oil_commodities': {
                        'title': 'Oil & Commodities',
                        'icon': '🛢️',
                        'data': self.get_oil_commodities_section()
                    },
                    'us_macro': {
                        'title': 'US Macro',
                        'icon': '🗽',
                        'data': self.get_us_macro_section()
                    },
                    'market_breadth': {
                        'title': 'Market Breadth',
                        'icon': '📊',
                        'data': self.get_market_breadth_section()
                    }
                },
                'last_updated': datetime.now().isoformat(),
                'next_update': (datetime.now() + timedelta(minutes=5)).isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting full dashboard: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }


# Singleton instance
_macro_dashboard_service = None


def get_macro_dashboard_service() -> MacroDashboardService:
    """Get singleton instance of MacroDashboardService"""
    global _macro_dashboard_service
    if _macro_dashboard_service is None:
        _macro_dashboard_service = MacroDashboardService()
    return _macro_dashboard_service
