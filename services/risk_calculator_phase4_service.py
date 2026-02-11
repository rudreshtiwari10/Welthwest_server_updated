"""
Risk Calculator Phase 4: Simple Portfolio View Service

Multi-stock portfolio overview with allocation percentages, risk exposure,
concentration warnings, and basic correlation tags.

Enhanced with real-time data, historical returns, and market sentiment analysis.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
from database import db
import yfinance as yf
import pandas as pd
import numpy as np


class RiskCalculatorPhase4Service:
    """Service for portfolio management and analytics"""

    def __init__(self):
        self.portfolio_collection = db['risk_calculator_portfolio']

    def get_portfolio(self, user_id: str) -> Dict[str, Any]:
        """Get or create user's portfolio"""
        try:
            portfolio = self.portfolio_collection.find_one({'user_id': user_id})

            if portfolio:
                return portfolio

            # Create new portfolio
            new_portfolio = {
                'user_id': user_id,
                'positions': [],
                'total_portfolio_value': 0,
                'total_risk_if_all_sl_hit': 0,
                'cash_balance': 0,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }

            result = self.portfolio_collection.insert_one(new_portfolio)
            new_portfolio['_id'] = result.inserted_id

            return new_portfolio

        except Exception as e:
            raise Exception(f"Error getting portfolio: {str(e)}")

    def add_position(self, user_id: str, position_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add or update a position in portfolio"""
        try:
            portfolio = self.get_portfolio(user_id)

            # Validate required fields
            required_fields = ['symbol', 'quantity', 'avg_entry_price', 'current_price', 'stop_loss']
            for field in required_fields:
                if field not in position_data:
                    raise ValueError(f"Missing required field: {field}")

            # Check if position already exists
            existing_positions = [p for p in portfolio['positions'] if p['symbol'] == position_data['symbol']]

            if existing_positions:
                # Update existing position
                for i, pos in enumerate(portfolio['positions']):
                    if pos['symbol'] == position_data['symbol']:
                        # Calculate new average entry price if adding to position
                        if 'add_quantity' in position_data and position_data['add_quantity'] > 0:
                            total_qty = pos['quantity'] + position_data['add_quantity']
                            total_cost = (pos['quantity'] * pos['avg_entry_price']) + \
                                        (position_data['add_quantity'] * position_data['avg_entry_price'])
                            position_data['avg_entry_price'] = total_cost / total_qty
                            position_data['quantity'] = total_qty

                        portfolio['positions'][i].update({
                            'quantity': position_data.get('quantity', pos['quantity']),
                            'avg_entry_price': position_data.get('avg_entry_price', pos['avg_entry_price']),
                            'current_price': position_data['current_price'],
                            'stop_loss': position_data.get('stop_loss', pos['stop_loss']),
                            'target': position_data.get('target', pos.get('target')),
                            'sector': position_data.get('sector', pos.get('sector', 'Other')),
                            'correlation_group': position_data.get('correlation_group', pos.get('correlation_group', 'uncorrelated')),
                            'last_updated': datetime.now()
                        })
                        break
            else:
                # Add new position
                new_position = {
                    'symbol': position_data['symbol'],
                    'quantity': position_data['quantity'],
                    'avg_entry_price': position_data['avg_entry_price'],
                    'current_price': position_data['current_price'],
                    'stop_loss': position_data['stop_loss'],
                    'target': position_data.get('target'),
                    'position_value': position_data['quantity'] * position_data['current_price'],
                    'unrealized_pnl': (position_data['current_price'] - position_data['avg_entry_price']) * position_data['quantity'],
                    'risk_amount': abs(position_data['current_price'] - position_data['stop_loss']) * position_data['quantity'],
                    'sector': position_data.get('sector', 'Other'),
                    'correlation_group': position_data.get('correlation_group', 'uncorrelated'),
                    'added_date': datetime.now(),
                    'last_updated': datetime.now()
                }

                portfolio['positions'].append(new_position)

            # Recalculate portfolio values
            self._recalculate_portfolio_values(portfolio)

            # Update in database
            self.portfolio_collection.update_one(
                {'_id': portfolio['_id']},
                {'$set': {
                    'positions': portfolio['positions'],
                    'total_portfolio_value': portfolio['total_portfolio_value'],
                    'total_risk_if_all_sl_hit': portfolio['total_risk_if_all_sl_hit'],
                    'updated_at': datetime.now()
                }}
            )

            return self.get_portfolio(user_id)

        except Exception as e:
            raise Exception(f"Error adding position: {str(e)}")

    def update_position_prices(self, user_id: str, symbol: str, current_price: float) -> Dict[str, Any]:
        """Update current price for a position"""
        try:
            portfolio = self.get_portfolio(user_id)

            updated = False
            for position in portfolio['positions']:
                if position['symbol'] == symbol:
                    position['current_price'] = current_price
                    position['position_value'] = position['quantity'] * current_price
                    position['unrealized_pnl'] = (current_price - position['avg_entry_price']) * position['quantity']
                    position['risk_amount'] = abs(current_price - position['stop_loss']) * position['quantity']
                    position['last_updated'] = datetime.now()
                    updated = True
                    break

            if not updated:
                raise ValueError(f"Position {symbol} not found in portfolio")

            # Recalculate portfolio values
            self._recalculate_portfolio_values(portfolio)

            # Update in database
            self.portfolio_collection.update_one(
                {'_id': portfolio['_id']},
                {'$set': {
                    'positions': portfolio['positions'],
                    'total_portfolio_value': portfolio['total_portfolio_value'],
                    'total_risk_if_all_sl_hit': portfolio['total_risk_if_all_sl_hit'],
                    'updated_at': datetime.now()
                }}
            )

            return self.get_portfolio(user_id)

        except Exception as e:
            raise Exception(f"Error updating position price: {str(e)}")

    def remove_position(self, user_id: str, symbol: str) -> Dict[str, Any]:
        """Remove a position from portfolio"""
        try:
            portfolio = self.get_portfolio(user_id)

            # Remove position
            portfolio['positions'] = [p for p in portfolio['positions'] if p['symbol'] != symbol]

            # Recalculate portfolio values
            self._recalculate_portfolio_values(portfolio)

            # Update in database
            self.portfolio_collection.update_one(
                {'_id': portfolio['_id']},
                {'$set': {
                    'positions': portfolio['positions'],
                    'total_portfolio_value': portfolio['total_portfolio_value'],
                    'total_risk_if_all_sl_hit': portfolio['total_risk_if_all_sl_hit'],
                    'updated_at': datetime.now()
                }}
            )

            return self.get_portfolio(user_id)

        except Exception as e:
            raise Exception(f"Error removing position: {str(e)}")

    def get_portfolio_analytics(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive portfolio analytics"""
        try:
            portfolio = self.get_portfolio(user_id)
            user_settings = db['risk_calculator_settings'].find_one({'user_id': user_id}) or {}

            # Calculate allocations
            allocations = self._calculate_allocations(portfolio)
            sector_allocations = self._calculate_sector_allocations(portfolio)

            # Generate warnings
            warnings = self._generate_warnings(portfolio, user_settings)

            # Calculate aggregate metrics
            total_unrealized_pnl = sum(p.get('unrealized_pnl', 0) for p in portfolio['positions'])
            total_portfolio_value = portfolio.get('total_portfolio_value', 0)
            total_risk = portfolio.get('total_risk_if_all_sl_hit', 0)

            portfolio_return_percent = 0
            if total_portfolio_value > 0:
                initial_value = total_portfolio_value - total_unrealized_pnl
                if initial_value > 0:
                    portfolio_return_percent = (total_unrealized_pnl / initial_value) * 100

            risk_percent_of_portfolio = 0
            if total_portfolio_value > 0:
                risk_percent_of_portfolio = (total_risk / total_portfolio_value) * 100

            analytics = {
                'portfolio': {
                    'total_value': total_portfolio_value,
                    'total_unrealized_pnl': total_unrealized_pnl,
                    'total_risk_if_all_sl_hit': total_risk,
                    'portfolio_return_percent': portfolio_return_percent,
                    'risk_percent_of_portfolio': risk_percent_of_portfolio,
                    'positions_count': len(portfolio['positions']),
                    'cash_balance': portfolio.get('cash_balance', 0)
                },
                'positions': portfolio['positions'],
                'allocations': allocations,
                'sector_allocations': sector_allocations,
                'warnings': warnings,
                'disclaimer': "This is an analytical tool based on your own trading rules. It does not provide investment advice."
            }

            return analytics

        except Exception as e:
            raise Exception(f"Error getting portfolio analytics: {str(e)}")

    # Private helper methods

    def _recalculate_portfolio_values(self, portfolio: Dict[str, Any]) -> None:
        """Recalculate total portfolio values"""
        total_value = 0
        total_risk = 0

        for position in portfolio['positions']:
            position['position_value'] = position['quantity'] * position['current_price']
            position['unrealized_pnl'] = (position['current_price'] - position['avg_entry_price']) * position['quantity']
            position['risk_amount'] = abs(position['current_price'] - position['stop_loss']) * position['quantity']

            total_value += position['position_value']
            total_risk += position['risk_amount']

        portfolio['total_portfolio_value'] = total_value
        portfolio['total_risk_if_all_sl_hit'] = total_risk

    def _calculate_allocations(self, portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Calculate position allocation percentages"""
        total_value = portfolio.get('total_portfolio_value', 0)

        if total_value == 0:
            return []

        allocations = []
        for position in portfolio['positions']:
            allocation_percent = (position['position_value'] / total_value) * 100
            allocations.append({
                'symbol': position['symbol'],
                'value': position['position_value'],
                'allocation_percent': allocation_percent
            })

        return sorted(allocations, key=lambda x: x['allocation_percent'], reverse=True)

    def _calculate_sector_allocations(self, portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Calculate sector allocation percentages"""
        total_value = portfolio.get('total_portfolio_value', 0)

        if total_value == 0:
            return []

        sector_values = {}
        for position in portfolio['positions']:
            sector = position.get('sector', 'Other')
            sector_values[sector] = sector_values.get(sector, 0) + position['position_value']

        sector_allocations = []
        for sector, value in sector_values.items():
            allocation_percent = (value / total_value) * 100
            sector_allocations.append({
                'sector': sector,
                'value': value,
                'allocation_percent': allocation_percent
            })

        return sorted(sector_allocations, key=lambda x: x['allocation_percent'], reverse=True)

    def _generate_warnings(self, portfolio: Dict[str, Any], user_settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate concentration and correlation warnings"""
        warnings = []
        total_value = portfolio.get('total_portfolio_value', 0)

        if total_value == 0:
            return warnings

        # Position concentration warning (>25% in single stock)
        for position in portfolio['positions']:
            allocation_percent = (position['position_value'] / total_value) * 100
            if allocation_percent > 25:
                warnings.append({
                    'type': 'concentration',
                    'severity': 'high',
                    'title': f'High Concentration in {position["symbol"]}',
                    'message': f'{position["symbol"]} represents {allocation_percent:.1f}% of your portfolio. Consider diversification.'
                })

        # Sector concentration warning (>40% in single sector)
        sector_allocations = self._calculate_sector_allocations(portfolio)
        for sector_alloc in sector_allocations:
            if sector_alloc['allocation_percent'] > 40:
                warnings.append({
                    'type': 'sector_concentration',
                    'severity': 'medium',
                    'title': f'High {sector_alloc["sector"]} Sector Exposure',
                    'message': f'{sector_alloc["sector"]} sector represents {sector_alloc["allocation_percent"]:.1f}% of your portfolio.'
                })

        # Correlation warning (multiple positions in same correlation group)
        correlation_groups = {}
        for position in portfolio['positions']:
            group = position.get('correlation_group', 'uncorrelated')
            if group != 'uncorrelated':
                correlation_groups[group] = correlation_groups.get(group, 0) + 1

        for group, count in correlation_groups.items():
            if count > 2:
                warnings.append({
                    'type': 'correlation',
                    'severity': 'medium',
                    'title': f'Correlated Positions: {group}',
                    'message': f'You have {count} positions in the {group} group. They may move together.'
                })

        # Total risk warning (>20% of portfolio at risk)
        total_risk = portfolio.get('total_risk_if_all_sl_hit', 0)
        risk_percent = (total_risk / total_value) * 100
        if risk_percent > 20:
            warnings.append({
                'type': 'risk_exposure',
                'severity': 'high',
                'title': 'High Portfolio Risk',
                'message': f'Total risk if all stop losses hit: {risk_percent:.1f}% of portfolio value.'
            })

        return warnings

    def get_realtime_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch real-time prices from yfinance"""
        try:
            prices = {}
            for symbol in symbols:
                try:
                    # Add .NS suffix for Indian stocks if not present
                    ticker_symbol = symbol if '.NS' in symbol else f"{symbol}.NS"
                    ticker = yf.Ticker(ticker_symbol)

                    # Get latest price
                    hist = ticker.history(period='1d')
                    if not hist.empty:
                        prices[symbol] = float(hist['Close'].iloc[-1])
                    else:
                        # Fallback to info if history fails
                        info = ticker.info
                        prices[symbol] = float(info.get('currentPrice', info.get('regularMarketPrice', 0)))
                except Exception as e:
                    print(f"Error fetching price for {symbol}: {str(e)}")
                    prices[symbol] = 0

            return prices
        except Exception as e:
            raise Exception(f"Error fetching realtime prices: {str(e)}")

    def get_historical_returns(self, user_id: str) -> Dict[str, Any]:
        """Calculate historical returns for 3m, 6m, 1y timeframes"""
        try:
            portfolio = self.get_portfolio(user_id)

            if not portfolio['positions']:
                return {
                    'individual_returns': [],
                    'consolidated_returns': {
                        '3m': 0,
                        '6m': 0,
                        '1y': 0
                    },
                    'disclaimer': 'Historical returns are for informational purposes only.'
                }

            # Define timeframes
            today = datetime.now()
            timeframes = {
                '3m': today - timedelta(days=90),
                '6m': today - timedelta(days=180),
                '1y': today - timedelta(days=365)
            }

            individual_returns = []
            consolidated_returns = {'3m': 0, '6m': 0, '1y': 0}

            for position in portfolio['positions']:
                symbol = position['symbol']
                ticker_symbol = symbol if '.NS' in symbol else f"{symbol}.NS"
                current_value = position['position_value']

                try:
                    ticker = yf.Ticker(ticker_symbol)
                    position_returns = {
                        'symbol': symbol,
                        'current_value': current_value,
                        'returns': {}
                    }

                    for period, start_date in timeframes.items():
                        try:
                            # Fetch historical data
                            hist = ticker.history(start=start_date, end=today)

                            if not hist.empty:
                                historical_price = float(hist['Close'].iloc[0])
                                current_price = position['current_price']
                                quantity = position['quantity']

                                # Calculate what value would have been at historical price
                                historical_value = historical_price * quantity
                                # Return in rupees
                                return_value = current_value - historical_value
                                # Return in percentage
                                return_percent = ((current_price - historical_price) / historical_price) * 100

                                position_returns['returns'][period] = {
                                    'return_value': return_value,
                                    'return_percent': return_percent,
                                    'historical_price': historical_price,
                                    'current_price': current_price
                                }

                                # Add to consolidated returns
                                consolidated_returns[period] += return_value
                            else:
                                position_returns['returns'][period] = {
                                    'return_value': 0,
                                    'return_percent': 0,
                                    'error': 'No historical data available'
                                }
                        except Exception as e:
                            position_returns['returns'][period] = {
                                'return_value': 0,
                                'return_percent': 0,
                                'error': str(e)
                            }

                    individual_returns.append(position_returns)

                except Exception as e:
                    print(f"Error calculating returns for {symbol}: {str(e)}")

            return {
                'individual_returns': individual_returns,
                'consolidated_returns': consolidated_returns,
                'disclaimer': 'Historical returns are for informational purposes only. Past performance does not guarantee future results.'
            }

        except Exception as e:
            raise Exception(f"Error calculating historical returns: {str(e)}")

    def get_portfolio_pnl_graph(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Generate portfolio PnL graph data over specified days"""
        try:
            portfolio = self.get_portfolio(user_id)

            if not portfolio['positions']:
                return {
                    'graph_data': [],
                    'total_pnl': 0,
                    'pnl_percent': 0
                }

            # Get date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Fetch historical data for all positions
            all_data = []
            for position in portfolio['positions']:
                symbol = position['symbol']
                ticker_symbol = symbol if '.NS' in symbol else f"{symbol}.NS"
                quantity = position['quantity']
                avg_entry = position['avg_entry_price']

                try:
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(start=start_date, end=end_date)

                    if not hist.empty:
                        # Calculate daily PnL for this position
                        hist['pnl'] = (hist['Close'] - avg_entry) * quantity
                        hist['symbol'] = symbol
                        all_data.append(hist[['pnl']])
                except Exception as e:
                    print(f"Error fetching history for {symbol}: {str(e)}")

            if not all_data:
                return {
                    'graph_data': [],
                    'total_pnl': 0,
                    'pnl_percent': 0
                }

            # Combine all positions' PnL
            combined_df = pd.concat(all_data, axis=1)
            combined_df['total_pnl'] = combined_df.sum(axis=1)

            # Format for frontend
            graph_data = []
            for date, row in combined_df.iterrows():
                graph_data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'pnl': float(row['total_pnl']) if not pd.isna(row['total_pnl']) else 0
                })

            # Calculate total metrics
            total_pnl = sum(p.get('unrealized_pnl', 0) for p in portfolio['positions'])
            total_investment = sum(p['quantity'] * p['avg_entry_price'] for p in portfolio['positions'])
            pnl_percent = (total_pnl / total_investment * 100) if total_investment > 0 else 0

            return {
                'graph_data': graph_data,
                'total_pnl': total_pnl,
                'pnl_percent': pnl_percent
            }

        except Exception as e:
            raise Exception(f"Error generating PnL graph: {str(e)}")

    def get_yearly_monthly_pnl_analysis(self, user_id: str) -> Dict[str, Any]:
        """
        Generate 1-year monthly PnL analysis showing what returns would have been
        if stocks were purchased at the beginning of each month
        """
        try:
            portfolio = self.get_portfolio(user_id)

            if not portfolio['positions']:
                return {
                    'graph_data': [],
                    'table_data': [],
                    'summary': {
                        'total_months': 0,
                        'positive_months': 0,
                        'negative_months': 0,
                        'best_month': None,
                        'worst_month': None
                    }
                }

            # Get date range - last 12 months
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)

            # Generate month start dates for the past year
            month_dates = []
            current_month = start_date.replace(day=1)
            while current_month <= end_date:
                month_dates.append(current_month)
                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)

            # Data structures for results
            monthly_data = []

            for month_start in month_dates:
                month_name = month_start.strftime('%b %Y')
                month_pnl = 0
                month_investment = 0
                stock_details = []

                for position in portfolio['positions']:
                    symbol = position['symbol']
                    ticker_symbol = symbol if '.NS' in symbol else f"{symbol}.NS"
                    quantity = position['quantity']
                    current_price = position['current_price']

                    try:
                        ticker = yf.Ticker(ticker_symbol)

                        # Fetch historical data for this month
                        month_end = month_start + timedelta(days=32)
                        month_end = month_end.replace(day=1) - timedelta(days=1)  # Last day of month

                        hist = ticker.history(start=month_start, end=min(month_end, end_date))

                        if not hist.empty:
                            # Get price at month start (buy price)
                            month_start_price = float(hist['Close'].iloc[0])

                            # Calculate what the investment would have been
                            investment_value = month_start_price * quantity
                            current_value = current_price * quantity

                            # Calculate PnL
                            pnl = current_value - investment_value
                            pnl_percent = ((current_price - month_start_price) / month_start_price) * 100

                            month_pnl += pnl
                            month_investment += investment_value

                            stock_details.append({
                                'symbol': symbol,
                                'buy_price': month_start_price,
                                'current_price': current_price,
                                'quantity': quantity,
                                'pnl': pnl,
                                'pnl_percent': pnl_percent
                            })
                        else:
                            # No data for this month, use current price as estimate
                            investment_value = current_price * quantity
                            month_investment += investment_value

                            stock_details.append({
                                'symbol': symbol,
                                'buy_price': current_price,
                                'current_price': current_price,
                                'quantity': quantity,
                                'pnl': 0,
                                'pnl_percent': 0
                            })

                    except Exception as e:
                        print(f"Error fetching data for {symbol} in {month_name}: {str(e)}")
                        continue

                # Calculate month percentage
                month_pnl_percent = (month_pnl / month_investment * 100) if month_investment > 0 else 0

                monthly_data.append({
                    'month': month_name,
                    'month_date': month_start.strftime('%Y-%m'),
                    'total_pnl': month_pnl,
                    'total_investment': month_investment,
                    'pnl_percent': month_pnl_percent,
                    'stock_details': stock_details
                })

            # Calculate summary statistics
            positive_months = sum(1 for m in monthly_data if m['total_pnl'] > 0)
            negative_months = sum(1 for m in monthly_data if m['total_pnl'] < 0)

            best_month = max(monthly_data, key=lambda x: x['pnl_percent']) if monthly_data else None
            worst_month = min(monthly_data, key=lambda x: x['pnl_percent']) if monthly_data else None

            # Format graph data (simplified for chart)
            graph_data = [
                {
                    'month': m['month'],
                    'pnl': m['total_pnl'],
                    'pnl_percent': m['pnl_percent']
                }
                for m in monthly_data
            ]

            return {
                'graph_data': graph_data,
                'table_data': monthly_data,
                'summary': {
                    'total_months': len(monthly_data),
                    'positive_months': positive_months,
                    'negative_months': negative_months,
                    'best_month': {
                        'month': best_month['month'],
                        'pnl': best_month['total_pnl'],
                        'pnl_percent': best_month['pnl_percent']
                    } if best_month else None,
                    'worst_month': {
                        'month': worst_month['month'],
                        'pnl': worst_month['total_pnl'],
                        'pnl_percent': worst_month['pnl_percent']
                    } if worst_month else None
                },
                'disclaimer': 'This analysis shows hypothetical returns if positions were purchased at month start prices. Past performance does not guarantee future results.'
            }

        except Exception as e:
            raise Exception(f"Error generating yearly monthly PnL analysis: {str(e)}")

    def get_market_sentiment(self, symbols: List[str]) -> Dict[str, Any]:
        """Get today's market sentiment and pattern analysis for symbols"""
        try:
            sentiment_data = []

            for symbol in symbols:
                ticker_symbol = symbol if '.NS' in symbol else f"{symbol}.NS"

                try:
                    ticker = yf.Ticker(ticker_symbol)

                    # Get recent data (last 5 days for pattern analysis)
                    hist = ticker.history(period='5d')

                    if hist.empty or len(hist) < 2:
                        continue

                    # Today's data
                    today = hist.iloc[-1]
                    yesterday = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]

                    open_price = float(today['Open'])
                    high_price = float(today['High'])
                    low_price = float(today['Low'])
                    close_price = float(today['Close'])
                    prev_close = float(yesterday['Close'])
                    volume = float(today['Volume'])

                    # Calculate metrics
                    day_change = close_price - prev_close
                    day_change_percent = (day_change / prev_close) * 100
                    intraday_range = high_price - low_price
                    body = abs(close_price - open_price)

                    # Determine candle pattern
                    candle_pattern = 'neutral'
                    candle_description = ''

                    if close_price > open_price:
                        # Bullish candle
                        if body > (intraday_range * 0.7):
                            candle_pattern = 'strong_bullish'
                            candle_description = 'Strong bullish candle with large green body'
                        else:
                            candle_pattern = 'bullish'
                            candle_description = 'Bullish candle with moderate body'
                    elif close_price < open_price:
                        # Bearish candle
                        if body > (intraday_range * 0.7):
                            candle_pattern = 'strong_bearish'
                            candle_description = 'Strong bearish candle with large red body'
                        else:
                            candle_pattern = 'bearish'
                            candle_description = 'Bearish candle with moderate body'
                    else:
                        candle_pattern = 'doji'
                        candle_description = 'Doji candle indicating indecision'

                    # Detect specific patterns
                    if body < (intraday_range * 0.3):
                        if close_price > open_price:
                            candle_pattern = 'hammer'
                            candle_description = 'Hammer pattern - potential bullish reversal'
                        else:
                            candle_pattern = 'hanging_man'
                            candle_description = 'Hanging man pattern - potential bearish reversal'

                    # Sentiment based on price action
                    if day_change_percent > 2:
                        sentiment = 'very_bullish'
                    elif day_change_percent > 0.5:
                        sentiment = 'bullish'
                    elif day_change_percent < -2:
                        sentiment = 'very_bearish'
                    elif day_change_percent < -0.5:
                        sentiment = 'bearish'
                    else:
                        sentiment = 'neutral'

                    sentiment_data.append({
                        'symbol': symbol,
                        'sentiment': sentiment,
                        'day_change': day_change,
                        'day_change_percent': day_change_percent,
                        'candle_pattern': candle_pattern,
                        'candle_description': candle_description,
                        'price_data': {
                            'open': open_price,
                            'high': high_price,
                            'low': low_price,
                            'close': close_price,
                            'volume': volume,
                            'prev_close': prev_close
                        }
                    })

                except Exception as e:
                    print(f"Error analyzing sentiment for {symbol}: {str(e)}")

            return {
                'sentiment_analysis': sentiment_data,
                'disclaimer': 'Market sentiment is for informational purposes only and should not be considered as trading advice.'
            }

        except Exception as e:
            raise Exception(f"Error getting market sentiment: {str(e)}")


# Singleton instance
risk_phase4_service = RiskCalculatorPhase4Service()
