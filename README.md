# Indian Stock Market Data API

A Flask-based REST API for retrieving Indian stock market data using Yahoo Finance.

## Features

- Historical stock data retrieval for Indian markets
- Live (latest) stock data retrieval
- OHLC data for specific date ranges
- Stock comparison functionality
- Statistical analysis of stock data
- Ticker symbol validation
- Indian market indices data
- Top gainers and losers
- User authentication with JWT
- User profile management

## Project Structure

```
.
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── requirements.txt       # Python dependencies
├── run.py                 # Script to run the application
├── .env                   # Environment variables (create this file locally)
├── services/
│   ├── stock_service.py   # Core stock data functionality
│   ├── user_service.py    # User authentication and management
│   └── utils.py           # Utility functions
```

## API Endpoints

### Authentication

#### Register User

```
POST /api/auth/register
```

Request Body:
```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "Password123!",
  "confirm_password": "Password123!"
}
```

Response:
```json
{
  "message": "Registration successful",
  "user": {
    "id": "user_id",
    "username": "testuser",
    "email": "test@example.com",
    "first_name": "",
    "last_name": "",
    "avatar_url": ""
  },
  "access_token": "jwt_access_token",
  "refresh_token": "jwt_refresh_token"
}
```

Technical Analysis:
- GET /api/indicators?ticker=RELIANCE&indicators=rsi,macd,bollinger
- GET /api/screener?criteria=rsi<30,volume>1000000
- GET /api/intraday?ticker=RELIANCE&interval=5m
- GET /api/signals?ticker=RELIANCE
- GET /api/levels?ticker=RELIANCE
- GET /api/patterns?ticker=RELIANCE

Portfolio Management:
- GET /api/portfolio/performance
- POST /api/portfolio/add
- POST /api/risk-calculator
- GET /api/correlation?tickers=RELIANCE,TCS,INFY

Market Intelligence:
- GET /api/market-breadth

#### Login User

```
POST /api/auth/login
```

Request Body:
```json
{
  "username_or_email": "testuser",
  "password": "Password123!"
}
```

Response:
```json
{
  "message": "Login successful",
  "user": {
    "id": "user_id",
    "username": "testuser",
    "email": "test@example.com",
    "first_name": "",
    "last_name": "",
    "avatar_url": ""
  },
  "access_token": "jwt_access_token",
  "refresh_token": "jwt_refresh_token"
}
```

#### Get Current User

```
GET /api/auth/me
```

Headers:
```
Authorization: Bearer jwt_access_token
```

Response:
```json
{
  "user": {
    "id": "user_id",
    "username": "testuser",
    "email": "test@example.com",
    "first_name": "",
    "last_name": "",
    "avatar_url": ""
  }
}
```

#### Update User Profile

```
PUT /api/auth/profile
```

Headers:
```
Authorization: Bearer jwt_access_token
```

Request Body:
```json
{
  "first_name": "Test",
  "last_name": "User",
  "avatar_url": "https://example.com/avatar.jpg"
}
```

Response:
```json
{
  "message": "Profile updated successfully",
  "user": {
    "id": "user_id",
    "username": "testuser",
    "email": "test@example.com",
    "first_name": "Test",
    "last_name": "User",
    "avatar_url": "https://example.com/avatar.jpg"
  }
}
```

#### Refresh Access Token

```
POST /api/auth/refresh
```

Request Body:
```json
{
  "refresh_token": "jwt_refresh_token"
}
```

Response:
```json
{
  "access_token": "new_jwt_access_token",
  "user": {
    "id": "user_id",
    "username": "testuser",
    "email": "test@example.com",
    "first_name": "Test",
    "last_name": "User",
    "avatar_url": "https://example.com/avatar.jpg"
  }
}
```

#### Logout User

```
POST /api/auth/logout
```

Request Body:
```json
{
  "refresh_token": "jwt_refresh_token"
}
```

Response:
```json
{
  "message": "Logout successful"
}
```

### Historical Data

```
GET /api/historical?ticker=RELIANCE&period=1y&interval=1d
```

Parameters:
- `ticker`: Stock ticker symbol (default: RELIANCE)
- `period`: Time period (default: 1y)
- `interval`: Data interval (default: 1d)

### OHLC Data

```
GET /api/ohlc?ticker=TCS&start_date=2023-01-01&end_date=2023-12-31&interval=1d
```

Parameters:
- `ticker`: Stock ticker symbol (default: RELIANCE)
- `start_date`: Start date in format YYYY-MM-DD (default: 1 year ago)
- `end_date`: End date in format YYYY-MM-DD (default: today)
- `interval`: Data interval (default: 1d)

### Live Data

```
GET /api/live?tickers=RELIANCE,TCS,INFY
```

Parameters:
- `tickers`: Comma-separated list of ticker symbols (default: RELIANCE)

### Validate Ticker

```
GET /api/validate?ticker=RELIANCE
```

Parameters:
- `ticker`: Stock ticker symbol to validate

### Compare Stocks

```
GET /api/compare?tickers=RELIANCE,TCS&period=1y&interval=1d
```

Parameters:
- `tickers`: Comma-separated list of ticker symbols (default: RELIANCE,TCS)
- `period`: Time period (default: 1y)
- `interval`: Data interval (default: 1d)

### Stock Statistics

```
GET /api/statistics?ticker=RELIANCE&period=1y&interval=1d
```

Parameters:
- `ticker`: Stock ticker symbol (default: RELIANCE)
- `period`: Time period (default: 1y)
- `interval`: Data interval (default: 1d)

### Market Indices

```
GET /api/market-indices
```

Returns data for major Indian market indices:
- NIFTY 50 (^NSEI)
- SENSEX (^BSESN)
- NIFTY IT (^CNXIT)
- NIFTY BANK (^NSEBANK)

### Top Gainers and Losers

```
GET /api/top-gainers-losers
```

Returns the top 5 gainers and losers in the Indian market for the day.

### Health Check

```
GET /health
```

Returns the health status of the API.

## Indian Market Support

For Indian stocks, you can use either the base ticker symbol or include the exchange suffix:

- Without suffix: `RELIANCE` (will default to NSE)
- With NSE suffix: `RELIANCE.NS` (National Stock Exchange)
- With BSE suffix: `RELIANCE.BO` (Bombay Stock Exchange)

The API supports major Indian indices:
- NIFTY 50 (^NSEI)
- SENSEX (^BSESN)
- NIFTY IT (^CNXIT)
- NIFTY BANK (^NSEBANK)

## Popular Indian Stocks

The API has built-in support for validating popular Indian stocks, including:
- RELIANCE (Reliance Industries)
- TCS (Tata Consultancy Services)
- HDFCBANK (HDFC Bank)
- INFY (Infosys)
- ICICIBANK (ICICI Bank)
- SBIN (State Bank of India)
- HINDUNILVR (Hindustan Unilever)
- BHARTIARTL (Bharti Airtel)
- ITC (ITC Limited)
- And many more...

## Time Period Options

- `1d`: 1 day
- `5d`: 5 days
- `1mo`: 1 month
- `3mo`: 3 months
- `6mo`: 6 months
- `1y`: 1 year
- `2y`: 2 years
- `5y`: 5 years
- `10y`: 10 years
- `ytd`: Year to date
- `max`: Maximum available data

## Interval Options

- `1m`: 1 minute
- `2m`: 2 minutes
- `5m`: 5 minutes
- `15m`: 15 minutes
- `30m`: 30 minutes
- `60m`: 60 minutes
- `90m`: 90 minutes
- `1h`: 1 hour
- `1d`: 1 day
- `5d`: 5 days
- `1wk`: 1 week
- `1mo`: 1 month
- `3mo`: 3 months

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following content:
   ```
   FLASK_ENV=development
   PORT=5000
   ```
4. Run the application:
   ```
   python run.py
   ```

## Usage with Frontend

This API is designed to work with a frontend application. Make sure your frontend makes requests to the appropriate endpoints.

Example frontend usage with JavaScript:

```javascript
// Fetch historical data for an Indian stock
fetch('http://localhost:5000/api/historical?ticker=RELIANCE&period=1y&interval=1d')
  .then(response => response.json())
  .then(data => console.log(data));

// Fetch OHLC data with specific date range
fetch('http://localhost:5000/api/ohlc?ticker=TCS&start_date=2023-01-01&end_date=2023-12-31&interval=1d')
  .then(response => response.json())
  .then(data => console.log(data));

// Fetch market indices
fetch('http://localhost:5000/api/market-indices')
  .then(response => response.json())
  .then(data => console.log(data));

// Fetch top gainers and losers
fetch('http://localhost:5000/api/top-gainers-losers')
  .then(response => response.json())
  .then(data => console.log(data));
```

## Future Enhancements

- Add authentication for API endpoints
- Implement rate limiting
- Add caching for frequently requested data
- Add technical indicators (moving averages, RSI, MACD, etc.)
- Support for more Indian indices and sectors
- Historical options data for Indian markets 