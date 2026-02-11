# Risk Calculator Phase 1 - Setup & Testing Guide

## Quick Start

The Risk Calculator Phase 1 has been fully integrated into the WelthWest backend. Follow these steps to start using it.

---

## What's Been Implemented

### ✅ Phase 1 - Complete

1. **Position Size Calculator**
   - Calculates max quantity based on risk parameters
   - Supports percentage or fixed rupee risk
   - Validates stop loss and capital constraints

2. **Risk Analysis**
   - Risk per share calculation
   - Risk:Reward ratio (if target provided)
   - Stop loss distance (% and rupees)

3. **Trading Cost Calculator**
   - Complete cost breakdown:
     - Brokerage (broker-specific)
     - STT/CTT (trade type specific)
     - Exchange transaction charges
     - SEBI turnover charges (₹10/crore)
     - Stamp duty (state-wise)
     - GST (18% on applicable charges)

4. **Scenario Analysis**
   - Net P&L at stop loss (after costs)
   - Net P&L at target (after costs)
   - Breakeven price calculation

5. **Multi-Broker Support**
   - Zerodha (zero delivery brokerage)
   - Upstox (competitive rates)
   - Custom (configurable)

6. **SEBI Compliance**
   - No trading recommendations
   - Theoretical illustrations only
   - Clear disclaimers on all responses

---

## Files Created

```
Welthwest_server_updated/
├── services/
│   └── risk_calculator_service.py          # Core calculation logic
├── routes/
│   └── risk_calculator_routes.py           # API endpoints
├── docs/
│   ├── RISK_CALCULATOR_PHASE1_API.md       # API documentation
│   ├── RISK_CALCULATOR_SETUP.md            # This file
│   └── Risk_Calculator_Phase1.postman_collection.json
└── app.py                                   # Updated with blueprint registration
```

### Modified Files

- `app.py` - Added risk calculator blueprint import and registration
- `config.py` - Added risk-calculator feature limits for all plans

---

## Configuration

### Feature Limits (Already Configured)

| Plan | Daily Calculations |
|------|-------------------|
| FREE | 20 |
| STARTER | 50 |
| PRO | 100 |
| ADVANCED | 200 |
| ENTERPRISE | 500 |
| Anonymous | 3 |

### Environment Variables

No additional environment variables needed. Uses existing JWT and MongoDB configuration.

---

## Starting the Server

1. **Navigate to server directory:**
   ```bash
   cd "C:\Users\Kunal Kumar\Desktop\WelthWest\Trials\WelthWest Final all website integration\WelthWest\Welthwest_server_updated"
   ```

2. **Activate virtual environment (if using one):**
   ```bash
   # Windows
   venv\Scripts\activate

   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies (if not already installed):**
   ```bash
   pip install flask flask-cors flask-jwt-extended pymongo python-dotenv
   ```

4. **Start the server:**
   ```bash
   python app.py
   ```

5. **Verify server is running:**
   ```bash
   curl http://localhost:8000/api/risk-calculator/health
   ```

   Expected response:
   ```json
   {
     "success": true,
     "service": "Risk Calculator - Phase 1",
     "status": "operational"
   }
   ```

---

## Testing the API

### Method 1: Using Postman

1. Import the collection: `docs/Risk_Calculator_Phase1.postman_collection.json`
2. Set variables:
   - `base_url`: `http://localhost:8000`
   - `jwt_token`: Your JWT token from login
3. Run any request

### Method 2: Using cURL

#### Step 1: Login to get JWT token
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your@email.com",
    "password": "yourpassword"
  }'
```

Save the `access_token` from response.

#### Step 2: Calculate position & costs
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

### Method 3: Using Python Requests

```python
import requests
import json

# Base URL
BASE_URL = "http://localhost:8000"

# Step 1: Login
login_response = requests.post(
    f"{BASE_URL}/api/auth/login",
    json={
        "email": "your@email.com",
        "password": "yourpassword"
    }
)
jwt_token = login_response.json()['access_token']

# Step 2: Calculate risk
headers = {
    "Authorization": f"Bearer {jwt_token}",
    "Content-Type": "application/json"
}

trade_data = {
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

response = requests.post(
    f"{BASE_URL}/api/risk-calculator/calculate",
    headers=headers,
    json=trade_data
)

result = response.json()
print(json.dumps(result, indent=2))

# Extract key information
if result['success']:
    data = result['data']
    print(f"\n=== RESULTS ===")
    print(f"Max Quantity: {data['position_sizing']['max_quantity']} shares")
    print(f"Position Value: ₹{data['position_sizing']['position_value']:,.2f}")
    print(f"Risk Amount: ₹{data['risk_analysis']['risk_amount']:,.2f}")
    print(f"Risk:Reward: {data['risk_reward']['ratio_text']}")
    print(f"Total Costs: ₹{data['cost_breakdown']['estimated_costs_at_entry']['total_cost']:.2f}")
    print(f"Breakeven Price: ₹{data['scenario_analysis']['breakeven_price']}")
    if data['scenario_analysis']['at_target']:
        print(f"Net Profit at Target: ₹{data['scenario_analysis']['at_target']['net_profit_after_costs']:,.2f}")
```

---

## Example Test Scenarios

### Scenario 1: Conservative Delivery Trade
```json
{
  "symbol": "TCS",
  "trade_type": "delivery",
  "buy_price": 3500,
  "stop_loss_price": 3475,
  "target_price": 3600,
  "capital_available": 100000,
  "max_risk_per_trade": 1,
  "max_risk_type": "percentage",
  "broker": "zerodha"
}
```

**Expected:** Low risk (1%), good R:R (4:1), minimal costs due to zero brokerage

---

### Scenario 2: Aggressive Intraday Trade
```json
{
  "symbol": "BANKNIFTY",
  "trade_type": "intraday",
  "buy_price": 45000,
  "stop_loss_price": 44900,
  "target_price": 45300,
  "capital_available": 200000,
  "max_risk_per_trade": 5000,
  "max_risk_type": "rupees",
  "broker": "upstox"
}
```

**Expected:** Higher quantity, tighter stops, intraday STT (only on sell)

---

### Scenario 3: F&O Trade
```json
{
  "symbol": "NIFTY",
  "trade_type": "fno",
  "buy_price": 21500,
  "stop_loss_price": 21400,
  "target_price": 21700,
  "capital_available": 300000,
  "max_risk_per_trade": 3,
  "max_risk_type": "percentage",
  "broker": "zerodha"
}
```

**Expected:** Flat ₹20 brokerage, F&O STT rates, higher leverage

---

### Scenario 4: Without Target (Open-ended)
```json
{
  "symbol": "HDFCBANK",
  "trade_type": "delivery",
  "buy_price": 1600,
  "stop_loss_price": 1580,
  "capital_available": 80000,
  "max_risk_per_trade": 2,
  "max_risk_type": "percentage",
  "broker": "zerodha"
}
```

**Expected:** No target analysis, but all other metrics provided

---

## Validation & Error Handling

### Valid Input Ranges

- **Buy Price**: Must be > 0
- **Stop Loss**: Must be > 0 and < buy_price
- **Target**: Optional, must be > buy_price if provided
- **Capital**: Must be > 0
- **Risk**: Must be > 0
  - If percentage: Must be ≤ 100%
  - If rupees: Must be ≤ capital
- **Trade Type**: `delivery`, `intraday`, or `fno`
- **Broker**: `zerodha`, `upstox`, or `custom`
- **Risk Type**: `percentage` or `rupees`

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Stop loss must be below buy price" | SL ≥ Buy price | Ensure SL < Buy price |
| "Missing required fields" | Incomplete request | Check all required fields |
| "Invalid trade type" | Wrong trade_type value | Use: delivery/intraday/fno |
| "Risk percentage cannot exceed 100%" | Risk > 100% | Use reasonable risk % |
| "Daily limit exceeded" | Used up daily quota | Upgrade plan or wait for reset |
| "Missing Authorization Header" | No JWT token | Login first to get token |

---

## API Endpoints Summary

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/api/risk-calculator/calculate` | POST | ✅ Yes | Main calculation endpoint |
| `/api/risk-calculator/brokers` | GET | ✅ Yes | List available brokers |
| `/api/risk-calculator/validate-trade` | POST | ✅ Yes | Quick validation |
| `/api/risk-calculator/cost-breakdown` | POST | ✅ Yes | Cost-only calculation |
| `/api/risk-calculator/health` | GET | ❌ No | Service health check |

---

## Response Structure

### Success Response
```json
{
  "success": true,
  "data": {
    "symbol": "...",
    "position_sizing": { ... },
    "risk_analysis": { ... },
    "risk_reward": { ... },
    "cost_breakdown": { ... },
    "scenario_analysis": { ... },
    "disclaimer": "..."
  },
  "timestamp": "..."
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message here"
}
```

---

## Usage Limits & Rate Limiting

### How It Works

- Limits are per-user, per-day
- Resets at midnight (Asia/Kolkata timezone)
- Anonymous users: 3 calculations per session (30-day cookie)
- Authenticated users: Based on subscription plan

### Check Remaining Usage

```bash
curl -X GET http://localhost:8000/api/premium/feature/risk-calculator/remaining \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Response:
```json
{
  "feature_key": "risk-calculator",
  "limit": 20,
  "used": 5,
  "remaining": 15,
  "reset_at": "2026-01-24T00:00:00Z"
}
```

---

## Troubleshooting

### Issue: "Module not found" error
**Solution:**
```bash
cd Welthwest_server_updated
pip install -r requirements.txt
```

### Issue: "Blueprint not found" error
**Solution:** Verify `app.py` has these lines:
```python
from routes.risk_calculator_routes import risk_calculator_bp
app.register_blueprint(risk_calculator_bp)
```

### Issue: "Feature limit not found" error
**Solution:** Restart Flask server to reload `config.py` changes

### Issue: JWT token expired
**Solution:**
```bash
# Get new token
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Authorization: Bearer YOUR_REFRESH_TOKEN"
```

### Issue: MongoDB connection error
**Solution:** Check `.env` file has correct `MONGODB_URI`

---

## Integration with Frontend

### React Example

```javascript
// RiskCalculator.jsx
import React, { useState } from 'react';
import axios from 'axios';

const RiskCalculator = () => {
  const [formData, setFormData] = useState({
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

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleCalculate = async () => {
    setLoading(true);
    try {
      const response = await axios.post(
        'http://localhost:8000/api/risk-calculator/calculate',
        {
          symbol: formData.symbol,
          trade_type: formData.tradeType,
          buy_price: parseFloat(formData.buyPrice),
          stop_loss_price: parseFloat(formData.stopLoss),
          target_price: formData.target ? parseFloat(formData.target) : null,
          capital_available: parseFloat(formData.capital),
          max_risk_per_trade: parseFloat(formData.riskAmount),
          max_risk_type: formData.riskType,
          broker: formData.broker
        },
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`,
            'Content-Type': 'application/json'
          }
        }
      );

      setResult(response.data.data);
    } catch (error) {
      console.error('Error:', error.response?.data?.error || error.message);
      alert(error.response?.data?.error || 'Calculation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="risk-calculator">
      <h2>Risk Calculator - Phase 1</h2>

      {/* Form fields here */}

      <button onClick={handleCalculate} disabled={loading}>
        {loading ? 'Calculating...' : 'Calculate Risk'}
      </button>

      {result && (
        <div className="results">
          <h3>Results</h3>
          <p><strong>Max Quantity:</strong> {result.position_sizing.max_quantity} shares</p>
          <p><strong>Position Value:</strong> ₹{result.position_sizing.position_value.toLocaleString()}</p>
          <p><strong>Risk Amount:</strong> ₹{result.risk_analysis.risk_amount.toLocaleString()}</p>
          <p><strong>Risk:Reward:</strong> {result.risk_reward.ratio_text}</p>
          <p><strong>Total Costs:</strong> ₹{result.cost_breakdown.estimated_costs_at_entry.total_cost.toFixed(2)}</p>
          <p><strong>Breakeven Price:</strong> ₹{result.scenario_analysis.breakeven_price}</p>

          {result.scenario_analysis.at_target && (
            <div className="target-scenario">
              <h4>At Target (₹{formData.target})</h4>
              <p className="profit">
                Net Profit: ₹{result.scenario_analysis.at_target.net_profit_after_costs.toLocaleString()}
              </p>
            </div>
          )}

          <div className="sl-scenario">
            <h4>At Stop Loss (₹{formData.stopLoss})</h4>
            <p className="loss">
              Net Loss: ₹{Math.abs(result.scenario_analysis.at_stop_loss.net_loss_after_costs).toLocaleString()}
            </p>
          </div>

          <p className="disclaimer">{result.disclaimer}</p>
        </div>
      )}
    </div>
  );
};

export default RiskCalculator;
```

---

## Next Steps

### Phase 1 is Complete ✅

Ready for production use!

### Upcoming Phases (Roadmap)

- **Phase 2**: Trade checklists & discipline guardrails
- **Phase 3**: Session-level risk tracking
- **Phase 4**: Multi-stock portfolio view
- **Phase 5**: Trade journal with AI insights
- **Phase 6**: Scenario & cost simulation engine
- **Phase 7**: Portfolio risk analytics
- **Phase 8**: Notifications & reports
- **Phase 9**: Broker API integration (read-only)

---

## Support & Documentation

- **Full API Docs**: `docs/RISK_CALCULATOR_PHASE1_API.md`
- **Postman Collection**: `docs/Risk_Calculator_Phase1.postman_collection.json`
- **This Guide**: `docs/RISK_CALCULATOR_SETUP.md`

---

## Testing Checklist

- [ ] Server starts without errors
- [ ] Health check endpoint returns 200
- [ ] Can login and get JWT token
- [ ] Calculate endpoint returns valid results
- [ ] Brokers endpoint lists all brokers
- [ ] Validate endpoint catches errors
- [ ] Cost breakdown endpoint works
- [ ] Feature limits are enforced
- [ ] Error messages are clear
- [ ] All calculations are accurate

---

**Version:** Phase 1 - MVP Complete
**Date:** January 2026
**Status:** ✅ Ready for Production
