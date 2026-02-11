# Risk Calculator Phase 1 - API Documentation

## Overview

The Risk Calculator Phase 1 provides analytical tools for position sizing and trading cost calculation. This is a theoretical risk and cost illustration tool - **NOT a trading recommendation system**.

### SEBI Compliance
- All outputs are theoretical illustrations based on user inputs
- No trading recommendations or advice provided
- Clear disclaimers on all responses
- User-driven calculations only

---

## Base URL

```
/api/risk-calculator
```

---

## Authentication

All endpoints require JWT authentication unless otherwise specified.

**Header:**
```
Authorization: Bearer <your_jwt_token>
```

---

## Endpoints

### 1. Calculate Position Size & Costs

**POST** `/api/risk-calculator/calculate`

Main endpoint for Phase 1 - calculates position size, risk, and all trading costs.

#### Request Body

```json
{
  "symbol": "RELIANCE",
  "trade_type": "delivery",
  "buy_price": 2500,
  "stop_loss_price": 2450,
  "target_price": 2600,
  "capital_available": 100000,
  "max_risk_per_trade": 2,
  "max_risk_type": "percentage",
  "broker": "zerodha"
}
```

#### Parameters

| Parameter | Type | Required | Description | Valid Values |
|-----------|------|----------|-------------|--------------|
| symbol | string | Yes | Stock symbol | Any valid symbol (e.g., "RELIANCE", "TCS") |
| trade_type | string | Yes | Type of trade | `delivery`, `intraday`, `fno` |
| buy_price | number | Yes | Entry price | Positive number |
| stop_loss_price | number | Yes | Stop loss price | Must be below buy_price |
| target_price | number | No | Target price (optional) | Positive number |
| capital_available | number | Yes | Total capital available | Positive number |
| max_risk_per_trade | number | Yes | Maximum risk per trade | Positive number |
| max_risk_type | string | Yes | Risk type | `percentage` or `rupees` |
| broker | string | Yes | Broker name | `zerodha`, `upstox`, `custom` |

#### Response (200 OK)

```json
{
  "success": true,
  "data": {
    "symbol": "RELIANCE",
    "trade_type": "delivery",
    "broker": "zerodha",
    "inputs": {
      "buy_price": 2500,
      "stop_loss_price": 2450,
      "target_price": 2600,
      "capital_available": 100000,
      "max_risk_per_trade": 2,
      "max_risk_type": "percentage"
    },
    "position_sizing": {
      "max_quantity": 40,
      "position_value": 100000,
      "risk_per_share": 50,
      "message": "With your risk settings, maximum quantity is 40 shares."
    },
    "risk_analysis": {
      "risk_amount": 2000,
      "risk_percentage": 2,
      "sl_distance_percentage": 2,
      "sl_distance_rupees": 50
    },
    "risk_reward": {
      "has_target": true,
      "risk": 50,
      "reward": 100,
      "ratio": 2,
      "ratio_text": "1:2"
    },
    "cost_breakdown": {
      "estimated_costs_at_entry": {
        "buy_value": 100000,
        "sell_value": 100000,
        "total_turnover": 200000,
        "brokerage": 0,
        "brokerage_buy": 0,
        "brokerage_sell": 0,
        "stt_ctt": 200,
        "exchange_txn_charge": 6.9,
        "sebi_charges": 0.02,
        "stamp_duty": 15,
        "gst": 1.24,
        "total_cost": 223.16,
        "cost_percentage": 0.1116
      },
      "costs_at_stop_loss": {
        "buy_value": 100000,
        "sell_value": 98000,
        "total_turnover": 198000,
        "total_cost": 221.34,
        "cost_percentage": 0.1118
      },
      "costs_at_target": {
        "buy_value": 100000,
        "sell_value": 104000,
        "total_turnover": 204000,
        "total_cost": 227.72,
        "cost_percentage": 0.1116
      }
    },
    "scenario_analysis": {
      "breakeven_price": 2505.58,
      "at_stop_loss": {
        "gross_loss": -2000,
        "net_loss_after_costs": -2221.34,
        "total_costs": 221.34,
        "message": "If stop-loss hits, estimated loss (after costs): ₹2221.34"
      },
      "at_target": {
        "gross_profit": 4000,
        "net_profit_after_costs": 3772.28,
        "total_costs": 227.72,
        "message": "If target hits, estimated net gain (after costs): ₹3772.28"
      }
    },
    "disclaimer": "This is a theoretical risk and cost illustration based on the details you entered. It is not a recommendation to trade this security. All trading involves risk of loss."
  },
  "timestamp": "2026-01-23T12:00:00Z"
}
```

#### Error Responses

**400 Bad Request** - Invalid input
```json
{
  "success": false,
  "error": "Stop loss price must be below buy price for long positions"
}
```

**401 Unauthorized** - Missing or invalid JWT
```json
{
  "msg": "Missing Authorization Header"
}
```

**429 Too Many Requests** - Rate limit exceeded
```json
{
  "error": "Daily limit exceeded for risk-calculator",
  "limit": 20,
  "used": 20,
  "reset_at": "2026-01-24T00:00:00Z"
}
```

---

### 2. Get Available Brokers

**GET** `/api/risk-calculator/brokers`

Returns list of supported brokers with their cost profiles.

#### Response (200 OK)

```json
{
  "success": true,
  "brokers": [
    {
      "broker": "zerodha",
      "name": "Zerodha",
      "profiles": {
        "delivery": {
          "brokerage": 0,
          "brokerage_type": "flat",
          "max_brokerage": 0
        },
        "intraday": {
          "brokerage": 0.0003,
          "brokerage_type": "percentage",
          "max_brokerage": 20
        },
        "fno": {
          "brokerage": 20,
          "brokerage_type": "flat"
        }
      }
    },
    {
      "broker": "upstox",
      "name": "Upstox",
      "profiles": {
        "delivery": {
          "brokerage": 0.0025,
          "brokerage_type": "percentage",
          "max_brokerage": 20
        },
        "intraday": {
          "brokerage": 0.0005,
          "brokerage_type": "percentage",
          "max_brokerage": 20
        },
        "fno": {
          "brokerage": 20,
          "brokerage_type": "flat"
        }
      }
    }
  ]
}
```

---

### 3. Validate Trade Parameters

**POST** `/api/risk-calculator/validate-trade`

Quick validation of trade parameters without full calculation. Useful for frontend validation.

#### Request Body

```json
{
  "buy_price": 2500,
  "stop_loss_price": 2450,
  "target_price": 2600,
  "capital_available": 100000,
  "max_risk_per_trade": 2,
  "max_risk_type": "percentage"
}
```

#### Response (200 OK)

```json
{
  "success": true,
  "validation": {
    "is_valid": true,
    "errors": [],
    "warnings": [
      "Risk:Reward ratio is 2:1 - acceptable but could be improved"
    ],
    "quick_estimate": {
      "estimated_quantity": 40,
      "estimated_position_value": 100000,
      "estimated_risk": 2000
    }
  }
}
```

---

### 4. Get Cost Breakdown

**POST** `/api/risk-calculator/cost-breakdown`

Get detailed cost breakdown for a specific quantity without position sizing calculation.

#### Request Body

```json
{
  "trade_type": "delivery",
  "broker": "zerodha",
  "buy_price": 2500,
  "sell_price": 2600,
  "quantity": 10
}
```

#### Response (200 OK)

```json
{
  "success": true,
  "data": {
    "cost_breakdown": {
      "buy_value": 25000,
      "sell_value": 26000,
      "total_turnover": 51000,
      "brokerage": 0,
      "stt_ctt": 51,
      "exchange_txn_charge": 1.76,
      "sebi_charges": 0.01,
      "stamp_duty": 3.75,
      "gst": 0.32,
      "total_cost": 56.84,
      "cost_percentage": 0.1115
    },
    "profit_loss": {
      "gross_pl": 1000,
      "net_pl": 943.16,
      "total_costs": 56.84,
      "cost_impact_on_pl": 56.84,
      "net_return_percentage": 3.77
    },
    "breakeven_price": 2505.68,
    "trade_details": {
      "trade_type": "delivery",
      "broker": "zerodha",
      "buy_price": 2500,
      "sell_price": 2600,
      "quantity": 10
    }
  }
}
```

---

### 5. Health Check

**GET** `/api/risk-calculator/health`

Check if the Risk Calculator service is operational.

#### Response (200 OK)

```json
{
  "success": true,
  "service": "Risk Calculator - Phase 1",
  "status": "operational",
  "features": [
    "Position sizing based on risk parameters",
    "Complete cost breakdown (brokerage, STT, charges)",
    "Risk:Reward ratio calculation",
    "Net P&L estimation with costs",
    "Breakeven price calculation",
    "Multi-broker support (Zerodha, Upstox, Custom)"
  ]
}
```

---

## Feature Limits (Daily)

| Plan | Daily Calculations |
|------|-------------------|
| FREE | 20 |
| STARTER | 50 |
| PRO | 100 |
| ADVANCED | 200 |
| ENTERPRISE | 500 |

Anonymous users: 3 calculations (no login required)

---

## Cost Components Explained

### 1. Brokerage
- **Zerodha Delivery**: ₹0 (free)
- **Zerodha Intraday**: 0.03% or ₹20 per order (whichever is lower)
- **Upstox Delivery**: 0.25% or ₹20 per order (whichever is lower)
- **F&O**: Flat ₹20 per order (both brokers)

### 2. STT/CTT (Securities Transaction Tax)
- **Delivery**: 0.1% on both buy and sell
- **Intraday**: 0.025% on sell side only
- **F&O**: 0.01% on sell side

### 3. Exchange Transaction Charges
- NSE: 0.00345% of turnover

### 4. SEBI Charges
- ₹10 per crore of turnover

### 5. Stamp Duty
- 0.015% on buy side (Maharashtra, varies by state)

### 6. GST
- 18% on (Brokerage + Exchange Charges + SEBI Charges)

---

## Example cURL Commands

### Calculate Position & Costs

```bash
curl -X POST http://localhost:8000/api/risk-calculator/calculate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "RELIANCE",
    "trade_type": "delivery",
    "buy_price": 2500,
    "stop_loss_price": 2450,
    "target_price": 2600,
    "capital_available": 100000,
    "max_risk_per_trade": 2,
    "max_risk_type": "percentage",
    "broker": "zerodha"
  }'
```

### Get Brokers

```bash
curl -X GET http://localhost:8000/api/risk-calculator/brokers \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Validate Trade

```bash
curl -X POST http://localhost:8000/api/risk-calculator/validate-trade \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "buy_price": 2500,
    "stop_loss_price": 2450,
    "target_price": 2600,
    "capital_available": 100000,
    "max_risk_per_trade": 2,
    "max_risk_type": "percentage"
  }'
```

### Cost Breakdown

```bash
curl -X POST http://localhost:8000/api/risk-calculator/cost-breakdown \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "trade_type": "delivery",
    "broker": "zerodha",
    "buy_price": 2500,
    "sell_price": 2600,
    "quantity": 10
  }'
```

---

## Integration Guide

### Frontend Integration Example (JavaScript/React)

```javascript
// Calculate position and costs
async function calculateRisk(tradeData) {
  const response = await fetch('http://localhost:8000/api/risk-calculator/calculate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getJWTToken()}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      symbol: tradeData.symbol,
      trade_type: tradeData.tradeType,
      buy_price: parseFloat(tradeData.buyPrice),
      stop_loss_price: parseFloat(tradeData.stopLoss),
      target_price: tradeData.target ? parseFloat(tradeData.target) : null,
      capital_available: parseFloat(tradeData.capital),
      max_risk_per_trade: parseFloat(tradeData.riskAmount),
      max_risk_type: tradeData.riskType,
      broker: tradeData.broker
    })
  });

  const result = await response.json();

  if (result.success) {
    return result.data;
  } else {
    throw new Error(result.error);
  }
}

// Usage
try {
  const riskAnalysis = await calculateRisk({
    symbol: 'RELIANCE',
    tradeType: 'delivery',
    buyPrice: 2500,
    stopLoss: 2450,
    target: 2600,
    capital: 100000,
    riskAmount: 2,
    riskType: 'percentage',
    broker: 'zerodha'
  });

  console.log('Max Quantity:', riskAnalysis.position_sizing.max_quantity);
  console.log('Risk Amount:', riskAnalysis.risk_analysis.risk_amount);
  console.log('Net Profit at Target:', riskAnalysis.scenario_analysis.at_target.net_profit_after_costs);
} catch (error) {
  console.error('Error:', error.message);
}
```

---

## Notes

### SEBI Compliance
- All responses include disclaimer text
- No "Buy/Sell" recommendations
- Only analytical calculations based on user inputs
- User maintains full control over trade decisions

### Accuracy
- Cost calculations based on current broker fee structures
- Actual costs may vary slightly due to rounding
- Always verify final costs with your broker

### Supported Brokers
- Zerodha (full support)
- Upstox (full support)
- Custom (configurable rates)

### Future Phases
Phase 1 is complete. Future phases will add:
- Phase 2: Trade checklists & discipline guardrails
- Phase 3: Session-level risk tracking
- Phase 4: Multi-stock portfolio view
- Phase 5: Trade journal with AI insights
- And more...

---

## Support

For issues or questions, contact: support@welthwest.com

**Version:** Phase 1 - MVP
**Last Updated:** January 2026
