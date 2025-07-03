import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from services.stock_service import get_historical_data
from datetime import datetime, timedelta

class PortfolioService:
    def __init__(self):
        self.risk_free_rate = 0.05  # 5% annual risk-free rate
        
    def calculate_portfolio_performance(self, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate portfolio performance metrics
        
        Args:
            holdings: List of dictionaries containing stock holdings
                     [{"ticker": "RELIANCE.NS", "quantity": 100, "buy_price": 2500.0}, ...]
        """
        if not holdings:
            return {"error": "Empty portfolio"}
            
        total_value = 0
        total_cost = 0
        returns = []
        weights = []
        
        # Calculate current value and returns
        for holding in holdings:
            try:
                df = get_historical_data(holding['ticker'], period="1y")
                if df.empty:
                    continue
                    
                current_price = df['Close'].iloc[-1]
                position_value = current_price * holding['quantity']
                position_cost = holding['buy_price'] * holding['quantity']
                
                total_value += position_value
                total_cost += position_cost
                
                # Calculate returns
                daily_returns = df['Close'].pct_change().dropna()
                returns.append(daily_returns)
                weights.append(position_value)
                
            except Exception:
                continue
                
        if not returns:
            return {"error": "Could not calculate portfolio metrics"}
            
        # Normalize weights
        weights = np.array(weights) / total_value
        
        # Calculate portfolio metrics
        portfolio_return = (total_value - total_cost) / total_cost
        portfolio_daily_returns = pd.concat(returns, axis=1).mean(axis=1)
        
        volatility = portfolio_daily_returns.std() * np.sqrt(252)  # Annualized volatility
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / volatility if volatility != 0 else 0
        
        # Calculate Value at Risk (VaR)
        var_95 = np.percentile(portfolio_daily_returns, 5) * total_value
        var_99 = np.percentile(portfolio_daily_returns, 1) * total_value
        
        return {
            "total_value": float(total_value),
            "total_cost": float(total_cost),
            "return": float(portfolio_return),
            "return_pct": float(portfolio_return * 100),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe_ratio),
            "value_at_risk": {
                "var_95": float(var_95),
                "var_99": float(var_99)
            }
        }
    
    def calculate_position_size(self, ticker: str, risk_per_trade: float, account_size: float, stop_loss_pct: float) -> Dict[str, Any]:
        """
        Calculate position size based on risk parameters
        
        Args:
            ticker: Stock symbol
            risk_per_trade: Maximum risk per trade as percentage of account
            account_size: Total account size
            stop_loss_pct: Stop loss percentage
        """
        try:
            df = get_historical_data(ticker, period="1mo")
            if df.empty:
                return {"error": "No data available"}
                
            current_price = df['Close'].iloc[-1]
            atr = self._calculate_atr(df)  # Average True Range for volatility
            
            # Calculate risk amount
            risk_amount = account_size * (risk_per_trade / 100)
            stop_loss_amount = current_price * (stop_loss_pct / 100)
            
            # Calculate position size
            position_size = risk_amount / stop_loss_amount
            position_value = position_size * current_price
            
            # Calculate risk/reward scenarios
            reward_scenarios = {
                "1:1": current_price + stop_loss_amount,
                "2:1": current_price + (2 * stop_loss_amount),
                "3:1": current_price + (3 * stop_loss_amount)
            }
            
            return {
                "position_size": float(position_size),
                "position_value": float(position_value),
                "stop_loss_price": float(current_price - stop_loss_amount),
                "risk_amount": float(risk_amount),
                "volatility_atr": float(atr),
                "reward_targets": {k: float(v) for k, v in reward_scenarios.items()}
            }
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_correlation_matrix(self, tickers: List[str]) -> Dict[str, Any]:
        """Calculate correlation matrix between multiple stocks"""
        try:
            # Get historical data for all stocks
            data = {}
            for ticker in tickers:
                df = get_historical_data(ticker, period="1y")
                if not df.empty:
                    data[ticker] = df['Close']
                    
            if not data:
                return {"error": "No data available"}
                
            # Create DataFrame with all stock prices
            df = pd.DataFrame(data)
            
            # Calculate correlation matrix
            corr_matrix = df.corr()
            
            # Convert correlation matrix to dictionary format
            correlations = {}
            for ticker1 in tickers:
                correlations[ticker1] = {}
                for ticker2 in tickers:
                    if ticker1 in corr_matrix.index and ticker2 in corr_matrix.columns:
                        correlations[ticker1][ticker2] = float(corr_matrix.loc[ticker1, ticker2])
                    else:
                        correlations[ticker1][ticker2] = None
            
            return {
                "correlations": correlations,
                "summary": {
                    "highest_correlation": {
                        "pair": self._get_highest_correlation_pair(corr_matrix),
                        "value": float(corr_matrix.max().max())
                    },
                    "lowest_correlation": {
                        "pair": self._get_lowest_correlation_pair(corr_matrix),
                        "value": float(corr_matrix.min().min())
                    }
                }
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        return float(atr)
    
    def _get_highest_correlation_pair(self, corr_matrix: pd.DataFrame) -> List[str]:
        """Get the pair of stocks with highest correlation"""
        # Set diagonal to -1 to exclude self-correlation
        np.fill_diagonal(corr_matrix.values, -1)
        
        # Find maximum correlation
        i, j = np.unravel_index(corr_matrix.values.argmax(), corr_matrix.values.shape)
        
        return [corr_matrix.index[i], corr_matrix.columns[j]]
    
    def _get_lowest_correlation_pair(self, corr_matrix: pd.DataFrame) -> List[str]:
        """Get the pair of stocks with lowest correlation"""
        # Set diagonal to 1 to exclude self-correlation
        np.fill_diagonal(corr_matrix.values, 1)
        
        # Find minimum correlation
        i, j = np.unravel_index(corr_matrix.values.argmin(), corr_matrix.values.shape)
        
        return [corr_matrix.index[i], corr_matrix.columns[j]] 