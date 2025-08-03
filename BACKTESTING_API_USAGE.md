# Comprehensive Backtesting API Usage Guide

## New Endpoint: `/api/backtesting/newrun`

This endpoint replicates your Colab-based backtester exactly within the Flask API, preserving all inputs, outputs, and metrics.

### Request Format

```http
POST /api/backtesting/newrun
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Request Body Parameters

```json
{
  "stock_symbol": "RELIANCE",
  "selected_indicators": {
    "RSI": {
      "period": 14,
      "oversold": 30,
      "overbought": 70
    },
    "MACD": {
      "fast_period": 12,
      "slow_period": 26,
      "signal_period": 9
    },
    "Bollinger_Bands": {
      "period": 20,
      "std_dev": 2
    },
    "Stochastic": {
      "k_period": 14,
      "d_period": 3,
      "oversold": 20,
      "overbought": 80
    },
    "SMA": {
      "periods": [20, 50]
    },
    "EMA": {
      "periods": [12, 26]
    },
    "ADX": {
      "period": 14,
      "threshold": 25
    },
    "Williams_R": {
      "period": 14,
      "oversold": -80,
      "overbought": -20
    },
    "CCI": {
      "period": 20
    },
    "ATR": {
      "period": 14
    },
    "OBV": {}
  },
  "voting_threshold": 0.6,
  "period": "1y",
  "timeframe": "1d",
  "initial_capital": 100000,
  "position_size_pct": 0.1,
  "risk_reward_ratio": 2.0,
  "max_drawdown_pct": 0.05,
  "monte_carlo_simulations": 1000,
  "confidence_level": 0.95
}
```

### Parameter Descriptions

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `stock_symbol` | string | Yes | Stock symbol (e.g., "RELIANCE", "TCS") |
| `selected_indicators` | object | Yes | Technical indicators configuration |
| `voting_threshold` | float | Yes | Minimum voting threshold (0.0-1.0) |
| `period` | string | Yes | Data period ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max") |
| `timeframe` | string | Yes | Data interval ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo") |
| `initial_capital` | float | Yes | Starting capital amount |
| `position_size_pct` | float | Yes | Position size as percentage (0.0-1.0) |
| `risk_reward_ratio` | float | No | Risk-reward ratio (default: 2.0) |
| `max_drawdown_pct` | float | No | Maximum drawdown percentage (default: 0.05) |
| `monte_carlo_simulations` | integer | No | Number of Monte Carlo simulations (default: 0) |
| `confidence_level` | float | No | Confidence level for Monte Carlo (default: 0.95) |

### Available Indicators

1. **RSI (Relative Strength Index)**
   - `period`: Calculation period (default: 14)
   - `oversold`: Oversold threshold (default: 30)
   - `overbought`: Overbought threshold (default: 70)

2. **MACD (Moving Average Convergence Divergence)**
   - `fast_period`: Fast EMA period (default: 12)
   - `slow_period`: Slow EMA period (default: 26)
   - `signal_period`: Signal line period (default: 9)

3. **Bollinger Bands**
   - `period`: Moving average period (default: 20)
   - `std_dev`: Standard deviation multiplier (default: 2)

4. **Stochastic Oscillator**
   - `k_period`: %K calculation period (default: 14)
   - `d_period`: %D smoothing period (default: 3)
   - `oversold`: Oversold threshold (default: 20)
   - `overbought`: Overbought threshold (default: 80)

5. **Simple Moving Average (SMA)**
   - `periods`: Array of periods (e.g., [20, 50])

6. **Exponential Moving Average (EMA)**
   - `periods`: Array of periods (e.g., [12, 26])

7. **ADX (Average Directional Index)**
   - `period`: Calculation period (default: 14)
   - `threshold`: Trend strength threshold (default: 25)

8. **Williams %R**
   - `period`: Calculation period (default: 14)
   - `oversold`: Oversold threshold (default: -80)
   - `overbought`: Overbought threshold (default: -20)

9. **CCI (Commodity Channel Index)**
   - `period`: Calculation period (default: 20)

10. **ATR (Average True Range)**
    - `period`: Calculation period (default: 14)

11. **OBV (On Balance Volume)**
    - No parameters required

### Response Format

```json
{
  "success": true,
  "data": {
    "metrics": {
      "Total_Return": 15234.56,
      "Total_Return_Pct": 15.23,
      "Number_of_Trades": 24,
      "Win_Rate": 62.5,
      "Average_Win": 850.25,
      "Average_Loss": -425.18,
      "Profit_Factor": 2.15,
      "Max_Drawdown": 8.45,
      "Sharpe_Ratio": 1.23,
      "Sortino_Ratio": 1.56,
      "Calmar_Ratio": 1.85,
      "Best_Trade": 2850.75,
      "Worst_Trade": -1245.89,
      "Average_Trade": 634.77,
      "Total_Profits": 20400.50,
      "Total_Losses": 5165.94
    },
    "trades": [
      {
        "Entry_Date": "2023-03-15T00:00:00.000Z",
        "Exit_Date": "2023-03-22T00:00:00.000Z",
        "Entry_Price": 2456.75,
        "Exit_Price": 2589.30,
        "Position_Size": 4.07,
        "Direction": "Long",
        "PnL": 539.36,
        "Return_Pct": 5.39,
        "Exit_Reason": "Take Profit"
      }
    ],
    "equity_curve": [
      {
        "Date": "2023-01-01T00:00:00.000Z",
        "Equity": 100000.00,
        "Capital": 100000.00,
        "Position": 0,
        "Price": 2345.60,
        "Drawdown": 0.0
      }
    ],
    "stock_data": [
      {
        "Date": "2023-01-01T00:00:00.000Z",
        "Open": 2340.50,
        "High": 2367.80,
        "Low": 2335.20,
        "Close": 2345.60,
        "Volume": 1234567,
        "Signal": 0
      }
    ],
    "charts": {
      "candlestick": "{...plotly_json...}",
      "equity_curve": "{...plotly_json...}",
      "drawdown": "{...plotly_json...}"
    },
    "monte_carlo": {
      "statistics": {
        "Mean_Return": 12.45,
        "Std_Return": 8.23,
        "Min_Return": -15.67,
        "Max_Return": 45.89,
        "VaR_95.0%": -8.45,
        "CVaR_95.0%": -12.34,
        "Confidence_Interval_Lower": -8.45,
        "Confidence_Interval_Upper": 33.35,
        "Probability_of_Loss": 25.6
      },
      "results": [
        {
          "Simulation": 1,
          "Final_Return_Pct": 12.45,
          "Final_Capital": 112450.00
        }
      ]
    },
    "summary": {
      "symbol": "RELIANCE",
      "period": "1y",
      "timeframe": "1d",
      "total_data_points": 252,
      "indicators_used": ["RSI", "MACD", "Bollinger_Bands"],
      "voting_threshold": 0.6,
      "backtest_period": {
        "start_date": "2023-01-01",
        "end_date": "2023-12-31"
      }
    }
  }
}
```

### Key Features

1. **Exact Colab Replication**: Same parameter names and structure as your Colab implementation
2. **Comprehensive Metrics**: All performance metrics including Sharpe, Sortino, and Calmar ratios
3. **Interactive Charts**: Candlestick charts with buy/sell signals, equity curve, and drawdown charts
4. **Monte Carlo Analysis**: Optional Monte Carlo simulation for risk assessment
5. **Risk Management**: Built-in stop-loss, take-profit, and maximum drawdown protection
6. **Voting System**: Multi-indicator voting mechanism for signal generation

### Frontend Integration Example

```javascript
// Example function to call the new backtesting endpoint
async function runComprehensiveBacktest(params) {
  try {
    const response = await fetch('/api/backtesting/newrun', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${userToken}`
      },
      body: JSON.stringify(params)
    });

    if (response.ok) {
      const result = await response.json();
      
      // Display metrics
      displayMetrics(result.data.metrics);
      
      // Render charts
      renderChart('candlestick-container', JSON.parse(result.data.charts.candlestick));
      renderChart('equity-container', JSON.parse(result.data.charts.equity_curve));
      renderChart('drawdown-container', JSON.parse(result.data.charts.drawdown));
      
      // Display trades table
      displayTradesTable(result.data.trades);
      
      // Show Monte Carlo results if available
      if (result.data.monte_carlo) {
        displayMonteCarloResults(result.data.monte_carlo);
      }
      
      return result;
    } else {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
  } catch (error) {
    console.error('Backtest error:', error);
    throw error;
  }
}

// Example usage
const backtestParams = {
  stock_symbol: "RELIANCE",
  selected_indicators: {
    RSI: { period: 14, oversold: 30, overbought: 70 },
    MACD: { fast_period: 12, slow_period: 26, signal_period: 9 },
    SMA: { periods: [20, 50] }
  },
  voting_threshold: 0.6,
  period: "1y",
  timeframe: "1d",
  initial_capital: 100000,
  position_size_pct: 0.1,
  risk_reward_ratio: 2.0,
  max_drawdown_pct: 0.05,
  monte_carlo_simulations: 1000,
  confidence_level: 0.95
};

runComprehensiveBacktest(backtestParams)
  .then(result => console.log('Backtest completed:', result))
  .catch(error => console.error('Backtest failed:', error));
```

### Error Handling

The endpoint returns appropriate HTTP status codes:

- `200`: Success
- `400`: Bad request (missing parameters, invalid values)
- `401`: Unauthorized (invalid JWT token)
- `403`: Forbidden (subscription doesn't include backtesting)
- `404`: Not found (no data for symbol)
- `500`: Internal server error

### Performance Considerations

1. **Caching**: Stock data is cached to improve performance
2. **Timeouts**: Long-running backtests may timeout; consider using shorter periods for testing
3. **Rate Limits**: API calls are rate-limited based on subscription tier
4. **Data Limits**: Maximum data points may be limited based on subscription

### Migration from Existing Endpoint

The new `/api/backtesting/newrun` endpoint is designed to replace the existing `/api/backtesting/run` endpoint with:

1. Better parameter naming (matches Colab exactly)
2. More comprehensive output (includes charts and Monte Carlo)
3. Improved risk management
4. Enhanced error handling
5. Better performance metrics

Both endpoints can coexist during the transition period.