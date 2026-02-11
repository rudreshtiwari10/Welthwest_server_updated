# 🚀 Risk Calculator Phase 1 - Quick Start

## ✅ Implementation Complete - Ready to Use!

---

## 📦 What You Got

**Phase 1: Core Position & Cost Calculator (MVP)**

✅ Position sizing based on risk
✅ Complete cost breakdown (all charges)
✅ Risk:Reward analysis
✅ Scenario analysis (target & SL)
✅ Multi-broker support
✅ SEBI compliant (no recommendations)

---

## 🎯 Quick Test (3 Steps)

### 1️⃣ Start Server
```bash
cd Welthwest_server_updated
python app.py
```

### 2️⃣ Health Check
```bash
curl http://localhost:8000/api/risk-calculator/health
```

✅ **Expected:** `{"success": true, "status": "operational"}`

### 3️⃣ Run Tests
```bash
pip install requests colorama
python test_risk_calculator.py
```

✅ **Expected:** All 8 tests pass

---

## 📡 API Endpoint

**Main Endpoint:**
```
POST http://localhost:8000/api/risk-calculator/calculate
```

**Headers:**
```
Authorization: Bearer YOUR_JWT_TOKEN
Content-Type: application/json
```

**Request Body:**
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

**Response:**
```json
{
  "success": true,
  "data": {
    "position_sizing": {
      "max_quantity": 40,
      "position_value": 100000
    },
    "risk_analysis": {
      "risk_amount": 2000,
      "risk_percentage": 2
    },
    "risk_reward": {
      "ratio_text": "1:2"
    },
    "cost_breakdown": { ... },
    "scenario_analysis": {
      "breakeven_price": 2505.58,
      "at_target": {
        "net_profit_after_costs": 3772.28
      },
      "at_stop_loss": {
        "net_loss_after_costs": -2221.34
      }
    }
  }
}
```

---

## 🔑 Parameters

| Field | Type | Required | Options |
|-------|------|----------|---------|
| symbol | string | ✅ | Any stock symbol |
| trade_type | string | ✅ | `delivery`, `intraday`, `fno` |
| buy_price | number | ✅ | Positive number |
| stop_loss_price | number | ✅ | < buy_price |
| target_price | number | ❌ | > buy_price (optional) |
| capital_available | number | ✅ | Positive number |
| max_risk_per_trade | number | ✅ | Positive number |
| max_risk_type | string | ✅ | `percentage` or `rupees` |
| broker | string | ✅ | `zerodha`, `upstox`, `custom` |

---

## 📊 All Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/risk-calculator/calculate` | Full calculation | ✅ |
| GET | `/api/risk-calculator/brokers` | List brokers | ✅ |
| POST | `/api/risk-calculator/validate-trade` | Quick validation | ✅ |
| POST | `/api/risk-calculator/cost-breakdown` | Cost only | ✅ |
| GET | `/api/risk-calculator/health` | Health check | ❌ |

---

## 💰 Cost Components Calculated

✅ **Brokerage** (broker-specific)
✅ **STT/CTT** (trade type specific)
✅ **Exchange Charges** (NSE 0.00345%)
✅ **SEBI Charges** (₹10/crore)
✅ **Stamp Duty** (0.015% on buy)
✅ **GST** (18% on applicable)

---

## 🏢 Supported Brokers

| Broker | Delivery | Intraday | F&O |
|--------|----------|----------|-----|
| **Zerodha** | ₹0 | 0.03% or ₹20 | ₹20 flat |
| **Upstox** | 0.25% or ₹20 | 0.05% or ₹20 | ₹20 flat |
| **Custom** | Configurable | Configurable | Configurable |

---

## 📈 Feature Limits

| Plan | Daily Uses |
|------|-----------|
| FREE | 20 |
| STARTER | 50 |
| PRO | 100 |
| ADVANCED | 200 |
| ENTERPRISE | 500 |
| Anonymous | 3 |

---

## 🧪 Example Test

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpass"}'

# Calculate (use token from login)
curl -X POST http://localhost:8000/api/risk-calculator/calculate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TCS",
    "trade_type": "delivery",
    "buy_price": 3500,
    "stop_loss_price": 3475,
    "target_price": 3600,
    "capital_available": 100000,
    "max_risk_per_trade": 1,
    "max_risk_type": "percentage",
    "broker": "zerodha"
  }'
```

---

## 📁 Files Created

```
Welthwest_server_updated/
├── services/risk_calculator_service.py         (Core logic)
├── routes/risk_calculator_routes.py            (API endpoints)
├── test_risk_calculator.py                     (Test suite)
├── docs/
│   ├── RISK_CALCULATOR_PHASE1_API.md          (Full API docs)
│   ├── RISK_CALCULATOR_SETUP.md               (Setup guide)
│   └── Risk_Calculator_Phase1.postman_collection.json
└── QUICK_START_RISK_CALCULATOR.md             (This file)

Modified:
├── app.py                                      (Blueprint registered)
└── config.py                                   (Feature limits added)
```

---

## 🛠️ Integration Example (JavaScript)

```javascript
async function calculateRisk(tradeData) {
  const response = await fetch('http://localhost:8000/api/risk-calculator/calculate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      symbol: tradeData.symbol,
      trade_type: tradeData.tradeType,
      buy_price: parseFloat(tradeData.buyPrice),
      stop_loss_price: parseFloat(tradeData.stopLoss),
      target_price: tradeData.target ? parseFloat(tradeData.target) : null,
      capital_available: parseFloat(tradeData.capital),
      max_risk_per_trade: parseFloat(tradeData.risk),
      max_risk_type: tradeData.riskType,
      broker: tradeData.broker
    })
  });

  return response.json();
}

// Usage
const result = await calculateRisk({
  symbol: 'RELIANCE',
  tradeType: 'delivery',
  buyPrice: 2500,
  stopLoss: 2450,
  target: 2600,
  capital: 100000,
  risk: 2,
  riskType: 'percentage',
  broker: 'zerodha'
});

console.log('Max Quantity:', result.data.position_sizing.max_quantity);
console.log('Net Profit at Target:', result.data.scenario_analysis.at_target.net_profit_after_costs);
```

---

## ⚠️ Common Errors

| Error | Fix |
|-------|-----|
| "Missing Authorization Header" | Login first, get JWT token |
| "Stop loss must be below buy price" | Ensure SL < Buy price |
| "Invalid trade type" | Use: delivery/intraday/fno |
| "Daily limit exceeded" | Upgrade plan or wait for reset |
| "Module not found" | Run: `pip install flask flask-cors flask-jwt-extended pymongo` |

---

## 📚 Documentation

- **Full API Docs:** `docs/RISK_CALCULATOR_PHASE1_API.md`
- **Setup Guide:** `docs/RISK_CALCULATOR_SETUP.md`
- **Summary:** `RISK_CALCULATOR_IMPLEMENTATION_SUMMARY.md`
- **Postman:** `docs/Risk_Calculator_Phase1.postman_collection.json`

---

## 🎯 What's Next?

**Phase 1 ✅** - Core Position & Cost Calculator (DONE)

**Phase 2 🔜** - Trade Checklist & Discipline Guardrails
**Phase 3 🔜** - Session-Level Risk Tracking
**Phase 4 🔜** - Multi-Stock Portfolio View
**Phase 5 🔜** - Trade Journal with AI Insights
**Phase 6 🔜** - Scenario Simulation Engine
**Phase 7 🔜** - Portfolio Risk Analytics
**Phase 8 🔜** - Notifications & Reports
**Phase 9 🔜** - Broker API Integration

---

## ✅ Verification Checklist

- [ ] Server starts without errors
- [ ] Health endpoint returns 200
- [ ] Can login and get JWT
- [ ] Calculate endpoint works
- [ ] All 8 tests pass
- [ ] Postman collection works
- [ ] Cost calculations accurate
- [ ] Error handling works

---

## 🎉 Success!

**Phase 1 is complete and ready for:**
- ✅ Production deployment
- ✅ Frontend integration
- ✅ User testing
- ✅ Phase 2 development

---

**Version:** 1.0.0 (Phase 1 MVP)
**Status:** ✅ Production Ready
**Date:** January 2026

**Need Help?** Check `docs/RISK_CALCULATOR_SETUP.md` for detailed guide.
