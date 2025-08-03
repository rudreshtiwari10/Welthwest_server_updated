# Indian Stock Market Strategy Builder with Backtesting
# Run this in Google Colab

# Install required packages
!pip install yfinance ta plotly pandas numpy matplotlib seaborn -q

import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import ta
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator
import warnings
warnings.filterwarnings('ignore')

# Set up plotting style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

class IndianStockStrategyBuilder:
    def __init__(self):
        self.indicators_config = {
            'ema': {'name': 'EMA/SMA', 'category': 'trend'},
            'macd': {'name': 'MACD', 'category': 'trend'},
            'rsi': {'name': 'RSI', 'category': 'momentum'},
            'stochastic': {'name': 'Stochastic', 'category': 'momentum'},
            'bb': {'name': 'Bollinger Bands', 'category': 'volatility'},
            'atr': {'name': 'ATR', 'category': 'volatility'},
            'obv': {'name': 'OBV', 'category': 'volume'},
            'vwap': {'name': 'VWAP', 'category': 'volume'}
        }
        
    def fetch_stock_data(self, symbol, period='1y', interval='1d'):
        """Fetch stock data from Yahoo Finance"""
        # Add .NS for NSE stocks
        if not symbol.endswith('.NS'):
            symbol = symbol + '.NS'
        
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period=period, interval=interval)
            df.reset_index(inplace=True)
            return df
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None
    
    def calculate_indicators(self, df, selected_indicators):
        """Calculate selected technical indicators"""
        df = df.copy()
        
        # EMA/SMA
        if 'ema' in selected_indicators:
            df['EMA_20'] = EMAIndicator(close=df['Close'], window=20).ema_indicator()
            df['SMA_50'] = SMAIndicator(close=df['Close'], window=50).sma_indicator()
            df['EMA_Signal'] = np.where(df['Close'] > df['EMA_20'], 1, -1)
        
        # MACD
        if 'macd' in selected_indicators:
            macd = MACD(close=df['Close'])
            df['MACD'] = macd.macd()
            df['MACD_Signal'] = macd.macd_signal()
            df['MACD_Buy'] = np.where(df['MACD'] > df['MACD_Signal'], 1, -1)
        
        # RSI
        if 'rsi' in selected_indicators:
            df['RSI'] = RSIIndicator(close=df['Close']).rsi()
            df['RSI_Signal'] = np.where((df['RSI'] > 30) & (df['RSI'] < 70), 
                                       np.where(df['RSI'] < 50, 1, -1), 0)
        
        # Stochastic
        if 'stochastic' in selected_indicators:
            stoch = StochasticOscillator(high=df['High'], low=df['Low'], close=df['Close'])
            df['Stoch_K'] = stoch.stoch()
            df['Stoch_D'] = stoch.stoch_signal()
            df['Stoch_Signal'] = np.where((df['Stoch_K'] > df['Stoch_D']) & (df['Stoch_K'] < 20), 1,
                                         np.where((df['Stoch_K'] < df['Stoch_D']) & (df['Stoch_K'] > 80), -1, 0))
        
        # Bollinger Bands
        if 'bb' in selected_indicators:
            bb = BollingerBands(close=df['Close'])
            df['BB_High'] = bb.bollinger_hband()
            df['BB_Low'] = bb.bollinger_lband()
            df['BB_Mid'] = bb.bollinger_mavg()
            df['BB_Signal'] = np.where(df['Close'] <= df['BB_Low'], 1,
                                      np.where(df['Close'] >= df['BB_High'], -1, 0))
        
        # ATR (for stop loss calculation)
        if 'atr' in selected_indicators:
            df['ATR'] = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close']).average_true_range()
        
        # OBV
        if 'obv' in selected_indicators:
            df['OBV'] = OnBalanceVolumeIndicator(close=df['Close'], volume=df['Volume']).on_balance_volume()
            df['OBV_EMA'] = df['OBV'].ewm(span=20).mean()
            df['OBV_Signal'] = np.where(df['OBV'] > df['OBV_EMA'], 1, -1)
        
        # VWAP
        if 'vwap' in selected_indicators:
            df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()
            df['VWAP_Signal'] = np.where(df['Close'] > df['VWAP'], 1, -1)
        
        return df
    
    def generate_voting_signals(self, df, selected_indicators, voting_threshold=60):
        """Generate buy/sell signals based on voting system"""
        signal_columns = [col for col in df.columns if col.endswith('_Signal') or col.endswith('_Buy')]
        
        if not signal_columns:
            return df
        
        # Calculate voting score
        df['Vote_Score'] = df[signal_columns].sum(axis=1)
        df['Vote_Percentage'] = (df['Vote_Score'] / len(signal_columns)) * 100
        
        # Generate signals based on voting threshold
        df['Signal'] = 0
        df.loc[df['Vote_Percentage'] >= voting_threshold, 'Signal'] = 1  # Buy
        df.loc[df['Vote_Percentage'] <= -voting_threshold, 'Signal'] = -1  # Sell
        
        return df
    
    def backtest_strategy(self, df, initial_capital=100000, position_size_pct=10, 
                         risk_reward_ratio=2, max_drawdown_pct=10):
        """Backtest the trading strategy"""
        df = df.copy()
        
        # Initialize tracking variables
        capital = initial_capital
        position = 0
        trades = []
        equity_curve = []
        
        # Calculate position size
        position_value = capital * (position_size_pct / 100)
        
        for i in range(1, len(df)):
            current_price = df.loc[i, 'Close']
            signal = df.loc[i, 'Signal']
            
            # Entry logic
            if signal == 1 and position == 0:  # Buy signal
                shares = int(position_value / current_price)
                if shares > 0:
                    position = shares
                    entry_price = current_price
                    
                    # Calculate stop loss and take profit
                    if 'ATR' in df.columns:
                        atr = df.loc[i, 'ATR']
                        stop_loss = entry_price - (2 * atr)
                        take_profit = entry_price + (risk_reward_ratio * 2 * atr)
                    else:
                        stop_loss = entry_price * 0.98  # 2% stop loss
                        take_profit = entry_price * (1 + (0.02 * risk_reward_ratio))
                    
                    capital -= shares * current_price
                    
                    trades.append({
                        'Date': df.loc[i, 'Date'],
                        'Type': 'BUY',
                        'Price': current_price,
                        'Shares': shares,
                        'Value': shares * current_price
                    })
            
            # Exit logic
            elif position > 0:
                exit_trade = False
                exit_reason = ''
                
                # Check stop loss
                if current_price <= stop_loss:
                    exit_trade = True
                    exit_reason = 'Stop Loss'
                
                # Check take profit
                elif current_price >= take_profit:
                    exit_trade = True
                    exit_reason = 'Take Profit'
                
                # Check sell signal
                elif signal == -1:
                    exit_trade = True
                    exit_reason = 'Sell Signal'
                
                if exit_trade:
                    capital += position * current_price
                    pnl = (current_price - entry_price) * position
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                    
                    trades.append({
                        'Date': df.loc[i, 'Date'],
                        'Type': 'SELL',
                        'Price': current_price,
                        'Shares': position,
                        'Value': position * current_price,
                        'PnL': pnl,
                        'PnL_Pct': pnl_pct,
                        'Exit_Reason': exit_reason
                    })
                    
                    position = 0
            
            # Calculate equity
            current_equity = capital + (position * current_price if position > 0 else 0)
            equity_curve.append({
                'Date': df.loc[i, 'Date'],
                'Equity': current_equity,
                'Drawdown': ((current_equity - initial_capital) / initial_capital) * 100
            })
        
        # Create results summary
        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_curve)
        
        # Calculate performance metrics
        if len(trades_df) > 0:
            winning_trades = trades_df[trades_df['PnL'] > 0] if 'PnL' in trades_df.columns else pd.DataFrame()
            losing_trades = trades_df[trades_df['PnL'] < 0] if 'PnL' in trades_df.columns else pd.DataFrame()
            
            metrics = {
                'Total Trades': len(trades_df[trades_df['Type'] == 'SELL']),
                'Winning Trades': len(winning_trades),
                'Losing Trades': len(losing_trades),
                'Win Rate': (len(winning_trades) / len(trades_df[trades_df['Type'] == 'SELL']) * 100) if len(trades_df[trades_df['Type'] == 'SELL']) > 0 else 0,
                'Total PnL': trades_df['PnL'].sum() if 'PnL' in trades_df.columns else 0,
                'Average Win': winning_trades['PnL'].mean() if len(winning_trades) > 0 else 0,
                'Average Loss': losing_trades['PnL'].mean() if len(losing_trades) > 0 else 0,
                'Max Drawdown': equity_df['Drawdown'].min(),
                'Final Equity': equity_df['Equity'].iloc[-1] if len(equity_df) > 0 else initial_capital,
                'Return %': ((equity_df['Equity'].iloc[-1] - initial_capital) / initial_capital * 100) if len(equity_df) > 0 else 0
            }
        else:
            metrics = {
                'Total Trades': 0,
                'Winning Trades': 0,
                'Losing Trades': 0,
                'Win Rate': 0,
                'Total PnL': 0,
                'Average Win': 0,
                'Average Loss': 0,
                'Max Drawdown': 0,
                'Final Equity': initial_capital,
                'Return %': 0
            }
        
        return trades_df, equity_df, metrics
    
    def plot_backtest_results(self, df, trades_df, equity_df, selected_indicators):
        """Plot candlestick chart with buy/sell signals and indicators"""
        # Create subplots
        fig = make_subplots(rows=3, cols=1, 
                           shared_xaxes=True,
                           vertical_spacing=0.03,
                           row_heights=[0.6, 0.2, 0.2],
                           subplot_titles=('Price Action with Signals', 'Indicators', 'Equity Curve'))
        
        # Candlestick chart
        fig.add_trace(go.Candlestick(x=df['Date'],
                                    open=df['Open'],
                                    high=df['High'],
                                    low=df['Low'],
                                    close=df['Close'],
                                    name='Price'),
                     row=1, col=1)
        
        # Add buy/sell signals
        buy_signals = trades_df[trades_df['Type'] == 'BUY']
        sell_signals = trades_df[trades_df['Type'] == 'SELL']
        
        if len(buy_signals) > 0:
            fig.add_trace(go.Scatter(x=buy_signals['Date'], 
                                   y=buy_signals['Price'],
                                   mode='markers',
                                   marker=dict(symbol='triangle-up', size=15, color='green'),
                                   name='Buy Signal'),
                         row=1, col=1)
        
        if len(sell_signals) > 0:
            fig.add_trace(go.Scatter(x=sell_signals['Date'], 
                                   y=sell_signals['Price'],
                                   mode='markers',
                                   marker=dict(symbol='triangle-down', size=15, color='red'),
                                   name='Sell Signal'),
                         row=1, col=1)
        
        # Add selected indicators
        if 'ema' in selected_indicators and 'EMA_20' in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA_20'], 
                                   name='EMA 20', line=dict(color='blue', width=1)),
                         row=1, col=1)
        
        if 'bb' in selected_indicators and 'BB_High' in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['BB_High'], 
                                   name='BB Upper', line=dict(color='gray', width=1, dash='dash')),
                         row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Date'], y=df['BB_Low'], 
                                   name='BB Lower', line=dict(color='gray', width=1, dash='dash')),
                         row=1, col=1)
        
        # Add RSI if selected
        if 'rsi' in selected_indicators and 'RSI' in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['RSI'], 
                                   name='RSI', line=dict(color='purple')),
                         row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        
        # Add voting score
        if 'Vote_Percentage' in df.columns:
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Vote_Percentage'], 
                                   name='Vote %', line=dict(color='orange')),
                         row=2, col=1)
        
        # Add equity curve
        if len(equity_df) > 0:
            fig.add_trace(go.Scatter(x=equity_df['Date'], y=equity_df['Equity'], 
                                   name='Equity', line=dict(color='green', width=2)),
                         row=3, col=1)
        
        # Update layout
        fig.update_layout(height=1000, 
                         title='Backtest Results - Indian Stock Strategy',
                         xaxis_rangeslider_visible=False,
                         showlegend=True)
        
        fig.update_xaxes(title_text="Date", row=3, col=1)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Value", row=2, col=1)
        fig.update_yaxes(title_text="Equity", row=3, col=1)
        
        return fig
    
    def display_metrics(self, metrics, trades_df):
        """Display performance metrics"""
        print("\n" + "="*50)
        print("BACKTEST PERFORMANCE METRICS")
        print("="*50)
        
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"{key:.<30} {value:>15.2f}")
            else:
                print(f"{key:.<30} {value:>15}")
        
        print("\n" + "="*50)
        print("TRADE SUMMARY")
        print("="*50)
        
        if len(trades_df) > 0:
            print("\nRecent Trades:")
            print(trades_df.tail(10).to_string(index=False))
    
    def monte_carlo_analysis(self, trades_df, initial_capital, num_simulations=1000, confidence_level=0.95):
        """
        Perform Monte Carlo simulation by randomly reshuffling the trade sequence
        to estimate the range of possible outcomes.
        
        Parameters:
        -----------
        trades_df : pandas DataFrame
            DataFrame containing trade history with PnL values
        initial_capital : float
            Starting capital amount
        num_simulations : int
            Number of Monte Carlo simulations to run
        confidence_level : float
            Confidence level for calculating intervals (0-1)
            
        Returns:
        --------
        tuple : (monte_carlo_stats, monte_carlo_results)
            Statistics and detailed results of the simulations
        """
        if len(trades_df) == 0 or 'PnL' not in trades_df.columns:
            print("No trades available for Monte Carlo simulation")
            return None, None
        
        # Extract only completed trades (SELL trades with PnL)
        completed_trades = trades_df[trades_df['Type'] == 'SELL'].copy()
        if len(completed_trades) == 0:
            print("No completed trades available for Monte Carlo simulation")
            return None, None
        
        # Prepare for simulation
        pnl_values = completed_trades['PnL'].values
        simulation_results = []
        
        # Run simulations
        for i in range(num_simulations):
            # Randomly reshuffle the sequence of trades
            np.random.shuffle(pnl_values)
            
            # Calculate equity curve
            equity = initial_capital + np.cumsum(pnl_values)
            
            # Calculate drawdown
            max_equity = np.maximum.accumulate(equity)
            drawdown = (equity - max_equity) / max_equity * 100
            
            # Store results
            simulation_results.append({
                'final_equity': equity[-1],
                'return_pct': (equity[-1] - initial_capital) / initial_capital * 100,
                'max_drawdown': np.min(drawdown),
                'equity_curve': equity
            })
        
        # Convert results to DataFrame
        results_df = pd.DataFrame(simulation_results)
        
        # Calculate statistics
        conf_lower = (1 - confidence_level) / 2
        conf_upper = 1 - conf_lower
        
        stats = {
            'mean_return': results_df['return_pct'].mean(),
            'median_return': results_df['return_pct'].median(),
            'min_return': results_df['return_pct'].min(),
            'max_return': results_df['return_pct'].max(),
            'mean_drawdown': results_df['max_drawdown'].mean(),
            'worst_drawdown': results_df['max_drawdown'].min(),
            'conf_lower': results_df['return_pct'].quantile(conf_lower),
            'conf_upper': results_df['return_pct'].quantile(conf_upper),
            'probability_profit': (results_df['return_pct'] > 0).mean() * 100,
            'probability_loss': (results_df['return_pct'] < 0).mean() * 100,
        }
        
        # Plot Monte Carlo simulation results
        plt.figure(figsize=(15, 10))
        
        # Plot 1: Equity Curves
        plt.subplot(2, 2, 1)
        # Plot a sample of equity curves (e.g., 100) to avoid overcrowding
        sample_size = min(100, num_simulations)
        sample_indices = np.random.choice(num_simulations, sample_size, replace=False)
        
        for idx in sample_indices:
            plt.plot(simulation_results[idx]['equity_curve'], alpha=0.1, color='blue')
        
        # Plot mean equity curve
        mean_equity = np.mean([sim['equity_curve'] for sim in simulation_results], axis=0)
        plt.plot(mean_equity, linewidth=2, color='black', label='Mean')
        
        plt.xlabel('Trade Number')
        plt.ylabel('Equity')
        plt.title('Monte Carlo Simulation - Equity Curves')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Plot 2: Final Equity Distribution
        plt.subplot(2, 2, 2)
        plt.hist(results_df['final_equity'], bins=50, alpha=0.7, color='skyblue', edgecolor='black')
        plt.axvline(x=initial_capital, color='red', linestyle='--', label='Initial Capital')
        plt.axvline(x=results_df['final_equity'].quantile(conf_lower), color='orange', linestyle='--', 
                    label=f'{conf_lower*100:.1f}% Percentile')
        plt.axvline(x=results_df['final_equity'].quantile(conf_upper), color='green', linestyle='--', 
                    label=f'{conf_upper*100:.1f}% Percentile')
        plt.xlabel('Final Equity')
        plt.ylabel('Frequency')
        plt.title('Distribution of Final Equity')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Plot 3: Return Distribution
        plt.subplot(2, 2, 3)
        plt.hist(results_df['return_pct'], bins=50, alpha=0.7, color='lightgreen', edgecolor='black')
        plt.axvline(x=0, color='red', linestyle='--', label='Break Even')
        plt.axvline(x=results_df['return_pct'].mean(), color='blue', linestyle='--', label='Mean Return')
        plt.xlabel('Return (%)')
        plt.ylabel('Frequency')
        plt.title('Distribution of Returns')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Plot 4: Drawdown Distribution
        plt.subplot(2, 2, 4)
        plt.hist(results_df['max_drawdown'], bins=50, alpha=0.7, color='salmon', edgecolor='black')
        plt.axvline(x=results_df['max_drawdown'].mean(), color='red', linestyle='--', label='Mean Max Drawdown')
        plt.xlabel('Maximum Drawdown (%)')
        plt.ylabel('Frequency')
        plt.title('Distribution of Maximum Drawdowns')
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        plt.tight_layout()
        plt.show()
        
        # Print statistics
        print("\n" + "="*50)
        print("MONTE CARLO SIMULATION RESULTS")
        print("="*50)
        print(f"Number of Simulations: {num_simulations}")
        print(f"Confidence Level: {confidence_level*100}%")
        print(f"Mean Return: {stats['mean_return']:.2f}%")
        print(f"Median Return: {stats['median_return']:.2f}%")
        print(f"Min Return: {stats['min_return']:.2f}%")
        print(f"Max Return: {stats['max_return']:.2f}%")
        print(f"Return Range ({confidence_level*100}% CI): [{stats['conf_lower']:.2f}% to {stats['conf_upper']:.2f}%]")
        print(f"Mean Maximum Drawdown: {stats['mean_drawdown']:.2f}%")
        print(f"Worst Drawdown: {stats['worst_drawdown']:.2f}%")
        print(f"Probability of Profit: {stats['probability_profit']:.2f}%")
        print(f"Probability of Loss: {stats['probability_loss']:.2f}%")
        
        return stats, results_df

# Example usage
def run_backtest():
    # User inputs - Modify these parameters
    strategy_params = {
        'stock_symbol': 'RELIANCE',  # Indian stock symbol
        'selected_indicators': ['ema', 'bb', 'macd'],  # Select multiple indicators
        'timeframe': '1d',  # 1d, 1h, 15m, 5m
        'period': '6mo',  # 1mo, 3mo, 6mo, 1y, 2y
        'voting_threshold': 50,  # Percentage of indicators needed to agree (0-100)
        'risk_reward_ratio': 2,  # Risk:Reward ratio
        'position_size_pct': 10,  # Percentage of capital per trade
        'initial_capital': 100000,  # Starting capital in INR
        'max_drawdown_pct': 10  # Maximum allowed drawdown percentage
    }
    
    # Initialize strategy builder
    strategy = IndianStockStrategyBuilder()
    
    # Fetch stock data
    print(f"Fetching data for {strategy_params['stock_symbol']}...")
    df = strategy.fetch_stock_data(
        symbol=strategy_params['stock_symbol'],
        period=strategy_params['period'],
        interval=strategy_params['timeframe']
    )
    
    if df is None or len(df) == 0:
        print("Failed to fetch stock data!")
        return
    
    print(f"Data fetched: {len(df)} records from {df['Date'].min()} to {df['Date'].max()}")
    
    # Calculate indicators
    print("\nCalculating indicators...")
    df = strategy.calculate_indicators(df, strategy_params['selected_indicators'])
    
    # Generate voting signals
    print("Generating trading signals...")
    df = strategy.generate_voting_signals(
        df, 
        strategy_params['selected_indicators'],
        strategy_params['voting_threshold']
    )
    
    # Run backtest
    print("\nRunning backtest...")
    trades_df, equity_df, metrics = strategy.backtest_strategy(
        df,
        initial_capital=strategy_params['initial_capital'],
        position_size_pct=strategy_params['position_size_pct'],
        risk_reward_ratio=strategy_params['risk_reward_ratio'],
        max_drawdown_pct=strategy_params['max_drawdown_pct']
    )
    
    # Display results
    strategy.display_metrics(metrics, trades_df)
    
    # Plot results
    print("\nGenerating charts...")
    fig = strategy.plot_backtest_results(
        df, trades_df, equity_df, 
        strategy_params['selected_indicators']
    )
    fig.show()
    
    # Additional analysis plots
    if len(trades_df[trades_df['Type'] == 'SELL']) > 0:
        plt.figure(figsize=(15, 10))
        
        # Plot 1: PnL Distribution
        plt.subplot(2, 2, 1)
        sell_trades = trades_df[trades_df['Type'] == 'SELL']
        if 'PnL' in sell_trades.columns:
            plt.hist(sell_trades['PnL'], bins=20, alpha=0.7, color='skyblue', edgecolor='black')
            plt.axvline(x=0, color='red', linestyle='--', alpha=0.7)
            plt.xlabel('Profit/Loss (INR)')
            plt.ylabel('Frequency')
            plt.title('PnL Distribution')
            plt.grid(True, alpha=0.3)
        
        # Plot 2: Win Rate by Exit Reason
        plt.subplot(2, 2, 2)
        if 'Exit_Reason' in sell_trades.columns:
            exit_summary = sell_trades.groupby('Exit_Reason')['PnL'].agg(['count', 'sum', 'mean'])
            exit_summary.plot(kind='bar', y='count', ax=plt.gca(), alpha=0.7, color='lightcoral')
            plt.xlabel('Exit Reason')
            plt.ylabel('Number of Trades')
            plt.title('Trades by Exit Reason')
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
        
        # Plot 3: Cumulative PnL
        plt.subplot(2, 2, 3)
        if 'PnL' in sell_trades.columns:
            cumulative_pnl = sell_trades['PnL'].cumsum()
            plt.plot(range(len(cumulative_pnl)), cumulative_pnl, linewidth=2, color='green')
            plt.fill_between(range(len(cumulative_pnl)), 0, cumulative_pnl, alpha=0.3, color='green')
            plt.xlabel('Trade Number')
            plt.ylabel('Cumulative PnL (INR)')
            plt.title('Cumulative Profit/Loss')
            plt.grid(True, alpha=0.3)
        
        # Plot 4: Monthly Returns
        plt.subplot(2, 2, 4)
        if len(equity_df) > 0:
            equity_df['Date'] = pd.to_datetime(equity_df['Date'])
            equity_df.set_index('Date', inplace=True)
            monthly_returns = equity_df['Equity'].resample('M').last().pct_change() * 100
            monthly_returns.dropna().plot(kind='bar', alpha=0.7, color='lightgreen')
            plt.xlabel('Month')
            plt.ylabel('Return (%)')
            plt.title('Monthly Returns')
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()
    
    # Signal Analysis
    print("\n" + "="*50)
    print("SIGNAL ANALYSIS")
    print("="*50)
    
    signal_counts = df['Signal'].value_counts()
    print(f"Buy Signals: {signal_counts.get(1, 0)}")
    print(f"Sell Signals: {signal_counts.get(-1, 0)}")
    print(f"Neutral: {signal_counts.get(0, 0)}")
    
    # Indicator contribution
    print("\nIndicator Voting Distribution:")
    if 'Vote_Percentage' in df.columns:
        vote_dist = df['Vote_Percentage'].describe()
        print(vote_dist)
    
    return df, trades_df, equity_df, metrics

def run_advanced_backtest():
    # User inputs - Modify these parameters
    strategy_params = {
        'stock_symbol': 'RELIANCE',  # Indian stock symbol
        'selected_indicators': ['ema', 'bb', 'macd', 'rsi'],  # Select multiple indicators
        'timeframe': '1d',  # 1d, 1h, 15m, 5m
        'period': '1y',  # 1mo, 3mo, 6mo, 1y, 2y
        'voting_threshold': 50,  # Percentage of indicators needed to agree (0-100)
        'risk_reward_ratio': 2,  # Risk:Reward ratio
        'position_size_pct': 10,  # Percentage of capital per trade
        'initial_capital': 100000,  # Starting capital in INR
        'max_drawdown_pct': 10,  # Maximum allowed drawdown percentage
        'monte_carlo_simulations': 1000,  # Number of Monte Carlo simulations
        'confidence_level': 0.95  # Confidence level for Monte Carlo analysis
    }
    
    # Initialize strategy builder
    strategy = IndianStockStrategyBuilder()
    
    # Fetch stock data
    print(f"Fetching data for {strategy_params['stock_symbol']}...")
    df = strategy.fetch_stock_data(
        symbol=strategy_params['stock_symbol'],
        period=strategy_params['period'],
        interval=strategy_params['timeframe']
    )
    
    if df is None or len(df) == 0:
        print("Failed to fetch stock data!")
        return
    
    print(f"Data fetched: {len(df)} records from {df['Date'].min()} to {df['Date'].max()}")
    
    # Calculate indicators
    print("\nCalculating indicators...")
    df = strategy.calculate_indicators(df, strategy_params['selected_indicators'])
    
    # Generate voting signals
    print("Generating trading signals...")
    df = strategy.generate_voting_signals(
        df, 
        strategy_params['selected_indicators'],
        strategy_params['voting_threshold']
    )
    
    # Run backtest
    print("\nRunning backtest...")
    trades_df, equity_df, metrics = strategy.backtest_strategy(
        df,
        initial_capital=strategy_params['initial_capital'],
        position_size_pct=strategy_params['position_size_pct'],
        risk_reward_ratio=strategy_params['risk_reward_ratio'],
        max_drawdown_pct=strategy_params['max_drawdown_pct']
    )
    
    # Display results
    strategy.display_metrics(metrics, trades_df)
    
    # Plot results
    print("\nGenerating charts...")
    fig = strategy.plot_backtest_results(
        df, trades_df, equity_df, 
        strategy_params['selected_indicators']
    )
    fig.show()
    
    # Run Monte Carlo simulation
    print("\nRunning Monte Carlo simulation...")
    monte_carlo_stats, mc_results = strategy.monte_carlo_analysis(
        trades_df,
        strategy_params['initial_capital'],
        num_simulations=strategy_params['monte_carlo_simulations'],
        confidence_level=strategy_params['confidence_level']
    )
    
    # Additional analysis and visualizations...
    
    return df, trades_df, equity_df, metrics, monte_carlo_stats, mc_results

# Run the backtest
if __name__ == "__main__":
    # You can modify the parameters in the run_backtest function
    results = run_advanced_backtest()  # Changed from run_backtest to run_advanced_backtest
    
    # Interactive parameter selection (optional)
    print("\n" + "="*50)
    print("CUSTOMIZE YOUR STRATEGY")
    print("="*50)
    print("\nAvailable Indicators:")
    print("- ema: Exponential/Simple Moving Average")
    print("- macd: MACD (Moving Average Convergence Divergence)")
    print("- rsi: Relative Strength Index")
    print("- stochastic: Stochastic Oscillator")
    print("- bb: Bollinger Bands")
    print("- atr: Average True Range")
    print("- obv: On Balance Volume")
    print("- vwap: Volume Weighted Average Price")
    
    print("\nPopular Indian Stocks:")
    print("RELIANCE, TCS, INFY, HDFC, ICICIBANK, SBIN, ITC, BHARTIARTL, WIPRO, HCLTECH")
    
    print("\nTimeframes: 1m, 5m, 15m, 30m, 1h, 1d, 1wk")
    print("\nModify the strategy_params dictionary in run_advanced_backtest() to test different configurations!")