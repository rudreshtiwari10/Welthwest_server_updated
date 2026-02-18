"""
Simple Vectorized Backtest Engine - Fast strategy backtesting

Implements simple, fast, vectorized backtesting for common strategies:
- SMA Crossover (fast SMA crosses slow SMA)
- RSI Mean Reversion (buy oversold, sell overbought)
- EMA Crossover
- MACD Signal Crossover
- Bollinger Band Bounce

Features:
- Vectorized calculations for speed
- Commission and slippage modeling
- Comprehensive performance metrics
- Equity curve generation
- Trade log with entry/exit points
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
# yfinance imported lazily inside fetch_data to avoid slow startup
from services.indicators_service import IndicatorEngine

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleBacktestEngine:
    """
    Simple vectorized backtesting engine for common trading strategies
    """

    def __init__(self):
        self.indicator_engine = IndicatorEngine()

    def fetch_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch historical OHLCV data

        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date, end=end_date)

            if data.empty:
                raise ValueError(f"No data available for {symbol}")

            return data

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            raise

    def calculate_metrics(self, returns: pd.Series, equity_curve: pd.Series,
                         trades: List[Dict], initial_capital: float) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics

        Args:
            returns: Series of returns
            equity_curve: Portfolio value over time
            trades: List of trades
            initial_capital: Starting capital

        Returns:
            Dictionary of performance metrics
        """
        # Basic metrics
        total_return = ((equity_curve.iloc[-1] - initial_capital) / initial_capital) * 100
        num_trades = len([t for t in trades if t['type'] == 'buy'])

        # Calculate winning/losing trades
        winning_trades = [t for t in trades if t.get('profit', 0) > 0]
        losing_trades = [t for t in trades if t.get('profit', 0) < 0]

        win_rate = (len(winning_trades) / num_trades * 100) if num_trades > 0 else 0

        # Average profit/loss
        avg_win = np.mean([t['profit'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['profit'] for t in losing_trades]) if losing_trades else 0

        # Drawdown calculation
        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max * 100
        max_drawdown = drawdown.min()

        # Volatility and Sharpe ratio
        volatility = returns.std() * np.sqrt(252) * 100  # Annualized
        sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252)
        sortino_ratio = (returns.mean() * 252 / downside_std) if downside_std > 0 else 0

        # Profit factor
        total_wins = sum([t['profit'] for t in winning_trades]) if winning_trades else 0
        total_losses = abs(sum([t['profit'] for t in losing_trades])) if losing_trades else 0
        profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf')

        # Expectancy
        expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * abs(avg_loss))

        return {
            'total_return_pct': round(total_return, 2),
            'total_return_value': round(equity_curve.iloc[-1] - initial_capital, 2),
            'final_portfolio_value': round(equity_curve.iloc[-1], 2),
            'initial_capital': initial_capital,
            'num_trades': num_trades,
            'num_winning_trades': len(winning_trades),
            'num_losing_trades': len(losing_trades),
            'win_rate_pct': round(win_rate, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'volatility_pct': round(volatility, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'sortino_ratio': round(sortino_ratio, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 'inf',
            'expectancy': round(expectancy, 2)
        }

    def backtest_sma_crossover(self, symbol: str, start_date: str, end_date: str,
                               fast_period: int = 20, slow_period: int = 50,
                               initial_capital: float = 100000,
                               commission: float = 0.001,
                               slippage: float = 0.001) -> Dict[str, Any]:
        """
        Backtest SMA Crossover Strategy

        Buy Signal: Fast SMA crosses above Slow SMA
        Sell Signal: Fast SMA crosses below Slow SMA

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            fast_period: Fast SMA period
            slow_period: Slow SMA period
            initial_capital: Starting capital
            commission: Commission per trade (as decimal, e.g., 0.001 = 0.1%)
            slippage: Slippage per trade (as decimal)

        Returns:
            Backtest results with metrics and trades
        """
        try:
            # Fetch data
            data = self.fetch_data(symbol, start_date, end_date)
            close = data['Close']

            # Calculate SMAs
            sma_fast = close.rolling(window=fast_period).mean()
            sma_slow = close.rolling(window=slow_period).mean()

            # Generate signals (1 = long, 0 = cash, -1 = short)
            # Buy when fast crosses above slow
            signal = pd.Series(0, index=data.index)
            signal[sma_fast > sma_slow] = 1
            signal[sma_fast <= sma_slow] = 0

            # Calculate positions (when signal changes)
            positions = signal.diff()

            # Simulate trading
            portfolio_value = initial_capital
            cash = initial_capital
            shares = 0
            equity_curve = []
            trades = []

            for date, row in data.iterrows():
                current_price = row['Close']
                pos = positions.loc[date] if date in positions.index else 0

                # Buy signal
                if pos == 1 and cash > 0:
                    # Calculate shares to buy
                    cost_per_share = current_price * (1 + slippage + commission)
                    shares_to_buy = cash // cost_per_share
                    if shares_to_buy > 0:
                        total_cost = shares_to_buy * cost_per_share
                        cash -= total_cost
                        shares += shares_to_buy
                        trades.append({
                            'date': date.strftime('%Y-%m-%d'),
                            'type': 'buy',
                            'price': round(current_price, 2),
                            'shares': int(shares_to_buy),
                            'value': round(total_cost, 2)
                        })

                # Sell signal
                elif pos == -1 and shares > 0:
                    # Sell all shares
                    proceeds_per_share = current_price * (1 - slippage - commission)
                    total_proceeds = shares * proceeds_per_share
                    profit = total_proceeds - (shares * trades[-1]['price'])  # Approximate profit
                    cash += total_proceeds
                    trades.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'type': 'sell',
                        'price': round(current_price, 2),
                        'shares': int(shares),
                        'value': round(total_proceeds, 2),
                        'profit': round(profit, 2)
                    })
                    shares = 0

                # Calculate portfolio value
                portfolio_value = cash + (shares * current_price)
                equity_curve.append(portfolio_value)

            # Create equity curve series
            equity_series = pd.Series(equity_curve, index=data.index)

            # Calculate returns
            returns = equity_series.pct_change().fillna(0)

            # Calculate metrics
            metrics = self.calculate_metrics(returns, equity_series, trades, initial_capital)

            return {
                'strategy': 'SMA Crossover',
                'symbol': symbol,
                'start_date': start_date,
                'end_date': end_date,
                'parameters': {
                    'fast_sma': fast_period,
                    'slow_sma': slow_period,
                    'initial_capital': initial_capital,
                    'commission': commission * 100,
                    'slippage': slippage * 100
                },
                'metrics': metrics,
                'equity_curve': {
                    'dates': equity_series.index.strftime('%Y-%m-%d').tolist(),
                    'values': equity_series.round(2).tolist()
                },
                'trades': trades,
                'chart_data': {
                    'dates': data.index.strftime('%Y-%m-%d').tolist(),
                    'close': close.round(2).tolist(),
                    'sma_fast': sma_fast.round(2).tolist(),
                    'sma_slow': sma_slow.round(2).tolist()
                }
            }

        except Exception as e:
            logger.error(f"Error in SMA crossover backtest: {str(e)}")
            return {'error': str(e)}

    def backtest_rsi_strategy(self, symbol: str, start_date: str, end_date: str,
                             rsi_period: int = 14, oversold: int = 30, overbought: int = 70,
                             initial_capital: float = 100000,
                             commission: float = 0.001,
                             slippage: float = 0.001) -> Dict[str, Any]:
        """
        Backtest RSI Mean Reversion Strategy

        Buy Signal: RSI < oversold threshold
        Sell Signal: RSI > overbought threshold

        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            rsi_period: RSI calculation period
            oversold: Oversold threshold
            overbought: Overbought threshold
            initial_capital: Starting capital
            commission: Commission per trade
            slippage: Slippage per trade

        Returns:
            Backtest results
        """
        try:
            # Fetch data
            data = self.fetch_data(symbol, start_date, end_date)
            close = data['Close']

            # Calculate RSI
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # Generate signals
            signal = pd.Series(0, index=data.index)
            signal[rsi < oversold] = 1  # Buy signal
            signal[rsi > overbought] = -1  # Sell signal

            # Track position state
            in_position = False
            portfolio_value = initial_capital
            cash = initial_capital
            shares = 0
            equity_curve = []
            trades = []

            for date, row in data.iterrows():
                current_price = row['Close']
                current_signal = signal.loc[date] if date in signal.index else 0

                # Buy signal and not in position
                if current_signal == 1 and not in_position and cash > 0:
                    cost_per_share = current_price * (1 + slippage + commission)
                    shares_to_buy = cash // cost_per_share
                    if shares_to_buy > 0:
                        total_cost = shares_to_buy * cost_per_share
                        cash -= total_cost
                        shares += shares_to_buy
                        in_position = True
                        entry_price = current_price
                        trades.append({
                            'date': date.strftime('%Y-%m-%d'),
                            'type': 'buy',
                            'price': round(current_price, 2),
                            'shares': int(shares_to_buy),
                            'value': round(total_cost, 2)
                        })

                # Sell signal and in position
                elif current_signal == -1 and in_position and shares > 0:
                    proceeds_per_share = current_price * (1 - slippage - commission)
                    total_proceeds = shares * proceeds_per_share
                    profit = (current_price - entry_price) * shares - (shares * current_price * (commission + slippage) * 2)
                    cash += total_proceeds
                    trades.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'type': 'sell',
                        'price': round(current_price, 2),
                        'shares': int(shares),
                        'value': round(total_proceeds, 2),
                        'profit': round(profit, 2)
                    })
                    shares = 0
                    in_position = False

                # Calculate portfolio value
                portfolio_value = cash + (shares * current_price)
                equity_curve.append(portfolio_value)

            # Create equity curve series
            equity_series = pd.Series(equity_curve, index=data.index)
            returns = equity_series.pct_change().fillna(0)

            # Calculate metrics
            metrics = self.calculate_metrics(returns, equity_series, trades, initial_capital)

            return {
                'strategy': 'RSI Mean Reversion',
                'symbol': symbol,
                'start_date': start_date,
                'end_date': end_date,
                'parameters': {
                    'rsi_period': rsi_period,
                    'oversold': oversold,
                    'overbought': overbought,
                    'initial_capital': initial_capital,
                    'commission': commission * 100,
                    'slippage': slippage * 100
                },
                'metrics': metrics,
                'equity_curve': {
                    'dates': equity_series.index.strftime('%Y-%m-%d').tolist(),
                    'values': equity_series.round(2).tolist()
                },
                'trades': trades,
                'chart_data': {
                    'dates': data.index.strftime('%Y-%m-%d').tolist(),
                    'close': close.round(2).tolist(),
                    'rsi': rsi.round(2).tolist()
                }
            }

        except Exception as e:
            logger.error(f"Error in RSI backtest: {str(e)}")
            return {'error': str(e)}

    def backtest_ema_crossover(self, symbol: str, start_date: str, end_date: str,
                               fast_period: int = 12, slow_period: int = 26,
                               initial_capital: float = 100000,
                               commission: float = 0.001,
                               slippage: float = 0.001) -> Dict[str, Any]:
        """
        Backtest EMA Crossover Strategy

        Buy Signal: Fast EMA crosses above Slow EMA
        Sell Signal: Fast EMA crosses below Slow EMA
        """
        try:
            # Fetch data
            data = self.fetch_data(symbol, start_date, end_date)
            close = data['Close']

            # Calculate EMAs
            ema_fast = close.ewm(span=fast_period, adjust=False).mean()
            ema_slow = close.ewm(span=slow_period, adjust=False).mean()

            # Generate signals
            signal = pd.Series(0, index=data.index)
            signal[ema_fast > ema_slow] = 1
            signal[ema_fast <= ema_slow] = 0

            # Calculate positions
            positions = signal.diff()

            # Simulate trading (similar to SMA crossover)
            portfolio_value = initial_capital
            cash = initial_capital
            shares = 0
            equity_curve = []
            trades = []

            for date, row in data.iterrows():
                current_price = row['Close']
                pos = positions.loc[date] if date in positions.index else 0

                if pos == 1 and cash > 0:
                    cost_per_share = current_price * (1 + slippage + commission)
                    shares_to_buy = cash // cost_per_share
                    if shares_to_buy > 0:
                        total_cost = shares_to_buy * cost_per_share
                        cash -= total_cost
                        shares += shares_to_buy
                        trades.append({
                            'date': date.strftime('%Y-%m-%d'),
                            'type': 'buy',
                            'price': round(current_price, 2),
                            'shares': int(shares_to_buy),
                            'value': round(total_cost, 2)
                        })

                elif pos == -1 and shares > 0:
                    proceeds_per_share = current_price * (1 - slippage - commission)
                    total_proceeds = shares * proceeds_per_share
                    profit = total_proceeds - (shares * trades[-1]['price'])
                    cash += total_proceeds
                    trades.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'type': 'sell',
                        'price': round(current_price, 2),
                        'shares': int(shares),
                        'value': round(total_proceeds, 2),
                        'profit': round(profit, 2)
                    })
                    shares = 0

                portfolio_value = cash + (shares * current_price)
                equity_curve.append(portfolio_value)

            equity_series = pd.Series(equity_curve, index=data.index)
            returns = equity_series.pct_change().fillna(0)
            metrics = self.calculate_metrics(returns, equity_series, trades, initial_capital)

            return {
                'strategy': 'EMA Crossover',
                'symbol': symbol,
                'start_date': start_date,
                'end_date': end_date,
                'parameters': {
                    'fast_ema': fast_period,
                    'slow_ema': slow_period,
                    'initial_capital': initial_capital,
                    'commission': commission * 100,
                    'slippage': slippage * 100
                },
                'metrics': metrics,
                'equity_curve': {
                    'dates': equity_series.index.strftime('%Y-%m-%d').tolist(),
                    'values': equity_series.round(2).tolist()
                },
                'trades': trades,
                'chart_data': {
                    'dates': data.index.strftime('%Y-%m-%d').tolist(),
                    'close': close.round(2).tolist(),
                    'ema_fast': ema_fast.round(2).tolist(),
                    'ema_slow': ema_slow.round(2).tolist()
                }
            }

        except Exception as e:
            logger.error(f"Error in EMA crossover backtest: {str(e)}")
            return {'error': str(e)}


# Singleton instance
simple_backtest_engine = SimpleBacktestEngine()


# Helper functions
def run_backtest(strategy: str, symbol: str, start_date: str, end_date: str,
                **kwargs) -> Dict[str, Any]:
    """
    Run a backtest for a specific strategy

    Args:
        strategy: Strategy name (sma_crossover, rsi, ema_crossover)
        symbol: Stock symbol
        start_date: Start date
        end_date: End date
        **kwargs: Strategy-specific parameters

    Returns:
        Backtest results
    """
    strategies = {
        'sma_crossover': simple_backtest_engine.backtest_sma_crossover,
        'rsi': simple_backtest_engine.backtest_rsi_strategy,
        'ema_crossover': simple_backtest_engine.backtest_ema_crossover
    }

    if strategy not in strategies:
        return {
            'error': f'Unknown strategy: {strategy}',
            'available_strategies': list(strategies.keys())
        }

    return strategies[strategy](symbol, start_date, end_date, **kwargs)
