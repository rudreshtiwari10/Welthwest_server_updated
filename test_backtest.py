import logging
from services.backtesting_service import BacktestingService
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def main():
    try:
        # Initialize backtesting service
        bs = BacktestingService()
        
        # Set date range
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        # Define indicators
        indicators = [
            {
                'type': 'RSI',
                'parameters': {'period': 14}
            },
            {
                'type': 'MACD',
                'parameters': {
                    'fastperiod': 12,
                    'slowperiod': 26,
                    'signalperiod': 9
                }
            }
        ]
        
        # Run backtest
        logger.info("Starting backtest...")
        result = bs.run_backtest(
            ticker='RELIANCE.NS',
            start_date=start_date,
            end_date=end_date,
            indicators=indicators,
            initial_capital=100000,
            position_size=0.1
        )
        
        # Log performance metrics
        logger.info("\nPerformance Metrics:")
        logger.info(f"Total Return: {result['performance']['total_return']:.2f}%")
        logger.info(f"Annualized Return: {result['performance']['annualized_return']:.2f}%")
        logger.info(f"Sharpe Ratio: {result['performance']['sharpe_ratio']:.2f}")
        logger.info(f"Max Drawdown: {result['performance']['max_drawdown']:.2f}%")
        logger.info(f"Win Rate: {result['performance']['win_rate']:.2f}%")
        
        # Validate metrics
        logger.info("\nValidating metrics...")
        assert not np.isnan(result['performance']['total_return']), "Total return is NaN"
        assert not np.isnan(result['performance']['annualized_return']), "Annualized return is NaN"
        assert not np.isnan(result['performance']['sharpe_ratio']), "Sharpe ratio is NaN"
        assert not np.isnan(result['performance']['max_drawdown']), "Max drawdown is NaN"
        assert not np.isnan(result['performance']['win_rate']), "Win rate is NaN"
        
        logger.info("All metrics validated successfully!")
        
    except Exception as e:
        logger.error(f"Error in test: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main() 