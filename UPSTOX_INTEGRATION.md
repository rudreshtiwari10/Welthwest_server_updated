# Upstox API Integration Guide

## Overview

This project now supports **Upstox API** as the primary data source for Indian stock market data, with **Yahoo Finance** as a fallback option. This integration provides:

- Real-time market data
- Historical stock data
- Market indices information
- Live stock quotes
- OAuth-based authentication

## Features

### Primary Data Source: Upstox API
- ✅ Real-time stock prices
- ✅ Historical OHLCV data
- ✅ Market indices (NIFTY, SENSEX, BANKNIFTY)
- ✅ Live market quotes
- ✅ OAuth 2.0 authentication
- ✅ Automatic caching for performance

### Fallback Data Source: Yahoo Finance
- ✅ Automatic fallback when Upstox is unavailable
- ✅ Supports NSE and BSE data
- ✅ No authentication required
- ✅ Reliable backup option

## Setup Instructions

### 1. Get Upstox API Credentials

1. Visit [Upstox Developer Portal](https://upstox.com/developer/)
2. Create a developer account
3. Create a new app to get:
   - **API Key** (Client ID)
   - **API Secret** (Client Secret)
   - **Redirect URI** (e.g., `http://localhost:8000/api/upstox/callback`)

### 2. Configure Environment Variables

Add the following to your `.env` file:

```env
# Upstox API Configuration
UPSTOX_API_KEY=your-upstox-api-key
UPSTOX_API_SECRET=your-upstox-api-secret
UPSTOX_REDIRECT_URI=http://localhost:8000/api/upstox/callback
```

### 3. Install Dependencies

The required dependencies are already added to `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4. Authentication Flow

#### Option A: Using the API Endpoints (Recommended)

1. **Get Login URL**:
   ```bash
   curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        http://localhost:8000/api/upstox/login-url
   ```

2. **Visit the Login URL** and authorize your app

3. **Handle the Callback** - The system will automatically handle the OAuth callback

4. **Check Status**:
   ```bash
   curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        http://localhost:8000/api/upstox/status
   ```

#### Option B: Manual Token Setting

If you already have an access token:

```bash
curl -X POST \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -d '{"access_token": "YOUR_UPSTOX_ACCESS_TOKEN"}' \
     http://localhost:8000/api/upstox/set-token
```

## API Endpoints

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/api/upstox/login-url` | Get OAuth login URL | JWT |
| GET | `/api/upstox/callback` | Handle OAuth callback | No |
| POST | `/api/upstox/set-token` | Set access token manually | JWT |
| GET | `/api/upstox/status` | Check connection status | JWT |

### Data Endpoints (Modified to use Upstox)

All existing data endpoints now use Upstox as primary source:

| Method | Endpoint | Description | Primary Source |
|--------|----------|-------------|----------------|
| GET | `/api/historical` | Historical data | Upstox → Yahoo Finance |
| GET | `/api/live` | Live stock data | Upstox → Yahoo Finance |
| GET | `/api/market-indices` | Market indices | Upstox → Yahoo Finance |
| GET | `/api/ohlc` | OHLC data | Upstox → Yahoo Finance |

## Code Examples

### Python Client Example

```python
import requests

# 1. Get login URL
response = requests.get(
    'http://localhost:8000/api/upstox/login-url',
    headers={'Authorization': 'Bearer YOUR_JWT_TOKEN'}
)
login_url = response.json()['login_url']
print(f"Visit: {login_url}")

# 2. After authorization, check status
response = requests.get(
    'http://localhost:8000/api/upstox/status',
    headers={'Authorization': 'Bearer YOUR_JWT_TOKEN'}
)
print(response.json())

# 3. Fetch historical data (now uses Upstox)
response = requests.get(
    'http://localhost:8000/api/historical?symbol=RELIANCE&period=1mo'
)
data = response.json()
```

### JavaScript/Frontend Example

```javascript
// Get login URL
const getUpstoxLoginUrl = async () => {
  const response = await fetch('/api/upstox/login-url', {
    headers: {
      'Authorization': `Bearer ${jwtToken}`
    }
  });
  const data = await response.json();
  window.open(data.login_url, '_blank');
};

// Check connection status
const checkUpstoxStatus = async () => {
  const response = await fetch('/api/upstox/status', {
    headers: {
      'Authorization': `Bearer ${jwtToken}`
    }
  });
  const status = await response.json();
  console.log('Upstox Status:', status);
};
```

## Testing

### Run Integration Tests

```bash
# Test basic integration (fallback to Yahoo Finance)
python test_upstox_integration.py

# Test with actual Upstox token
python test_upstox_integration.py --token YOUR_ACCESS_TOKEN
```

### Manual Testing

1. **Test Fallback Mechanism**:
   ```bash
   curl "http://localhost:8000/api/historical?symbol=RELIANCE&period=1mo"
   ```

2. **Test with Upstox Token**:
   ```bash
   # Set token first
   curl -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        -d '{"access_token": "YOUR_UPSTOX_TOKEN"}' \
        http://localhost:8000/api/upstox/set-token
   
   # Then test data fetching
   curl "http://localhost:8000/api/historical?symbol=RELIANCE&period=1mo"
   ```

## Architecture

### Data Flow

```
Client Request
    ↓
Stock Service
    ↓
Try Upstox API (Primary)
    ↓
If Upstox fails or unavailable
    ↓
Fallback to Yahoo Finance
    ↓
Return Data to Client
```

### Key Components

1. **`upstox_service.py`**: Core Upstox API integration
2. **`stock_service.py`**: Modified to use Upstox as primary
3. **`app.py`**: Added authentication endpoints
4. **`config.py`**: Environment configuration
5. **`test_upstox_integration.py`**: Integration tests

## Troubleshooting

### Common Issues

1. **"Access token not set"**
   - Solution: Complete the OAuth flow or set token manually

2. **"Failed to generate login URL"**
   - Check if `UPSTOX_API_KEY` and `UPSTOX_API_SECRET` are set correctly

3. **"Authentication failed"**
   - Verify your API credentials are correct
   - Check if redirect URI matches your app configuration

4. **Data not from Upstox**
   - Check if access token is valid
   - Verify token is set using `/api/upstox/status`

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Logs to Check

- **Upstox API calls**: Look for "Attempting to fetch data from Upstox"
- **Fallback triggers**: Look for "falling back to Yahoo Finance"
- **Authentication**: Look for "Upstox authentication successful"

## Production Considerations

### Security
- Store API credentials securely
- Use environment variables, not hardcoded values
- Implement token refresh mechanism
- Use HTTPS in production

### Performance
- Caching is enabled by default (10 minutes for historical data)
- Monitor API rate limits
- Implement circuit breaker pattern for resilience

### Monitoring
- Track API success rates
- Monitor fallback usage
- Set up alerts for authentication failures

## Rate Limits

### Upstox API Limits
- Check current limits in [Upstox documentation](https://upstox.com/developer/api-documentation/)
- Implement rate limiting in your application

### Yahoo Finance Fallback
- No official rate limits
- Implement reasonable delays between requests

## Support

For issues related to:
- **Upstox API**: Contact [Upstox Support](https://upstox.com/support/)
- **This Integration**: Check the logs and test with the provided test script
- **General Issues**: Review the troubleshooting section above

## Changelog

### v1.0.0 (Current)
- ✅ Initial Upstox API integration
- ✅ OAuth 2.0 authentication flow
- ✅ Fallback to Yahoo Finance
- ✅ Historical data support
- ✅ Live data support
- ✅ Market indices support
- ✅ Comprehensive test suite
- ✅ API endpoints for authentication

### Future Enhancements
- 🔄 Token refresh automation
- 🔄 WebSocket support for real-time data
- 🔄 Advanced order management
- 🔄 Portfolio tracking integration
- 🔄 Options data support 