# Frontend Integration Guide for Indian Stock Market API

This document provides examples and guidance on how to integrate your frontend application with the Indian Stock Market Data API.

## Base URL

For local development:
```
http://localhost:5000
```

## Authentication

Currently, the API does not require authentication. This may change in future versions.

## Common Response Structure

Most API responses follow this general structure:

```json
{
  "data": [...],  // Array of data points or object with data
  "ticker": "RELIANCE",  // The ticker symbol(s) requested
  // Other metadata specific to the endpoint
}
```

Error responses:

```json
{
  "error": "Error message details"
}
```

## Examples

### 1. Fetching Historical Data for Indian Stocks

```javascript
// React example
import { useState, useEffect } from 'react';

function StockChart({ ticker = 'RELIANCE', period = '1y', interval = '1d' }) {
  const [stockData, setStockData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetch(`http://localhost:5000/api/historical?ticker=${ticker}&period=${period}&interval=${interval}`)
      .then(response => {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.json();
      })
      .then(data => {
        setStockData(data);
        setLoading(false);
      })
      .catch(error => {
        setError(error.message);
        setLoading(false);
      });
  }, [ticker, period, interval]);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!stockData || !stockData.data || stockData.data.length === 0) {
    return <div>No data available</div>;
  }

  // Render your chart using stockData.data
  // Example with a chart library like Chart.js or Recharts would go here
  return (
    <div>
      <h2>{ticker} Stock Data</h2>
      <p>Data points: {stockData.data.length}</p>
      {/* Your chart component here */}
    </div>
  );
}
```

### 2. Live Data Dashboard for Indian Stocks

```javascript
// React example for a live data dashboard
function LiveStockDashboard({ tickers = 'RELIANCE,TCS,HDFCBANK' }) {
  const [liveData, setLiveData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Function to fetch data
  const fetchLiveData = async () => {
    try {
      const response = await fetch(`http://localhost:5000/api/live?tickers=${tickers}`);
      const data = await response.json();
      setLiveData(data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching live data:', error);
      setLoading(false);
    }
  };
  
  // Initial fetch
  useEffect(() => {
    fetchLiveData();
    
    // Set up polling every 60 seconds
    const intervalId = setInterval(fetchLiveData, 60000);
    
    // Clean up interval
    return () => clearInterval(intervalId);
  }, [tickers]);
  
  if (loading) return <div>Loading...</div>;
  if (!liveData || !liveData.data) return <div>No data available</div>;
  
  return (
    <div className="live-dashboard">
      <h2>Live Stock Dashboard</h2>
      <button onClick={fetchLiveData}>Refresh</button>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Price</th>
            <th>Change</th>
            <th>Volume</th>
          </tr>
        </thead>
        <tbody>
          {liveData.data.map(stock => (
            <tr key={stock.index}>
              <td>{stock.index}</td>
              <td>₹{stock.price}</td>
              <td>{stock.previousClose ? ((stock.price - stock.previousClose) / stock.previousClose * 100).toFixed(2) + '%' : 'N/A'}</td>
              <td>{stock.volume}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### 3. Stock Comparison for Indian Stocks

```javascript
// Example for comparing multiple Indian stocks
function StockComparison({ tickers = 'RELIANCE,TCS', period = '1y', interval = '1d' }) {
  const [comparisonData, setComparisonData] = useState(null);
  
  useEffect(() => {
    fetch(`http://localhost:5000/api/compare?tickers=${tickers}&period=${period}&interval=${interval}`)
      .then(response => response.json())
      .then(data => setComparisonData(data))
      .catch(error => console.error('Error fetching comparison data:', error));
  }, [tickers, period, interval]);
  
  if (!comparisonData) return <div>Loading...</div>;
  
  // Use normalized_data for better comparison visualization
  // normalized_data contains percentage change from first value
  
  return (
    <div>
      <h2>Stock Comparison</h2>
      {/* Render comparison chart using comparisonData.normalized_data */}
    </div>
  );
}
```

### 4. Indian Market Indices Display

```javascript
// Example for displaying Indian market indices
function MarketIndices() {
  const [indices, setIndices] = useState(null);
  
  useEffect(() => {
   fetch(`http://localhost:5000/api/market-indices`)
      .then(response => response.json())
      .then(data => setIndices(data.indices))
      .catch(error => console.error('Error fetching indices:', error));
  }, []);
  
  if (!indices) return <div>Loading indices...</div>;
  
  return (
    <div className="market-indices">
      <h2>Indian Market Indices</h2>
      <div className="indices-grid">
        {Object.entries(indices).map(([symbol, data]) => (
          <div key={symbol} className="index-card">
            <h3>{data.name}</h3>
            <p className="price">{data.price?.toFixed(2)}</p>
            <p className={`change ${data.percentChange > 0 ? 'positive' : 'negative'}`}>
              {data.change?.toFixed(2)} ({data.percentChange?.toFixed(2)}%)
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 5. Top Gainers and Losers

```javascript
// Example for displaying top gainers and losers
function TopGainersLosers() {
  const [marketData, setMarketData] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    fetch('http://localhost:5000/api/top-gainers-losers')
      .then(response => response.json())
      .then(data => {
        setMarketData(data);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching top gainers/losers:', error);
        setLoading(false);
      });
  }, []);
  
  if (loading) return <div>Loading market data...</div>;
  if (!marketData) return <div>No market data available</div>;
  
  return (
    <div className="market-movers">
      <div className="gainers-section">
        <h2>Top Gainers</h2>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Price</th>
              <th>Change %</th>
            </tr>
          </thead>
          <tbody>
            {marketData.gainers.map(stock => (
              <tr key={stock.symbol}>
                <td>{stock.name || stock.symbol}</td>
                <td>₹{stock.price.toFixed(2)}</td>
                <td className="positive">+{stock.percentChange.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      <div className="losers-section">
        <h2>Top Losers</h2>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Price</th>
              <th>Change %</th>
            </tr>
          </thead>
          <tbody>
            {marketData.losers.map(stock => (
              <tr key={stock.symbol}>
                <td>{stock.name || stock.symbol}</td>
                <td>₹{stock.price.toFixed(2)}</td>
                <td className="negative">{stock.percentChange.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

### 6. Indian Stock Search with Validation

```javascript
// Example for Indian stock search with validation
function StockSearch() {
  const [ticker, setTicker] = useState('');
  const [isValid, setIsValid] = useState(null);
  const [isChecking, setIsChecking] = useState(false);
  
  const validateTicker = async () => {
    if (!ticker) return;
    
    setIsChecking(true);
    try {
      const response = await fetch(`http://localhost:5000/api/validate?ticker=${ticker}`);
      const data = await response.json();
      setIsValid(data.valid);
    } catch (error) {
      console.error('Error validating ticker:', error);
      setIsValid(false);
    } finally {
      setIsChecking(false);
    }
  };
  
  return (
    <div className="stock-search">
      <h2>Search for an Indian Stock</h2>
      <div className="search-form">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Enter ticker symbol (e.g., RELIANCE, TCS)"
        />
        <button onClick={validateTicker} disabled={isChecking || !ticker}>
          {isChecking ? 'Checking...' : 'Search'}
        </button>
      </div>
      
      {isValid !== null && (
        <div className={`validation-result ${isValid ? 'valid' : 'invalid'}`}>
          {isValid ? (
            <p>✓ Valid ticker symbol. You can now view stock data.</p>
          ) : (
            <p>✗ Invalid ticker symbol. Please check and try again.</p>
          )}
        </div>
      )}
      
      {isValid && (
        <button onClick={() => {/* Navigate to stock detail page */}}>
          View {ticker} Data
        </button>
      )}
    </div>
  );
}
```

## Indian Stock Exchange Suffixes

When working with Indian stocks, you can use either the base symbol or the exchange-specific suffix:

- Base symbol (defaults to NSE): `RELIANCE`
- NSE-specific: `RELIANCE.NS` (National Stock Exchange)
- BSE-specific: `RELIANCE.BO` (Bombay Stock Exchange)

The API will automatically try NSE first, then BSE if needed.

## Best Practices

1. **Error Handling**: Always handle API errors gracefully in your frontend.
2. **Loading States**: Show loading indicators while fetching data.
3. **Caching**: Consider caching responses for better performance, especially for historical data that doesn't change frequently.
4. **Throttling**: Limit the frequency of live data requests to avoid unnecessary API calls.
5. **Responsive Design**: Ensure your charts and data displays work well on different screen sizes.

## Common Issues

1. **CORS Issues**: If you encounter CORS errors, make sure the API server has CORS enabled (which it does by default).
2. **Date Formats**: Pay attention to date formats when working with charts. The API returns dates in 'YYYY-MM-DD HH:MM:SS' format.
3. **Empty Responses**: Some stocks might not have data for certain periods or intervals. Always check for empty data arrays.
4. **Market Hours**: Live data might be less accurate outside of Indian market hours (9:15 AM to 3:30 PM IST, Monday to Friday).
5. **Exchange Holidays**: The API may return limited or no data on Indian market holidays.

## Need Help?

For additional assistance, refer to the main README.md file or contact the API development team. 