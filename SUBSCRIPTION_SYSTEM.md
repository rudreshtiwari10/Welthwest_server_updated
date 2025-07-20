# Subscription System Documentation

## Overview
The subscription system implements tiered access control for WelthWest features, with different limits and capabilities based on the user's subscription level.

## Subscription Tiers

### FREE Tier
- Cost: Free
- Features:
  - 2 backtests per day
  - 5 LLM queries per day
  - Delayed market data
  - Basic technical analysis

### BASIC Tier
- Cost: ₹399/month
- Features:
  - 10 backtests per day
  - 20 LLM queries per day
  - 15-minute delayed market data
  - All FREE tier features

### PRO Tier
- Cost: ₹999/month
- Features:
  - 30 backtests per day
  - 50 LLM queries per day
  - Real-time market data
  - All BASIC tier features

### ENTERPRISE Tier
- Cost: ₹2999/month
- Features:
  - Unlimited backtests
  - Unlimited LLM queries
  - Real-time market data
  - Priority support
  - All PRO tier features

## API Endpoints

### Get Subscription Details
```
GET /api/user/subscription
Authorization: Bearer <jwt_token>

Response:
{
    "tier": "FREE",
    "starts_at": "2024-01-01T00:00:00Z",
    "expires_at": null,
    "usage": {
        "daily": {
            "backtest_count": 0,
            "llm_query_count": 0
        }
    },
    "limits": {
        "backtest_daily_limit": 2,
        "llm_daily_limit": 5,
        "market_data_delay": "delayed"
    }
}
```

### Upgrade Subscription
```
POST /api/user/subscription/upgrade
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
    "tier": "PRO"
}

Response:
{
    "message": "Successfully upgraded to PRO tier"
}
```

### Get Usage Metrics
```
GET /api/user/usage
Authorization: Bearer <jwt_token>

Response:
{
    "tier": "BASIC",
    "daily_usage": {
        "backtest_count": 5,
        "llm_query_count": 10
    },
    "monthly_usage": {
        "backtest_count": 50,
        "llm_query_count": 100
    },
    "limits": {
        "backtest_daily_limit": 10,
        "llm_daily_limit": 20
    }
}
```

## Rate Limiting Headers
The system adds the following headers to API responses:
- `X-Market-Data-Delay`: Current market data delay level
- `X-Subscription-Tier`: Current subscription tier
- `X-Rate-Limit-Backtest`: Daily backtest limit
- `X-Rate-Limit-LLM`: Daily LLM query limit

## Error Responses

### Limit Exceeded
```json
{
    "error": "Subscription limit exceeded",
    "message": "Daily backtest limit reached for your subscription tier",
    "current_tier": "FREE",
    "usage": {
        "backtest": 2
    },
    "limit": 2,
    "upgrade_options": [
        {
            "tier": "BASIC",
            "price": 399,
            "limit": 10
        },
        {
            "tier": "PRO",
            "price": 999,
            "limit": 30
        }
    ]
}
```

## Environment Variables
Configure subscription limits in your .env file:
```
FREE_BACKTEST_LIMIT=2
FREE_LLM_LIMIT=5
BASIC_BACKTEST_LIMIT=10
BASIC_LLM_LIMIT=20
PRO_BACKTEST_LIMIT=30
PRO_LLM_LIMIT=50
USAGE_RESET_HOUR=0
USAGE_RESET_TIMEZONE=Asia/Kolkata
```

## Database Schema
The subscription data is stored in the user document:
```json
{
    "subscription": {
        "tier": "FREE|BASIC|PRO|ENTERPRISE",
        "starts_at": ISODate("2024-01-01T00:00:00Z"),
        "expires_at": ISODate("2024-02-01T00:00:00Z"),
        "usage": {
            "daily": {
                "backtest_count": 0,
                "llm_query_count": 0,
                "last_reset": ISODate("2024-01-01T00:00:00Z")
            },
            "monthly": {
                "backtest_count": 0,
                "llm_query_count": 0,
                "last_reset": ISODate("2024-01-01T00:00:00Z")
            }
        }
    }
}
```

## Usage Reset
- Daily counters reset at midnight in the configured timezone
- Monthly counters reset on the first day of each month
- Reset times are configurable via environment variables

## Protected Features
The following endpoints are protected by subscription limits:
- `/api/backtesting/run` - Limited by backtest count
- `/api/market/chat` - Limited by LLM query count
- `/api/market-indices` - Real-time vs delayed based on tier

## Implementation Details
- Subscription middleware checks and updates usage before allowing access
- Automatic counter resets handled by MongoDB queries
- Rate limit headers added to all responses
- Detailed error messages with upgrade options
- MongoDB indexes on subscription fields for performance 