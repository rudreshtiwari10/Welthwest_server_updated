"""
Risk Calculator Phase 6: Scenario & Cost Simulation Engine Service

Provides what-if scenario simulations, cost projections, and Monte Carlo analysis
for risk management and trade planning.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
import os
from pymongo import MongoClient
import random
import numpy as np


class RiskCalculatorPhase6Service:
    """Service for scenario simulations and cost analysis"""

    def __init__(self):
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('DB_NAME', 'welthwest')
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.simulations_collection = self.db['risk_calculator_simulations']
        self.trades_collection = self.db['risk_calculator_trades']
        self.settings_collection = self.db['risk_calculator_settings']

    def simulate_monthly_costs(
        self,
        user_id: str,
        trade_frequency: int,
        avg_position_size: float,
        broker_type: str = 'discount'
    ) -> Dict[str, Any]:
        """
        Simulate monthly trading costs based on frequency

        Args:
            user_id: User's ID
            trade_frequency: Number of trades per month
            avg_position_size: Average position size in INR
            broker_type: 'discount' or 'traditional'

        Returns:
            Cost breakdown and projections
        """
        try:
            # Define broker cost structures
            broker_costs = {
                'discount': {
                    'name': 'Discount Broker (e.g., Zerodha)',
                    'brokerage_per_order': 20,  # Flat ₹20 or 0.03%, whichever lower
                    'brokerage_percent': 0.03,
                    'stt_percent': 0.025,  # 0.025% on sell side for equity delivery
                    'exchange_charges_percent': 0.00325,
                    'gst_percent': 18,  # 18% on brokerage + transaction charges
                    'sebi_charges_percent': 0.0001,
                    'stamp_duty_percent': 0.015  # 0.015% on buy side
                },
                'traditional': {
                    'name': 'Traditional Broker',
                    'brokerage_percent': 0.50,  # 0.5% on both sides
                    'stt_percent': 0.025,
                    'exchange_charges_percent': 0.00325,
                    'gst_percent': 18,
                    'sebi_charges_percent': 0.0001,
                    'stamp_duty_percent': 0.015
                }
            }

            cost_structure = broker_costs.get(broker_type, broker_costs['discount'])

            # Calculate costs per trade (buy + sell)
            brokerage_buy = 0
            brokerage_sell = 0

            if broker_type == 'discount':
                brokerage_buy = min(20, avg_position_size * cost_structure['brokerage_percent'] / 100)
                brokerage_sell = min(20, avg_position_size * cost_structure['brokerage_percent'] / 100)
            else:
                brokerage_buy = avg_position_size * cost_structure['brokerage_percent'] / 100
                brokerage_sell = avg_position_size * cost_structure['brokerage_percent'] / 100

            # STT (only on sell side)
            stt = avg_position_size * cost_structure['stt_percent'] / 100

            # Exchange charges (both sides)
            exchange_charges = avg_position_size * cost_structure['exchange_charges_percent'] / 100 * 2

            # SEBI charges (both sides)
            sebi_charges = avg_position_size * cost_structure['sebi_charges_percent'] / 100 * 2

            # Stamp duty (only on buy side)
            stamp_duty = avg_position_size * cost_structure['stamp_duty_percent'] / 100

            # GST on brokerage + exchange charges
            taxable_amount = brokerage_buy + brokerage_sell + exchange_charges
            gst = taxable_amount * cost_structure['gst_percent'] / 100

            # Total cost per trade
            cost_per_trade = brokerage_buy + brokerage_sell + stt + exchange_charges + sebi_charges + stamp_duty + gst

            # Monthly costs
            monthly_brokerage = (brokerage_buy + brokerage_sell) * trade_frequency
            monthly_stt = stt * trade_frequency
            monthly_exchange_charges = exchange_charges * trade_frequency
            monthly_sebi_charges = sebi_charges * trade_frequency
            monthly_stamp_duty = stamp_duty * trade_frequency
            monthly_gst = gst * trade_frequency
            monthly_total = cost_per_trade * trade_frequency

            # Annual projection
            annual_total = monthly_total * 12

            # Calculate breakeven requirement
            breakeven_percent_per_trade = (cost_per_trade / avg_position_size) * 100

            # Calculate impact on returns (example scenarios)
            return_scenarios = []
            for return_percent in [1, 2, 3, 5, 10]:
                gross_profit = avg_position_size * return_percent / 100
                net_profit = gross_profit - cost_per_trade
                net_return_percent = (net_profit / avg_position_size) * 100

                return_scenarios.append({
                    'gross_return_percent': return_percent,
                    'gross_profit': round(gross_profit, 2),
                    'cost_per_trade': round(cost_per_trade, 2),
                    'net_profit': round(net_profit, 2),
                    'net_return_percent': round(net_return_percent, 2),
                    'cost_impact_percent': round(return_percent - net_return_percent, 2)
                })

            result = {
                'simulation_type': 'monthly_costs',
                'broker_type': cost_structure['name'],
                'trade_frequency': trade_frequency,
                'avg_position_size': avg_position_size,
                'cost_per_trade': round(cost_per_trade, 2),
                'cost_breakdown': {
                    'brokerage_buy': round(brokerage_buy, 2),
                    'brokerage_sell': round(brokerage_sell, 2),
                    'stt': round(stt, 2),
                    'exchange_charges': round(exchange_charges, 2),
                    'sebi_charges': round(sebi_charges, 2),
                    'stamp_duty': round(stamp_duty, 2),
                    'gst': round(gst, 2)
                },
                'monthly_costs': {
                    'total_brokerage': round(monthly_brokerage, 2),
                    'total_stt': round(monthly_stt, 2),
                    'total_exchange_charges': round(monthly_exchange_charges, 2),
                    'total_sebi_charges': round(monthly_sebi_charges, 2),
                    'total_stamp_duty': round(monthly_stamp_duty, 2),
                    'total_gst': round(monthly_gst, 2),
                    'total': round(monthly_total, 2)
                },
                'annual_projection': round(annual_total, 2),
                'breakeven_percent_per_trade': round(breakeven_percent_per_trade, 4),
                'return_scenarios': return_scenarios,
                'insights': [
                    f"You need at least {breakeven_percent_per_trade:.2f}% return per trade to break even",
                    f"Monthly trading costs: ₹{monthly_total:.2f} ({trade_frequency} trades)",
                    f"Annual projection: ₹{annual_total:.2f}"
                ]
            }

            return result

        except Exception as e:
            raise Exception(f"Error simulating monthly costs: {str(e)}")

    def simulate_risk_scenario(
        self,
        user_id: str,
        scenario_name: str,
        base_capital: float,
        scenario_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simulate what-if risk scenarios

        Args:
            user_id: User's ID
            scenario_name: Name of the scenario
            base_capital: Starting capital
            scenario_params: Scenario parameters (win_rate, avg_win, avg_loss, num_trades)

        Returns:
            Scenario simulation results
        """
        try:
            win_rate = scenario_params.get('win_rate', 50)  # percentage
            avg_win_percent = scenario_params.get('avg_win_percent', 2)
            avg_loss_percent = scenario_params.get('avg_loss_percent', 1)
            num_trades = scenario_params.get('num_trades', 100)
            risk_per_trade_percent = scenario_params.get('risk_per_trade_percent', 2)

            # Run simulation
            capital = base_capital
            capital_history = [capital]
            trade_results = []

            for i in range(num_trades):
                # Determine if trade wins or loses
                is_win = random.random() < (win_rate / 100)

                if is_win:
                    profit = capital * (avg_win_percent / 100)
                    capital += profit
                    trade_results.append({
                        'trade_num': i + 1,
                        'result': 'win',
                        'pnl': profit,
                        'capital_after': capital
                    })
                else:
                    loss = capital * (avg_loss_percent / 100)
                    capital -= loss
                    trade_results.append({
                        'trade_num': i + 1,
                        'result': 'loss',
                        'pnl': -loss,
                        'capital_after': capital
                    })

                capital_history.append(capital)

            # Calculate metrics
            final_capital = capital
            total_return = final_capital - base_capital
            total_return_percent = (total_return / base_capital) * 100

            max_capital = max(capital_history)
            max_drawdown = max([0] + [
                (max(capital_history[:i+1]) - capital_history[i]) / max(capital_history[:i+1]) * 100
                for i in range(1, len(capital_history))
            ])

            winning_trades = len([t for t in trade_results if t['result'] == 'win'])
            losing_trades = len([t for t in trade_results if t['result'] == 'loss'])
            actual_win_rate = (winning_trades / num_trades) * 100 if num_trades > 0 else 0

            result = {
                'simulation_type': 'risk_scenario',
                'scenario_name': scenario_name,
                'parameters': {
                    'base_capital': base_capital,
                    'win_rate': win_rate,
                    'avg_win_percent': avg_win_percent,
                    'avg_loss_percent': avg_loss_percent,
                    'num_trades': num_trades,
                    'risk_per_trade_percent': risk_per_trade_percent
                },
                'results': {
                    'final_capital': round(final_capital, 2),
                    'total_return': round(total_return, 2),
                    'total_return_percent': round(total_return_percent, 2),
                    'max_capital': round(max_capital, 2),
                    'max_drawdown_percent': round(max_drawdown, 2),
                    'winning_trades': winning_trades,
                    'losing_trades': losing_trades,
                    'actual_win_rate': round(actual_win_rate, 2)
                },
                'capital_curve': [round(c, 2) for c in capital_history[::max(1, len(capital_history)//50)]],  # Sample 50 points
                'insights': self._generate_scenario_insights(
                    total_return_percent,
                    max_drawdown,
                    actual_win_rate,
                    win_rate
                ),
                'simulated_at': datetime.now()
            }

            return result

        except Exception as e:
            raise Exception(f"Error simulating risk scenario: {str(e)}")

    def simulate_monte_carlo_drawdown(
        self,
        user_id: str,
        num_simulations: int = 1000,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Monte Carlo simulation for drawdown analysis

        Args:
            user_id: User's ID
            num_simulations: Number of Monte Carlo runs
            lookback_days: Days of historical data to use

        Returns:
            Monte Carlo simulation results
        """
        try:
            # Get historical trades
            start_date = datetime.now() - timedelta(days=lookback_days)
            trades = list(self.trades_collection.find({
                'user_id': user_id,
                'created_at': {'$gte': start_date},
                'exit_timestamp': {'$ne': None}
            }))

            if len(trades) < 10:
                return {
                    'message': 'Not enough historical trades for Monte Carlo simulation (minimum 10 required)',
                    'total_trades': len(trades)
                }

            # Extract PnL percentages
            pnl_percentages = []
            for trade in trades:
                pnl = trade.get('actual_pnl', 0)
                position_size = trade.get('position_size', trade.get('quantity', 1) * trade.get('entry_price', 1))
                if position_size > 0:
                    pnl_percent = (pnl / position_size) * 100
                    pnl_percentages.append(pnl_percent)

            if not pnl_percentages:
                return {'message': 'Could not calculate PnL percentages from historical trades'}

            # Get user settings
            settings = self.settings_collection.find_one({'user_id': user_id}) or {}
            capital_baseline = settings.get('capital_baseline', 100000)

            # Run Monte Carlo simulations
            max_drawdowns = []
            final_capitals = []

            for sim in range(num_simulations):
                capital = capital_baseline
                peak_capital = capital
                max_dd = 0

                # Simulate same number of trades as historical
                for _ in range(len(trades)):
                    # Randomly sample from historical PnL distribution
                    pnl_percent = random.choice(pnl_percentages)
                    capital += capital * (pnl_percent / 100)

                    # Track drawdown
                    peak_capital = max(peak_capital, capital)
                    if peak_capital > 0:
                        current_dd = ((peak_capital - capital) / peak_capital) * 100
                        max_dd = max(max_dd, current_dd)

                max_drawdowns.append(max_dd)
                final_capitals.append(capital)

            # Calculate statistics using numpy
            max_drawdowns_array = np.array(max_drawdowns)
            final_capitals_array = np.array(final_capitals)

            percentile_50 = float(np.percentile(max_drawdowns_array, 50))
            percentile_75 = float(np.percentile(max_drawdowns_array, 75))
            percentile_90 = float(np.percentile(max_drawdowns_array, 90))
            percentile_95 = float(np.percentile(max_drawdowns_array, 95))
            percentile_99 = float(np.percentile(max_drawdowns_array, 99))

            avg_drawdown = float(np.mean(max_drawdowns_array))
            worst_drawdown = float(np.max(max_drawdowns_array))
            best_drawdown = float(np.min(max_drawdowns_array))

            avg_final_capital = float(np.mean(final_capitals_array))
            avg_return_percent = ((avg_final_capital - capital_baseline) / capital_baseline) * 100

            result = {
                'simulation_type': 'monte_carlo_drawdown',
                'num_simulations': num_simulations,
                'historical_trades': len(trades),
                'lookback_days': lookback_days,
                'base_capital': capital_baseline,
                'drawdown_statistics': {
                    'average_max_drawdown_percent': round(avg_drawdown, 2),
                    'worst_case_drawdown_percent': round(worst_drawdown, 2),
                    'best_case_drawdown_percent': round(best_drawdown, 2),
                    'percentile_50_drawdown': round(percentile_50, 2),
                    'percentile_75_drawdown': round(percentile_75, 2),
                    'percentile_90_drawdown': round(percentile_90, 2),
                    'percentile_95_drawdown': round(percentile_95, 2),
                    'percentile_99_drawdown': round(percentile_99, 2)
                },
                'return_statistics': {
                    'avg_final_capital': round(avg_final_capital, 2),
                    'avg_return_percent': round(avg_return_percent, 2)
                },
                'risk_insights': [
                    f"50% chance of drawdown exceeding {percentile_50:.1f}%",
                    f"5% chance of drawdown exceeding {percentile_95:.1f}%",
                    f"Worst case scenario: {worst_drawdown:.1f}% drawdown",
                    f"Average expected return: {avg_return_percent:.1f}%"
                ],
                'simulated_at': datetime.now()
            }

            return result

        except Exception as e:
            raise Exception(f"Error in Monte Carlo simulation: {str(e)}")

    def save_simulation(
        self,
        user_id: str,
        simulation_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Save simulation results for future reference

        Args:
            user_id: User's ID
            simulation_data: Simulation results

        Returns:
            Saved simulation with ID
        """
        try:
            simulation = {
                'user_id': user_id,
                **simulation_data,
                'created_at': datetime.now()
            }

            result = self.simulations_collection.insert_one(simulation)
            simulation['_id'] = result.inserted_id

            return simulation

        except Exception as e:
            raise Exception(f"Error saving simulation: {str(e)}")

    def get_simulations(
        self,
        user_id: str,
        simulation_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get saved simulations

        Args:
            user_id: User's ID
            simulation_type: Filter by type (optional)
            limit: Maximum number of results

        Returns:
            List of saved simulations
        """
        try:
            query = {'user_id': user_id}

            if simulation_type:
                query['simulation_type'] = simulation_type

            simulations = list(self.simulations_collection.find(query)
                             .sort('created_at', -1)
                             .limit(limit))

            return simulations

        except Exception as e:
            raise Exception(f"Error getting simulations: {str(e)}")

    # Private helper methods

    def _generate_scenario_insights(
        self,
        return_percent: float,
        max_drawdown: float,
        actual_win_rate: float,
        expected_win_rate: float
    ) -> List[str]:
        """Generate insights from scenario simulation"""
        insights = []

        if return_percent > 20:
            insights.append(f"Strong performance: {return_percent:.1f}% return over simulation period")
        elif return_percent > 0:
            insights.append(f"Positive performance: {return_percent:.1f}% return")
        else:
            insights.append(f"Negative performance: {return_percent:.1f}% loss")

        if max_drawdown < 10:
            insights.append(f"Low risk: Maximum drawdown only {max_drawdown:.1f}%")
        elif max_drawdown < 20:
            insights.append(f"Moderate risk: Maximum drawdown {max_drawdown:.1f}%")
        else:
            insights.append(f"High risk: Maximum drawdown {max_drawdown:.1f}% - consider reducing position sizes")

        if abs(actual_win_rate - expected_win_rate) > 5:
            insights.append(f"Note: Actual win rate ({actual_win_rate:.1f}%) varied from expected ({expected_win_rate:.1f}%)")

        return insights


# Singleton instance
risk_phase6_service = RiskCalculatorPhase6Service()
