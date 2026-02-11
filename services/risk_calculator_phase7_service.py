"""
Risk Calculator Phase 7: Portfolio Risk Analytics Service

Provides comprehensive portfolio analytics including equity curves, drawdown analysis,
volatility metrics, and stress testing for advanced risk management.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from bson import ObjectId
import os
from pymongo import MongoClient
import numpy as np
from collections import defaultdict


class RiskCalculatorPhase7Service:
    """Service for advanced portfolio risk analytics"""

    def __init__(self):
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('DB_NAME', 'welthwest')
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.trades_collection = self.db['risk_calculator_trades']
        self.settings_collection = self.db['risk_calculator_settings']
        self.portfolio_collection = self.db['risk_calculator_portfolio']

    def calculate_equity_curve(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate equity curve from closed trades

        Args:
            user_id: User's ID
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Equity curve data with timestamps and values
        """
        try:
            # Build query
            query = {
                'user_id': user_id,
                'exit_timestamp': {'$ne': None}
            }

            if start_date:
                query['created_at'] = query.get('created_at', {})
                query['created_at']['$gte'] = start_date

            if end_date:
                query['created_at'] = query.get('created_at', {})
                query['created_at']['$lte'] = end_date

            # Get all closed trades sorted by exit time
            trades = list(self.trades_collection.find(query).sort('exit_timestamp', 1))

            if not trades:
                return {
                    'message': 'No closed trades found',
                    'equity_curve': [],
                    'initial_capital': 0,
                    'final_capital': 0
                }

            # Get initial capital
            settings = self.settings_collection.find_one({'user_id': user_id}) or {}
            initial_capital = settings.get('capital_baseline', 100000)

            # Build equity curve
            equity_curve = []
            running_capital = initial_capital
            cumulative_pnl = 0

            equity_curve.append({
                'timestamp': trades[0]['created_at'],
                'capital': running_capital,
                'cumulative_pnl': 0,
                'trade_num': 0
            })

            for idx, trade in enumerate(trades, 1):
                pnl = trade.get('actual_pnl', 0)
                cumulative_pnl += pnl
                running_capital = initial_capital + cumulative_pnl

                equity_curve.append({
                    'timestamp': trade['exit_timestamp'],
                    'capital': round(running_capital, 2),
                    'cumulative_pnl': round(cumulative_pnl, 2),
                    'trade_num': idx,
                    'trade_id': str(trade['_id']),
                    'symbol': trade.get('symbol', ''),
                    'pnl': round(pnl, 2)
                })

            return {
                'equity_curve': equity_curve,
                'initial_capital': initial_capital,
                'final_capital': round(running_capital, 2),
                'total_return': round(cumulative_pnl, 2),
                'total_return_percent': round((cumulative_pnl / initial_capital) * 100, 2),
                'total_trades': len(trades),
                'period_start': trades[0]['created_at'],
                'period_end': trades[-1]['exit_timestamp']
            }

        except Exception as e:
            raise Exception(f"Error calculating equity curve: {str(e)}")

    def calculate_drawdown_metrics(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive drawdown metrics

        Args:
            user_id: User's ID
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Drawdown analysis with max DD, average DD, duration
        """
        try:
            # Get equity curve
            equity_data = self.calculate_equity_curve(user_id, start_date, end_date)
            equity_curve = equity_data.get('equity_curve', [])

            if len(equity_curve) < 2:
                return {
                    'message': 'Insufficient data for drawdown analysis',
                    'max_drawdown': 0,
                    'avg_drawdown': 0
                }

            # Calculate drawdowns
            drawdowns = []
            peak_capital = equity_curve[0]['capital']
            peak_timestamp = equity_curve[0]['timestamp']
            in_drawdown = False
            current_drawdown_start = None

            for point in equity_curve:
                capital = point['capital']

                if capital > peak_capital:
                    # New peak
                    if in_drawdown:
                        # Drawdown ended
                        in_drawdown = False

                    peak_capital = capital
                    peak_timestamp = point['timestamp']
                else:
                    # In drawdown
                    dd_amount = peak_capital - capital
                    dd_percent = (dd_amount / peak_capital) * 100 if peak_capital > 0 else 0

                    if not in_drawdown and dd_percent > 0:
                        # Start of new drawdown
                        in_drawdown = True
                        current_drawdown_start = peak_timestamp

                    if dd_percent > 0:
                        drawdowns.append({
                            'timestamp': point['timestamp'],
                            'peak_capital': peak_capital,
                            'current_capital': capital,
                            'drawdown_amount': round(dd_amount, 2),
                            'drawdown_percent': round(dd_percent, 2),
                            'drawdown_start': current_drawdown_start,
                            'trade_num': point['trade_num']
                        })

            if not drawdowns:
                return {
                    'message': 'No drawdowns detected - portfolio has been continuously growing',
                    'max_drawdown_percent': 0,
                    'max_drawdown_amount': 0,
                    'avg_drawdown_percent': 0,
                    'num_drawdowns': 0
                }

            # Find maximum drawdown
            max_dd = max(drawdowns, key=lambda x: x['drawdown_percent'])

            # Calculate average drawdown
            avg_dd_percent = sum(d['drawdown_percent'] for d in drawdowns) / len(drawdowns)
            avg_dd_amount = sum(d['drawdown_amount'] for d in drawdowns) / len(drawdowns)

            # Calculate drawdown duration (for max DD)
            max_dd_duration_days = 0
            if max_dd['drawdown_start']:
                max_dd_duration = max_dd['timestamp'] - max_dd['drawdown_start']
                max_dd_duration_days = max_dd_duration.days

            # Count distinct drawdown periods
            unique_drawdown_periods = len(set(d['drawdown_start'] for d in drawdowns if d['drawdown_start']))

            return {
                'max_drawdown': {
                    'percent': round(max_dd['drawdown_percent'], 2),
                    'amount': round(max_dd['drawdown_amount'], 2),
                    'peak_capital': round(max_dd['peak_capital'], 2),
                    'trough_capital': round(max_dd['current_capital'], 2),
                    'timestamp': max_dd['timestamp'],
                    'duration_days': max_dd_duration_days,
                    'trade_num': max_dd['trade_num']
                },
                'average_drawdown': {
                    'percent': round(avg_dd_percent, 2),
                    'amount': round(avg_dd_amount, 2)
                },
                'drawdown_summary': {
                    'num_drawdown_periods': unique_drawdown_periods,
                    'total_drawdown_points': len(drawdowns),
                    'current_drawdown_percent': round(drawdowns[-1]['drawdown_percent'], 2) if drawdowns else 0
                },
                'drawdown_history': drawdowns[-20:],  # Last 20 drawdown points
                'insights': self._generate_drawdown_insights(max_dd, avg_dd_percent, unique_drawdown_periods)
            }

        except Exception as e:
            raise Exception(f"Error calculating drawdown metrics: {str(e)}")

    def calculate_volatility_metrics(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate volatility metrics including Sharpe ratio

        Args:
            user_id: User's ID
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Volatility analysis and risk-adjusted returns
        """
        try:
            # Get equity curve
            equity_data = self.calculate_equity_curve(user_id, start_date, end_date)
            equity_curve = equity_data.get('equity_curve', [])

            if len(equity_curve) < 3:
                return {
                    'message': 'Insufficient data for volatility analysis (minimum 3 trades required)',
                    'std_dev': 0,
                    'sharpe_ratio': 0
                }

            # Calculate returns between trades
            returns = []
            for i in range(1, len(equity_curve)):
                prev_capital = equity_curve[i-1]['capital']
                curr_capital = equity_curve[i]['capital']

                if prev_capital > 0:
                    ret = ((curr_capital - prev_capital) / prev_capital) * 100
                    returns.append(ret)

            if not returns:
                return {'message': 'Could not calculate returns', 'std_dev': 0, 'sharpe_ratio': 0}

            # Convert to numpy array for calculations
            returns_array = np.array(returns)

            # Calculate statistics
            mean_return = float(np.mean(returns_array))
            std_dev = float(np.std(returns_array, ddof=1))  # Sample standard deviation
            median_return = float(np.median(returns_array))

            # Calculate Sharpe Ratio (assuming risk-free rate = 0 for simplicity)
            # For more accuracy, could use actual risk-free rate (e.g., 6% annual)
            risk_free_rate_per_trade = 0  # Can be adjusted
            sharpe_ratio = (mean_return - risk_free_rate_per_trade) / std_dev if std_dev > 0 else 0

            # Calculate other risk metrics
            positive_returns = returns_array[returns_array > 0]
            negative_returns = returns_array[returns_array < 0]

            avg_gain = float(np.mean(positive_returns)) if len(positive_returns) > 0 else 0
            avg_loss = float(np.mean(np.abs(negative_returns))) if len(negative_returns) > 0 else 0

            profit_factor = avg_gain / avg_loss if avg_loss > 0 else float('inf')

            # Calculate downside deviation (for Sortino ratio)
            downside_returns = returns_array[returns_array < 0]
            downside_std = float(np.std(downside_returns, ddof=1)) if len(downside_returns) > 1 else 0
            sortino_ratio = (mean_return - risk_free_rate_per_trade) / downside_std if downside_std > 0 else 0

            # Calculate percentiles
            percentile_25 = float(np.percentile(returns_array, 25))
            percentile_75 = float(np.percentile(returns_array, 75))

            return {
                'return_statistics': {
                    'mean_return_percent': round(mean_return, 2),
                    'median_return_percent': round(median_return, 2),
                    'std_deviation': round(std_dev, 2),
                    'percentile_25': round(percentile_25, 2),
                    'percentile_75': round(percentile_75, 2)
                },
                'risk_metrics': {
                    'sharpe_ratio': round(sharpe_ratio, 2),
                    'sortino_ratio': round(sortino_ratio, 2),
                    'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'Infinity',
                    'downside_deviation': round(downside_std, 2)
                },
                'gain_loss_analysis': {
                    'avg_gain_percent': round(avg_gain, 2),
                    'avg_loss_percent': round(avg_loss, 2),
                    'gain_loss_ratio': round(avg_gain / avg_loss, 2) if avg_loss > 0 else 'N/A',
                    'num_positive_trades': len(positive_returns),
                    'num_negative_trades': len(negative_returns)
                },
                'insights': self._generate_volatility_insights(sharpe_ratio, std_dev, profit_factor)
            }

        except Exception as e:
            raise Exception(f"Error calculating volatility metrics: {str(e)}")

    def calculate_rolling_metrics(
        self,
        user_id: str,
        window_size: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate rolling performance metrics

        Args:
            user_id: User's ID
            window_size: Rolling window size (number of trades)
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Rolling metrics over time
        """
        try:
            # Get equity curve
            equity_data = self.calculate_equity_curve(user_id, start_date, end_date)
            equity_curve = equity_data.get('equity_curve', [])

            if len(equity_curve) < window_size + 1:
                return {
                    'message': f'Insufficient data for rolling analysis (minimum {window_size + 1} trades required)',
                    'rolling_metrics': []
                }

            # Calculate returns
            returns = []
            for i in range(1, len(equity_curve)):
                prev_capital = equity_curve[i-1]['capital']
                curr_capital = equity_curve[i]['capital']

                if prev_capital > 0:
                    ret = ((curr_capital - prev_capital) / prev_capital) * 100
                    returns.append(ret)

            # Calculate rolling metrics
            rolling_metrics = []

            for i in range(window_size, len(returns) + 1):
                window_returns = returns[i-window_size:i]
                window_returns_array = np.array(window_returns)

                # Calculate metrics for this window
                mean_return = float(np.mean(window_returns_array))
                std_dev = float(np.std(window_returns_array, ddof=1))
                sharpe = mean_return / std_dev if std_dev > 0 else 0

                win_rate = (len([r for r in window_returns if r > 0]) / window_size) * 100

                rolling_metrics.append({
                    'trade_num': i,
                    'timestamp': equity_curve[i]['timestamp'],
                    'avg_return_percent': round(mean_return, 2),
                    'std_deviation': round(std_dev, 2),
                    'sharpe_ratio': round(sharpe, 2),
                    'win_rate': round(win_rate, 2),
                    'capital': equity_curve[i]['capital']
                })

            return {
                'window_size': window_size,
                'rolling_metrics': rolling_metrics,
                'summary': {
                    'avg_rolling_sharpe': round(np.mean([m['sharpe_ratio'] for m in rolling_metrics]), 2),
                    'best_rolling_sharpe': round(max([m['sharpe_ratio'] for m in rolling_metrics]), 2),
                    'worst_rolling_sharpe': round(min([m['sharpe_ratio'] for m in rolling_metrics]), 2),
                    'avg_rolling_win_rate': round(np.mean([m['win_rate'] for m in rolling_metrics]), 2)
                }
            }

        except Exception as e:
            raise Exception(f"Error calculating rolling metrics: {str(e)}")

    def stress_test_portfolio(
        self,
        user_id: str,
        stress_scenarios: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Perform stress testing on portfolio

        Args:
            user_id: User's ID
            stress_scenarios: List of stress scenarios to test (optional)

        Returns:
            Stress test results
        """
        try:
            # Get current portfolio
            portfolio = self.portfolio_collection.find_one({'user_id': user_id})

            if not portfolio or not portfolio.get('positions'):
                return {
                    'message': 'No portfolio positions found',
                    'stress_tests': []
                }

            # Default stress scenarios if none provided
            if not stress_scenarios:
                stress_scenarios = [
                    {'name': 'Market Crash -10%', 'price_change_percent': -10},
                    {'name': 'Market Crash -20%', 'price_change_percent': -20},
                    {'name': 'Black Swan -30%', 'price_change_percent': -30},
                    {'name': 'Bull Rally +15%', 'price_change_percent': 15},
                    {'name': 'Individual Stock -50%', 'type': 'individual', 'price_change_percent': -50}
                ]

            # Current portfolio value
            current_value = portfolio.get('total_portfolio_value', 0)
            positions = portfolio.get('positions', [])

            stress_results = []

            for scenario in stress_scenarios:
                scenario_name = scenario['name']
                price_change = scenario.get('price_change_percent', 0)
                scenario_type = scenario.get('type', 'market_wide')

                if scenario_type == 'individual':
                    # Test each position individually
                    for position in positions:
                        individual_result = self._calculate_individual_stress(
                            position,
                            positions,
                            price_change,
                            current_value
                        )

                        stress_results.append({
                            'scenario': f"{scenario_name} - {position['symbol']}",
                            **individual_result
                        })
                else:
                    # Market-wide stress test
                    market_result = self._calculate_market_wide_stress(
                        positions,
                        price_change,
                        current_value
                    )

                    stress_results.append({
                        'scenario': scenario_name,
                        **market_result
                    })

            # Calculate worst case scenario
            worst_case = min(stress_results, key=lambda x: x['new_value_percent_change'])

            return {
                'current_portfolio_value': current_value,
                'num_positions': len(positions),
                'stress_tests': stress_results,
                'worst_case_scenario': {
                    'scenario': worst_case['scenario'],
                    'loss_amount': worst_case['loss_amount'],
                    'loss_percent': worst_case['new_value_percent_change']
                },
                'insights': self._generate_stress_test_insights(stress_results, current_value)
            }

        except Exception as e:
            raise Exception(f"Error in stress testing: {str(e)}")

    def get_comprehensive_analytics(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive portfolio risk analytics

        Args:
            user_id: User's ID
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Complete analytics package
        """
        try:
            # Calculate all metrics
            equity_curve = self.calculate_equity_curve(user_id, start_date, end_date)
            drawdown_metrics = self.calculate_drawdown_metrics(user_id, start_date, end_date)
            volatility_metrics = self.calculate_volatility_metrics(user_id, start_date, end_date)
            rolling_metrics = self.calculate_rolling_metrics(user_id, window_size=10, start_date=start_date, end_date=end_date)
            stress_tests = self.stress_test_portfolio(user_id)

            # Generate overall portfolio score
            portfolio_score = self._calculate_portfolio_score(
                equity_curve,
                drawdown_metrics,
                volatility_metrics
            )

            return {
                'equity_curve': equity_curve,
                'drawdown_analysis': drawdown_metrics,
                'volatility_analysis': volatility_metrics,
                'rolling_analysis': rolling_metrics,
                'stress_tests': stress_tests,
                'portfolio_score': portfolio_score,
                'generated_at': datetime.now(),
                'disclaimer': 'This is an analytical tool based on historical performance. Past performance does not guarantee future results.'
            }

        except Exception as e:
            raise Exception(f"Error generating comprehensive analytics: {str(e)}")

    # Private helper methods

    def _generate_drawdown_insights(
        self,
        max_dd: Dict[str, Any],
        avg_dd_percent: float,
        num_periods: int
    ) -> List[str]:
        """Generate insights from drawdown analysis"""
        insights = []

        if max_dd['percent'] < 10:
            insights.append(f"Excellent risk control: Maximum drawdown only {max_dd['percent']:.1f}%")
        elif max_dd['percent'] < 20:
            insights.append(f"Good risk management: Maximum drawdown {max_dd['percent']:.1f}%")
        else:
            insights.append(f"High risk exposure: Maximum drawdown {max_dd['percent']:.1f}% - consider reducing position sizes")

        if avg_dd_percent < max_dd['percent'] * 0.5:
            insights.append(f"Most drawdowns are smaller than maximum ({avg_dd_percent:.1f}% average)")

        if num_periods > 5:
            insights.append(f"Experienced {num_periods} separate drawdown periods - focus on consistency")

        return insights

    def _generate_volatility_insights(
        self,
        sharpe_ratio: float,
        std_dev: float,
        profit_factor: float
    ) -> List[str]:
        """Generate insights from volatility analysis"""
        insights = []

        if sharpe_ratio > 2:
            insights.append(f"Excellent risk-adjusted returns (Sharpe: {sharpe_ratio:.2f})")
        elif sharpe_ratio > 1:
            insights.append(f"Good risk-adjusted returns (Sharpe: {sharpe_ratio:.2f})")
        elif sharpe_ratio > 0:
            insights.append(f"Positive but modest risk-adjusted returns (Sharpe: {sharpe_ratio:.2f})")
        else:
            insights.append(f"Poor risk-adjusted returns (Sharpe: {sharpe_ratio:.2f}) - returns don't justify the risk")

        if std_dev < 2:
            insights.append(f"Low volatility trading style ({std_dev:.2f}% std dev)")
        elif std_dev > 5:
            insights.append(f"High volatility trading style ({std_dev:.2f}% std dev) - consider risk management")

        if profit_factor != float('inf') and profit_factor > 2:
            insights.append(f"Strong profit factor: {profit_factor:.2f} (winners outweigh losers)")

        return insights

    def _calculate_individual_stress(
        self,
        position: Dict[str, Any],
        all_positions: List[Dict[str, Any]],
        price_change_percent: float,
        current_value: float
    ) -> Dict[str, Any]:
        """Calculate stress impact on individual position"""
        # Calculate stressed position value
        stressed_position_value = position['position_value'] * (1 + price_change_percent / 100)
        position_change = stressed_position_value - position['position_value']

        # Calculate new portfolio value
        other_positions_value = sum(p['position_value'] for p in all_positions if p['symbol'] != position['symbol'])
        new_total_value = stressed_position_value + other_positions_value

        loss_amount = new_total_value - current_value
        loss_percent = (loss_amount / current_value) * 100 if current_value > 0 else 0

        return {
            'current_value': current_value,
            'new_value': round(new_total_value, 2),
            'loss_amount': round(loss_amount, 2),
            'new_value_percent_change': round(loss_percent, 2),
            'position_allocation_percent': round((position['position_value'] / current_value) * 100, 2) if current_value > 0 else 0
        }

    def _calculate_market_wide_stress(
        self,
        positions: List[Dict[str, Any]],
        price_change_percent: float,
        current_value: float
    ) -> Dict[str, Any]:
        """Calculate stress impact on entire portfolio"""
        # Apply price change to all positions
        new_total_value = sum(p['position_value'] * (1 + price_change_percent / 100) for p in positions)

        loss_amount = new_total_value - current_value
        loss_percent = (loss_amount / current_value) * 100 if current_value > 0 else 0

        return {
            'current_value': current_value,
            'new_value': round(new_total_value, 2),
            'loss_amount': round(loss_amount, 2),
            'new_value_percent_change': round(loss_percent, 2)
        }

    def _generate_stress_test_insights(
        self,
        stress_results: List[Dict[str, Any]],
        current_value: float
    ) -> List[str]:
        """Generate insights from stress testing"""
        insights = []

        # Find most severe scenario
        worst_loss = min(stress_results, key=lambda x: x['new_value_percent_change'])

        insights.append(f"Worst case scenario: {worst_loss['scenario']} would result in {abs(worst_loss['new_value_percent_change']):.1f}% loss")

        # Check if portfolio can withstand moderate stress
        moderate_crash = next((s for s in stress_results if 'Crash -10%' in s['scenario']), None)
        if moderate_crash and moderate_crash['new_value_percent_change'] > -15:
            insights.append("Portfolio shows resilience to moderate market corrections")

        # Individual position risk
        individual_tests = [s for s in stress_results if 'Individual' in s.get('scenario', '')]
        if individual_tests:
            worst_individual = min(individual_tests, key=lambda x: x['new_value_percent_change'])
            insights.append(f"High concentration risk: Single stock failure could cause {abs(worst_individual['new_value_percent_change']):.1f}% portfolio loss")

        return insights

    def _calculate_portfolio_score(
        self,
        equity_curve: Dict[str, Any],
        drawdown_metrics: Dict[str, Any],
        volatility_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate overall portfolio health score (0-100)"""
        score = 0
        max_score = 100
        breakdown = {}

        # Return performance (30 points)
        total_return_percent = equity_curve.get('total_return_percent', 0)
        if total_return_percent > 30:
            return_score = 30
        elif total_return_percent > 15:
            return_score = 25
        elif total_return_percent > 5:
            return_score = 20
        elif total_return_percent > 0:
            return_score = 15
        else:
            return_score = max(0, 10 + total_return_percent)  # Negative returns reduce score

        score += return_score
        breakdown['return_performance'] = return_score

        # Drawdown control (30 points)
        if 'max_drawdown' in drawdown_metrics:
            max_dd = drawdown_metrics['max_drawdown']['percent']
            if max_dd < 5:
                dd_score = 30
            elif max_dd < 10:
                dd_score = 25
            elif max_dd < 15:
                dd_score = 20
            elif max_dd < 20:
                dd_score = 15
            elif max_dd < 30:
                dd_score = 10
            else:
                dd_score = 5

            score += dd_score
            breakdown['drawdown_control'] = dd_score
        else:
            breakdown['drawdown_control'] = 15  # Neutral score if no data

        # Risk-adjusted returns (40 points)
        if 'risk_metrics' in volatility_metrics:
            sharpe = volatility_metrics['risk_metrics'].get('sharpe_ratio', 0)
            if sharpe > 2:
                sharpe_score = 40
            elif sharpe > 1.5:
                sharpe_score = 35
            elif sharpe > 1:
                sharpe_score = 30
            elif sharpe > 0.5:
                sharpe_score = 20
            elif sharpe > 0:
                sharpe_score = 10
            else:
                sharpe_score = 0

            score += sharpe_score
            breakdown['risk_adjusted_returns'] = sharpe_score
        else:
            breakdown['risk_adjusted_returns'] = 20  # Neutral score if no data

        # Determine grade
        if score >= 85:
            grade = 'A+'
            description = 'Excellent'
        elif score >= 75:
            grade = 'A'
            description = 'Very Good'
        elif score >= 65:
            grade = 'B'
            description = 'Good'
        elif score >= 55:
            grade = 'C'
            description = 'Average'
        else:
            grade = 'D'
            description = 'Needs Improvement'

        return {
            'score': round(score, 1),
            'max_score': max_score,
            'grade': grade,
            'description': description,
            'breakdown': breakdown
        }


# Singleton instance
risk_phase7_service = RiskCalculatorPhase7Service()
