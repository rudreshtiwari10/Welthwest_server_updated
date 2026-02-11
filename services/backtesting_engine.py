import yfinance as yf
import pandas as pd
import numpy as np
import ta
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from scipy import stats
import warnings
warnings.filterwarnings('ignore')

class IndianStockStrategyBuilder:
    """
    Comprehensive backtesting engine that replicates Colab-based strategy builder
    with exact same inputs, outputs, and metrics preservation
    """
    
    def __init__(self):
        self.stock_data = None
        self.trades = []
        self.equity_curve = []
        
    def fetch_stock_data(self, symbol, period='1y', interval='1d'):
        """
        Fetch stock data from Yahoo Finance
        
        Args:
            symbol (str): Stock symbol (e.g., 'RELIANCE.NS')
            period (str): Data period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            interval (str): Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
        
        Returns:
            pandas.DataFrame: OHLCV data
        """
        try:
            # Add .NS suffix for Indian stocks if not present
            if not symbol.endswith('.NS') and not symbol.endswith('.BO'):
                symbol = f"{symbol}.NS"
            
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"No data found for symbol: {symbol}")
                return None
            
            # Reset index to make Date a column
            df.reset_index(inplace=True)
            
            # Handle different column structures from yfinance
            expected_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            if len(df.columns) >= 6:
                df = df.iloc[:, :6]  # Take first 6 columns
                df.columns = expected_cols
            else:
                # If missing columns, pad with NaN
                for i, col in enumerate(expected_cols):
                    if i >= len(df.columns):
                        df[col] = np.nan
                    else:
                        df.columns.values[i] = col
            
            # Ensure proper data types
            df['Date'] = pd.to_datetime(df['Date'])
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            self.stock_data = df
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {str(e)}")
            return None
    
    def calculate_indicators(self, df, indicators):
        """
        Calculate technical indicators
        
        Args:
            df (pandas.DataFrame): OHLCV data
            indicators (dict): Dictionary of indicators and their parameters
        
        Returns:
            pandas.DataFrame: Data with calculated indicators
        """
        df = df.copy()
        
        # RSI
        if 'RSI' in indicators:
            rsi_params = indicators['RSI']
            df['RSI'] = ta.momentum.RSIIndicator(
                close=df['Close'], 
                window=rsi_params.get('period', 14)
            ).rsi()
        
        # MACD
        if 'MACD' in indicators:
            macd_params = indicators['MACD']
            macd_indicator = ta.trend.MACD(
                close=df['Close'],
                window_fast=macd_params.get('fast_period', 12),
                window_slow=macd_params.get('slow_period', 26),
                window_sign=macd_params.get('signal_period', 9)
            )
            df['MACD'] = macd_indicator.macd()
            df['MACD_Signal'] = macd_indicator.macd_signal()
            df['MACD_Histogram'] = macd_indicator.macd_diff()
        
        # Bollinger Bands
        if 'Bollinger_Bands' in indicators:
            bb_params = indicators['Bollinger_Bands']
            bb_indicator = ta.volatility.BollingerBands(
                close=df['Close'],
                window=bb_params.get('period', 20),
                window_dev=bb_params.get('std_dev', 2)
            )
            df['BB_Upper'] = bb_indicator.bollinger_hband()
            df['BB_Middle'] = bb_indicator.bollinger_mavg()
            df['BB_Lower'] = bb_indicator.bollinger_lband()
        
        # Stochastic Oscillator
        if 'Stochastic' in indicators:
            stoch_params = indicators['Stochastic']
            stoch_indicator = ta.momentum.StochasticOscillator(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                window=stoch_params.get('k_period', 14),
                smooth_window=stoch_params.get('d_period', 3)
            )
            df['Stoch_K'] = stoch_indicator.stoch()
            df['Stoch_D'] = stoch_indicator.stoch_signal()
        
        # Moving Averages
        if 'SMA' in indicators:
            sma_params = indicators['SMA']
            for period in sma_params.get('periods', [20, 50]):
                df[f'SMA_{period}'] = ta.trend.SMAIndicator(
                    close=df['Close'], 
                    window=period
                ).sma_indicator()
        
        if 'EMA' in indicators:
            ema_params = indicators['EMA']
            for period in ema_params.get('periods', [12, 26]):
                df[f'EMA_{period}'] = ta.trend.EMAIndicator(
                    close=df['Close'], 
                    window=period
                ).ema_indicator()
        
        # ADX
        if 'ADX' in indicators:
            adx_params = indicators['ADX']
            adx_indicator = ta.trend.ADXIndicator(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                window=adx_params.get('period', 14)
            )
            df['ADX'] = adx_indicator.adx()
            df['ADX_POS'] = adx_indicator.adx_pos()
            df['ADX_NEG'] = adx_indicator.adx_neg()
        
        # Williams %R
        if 'Williams_R' in indicators:
            wr_params = indicators['Williams_R']
            df['Williams_R'] = ta.momentum.WilliamsRIndicator(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                lbp=wr_params.get('period', 14)
            ).williams_r()
        
        # CCI
        if 'CCI' in indicators:
            cci_params = indicators['CCI']
            df['CCI'] = ta.trend.CCIIndicator(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                window=cci_params.get('period', 20)
            ).cci()
        
        # ATR
        if 'ATR' in indicators:
            atr_params = indicators['ATR']
            df['ATR'] = ta.volatility.AverageTrueRange(
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                window=atr_params.get('period', 14)
            ).average_true_range()
        
        # OBV
        if 'OBV' in indicators:
            df['OBV'] = ta.volume.OnBalanceVolumeIndicator(
                close=df['Close'],
                volume=df['Volume']
            ).on_balance_volume()

        # Supertrend
        if 'Supertrend' in indicators:
            from services.technical_analysis import TechnicalAnalysis
            tech_analysis = TechnicalAnalysis()
            st_params = indicators['Supertrend']
            st_data = tech_analysis._calculate_supertrend(
                df,
                period=st_params.get('period', 10),
                multiplier=st_params.get('multiplier', 3)
            )
            df['Supertrend'] = st_data['supertrend']
            df['ST_Direction'] = st_data['direction']
            df['ST_Upper'] = st_data['upper_band']
            df['ST_Lower'] = st_data['lower_band']

        # Ichimoku Cloud
        if 'Ichimoku' in indicators:
            from services.technical_analysis import TechnicalAnalysis
            tech_analysis = TechnicalAnalysis()
            ich_params = indicators['Ichimoku']
            ich_data = tech_analysis._calculate_ichimoku(
                df,
                period1=ich_params.get('period1', 9),
                period2=ich_params.get('period2', 26),
                period3=ich_params.get('period3', 52)
            )
            df['Ichimoku_Tenkan'] = ich_data['tenkan']
            df['Ichimoku_Kijun'] = ich_data['kijun']
            df['Ichimoku_SenkouA'] = ich_data['senkou_a']
            df['Ichimoku_SenkouB'] = ich_data['senkou_b']
            df['Ichimoku_Chikou'] = ich_data['chikou']

        # MFI (Money Flow Index)
        if 'MFI' in indicators:
            from services.technical_analysis import TechnicalAnalysis
            tech_analysis = TechnicalAnalysis()
            mfi_params = indicators['MFI']
            df['MFI'] = tech_analysis._calculate_mfi(
                df,
                period=mfi_params.get('period', 14)
            )

        # Keltner Channels
        if 'Keltner' in indicators:
            from services.technical_analysis import TechnicalAnalysis
            tech_analysis = TechnicalAnalysis()
            kc_params = indicators['Keltner']
            kc_data = tech_analysis._calculate_keltner_channels(
                df,
                ema_period=kc_params.get('ema_period', 20),
                atr_period=kc_params.get('atr_period', 14),
                atr_mult=kc_params.get('atr_mult', 2)
            )
            df['KC_Upper'] = kc_data['upper']
            df['KC_Middle'] = kc_data['middle']
            df['KC_Lower'] = kc_data['lower']

        return df
    
    def generate_voting_signals(self, df, indicators, voting_threshold=0.6):
        """
        Generate trading signals using voting mechanism
        
        Args:
            df (pandas.DataFrame): Data with indicators
            indicators (dict): Indicator configurations
            voting_threshold (float): Minimum voting threshold for signal generation
        
        Returns:
            pandas.DataFrame: Data with trading signals
        """
        df = df.copy()
        
        # Initialize voting columns
        df['Buy_Votes'] = 0
        df['Sell_Votes'] = 0
        df['Total_Indicators'] = 0
        
        # RSI signals
        if 'RSI' in indicators:
            rsi_params = indicators['RSI']
            oversold = rsi_params.get('oversold', 30)
            overbought = rsi_params.get('overbought', 70)
            
            df['Buy_Votes'] += (df['RSI'] < oversold).astype(int)
            df['Sell_Votes'] += (df['RSI'] > overbought).astype(int)
            df['Total_Indicators'] += 1
        
        # MACD signals
        if 'MACD' in indicators:
            df['Buy_Votes'] += ((df['MACD'] > df['MACD_Signal']) & 
                               (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1))).astype(int)
            df['Sell_Votes'] += ((df['MACD'] < df['MACD_Signal']) & 
                                (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1))).astype(int)
            df['Total_Indicators'] += 1
        
        # Bollinger Bands signals
        if 'Bollinger_Bands' in indicators:
            df['Buy_Votes'] += (df['Close'] < df['BB_Lower']).astype(int)
            df['Sell_Votes'] += (df['Close'] > df['BB_Upper']).astype(int)
            df['Total_Indicators'] += 1
        
        # Stochastic signals
        if 'Stochastic' in indicators:
            stoch_params = indicators['Stochastic']
            oversold = stoch_params.get('oversold', 20)
            overbought = stoch_params.get('overbought', 80)
            
            df['Buy_Votes'] += (df['Stoch_K'] < oversold).astype(int)
            df['Sell_Votes'] += (df['Stoch_K'] > overbought).astype(int)
            df['Total_Indicators'] += 1
        
        # Moving Average signals
        if 'SMA' in indicators:
            sma_params = indicators['SMA']
            periods = sma_params.get('periods', [20, 50])
            if len(periods) >= 2:
                short_ma = f'SMA_{min(periods)}'
                long_ma = f'SMA_{max(periods)}'
                df['Buy_Votes'] += ((df[short_ma] > df[long_ma]) & 
                                   (df[short_ma].shift(1) <= df[long_ma].shift(1))).astype(int)
                df['Sell_Votes'] += ((df[short_ma] < df[long_ma]) & 
                                    (df[short_ma].shift(1) >= df[long_ma].shift(1))).astype(int)
                df['Total_Indicators'] += 1
        
        # ADX signals
        if 'ADX' in indicators:
            adx_params = indicators['ADX']
            threshold = adx_params.get('threshold', 25)
            
            strong_trend = df['ADX'] > threshold
            df['Buy_Votes'] += (strong_trend & (df['ADX_POS'] > df['ADX_NEG'])).astype(int)
            df['Sell_Votes'] += (strong_trend & (df['ADX_NEG'] > df['ADX_POS'])).astype(int)
            df['Total_Indicators'] += 1
        
        # Williams %R signals
        if 'Williams_R' in indicators:
            wr_params = indicators['Williams_R']
            oversold = wr_params.get('oversold', -80)
            overbought = wr_params.get('overbought', -20)

            df['Buy_Votes'] += (df['Williams_R'] < oversold).astype(int)
            df['Sell_Votes'] += (df['Williams_R'] > overbought).astype(int)
            df['Total_Indicators'] += 1

        # EMA signals
        if 'EMA' in indicators:
            ema_params = indicators['EMA']
            periods = ema_params.get('periods', [12, 26])
            if len(periods) >= 2:
                short_ema = f'EMA_{min(periods)}'
                long_ema = f'EMA_{max(periods)}'
                df['Buy_Votes'] += ((df[short_ema] > df[long_ema]) &
                                   (df[short_ema].shift(1) <= df[long_ema].shift(1))).astype(int)
                df['Sell_Votes'] += ((df[short_ema] < df[long_ema]) &
                                    (df[short_ema].shift(1) >= df[long_ema].shift(1))).astype(int)
                df['Total_Indicators'] += 1

        # Supertrend signals
        if 'Supertrend' in indicators:
            df['Buy_Votes'] += ((df['ST_Direction'] == 1) &
                               (df['ST_Direction'].shift(1) != 1)).astype(int)
            df['Sell_Votes'] += ((df['ST_Direction'] == -1) &
                                (df['ST_Direction'].shift(1) != -1)).astype(int)
            df['Total_Indicators'] += 1

        # Ichimoku signals
        if 'Ichimoku' in indicators:
            # Bullish: Price > Cloud AND Tenkan > Kijun
            # Bearish: Price < Cloud AND Tenkan < Kijun
            cloud_top = df[['Ichimoku_SenkouA', 'Ichimoku_SenkouB']].max(axis=1)
            cloud_bottom = df[['Ichimoku_SenkouA', 'Ichimoku_SenkouB']].min(axis=1)

            bullish_ichimoku = (df['Close'] > cloud_top) & (df['Ichimoku_Tenkan'] > df['Ichimoku_Kijun'])
            bearish_ichimoku = (df['Close'] < cloud_bottom) & (df['Ichimoku_Tenkan'] < df['Ichimoku_Kijun'])

            df['Buy_Votes'] += bullish_ichimoku.astype(int)
            df['Sell_Votes'] += bearish_ichimoku.astype(int)
            df['Total_Indicators'] += 1

        # CCI signals
        if 'CCI' in indicators:
            # CCI > 100 = Buy (breakout), CCI < -100 = Sell (breakdown)
            df['Buy_Votes'] += ((df['CCI'] > 100) & (df['CCI'].shift(1) <= 100)).astype(int)
            df['Sell_Votes'] += ((df['CCI'] < -100) & (df['CCI'].shift(1) >= -100)).astype(int)
            df['Total_Indicators'] += 1

        # MFI signals
        if 'MFI' in indicators:
            mfi_params = indicators['MFI']
            oversold = mfi_params.get('oversold', 20)
            overbought = mfi_params.get('overbought', 80)

            df['Buy_Votes'] += ((df['MFI'] < oversold) |
                               ((df['MFI'] >= oversold) & (df['MFI'].shift(1) < oversold))).astype(int)
            df['Sell_Votes'] += ((df['MFI'] > overbought) |
                                ((df['MFI'] <= overbought) & (df['MFI'].shift(1) > overbought))).astype(int)
            df['Total_Indicators'] += 1

        # Keltner Channels signals
        if 'Keltner' in indicators:
            # Price crosses above upper channel = Buy (breakout)
            # Price crosses below lower channel = Sell (breakdown)
            df['Buy_Votes'] += ((df['Close'] > df['KC_Upper']) &
                               (df['Close'].shift(1) <= df['KC_Upper'].shift(1))).astype(int)
            df['Sell_Votes'] += ((df['Close'] < df['KC_Lower']) &
                                (df['Close'].shift(1) >= df['KC_Lower'].shift(1))).astype(int)
            df['Total_Indicators'] += 1

        # Calculate voting percentages
        df['Buy_Percentage'] = df['Buy_Votes'] / df['Total_Indicators']
        df['Sell_Percentage'] = df['Sell_Votes'] / df['Total_Indicators']
        
        # Generate final signals
        df['Signal'] = 0  # 0: Hold, 1: Buy, -1: Sell
        df.loc[df['Buy_Percentage'] >= voting_threshold, 'Signal'] = 1
        df.loc[df['Sell_Percentage'] >= voting_threshold, 'Signal'] = -1
        
        return df
    
    def backtest_strategy(self, df, initial_capital=100000, position_size_pct=0.1, 
                         risk_reward_ratio=2.0, max_drawdown_pct=0.05):
        """
        Run comprehensive backtesting with risk management
        
        Args:
            df (pandas.DataFrame): Data with signals
            initial_capital (float): Starting capital
            position_size_pct (float): Position size as percentage of capital
            risk_reward_ratio (float): Risk-reward ratio
            max_drawdown_pct (float): Maximum drawdown percentage
        
        Returns:
            tuple: (trades_df, equity_df, metrics)
        """
        df = df.copy()
        
        # Initialize tracking variables
        capital = initial_capital
        position = 0
        entry_price = 0
        stop_loss = 0
        take_profit = 0
        trades = []
        equity_curve = []
        peak_capital = initial_capital
        max_drawdown = 0
        
        for i, row in df.iterrows():
            current_price = row['Close']
            signal = row['Signal']
            date = row['Date']
            
            # Calculate current equity
            if position != 0:
                current_equity = capital + (position * (current_price - entry_price))
            else:
                current_equity = capital
            
            # Update peak and drawdown
            if current_equity > peak_capital:
                peak_capital = current_equity
            
            current_drawdown = (peak_capital - current_equity) / peak_capital
            if current_drawdown > max_drawdown:
                max_drawdown = current_drawdown
            
            # Risk management: Close position if max drawdown exceeded
            if current_drawdown > max_drawdown_pct and position != 0:
                # Close position due to risk management
                pnl = position * (current_price - entry_price)
                capital += pnl
                
                trades.append({
                    'Entry_Date': entry_date,
                    'Exit_Date': date,
                    'Entry_Price': entry_price,
                    'Exit_Price': current_price,
                    'Position_Size': abs(position),
                    'Direction': 'Long' if position > 0 else 'Short',
                    'PnL': pnl,
                    'Return_Pct': (pnl / (abs(position) * entry_price)) * 100,
                    'Exit_Reason': 'Risk Management'
                })
                
                position = 0
                entry_price = 0
                stop_loss = 0
                take_profit = 0
            
            # Check exit conditions for existing positions
            if position != 0:
                exit_triggered = False
                exit_reason = ''
                
                # Stop loss
                if position > 0 and current_price <= stop_loss:
                    exit_triggered = True
                    exit_reason = 'Stop Loss'
                elif position < 0 and current_price >= stop_loss:
                    exit_triggered = True
                    exit_reason = 'Stop Loss'
                
                # Take profit
                if position > 0 and current_price >= take_profit:
                    exit_triggered = True
                    exit_reason = 'Take Profit'
                elif position < 0 and current_price <= take_profit:
                    exit_triggered = True
                    exit_reason = 'Take Profit'
                
                # Opposite signal
                if (position > 0 and signal == -1) or (position < 0 and signal == 1):
                    exit_triggered = True
                    exit_reason = 'Signal Exit'
                
                if exit_triggered:
                    pnl = position * (current_price - entry_price)
                    capital += pnl
                    
                    trades.append({
                        'Entry_Date': entry_date,
                        'Exit_Date': date,
                        'Entry_Price': entry_price,
                        'Exit_Price': current_price,
                        'Position_Size': abs(position),
                        'Direction': 'Long' if position > 0 else 'Short',
                        'PnL': pnl,
                        'Return_Pct': (pnl / (abs(position) * entry_price)) * 100,
                        'Exit_Reason': exit_reason
                    })
                    
                    position = 0
                    entry_price = 0
                    stop_loss = 0
                    take_profit = 0
            
            # Enter new positions
            if position == 0 and signal != 0:
                position_value = capital * position_size_pct
                position_size = position_value / current_price
                
                if signal == 1:  # Buy signal
                    position = position_size
                    entry_price = current_price
                    entry_date = date
                    
                    # Calculate stop loss and take profit
                    atr = row.get('ATR', current_price * 0.02)  # Default 2% if ATR not available
                    stop_loss = entry_price - atr
                    take_profit = entry_price + (atr * risk_reward_ratio)
                    
                elif signal == -1:  # Sell signal
                    position = -position_size
                    entry_price = current_price
                    entry_date = date
                    
                    # Calculate stop loss and take profit
                    atr = row.get('ATR', current_price * 0.02)
                    stop_loss = entry_price + atr
                    take_profit = entry_price - (atr * risk_reward_ratio)
            
            # Record equity curve
            if position != 0:
                current_equity = capital + (position * (current_price - entry_price))
            else:
                current_equity = capital
            
            equity_curve.append({
                'Date': date,
                'Equity': current_equity,
                'Capital': capital,
                'Position': position,
                'Price': current_price,
                'Drawdown': current_drawdown
            })
        
        # Close any remaining position
        if position != 0:
            final_price = df.iloc[-1]['Close']
            final_date = df.iloc[-1]['Date']
            pnl = position * (final_price - entry_price)
            capital += pnl
            
            trades.append({
                'Entry_Date': entry_date,
                'Exit_Date': final_date,
                'Entry_Price': entry_price,
                'Exit_Price': final_price,
                'Position_Size': abs(position),
                'Direction': 'Long' if position > 0 else 'Short',
                'PnL': pnl,
                'Return_Pct': (pnl / (abs(position) * entry_price)) * 100,
                'Exit_Reason': 'End of Data'
            })
        
        # Create DataFrames
        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_curve)
        
        # Calculate comprehensive metrics
        metrics = self._calculate_metrics(trades_df, equity_df, initial_capital)
        
        return trades_df, equity_df, metrics
    
    def _calculate_metrics(self, trades_df, equity_df, initial_capital):
        """Calculate comprehensive performance metrics"""
        
        if trades_df.empty:
            return {
                'Total_Return': 0,
                'Total_Return_Pct': 0,
                'Number_of_Trades': 0,
                'Win_Rate': 0,
                'Average_Return': 0,
                'Profit_Factor': 0,
                'Max_Drawdown': 0,
                'Sharpe_Ratio': 0,
                'Sortino_Ratio': 0,
                'Calmar_Ratio': 0
            }
        
        final_capital = equity_df.iloc[-1]['Equity']
        total_return = final_capital - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        
        # Trade statistics
        winning_trades = trades_df[trades_df['PnL'] > 0]
        losing_trades = trades_df[trades_df['PnL'] < 0]
        
        win_rate = len(winning_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0
        avg_win = winning_trades['PnL'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['PnL'].mean() if len(losing_trades) > 0 else 0
        
        # Profit factor
        total_profits = winning_trades['PnL'].sum() if len(winning_trades) > 0 else 0
        total_losses = abs(losing_trades['PnL'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = total_profits / total_losses if total_losses > 0 else float('inf')
        
        # Drawdown
        equity_df['Peak'] = equity_df['Equity'].expanding().max()
        equity_df['Drawdown'] = (equity_df['Peak'] - equity_df['Equity']) / equity_df['Peak']
        max_drawdown = equity_df['Drawdown'].max() * 100
        
        # Returns for ratio calculations
        equity_df['Returns'] = equity_df['Equity'].pct_change().fillna(0)
        
        # Sharpe Ratio (assuming 252 trading days per year)
        excess_returns = equity_df['Returns'] - 0.02/252  # Assuming 2% risk-free rate
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0
        
        # Sortino Ratio
        negative_returns = equity_df['Returns'][equity_df['Returns'] < 0]
        downside_std = negative_returns.std() if len(negative_returns) > 0 else 0
        sortino_ratio = np.sqrt(252) * excess_returns.mean() / downside_std if downside_std > 0 else 0
        
        # Calmar Ratio
        annualized_return = (1 + total_return_pct/100) ** (252/len(equity_df)) - 1
        calmar_ratio = annualized_return / (max_drawdown/100) if max_drawdown > 0 else 0
        
        return {
            'Total_Return': total_return,
            'Total_Return_Pct': total_return_pct,
            'Number_of_Trades': len(trades_df),
            'Win_Rate': win_rate,
            'Average_Win': avg_win,
            'Average_Loss': avg_loss,
            'Profit_Factor': profit_factor,
            'Max_Drawdown': max_drawdown,
            'Sharpe_Ratio': sharpe_ratio,
            'Sortino_Ratio': sortino_ratio,
            'Calmar_Ratio': calmar_ratio,
            'Best_Trade': trades_df['PnL'].max() if len(trades_df) > 0 else 0,
            'Worst_Trade': trades_df['PnL'].min() if len(trades_df) > 0 else 0,
            'Average_Trade': trades_df['PnL'].mean() if len(trades_df) > 0 else 0,
            'Total_Profits': total_profits,
            'Total_Losses': total_losses
        }
    
    def monte_carlo_analysis(self, trades_df, initial_capital, num_simulations=1000, confidence_level=0.95):
        """
        Perform Monte Carlo analysis on trade results
        
        Args:
            trades_df (pandas.DataFrame): Historical trades
            initial_capital (float): Starting capital
            num_simulations (int): Number of simulations
            confidence_level (float): Confidence level for statistics
        
        Returns:
            tuple: (mc_stats, mc_results)
        """
        if trades_df.empty or num_simulations <= 0:
            return None, None
        
        returns = trades_df['Return_Pct'].values / 100
        
        # Run Monte Carlo simulations
        final_returns = []
        
        for _ in range(num_simulations):
            # Randomly sample returns with replacement
            simulated_returns = np.random.choice(returns, size=len(returns), replace=True)
            
            # Calculate cumulative return
            cumulative_return = (1 + simulated_returns).prod() - 1
            final_returns.append(cumulative_return)
        
        final_returns = np.array(final_returns)
        
        # Calculate statistics
        alpha = 1 - confidence_level
        lower_percentile = (alpha/2) * 100
        upper_percentile = (1 - alpha/2) * 100
        
        mc_stats = {
            'Mean_Return': np.mean(final_returns) * 100,
            'Std_Return': np.std(final_returns) * 100,
            'Min_Return': np.min(final_returns) * 100,
            'Max_Return': np.max(final_returns) * 100,
            f'VaR_{confidence_level*100}%': np.percentile(final_returns, lower_percentile) * 100,
            f'CVaR_{confidence_level*100}%': np.mean(final_returns[final_returns <= np.percentile(final_returns, lower_percentile)]) * 100,
            f'Confidence_Interval_Lower': np.percentile(final_returns, lower_percentile) * 100,
            f'Confidence_Interval_Upper': np.percentile(final_returns, upper_percentile) * 100,
            'Probability_of_Loss': np.sum(final_returns < 0) / num_simulations * 100
        }
        
        mc_results = pd.DataFrame({
            'Simulation': range(1, num_simulations + 1),
            'Final_Return_Pct': final_returns * 100,
            'Final_Capital': initial_capital * (1 + final_returns)
        })
        
        return mc_stats, mc_results
    
    def create_candlestick_chart(self, df, trades_df=None):
        """
        Create candlestick chart with indicators and buy/sell signals in separate panels

        Args:
            df (pandas.DataFrame): OHLCV data with indicators
            trades_df (pandas.DataFrame): Trade data for buy/sell markers

        Returns:
            plotly.graph_objects.Figure: Interactive candlestick chart
        """
        # Create subplots with separate panels for each indicator
        fig = make_subplots(
            rows=6, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,  # Increased spacing for better separation
            subplot_titles=('Price with Trading Signals', 'Moving Averages', 'Bollinger Bands', 'RSI', 'MACD', 'Volume'),
            row_heights=[0.35, 0.15, 0.15, 0.12, 0.13, 0.1]  # Adjusted for better proportions
        )
        
        # Panel 1: Candlestick chart ONLY (cleaner view)
        fig.add_trace(
            go.Candlestick(
                x=df['Date'],
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price',
                showlegend=True
            ),
            row=1, col=1
        )

        # Panel 2: Moving Averages (separate from price for clarity)
        if 'SMA_20' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['SMA_20'],
                    mode='lines',
                    name='SMA 20',
                    line=dict(color='#FF6B35', width=2.5)  # Bright orange for better visibility
                ),
                row=2, col=1
            )

        if 'SMA_50' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['SMA_50'],
                    mode='lines',
                    name='SMA 50',
                    line=dict(color='#004E89', width=2.5)  # Deep blue for better visibility
                ),
                row=2, col=1
            )

        # Also show price line in MA panel for reference
        fig.add_trace(
            go.Scatter(
                x=df['Date'],
                y=df['Close'],
                mode='lines',
                name='Close Price',
                line=dict(color='rgba(128, 128, 128, 0.5)', width=1.5, dash='dot'),
                showlegend=False
            ),
            row=2, col=1
        )

        # Panel 3: Bollinger Bands (separate panel)
        if 'BB_Upper' in df.columns:
            # Show price line for reference
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['Close'],
                    mode='lines',
                    name='Close Price',
                    line=dict(color='#2c3e50', width=2),
                    showlegend=False
                ),
                row=3, col=1
            )

            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['BB_Upper'],
                    mode='lines',
                    name='BB Upper',
                    line=dict(color='#E63946', width=2, dash='dash'),  # Vibrant red
                    showlegend=True
                ),
                row=3, col=1
            )

            if 'BB_Middle' in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df['Date'],
                        y=df['BB_Middle'],
                        mode='lines',
                        name='BB Middle',
                        line=dict(color='#6C757D', width=1.5),  # Medium gray
                        showlegend=True
                    ),
                    row=3, col=1
                )

            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['BB_Lower'],
                    mode='lines',
                    name='BB Lower',
                    line=dict(color='#06A77D', width=2, dash='dash'),  # Vibrant green
                    fill='tonexty',
                    fillcolor='rgba(6, 167, 125, 0.1)',
                    showlegend=True
                ),
                row=3, col=1
            )
        
        # Add buy/sell signals from trades
        if trades_df is not None and not trades_df.empty:
            # Buy signals
            buy_signals = trades_df[trades_df['Direction'] == 'Long']
            if not buy_signals.empty:
                fig.add_trace(
                    go.Scatter(
                        x=buy_signals['Entry_Date'],
                        y=buy_signals['Entry_Price'],
                        mode='markers',
                        name='Buy Signal',
                        marker=dict(
                            symbol='triangle-up',
                            size=12,
                            color='green'
                        )
                    ),
                    row=1, col=1
                )
            
            # Sell signals
            sell_signals = trades_df[trades_df['Direction'] == 'Short']
            if not sell_signals.empty:
                fig.add_trace(
                    go.Scatter(
                        x=sell_signals['Entry_Date'],
                        y=sell_signals['Entry_Price'],
                        mode='markers',
                        name='Sell Signal',
                        marker=dict(
                            symbol='triangle-down',
                            size=12,
                            color='red'
                        )
                    ),
                    row=1, col=1
                )
        
        # Panel 4: RSI (separate panel)
        if 'RSI' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['RSI'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='#9D4EDD', width=2.5),  # Vibrant purple
                    fill='tozeroy',
                    fillcolor='rgba(157, 78, 221, 0.15)'
                ),
                row=4, col=1
            )

            # RSI levels with shaded zones
            fig.add_hline(y=70, line_dash="dash", line_color="#E63946", line_width=2, row=4, col=1,
                         annotation_text="Overbought (70)", annotation_position="right",
                         annotation_font=dict(size=11, color="#E63946"))
            fig.add_hline(y=30, line_dash="dash", line_color="#06A77D", line_width=2, row=4, col=1,
                         annotation_text="Oversold (30)", annotation_position="right",
                         annotation_font=dict(size=11, color="#06A77D"))
            fig.add_hline(y=50, line_dash="dot", line_color="rgba(108, 117, 125, 0.5)", line_width=1, row=4, col=1)
        
        # Panel 5: MACD (separate panel)
        if 'MACD' in df.columns:
            # MACD Histogram first (background)
            if 'MACD_Histogram' in df.columns:
                colors = ['#06A77D' if val >= 0 else '#E63946' for val in df['MACD_Histogram']]
                fig.add_trace(
                    go.Bar(
                        x=df['Date'],
                        y=df['MACD_Histogram'],
                        name='MACD Histogram',
                        marker_color=colors,
                        opacity=0.6,
                        showlegend=True
                    ),
                    row=5, col=1
                )

            # MACD Line
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['MACD'],
                    mode='lines',
                    name='MACD',
                    line=dict(color='#0077B6', width=2.5)  # Bright blue
                ),
                row=5, col=1
            )

            # Signal Line
            if 'MACD_Signal' in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df['Date'],
                        y=df['MACD_Signal'],
                        mode='lines',
                        name='Signal',
                        line=dict(color='#FF6B35', width=2.5)  # Orange
                    ),
                    row=5, col=1
                )

            # Zero line
            fig.add_hline(y=0, line_dash="dot", line_color="rgba(108, 117, 125, 0.7)", line_width=1.5, row=5, col=1)
        
        # Panel 6: Volume (separate panel)
        # Color volume bars based on price movement
        colors = []
        for i in range(len(df)):
            if i == 0:
                colors.append('#0096C7')  # Light blue
            else:
                if df['Close'].iloc[i] >= df['Close'].iloc[i-1]:
                    colors.append('#06A77D')  # Green for up days
                else:
                    colors.append('#E63946')  # Red for down days

        fig.add_trace(
            go.Bar(
                x=df['Date'],
                y=df['Volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.7,
                showlegend=True
            ),
            row=6, col=1
        )
        
        # Update layout for better visibility
        fig.update_layout(
            title={
                'text': 'Stock Analysis with Trading Signals',
                'font': {'size': 20, 'color': '#2c3e50', 'family': 'Arial, sans-serif'},
                'y': 0.995,  # Position title higher to avoid overlap
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
            xaxis_rangeslider_visible=False,
            height=1800,  # Significantly increased height for better panel visibility
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.99,  # Position legend below title
                xanchor="center",
                x=0.5,
                font=dict(size=10),
                bgcolor='rgba(255, 255, 255, 0.9)',
                bordercolor='rgba(0, 0, 0, 0.2)',
                borderwidth=1
            ),
            hovermode='x unified',
            template='plotly_white',
            # Improved styling for better readability
            plot_bgcolor='rgba(250, 250, 250, 0.95)',
            paper_bgcolor='white',
            font=dict(size=12, color='#2c3e50')
        )

        # Update y-axes labels for each panel with better styling
        fig.update_yaxes(
            title_text="Price ($)",
            row=1, col=1,
            gridcolor='rgba(200, 200, 200, 0.5)',
            title_font=dict(size=13, color='#2c3e50'),
            tickfont=dict(size=11)
        )
        fig.update_yaxes(
            title_text="Moving Averages ($)",
            row=2, col=1,
            gridcolor='rgba(200, 200, 200, 0.5)',
            title_font=dict(size=13, color='#2c3e50'),
            tickfont=dict(size=11)
        )
        fig.update_yaxes(
            title_text="Bollinger Bands ($)",
            row=3, col=1,
            gridcolor='rgba(200, 200, 200, 0.5)',
            title_font=dict(size=13, color='#2c3e50'),
            tickfont=dict(size=11)
        )
        fig.update_yaxes(
            title_text="RSI",
            row=4, col=1,
            range=[0, 100],
            gridcolor='rgba(200, 200, 200, 0.5)',
            title_font=dict(size=13, color='#2c3e50'),
            tickfont=dict(size=11)
        )
        fig.update_yaxes(
            title_text="MACD",
            row=5, col=1,
            gridcolor='rgba(200, 200, 200, 0.5)',
            title_font=dict(size=13, color='#2c3e50'),
            tickfont=dict(size=11)
        )
        fig.update_yaxes(
            title_text="Volume",
            row=6, col=1,
            gridcolor='rgba(200, 200, 200, 0.5)',
            title_font=dict(size=13, color='#2c3e50'),
            tickfont=dict(size=11)
        )

        # Update x-axes with better styling
        fig.update_xaxes(
            showgrid=True,
            gridcolor='rgba(200, 200, 200, 0.5)',
            tickfont=dict(size=11)
        )

        # Update subplot title annotations for better visibility
        for annotation in fig['layout']['annotations']:
            annotation['font'] = dict(size=14, color='#2c3e50', family='Arial, sans-serif')
            annotation['yshift'] = 5

        return fig

    def create_price_chart_simple(self, df, trades_df=None):
        """
        Create a clean price chart with ONLY candlesticks and trading signals

        Args:
            df (pandas.DataFrame): OHLCV data
            trades_df (pandas.DataFrame): Trade data for buy/sell markers

        Returns:
            plotly.graph_objects.Figure: Simple price chart
        """
        fig = go.Figure()

        # Candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df['Date'],
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price',
                increasing_line_color='#10b981',
                decreasing_line_color='#ef4444'
            )
        )

        # Add buy/sell signals from trades
        if trades_df is not None and not trades_df.empty:
            # Buy signals
            buy_signals = trades_df[trades_df['Direction'] == 'Long']
            if not buy_signals.empty:
                fig.add_trace(
                    go.Scatter(
                        x=buy_signals['Entry_Date'],
                        y=buy_signals['Entry_Price'],
                        mode='markers',
                        name='Buy Signal',
                        marker=dict(
                            symbol='triangle-up',
                            size=14,
                            color='#10b981',
                            line=dict(color='white', width=2)
                        )
                    )
                )

            # Sell signals
            sell_signals = trades_df[trades_df['Direction'] == 'Short']
            if not sell_signals.empty:
                fig.add_trace(
                    go.Scatter(
                        x=sell_signals['Entry_Date'],
                        y=sell_signals['Entry_Price'],
                        mode='markers',
                        name='Sell Signal',
                        marker=dict(
                            symbol='triangle-down',
                            size=14,
                            color='#ef4444',
                            line=dict(color='white', width=2)
                        )
                    )
                )

        fig.update_layout(
            title={
                'text': 'Price Action with Trading Signals',
                'font': {'size': 18, 'color': '#1f2937'}
            },
            xaxis_title='Date',
            yaxis_title='Price ($)',
            xaxis_rangeslider_visible=False,
            height=500,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        fig.update_xaxes(showgrid=True, gridcolor='#f3f4f6')
        fig.update_yaxes(showgrid=True, gridcolor='#f3f4f6')

        return fig

    def create_moving_averages_chart_simple(self, df):
        """
        Create a clean moving averages chart

        Args:
            df (pandas.DataFrame): OHLCV data with moving averages

        Returns:
            plotly.graph_objects.Figure: Moving averages chart
        """
        fig = go.Figure()

        # Price line
        fig.add_trace(
            go.Scatter(
                x=df['Date'],
                y=df['Close'],
                mode='lines',
                name='Close Price',
                line=dict(color='#6b7280', width=1.5)
            )
        )

        # SMA 20
        if 'SMA_20' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['SMA_20'],
                    mode='lines',
                    name='SMA 20',
                    line=dict(color='#f97316', width=2.5)
                )
            )

        # SMA 50
        if 'SMA_50' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['SMA_50'],
                    mode='lines',
                    name='SMA 50',
                    line=dict(color='#3b82f6', width=2.5)
                )
            )

        fig.update_layout(
            title={
                'text': 'Moving Averages',
                'font': {'size': 18, 'color': '#1f2937'}
            },
            xaxis_title='Date',
            yaxis_title='Price ($)',
            height=400,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        fig.update_xaxes(showgrid=True, gridcolor='#f3f4f6')
        fig.update_yaxes(showgrid=True, gridcolor='#f3f4f6')

        return fig

    def create_bollinger_bands_chart_simple(self, df):
        """
        Create a clean Bollinger Bands chart

        Args:
            df (pandas.DataFrame): OHLCV data with Bollinger Bands

        Returns:
            plotly.graph_objects.Figure: Bollinger Bands chart
        """
        fig = go.Figure()

        if 'BB_Upper' in df.columns and 'BB_Lower' in df.columns:
            # Upper band
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['BB_Upper'],
                    mode='lines',
                    name='Upper Band',
                    line=dict(color='#ef4444', width=1.5, dash='dash')
                )
            )

            # Middle band
            if 'BB_Middle' in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df['Date'],
                        y=df['BB_Middle'],
                        mode='lines',
                        name='Middle Band (SMA 20)',
                        line=dict(color='#6b7280', width=1.5)
                    )
                )

            # Lower band with fill
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['BB_Lower'],
                    mode='lines',
                    name='Lower Band',
                    line=dict(color='#10b981', width=1.5, dash='dash'),
                    fill='tonexty',
                    fillcolor='rgba(59, 130, 246, 0.1)'
                )
            )

            # Price line
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['Close'],
                    mode='lines',
                    name='Close Price',
                    line=dict(color='#1f2937', width=2)
                )
            )

        fig.update_layout(
            title={
                'text': 'Bollinger Bands',
                'font': {'size': 18, 'color': '#1f2937'}
            },
            xaxis_title='Date',
            yaxis_title='Price ($)',
            height=400,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        fig.update_xaxes(showgrid=True, gridcolor='#f3f4f6')
        fig.update_yaxes(showgrid=True, gridcolor='#f3f4f6')

        return fig

    def create_rsi_chart_simple(self, df):
        """
        Create a clean RSI chart

        Args:
            df (pandas.DataFrame): OHLCV data with RSI

        Returns:
            plotly.graph_objects.Figure: RSI chart
        """
        fig = go.Figure()

        if 'RSI' in df.columns:
            # RSI line with gradient fill
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['RSI'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='#8b5cf6', width=2.5),
                    fill='tozeroy',
                    fillcolor='rgba(139, 92, 246, 0.1)'
                )
            )

            # Overbought zone
            fig.add_shape(
                type="rect",
                x0=df['Date'].iloc[0],
                x1=df['Date'].iloc[-1],
                y0=70,
                y1=100,
                fillcolor="rgba(239, 68, 68, 0.1)",
                line=dict(width=0),
                layer="below"
            )

            # Oversold zone
            fig.add_shape(
                type="rect",
                x0=df['Date'].iloc[0],
                x1=df['Date'].iloc[-1],
                y0=0,
                y1=30,
                fillcolor="rgba(16, 185, 129, 0.1)",
                line=dict(width=0),
                layer="below"
            )

            # Reference lines
            fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", line_width=1.5,
                         annotation_text="Overbought (70)", annotation_position="right")
            fig.add_hline(y=50, line_dash="dot", line_color="#6b7280", line_width=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#10b981", line_width=1.5,
                         annotation_text="Oversold (30)", annotation_position="right")

        fig.update_layout(
            title={
                'text': 'Relative Strength Index (RSI)',
                'font': {'size': 18, 'color': '#1f2937'}
            },
            xaxis_title='Date',
            yaxis_title='RSI',
            height=350,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white',
            yaxis_range=[0, 100]
        )

        fig.update_xaxes(showgrid=True, gridcolor='#f3f4f6')
        fig.update_yaxes(showgrid=True, gridcolor='#f3f4f6')

        return fig

    def create_macd_chart_simple(self, df):
        """
        Create a clean MACD chart

        Args:
            df (pandas.DataFrame): OHLCV data with MACD

        Returns:
            plotly.graph_objects.Figure: MACD chart
        """
        fig = go.Figure()

        if 'MACD' in df.columns:
            # MACD Histogram
            if 'MACD_Histogram' in df.columns:
                colors = ['#10b981' if val >= 0 else '#ef4444' for val in df['MACD_Histogram']]
                fig.add_trace(
                    go.Bar(
                        x=df['Date'],
                        y=df['MACD_Histogram'],
                        name='MACD Histogram',
                        marker_color=colors,
                        opacity=0.5
                    )
                )

            # MACD Line
            fig.add_trace(
                go.Scatter(
                    x=df['Date'],
                    y=df['MACD'],
                    mode='lines',
                    name='MACD',
                    line=dict(color='#3b82f6', width=2.5)
                )
            )

            # Signal Line
            if 'MACD_Signal' in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df['Date'],
                        y=df['MACD_Signal'],
                        mode='lines',
                        name='Signal',
                        line=dict(color='#f97316', width=2.5)
                    )
                )

            # Zero line
            fig.add_hline(y=0, line_dash="dot", line_color="#6b7280", line_width=1.5)

        fig.update_layout(
            title={
                'text': 'MACD (Moving Average Convergence Divergence)',
                'font': {'size': 18, 'color': '#1f2937'}
            },
            xaxis_title='Date',
            yaxis_title='MACD',
            height=350,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        fig.update_xaxes(showgrid=True, gridcolor='#f3f4f6')
        fig.update_yaxes(showgrid=True, gridcolor='#f3f4f6')

        return fig

    def create_volume_chart_simple(self, df):
        """
        Create a clean volume chart

        Args:
            df (pandas.DataFrame): OHLCV data

        Returns:
            plotly.graph_objects.Figure: Volume chart
        """
        fig = go.Figure()

        # Color volume bars based on price movement
        colors = []
        for i in range(len(df)):
            if i == 0:
                colors.append('#3b82f6')
            else:
                if df['Close'].iloc[i] >= df['Close'].iloc[i-1]:
                    colors.append('#10b981')
                else:
                    colors.append('#ef4444')

        fig.add_trace(
            go.Bar(
                x=df['Date'],
                y=df['Volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.7
            )
        )

        fig.update_layout(
            title={
                'text': 'Trading Volume',
                'font': {'size': 18, 'color': '#1f2937'}
            },
            xaxis_title='Date',
            yaxis_title='Volume',
            height=300,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white'
        )

        fig.update_xaxes(showgrid=True, gridcolor='#f3f4f6')
        fig.update_yaxes(showgrid=True, gridcolor='#f3f4f6')

        return fig

    def create_equity_curve_chart(self, equity_df):
        """
        Create equity curve chart
        
        Args:
            equity_df (pandas.DataFrame): Equity curve data
        
        Returns:
            plotly.graph_objects.Figure: Equity curve chart
        """
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
                x=equity_df['Date'],
                y=equity_df['Equity'],
                mode='lines',
                name='Equity Curve',
                line=dict(color='blue', width=2)
            )
        )
        
        fig.update_layout(
            title='Portfolio Equity Curve',
            xaxis_title='Date',
            yaxis_title='Portfolio Value',
            height=400
        )
        
        return fig
    
    def create_drawdown_chart(self, equity_df):
        """
        Create drawdown chart
        
        Args:
            equity_df (pandas.DataFrame): Equity curve data with drawdown
        
        Returns:
            plotly.graph_objects.Figure: Drawdown chart
        """
        if 'Drawdown' not in equity_df.columns:
            equity_df['Peak'] = equity_df['Equity'].expanding().max()
            equity_df['Drawdown'] = (equity_df['Peak'] - equity_df['Equity']) / equity_df['Peak'] * 100
        
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
                x=equity_df['Date'],
                y=-equity_df['Drawdown'],
                mode='lines',
                name='Drawdown',
                line=dict(color='red', width=2),
                fill='tozeroy',
                fillcolor='rgba(255,0,0,0.3)'
            )
        )
        
        fig.update_layout(
            title='Portfolio Drawdown',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)',
            height=300
        )

        return fig

    def create_comprehensive_charts(self, df, trades_df, equity_df):
        """
        Create comprehensive charts for backtesting results - now with separate, clean charts!

        Args:
            df (pandas.DataFrame): OHLCV data with indicators
            trades_df (pandas.DataFrame): Trade data
            equity_df (pandas.DataFrame): Equity curve data

        Returns:
            dict: Dictionary containing chart data (as JSON-serializable format)
        """
        charts = {}

        try:
            # 1. Simple price chart with trading signals
            price_fig = self.create_price_chart_simple(df, trades_df)
            charts['price_chart'] = price_fig.to_json()
        except Exception as e:
            print(f"Error creating price chart: {e}")
            charts['price_chart'] = None

        try:
            # 2. Moving averages chart
            ma_fig = self.create_moving_averages_chart_simple(df)
            charts['moving_averages'] = ma_fig.to_json()
        except Exception as e:
            print(f"Error creating moving averages chart: {e}")
            charts['moving_averages'] = None

        try:
            # 3. Bollinger Bands chart
            bb_fig = self.create_bollinger_bands_chart_simple(df)
            charts['bollinger_bands'] = bb_fig.to_json()
        except Exception as e:
            print(f"Error creating Bollinger Bands chart: {e}")
            charts['bollinger_bands'] = None

        try:
            # 4. RSI chart
            rsi_fig = self.create_rsi_chart_simple(df)
            charts['rsi'] = rsi_fig.to_json()
        except Exception as e:
            print(f"Error creating RSI chart: {e}")
            charts['rsi'] = None

        try:
            # 5. MACD chart
            macd_fig = self.create_macd_chart_simple(df)
            charts['macd'] = macd_fig.to_json()
        except Exception as e:
            print(f"Error creating MACD chart: {e}")
            charts['macd'] = None

        try:
            # 6. Volume chart
            volume_fig = self.create_volume_chart_simple(df)
            charts['volume'] = volume_fig.to_json()
        except Exception as e:
            print(f"Error creating volume chart: {e}")
            charts['volume'] = None

        try:
            # 7. Equity curve chart
            equity_fig = self.create_equity_curve_chart(equity_df)
            charts['equity_curve'] = equity_fig.to_json()
        except Exception as e:
            print(f"Error creating equity curve chart: {e}")
            charts['equity_curve'] = None

        try:
            # 8. Drawdown chart
            drawdown_fig = self.create_drawdown_chart(equity_df)
            charts['drawdown'] = drawdown_fig.to_json()
        except Exception as e:
            print(f"Error creating drawdown chart: {e}")
            charts['drawdown'] = None

        # Keep the old complex candlestick chart for backward compatibility (optional)
        try:
            candlestick_fig = self.create_candlestick_chart(df, trades_df)
            charts['candlestick'] = candlestick_fig.to_json()
        except Exception as e:
            print(f"Error creating legacy candlestick chart: {e}")
            charts['candlestick'] = None

        return charts