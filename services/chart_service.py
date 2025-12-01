"""
Chart Generation Service - Create visual charts with base64 encoding

Generates professional financial charts using matplotlib:
- Price charts with moving averages
- RSI charts
- MACD charts
- Bollinger Bands charts
- Combined technical analysis charts
- Backtest equity curves

All charts are exported as base64-encoded PNG images for easy embedding in JSON responses
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
import io
import base64
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChartService:
    """
    Professional financial chart generation service
    """

    def __init__(self):
        # Set default styling
        plt.style.use('seaborn-v0_8-darkgrid')
        self.default_figsize = (12, 8)
        self.default_dpi = 100

    def _fig_to_base64(self, fig: Figure) -> str:
        """
        Convert matplotlib figure to base64-encoded PNG string

        Args:
            fig: Matplotlib figure object

        Returns:
            Base64-encoded PNG image string
        """
        try:
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', dpi=self.default_dpi, bbox_inches='tight')
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            buffer.close()
            plt.close(fig)
            return img_base64
        except Exception as e:
            logger.error(f"Error converting figure to base64: {str(e)}")
            plt.close(fig)
            return ""

    def create_price_chart(self, data: Dict[str, Any], title: str = None) -> str:
        """
        Create a price chart with moving averages

        Args:
            data: Dictionary containing dates, close prices, and moving averages
            title: Chart title

        Returns:
            Base64-encoded PNG image
        """
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize)

            dates = pd.to_datetime(data['dates'])
            close = data['close']

            # Plot price
            ax.plot(dates, close, label='Close Price', color='#2E86AB', linewidth=2)

            # Plot moving averages if available
            if 'sma_20' in data and data['sma_20']:
                ax.plot(dates, data['sma_20'], label='SMA 20', color='#A23B72', linestyle='--', linewidth=1.5)

            if 'sma_50' in data and data['sma_50']:
                ax.plot(dates, data['sma_50'], label='SMA 50', color='#F18F01', linestyle='--', linewidth=1.5)

            if 'ema_20' in data and data['ema_20']:
                ax.plot(dates, data['ema_20'], label='EMA 20', color='#C73E1D', linestyle=':', linewidth=1.5, alpha=0.7)

            # Formatting
            ax.set_xlabel('Date', fontsize=12, fontweight='bold')
            ax.set_ylabel('Price', fontsize=12, fontweight='bold')
            ax.set_title(title or 'Stock Price Chart', fontsize=14, fontweight='bold')
            ax.legend(loc='best', framealpha=0.9)
            ax.grid(True, alpha=0.3)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating price chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""

    def create_rsi_chart(self, data: Dict[str, Any], title: str = None) -> str:
        """
        Create an RSI chart with overbought/oversold zones

        Args:
            data: Dictionary containing dates and RSI values
            title: Chart title

        Returns:
            Base64-encoded PNG image
        """
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize)

            dates = pd.to_datetime(data['dates'])
            rsi = data['rsi']

            # Plot RSI
            ax.plot(dates, rsi, label='RSI (14)', color='#2E86AB', linewidth=2)

            # Add overbought/oversold zones
            ax.axhline(y=70, color='#C73E1D', linestyle='--', linewidth=1, label='Overbought (70)')
            ax.axhline(y=30, color='#06A77D', linestyle='--', linewidth=1, label='Oversold (30)')
            ax.fill_between(dates, 70, 100, alpha=0.1, color='#C73E1D')
            ax.fill_between(dates, 0, 30, alpha=0.1, color='#06A77D')

            # Formatting
            ax.set_xlabel('Date', fontsize=12, fontweight='bold')
            ax.set_ylabel('RSI', fontsize=12, fontweight='bold')
            ax.set_title(title or 'Relative Strength Index (RSI)', fontsize=14, fontweight='bold')
            ax.legend(loc='best', framealpha=0.9)
            ax.grid(True, alpha=0.3)
            ax.set_ylim(0, 100)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating RSI chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""

    def create_macd_chart(self, data: Dict[str, Any], title: str = None) -> str:
        """
        Create a MACD chart with signal line and histogram

        Args:
            data: Dictionary containing dates, MACD, signal, and histogram
            title: Chart title

        Returns:
            Base64-encoded PNG image
        """
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize)

            dates = pd.to_datetime(data['dates'])
            macd = data['macd']
            signal = data['macd_signal']

            # Calculate histogram
            histogram = [m - s for m, s in zip(macd, signal)]

            # Plot MACD and signal lines
            ax.plot(dates, macd, label='MACD', color='#2E86AB', linewidth=2)
            ax.plot(dates, signal, label='Signal', color='#F18F01', linewidth=2)

            # Plot histogram
            colors = ['#06A77D' if h >= 0 else '#C73E1D' for h in histogram]
            ax.bar(dates, histogram, label='Histogram', color=colors, alpha=0.3, width=0.8)

            # Add zero line
            ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5, alpha=0.5)

            # Formatting
            ax.set_xlabel('Date', fontsize=12, fontweight='bold')
            ax.set_ylabel('MACD', fontsize=12, fontweight='bold')
            ax.set_title(title or 'MACD (Moving Average Convergence Divergence)', fontsize=14, fontweight='bold')
            ax.legend(loc='best', framealpha=0.9)
            ax.grid(True, alpha=0.3)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating MACD chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""

    def create_bollinger_bands_chart(self, data: Dict[str, Any], title: str = None) -> str:
        """
        Create a Bollinger Bands chart

        Args:
            data: Dictionary containing dates, close prices, and Bollinger Bands
            title: Chart title

        Returns:
            Base64-encoded PNG image
        """
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize)

            dates = pd.to_datetime(data['dates'])
            close = data['close']
            bb_upper = data['bb_upper']
            bb_middle = data['bb_middle']
            bb_lower = data['bb_lower']

            # Plot price
            ax.plot(dates, close, label='Close Price', color='#2E86AB', linewidth=2)

            # Plot Bollinger Bands
            ax.plot(dates, bb_upper, label='Upper Band', color='#C73E1D', linestyle='--', linewidth=1.5, alpha=0.7)
            ax.plot(dates, bb_middle, label='Middle Band (SMA 20)', color='#F18F01', linestyle='--', linewidth=1.5)
            ax.plot(dates, bb_lower, label='Lower Band', color='#06A77D', linestyle='--', linewidth=1.5, alpha=0.7)

            # Fill between bands
            ax.fill_between(dates, bb_lower, bb_upper, alpha=0.1, color='gray')

            # Formatting
            ax.set_xlabel('Date', fontsize=12, fontweight='bold')
            ax.set_ylabel('Price', fontsize=12, fontweight='bold')
            ax.set_title(title or 'Bollinger Bands', fontsize=14, fontweight='bold')
            ax.legend(loc='best', framealpha=0.9)
            ax.grid(True, alpha=0.3)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating Bollinger Bands chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""

    def create_comprehensive_chart(self, data: Dict[str, Any], symbol: str = None) -> str:
        """
        Create a comprehensive multi-panel chart with price, RSI, and MACD

        Args:
            data: Dictionary containing all indicator data
            symbol: Stock symbol for title

        Returns:
            Base64-encoded PNG image
        """
        try:
            # Create figure with subplots
            fig = plt.figure(figsize=(14, 10))
            gs = GridSpec(3, 1, height_ratios=[2, 1, 1], hspace=0.3)

            dates = pd.to_datetime(data['dates'])

            # Panel 1: Price + Bollinger Bands + Moving Averages
            ax1 = fig.add_subplot(gs[0])
            ax1.plot(dates, data['close'], label='Close Price', color='#2E86AB', linewidth=2, zorder=5)

            if 'bb_upper' in data and data['bb_upper']:
                ax1.plot(dates, data['bb_upper'], label='BB Upper', color='#C73E1D', linestyle='--', linewidth=1, alpha=0.5)
                ax1.plot(dates, data['bb_middle'], label='BB Middle', color='gray', linestyle='--', linewidth=1, alpha=0.5)
                ax1.plot(dates, data['bb_lower'], label='BB Lower', color='#06A77D', linestyle='--', linewidth=1, alpha=0.5)
                ax1.fill_between(dates, data['bb_lower'], data['bb_upper'], alpha=0.05, color='gray')

            if 'sma_20' in data and data['sma_20']:
                ax1.plot(dates, data['sma_20'], label='SMA 20', color='#A23B72', linestyle=':', linewidth=1.5)

            if 'sma_50' in data and data['sma_50']:
                ax1.plot(dates, data['sma_50'], label='SMA 50', color='#F18F01', linestyle=':', linewidth=1.5)

            ax1.set_ylabel('Price', fontsize=11, fontweight='bold')
            ax1.set_title(f'Technical Analysis - {symbol or "Stock"}', fontsize=14, fontweight='bold')
            ax1.legend(loc='best', fontsize=9, framealpha=0.9)
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

            # Panel 2: RSI
            ax2 = fig.add_subplot(gs[1], sharex=ax1)
            if 'rsi' in data and data['rsi']:
                ax2.plot(dates, data['rsi'], label='RSI (14)', color='#2E86AB', linewidth=2)
                ax2.axhline(y=70, color='#C73E1D', linestyle='--', linewidth=1, alpha=0.7)
                ax2.axhline(y=30, color='#06A77D', linestyle='--', linewidth=1, alpha=0.7)
                ax2.fill_between(dates, 70, 100, alpha=0.1, color='#C73E1D')
                ax2.fill_between(dates, 0, 30, alpha=0.1, color='#06A77D')
                ax2.set_ylim(0, 100)

            ax2.set_ylabel('RSI', fontsize=11, fontweight='bold')
            ax2.legend(loc='best', fontsize=9, framealpha=0.9)
            ax2.grid(True, alpha=0.3)

            # Panel 3: MACD
            ax3 = fig.add_subplot(gs[2], sharex=ax1)
            if 'macd' in data and data['macd']:
                ax3.plot(dates, data['macd'], label='MACD', color='#2E86AB', linewidth=2)
                ax3.plot(dates, data['macd_signal'], label='Signal', color='#F18F01', linewidth=2)

                histogram = [m - s for m, s in zip(data['macd'], data['macd_signal'])]
                colors = ['#06A77D' if h >= 0 else '#C73E1D' for h in histogram]
                ax3.bar(dates, histogram, color=colors, alpha=0.3, width=0.8)
                ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5, alpha=0.5)

            ax3.set_ylabel('MACD', fontsize=11, fontweight='bold')
            ax3.set_xlabel('Date', fontsize=11, fontweight='bold')
            ax3.legend(loc='best', fontsize=9, framealpha=0.9)
            ax3.grid(True, alpha=0.3)
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha='right')

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating comprehensive chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""

    def create_backtest_chart(self, equity_curve: List[float], dates: List[str],
                             trades: List[Dict] = None, title: str = None) -> str:
        """
        Create a backtest equity curve chart

        Args:
            equity_curve: List of portfolio values over time
            dates: List of dates corresponding to equity values
            trades: Optional list of trade dictionaries with 'date', 'type', 'price'
            title: Chart title

        Returns:
            Base64-encoded PNG image
        """
        try:
            fig, ax = plt.subplots(figsize=self.default_figsize)

            dates_dt = pd.to_datetime(dates)

            # Plot equity curve
            ax.plot(dates_dt, equity_curve, label='Portfolio Value', color='#2E86AB', linewidth=2)

            # Mark buy/sell points if trades provided
            if trades:
                buy_dates = [pd.to_datetime(t['date']) for t in trades if t.get('type') == 'buy']
                buy_prices = [t.get('portfolio_value', 0) for t in trades if t.get('type') == 'buy']
                sell_dates = [pd.to_datetime(t['date']) for t in trades if t.get('type') == 'sell']
                sell_prices = [t.get('portfolio_value', 0) for t in trades if t.get('type') == 'sell']

                if buy_dates and buy_prices:
                    ax.scatter(buy_dates, buy_prices, color='#06A77D', marker='^',
                             s=100, label='Buy', zorder=5)
                if sell_dates and sell_prices:
                    ax.scatter(sell_dates, sell_prices, color='#C73E1D', marker='v',
                             s=100, label='Sell', zorder=5)

            # Add horizontal line at starting value
            if equity_curve:
                ax.axhline(y=equity_curve[0], color='gray', linestyle='--',
                          linewidth=1, alpha=0.5, label='Initial Value')

            # Formatting
            ax.set_xlabel('Date', fontsize=12, fontweight='bold')
            ax.set_ylabel('Portfolio Value ($)', fontsize=12, fontweight='bold')
            ax.set_title(title or 'Backtest Equity Curve', fontsize=14, fontweight='bold')
            ax.legend(loc='best', framealpha=0.9)
            ax.grid(True, alpha=0.3)

            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            # Format y-axis as currency
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating backtest chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""

    def create_screener_comparison_chart(self, screener_results: List[Dict],
                                        metric: str = 'rsi', title: str = None) -> str:
        """
        Create a bar chart comparing screener results

        Args:
            screener_results: List of stock dictionaries with metrics
            metric: Metric to compare (rsi, score, etc.)
            title: Chart title

        Returns:
            Base64-encoded PNG image
        """
        try:
            fig, ax = plt.subplots(figsize=(12, 6))

            symbols = [r['symbol'] for r in screener_results[:20]]  # Top 20
            values = [r.get(metric, 0) for r in screener_results[:20]]

            # Color bars based on value
            colors = ['#06A77D' if v > 50 else '#C73E1D' for v in values]

            bars = ax.barh(symbols, values, color=colors, alpha=0.7)

            # Add value labels on bars
            for bar, value in zip(bars, values):
                width = bar.get_width()
                ax.text(width, bar.get_y() + bar.get_height()/2,
                       f'{value:.1f}', ha='left', va='center', fontsize=9)

            # Formatting
            ax.set_xlabel(metric.upper(), fontsize=12, fontweight='bold')
            ax.set_ylabel('Symbol', fontsize=12, fontweight='bold')
            ax.set_title(title or f'Top Stocks by {metric.upper()}', fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3, axis='x')

            plt.tight_layout()
            return self._fig_to_base64(fig)

        except Exception as e:
            logger.error(f"Error creating screener comparison chart: {str(e)}")
            if 'fig' in locals():
                plt.close(fig)
            return ""


# Singleton instance
chart_service = ChartService()


# Helper functions for easy access
def generate_chart(data: Dict[str, Any], chart_type: str = 'comprehensive', **kwargs) -> str:
    """
    Generate a chart based on type

    Args:
        data: Chart data
        chart_type: Type of chart (price, rsi, macd, bollinger, comprehensive, backtest, screener)
        **kwargs: Additional arguments passed to chart function

    Returns:
        Base64-encoded PNG image
    """
    chart_methods = {
        'price': chart_service.create_price_chart,
        'rsi': chart_service.create_rsi_chart,
        'macd': chart_service.create_macd_chart,
        'bollinger': chart_service.create_bollinger_bands_chart,
        'comprehensive': chart_service.create_comprehensive_chart,
        'backtest': chart_service.create_backtest_chart,
        'screener': chart_service.create_screener_comparison_chart
    }

    method = chart_methods.get(chart_type, chart_service.create_comprehensive_chart)
    return method(data, **kwargs)
