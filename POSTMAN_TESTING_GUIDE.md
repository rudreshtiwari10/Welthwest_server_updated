# Complete Premium Plan & Payment Testing Guide (Postman)

## 🎯 Testing Strategy

We'll test in **3 modes**:
1. **Manual Credit Mode** (No payment gateway - easiest)
2. **Mock Payment Mode** (Testing flow without real Cashfree)
3. **Real Cashfree Mode** (With actual credentials)

---

## Mode 1: Manual Credit Testing (Recommended First)

### Prerequisites
```bash
# In .env file
IS_PAYMENT_GATEWAY_ENABLED=false
```

### Step 1: Create User & Login

**POST** `http://localhost:5000/api/register`
```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "Test123!"
}
```

**Response:**
```json
{
  "message": "User registered successfully",
  "user_id": "67234abc123def456789"
}
```

**POST** `http://localhost:5000/api/login`
```json
{
  "email": "test@example.com",
  "password": "Test123!"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJh...",
  "user": { ... }
}
```

**Save this token!** You'll use it as `Bearer <token>` in all authenticated requests.

---

### Step 2: Check Current Subscription

**GET** `http://localhost:5000/api/premium/user/subscription`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Response:**
```json
{
  "success": true,
  "subscription": {
    "plan": "FREE",
    "limits": {
      "welth-market-regime": 10,
      "welth-ai-assistant": 15,
      "backtest-beta": 5
    },
    "is_active": true
  }
}
```

---

### Step 3: Test Feature Usage (AI Assistant)

**POST** `http://localhost:5000/api/nextgenchat`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**
```json
{
  "message": "What is the stock market?",
  "model": "gpt-3.5-turbo"
}
```

**First Request Response:**
```json
{
  "response": "The stock market is...",
  ...
}
```

**Check Response Headers:**
```
X-RateLimit-Limit: 15
X-RateLimit-Remaining: 14
X-RateLimit-Feature: welth-ai-assistant
```

**After 15 requests, you'll get:**
```json
{
  "error": "usage_limit_reached",
  "message": "Daily limit reached for this feature. Upgrade to continue.",
  "premium_url": "/premium",
  "current_plan": "FREE",
  "suggested_plan": "STARTER",
  "remaining": 0,
  "limit": 15
}
```
**Status:** `403 Forbidden`

---

### Step 4: Check Usage Stats

**GET** `http://localhost:5000/api/premium/user/usage`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Response:**
```json
{
  "success": true,
  "usage": {
    "welth-market-regime": {
      "used": 0,
      "remaining": 10,
      "limit": 10
    },
    "welth-ai-assistant": {
      "used": 15,
      "remaining": 0,
      "limit": 15
    },
    "backtest-beta": {
      "used": 0,
      "remaining": 5,
      "limit": 5
    }
  },
  "subscription": {
    "plan": "FREE",
    "is_active": true
  }
}
```

---

### Step 5: Get All Plans

**GET** `http://localhost:5000/api/premium/plans`

**No Auth Required**

**Response:**
```json
{
  "success": true,
  "plans": [
    {
      "_id": "FREE",
      "display_name": "Free",
      "prices": {
        "weekly": 0,
        "monthly": 0,
        "annual": 0
      },
      "limits": {
        "welth-market-regime": 10,
        "welth-ai-assistant": 15,
        "backtest-beta": 5
      }
    },
    {
      "_id": "STARTER",
      "display_name": "Starter",
      "prices": {
        "weekly": 149,
        "monthly": 299,
        "annual": 2999
      },
      "limits": {
        "welth-market-regime": 20,
        "welth-ai-assistant": 25,
        "backtest-beta": 15
      }
    },
    ...
  ]
}
```

---

### Step 6: Manual Credit (Admin Action)

First, make yourself admin in MongoDB:
```bash
mongo
use welthwest
db.users.updateOne(
  { email: "test@example.com" },
  { $set: { role: "admin" } }
)
```

**POST** `http://localhost:5000/api/admin/manual-credit`

**Headers:**
```
Authorization: Bearer YOUR_ADMIN_TOKEN
Content-Type: application/json
```

**Body:**
```json
{
  "user_id": "67234abc123def456789",
  "plan": "PRO",
  "duration": "monthly",
  "note": "Testing premium features"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully applied PRO subscription",
  "user_id": "67234abc123def456789",
  "plan": "PRO",
  "duration": "monthly"
}
```

---

### Step 7: Verify Upgrade

**GET** `http://localhost:5000/api/premium/user/subscription`

**Response:**
```json
{
  "success": true,
  "subscription": {
    "plan": "PRO",
    "plan_duration": "monthly",
    "start_date": "2025-10-30T...",
    "expiry_date": "2025-11-29T...",
    "limits": {
      "welth-market-regime": 30,
      "welth-ai-assistant": 35,
      "backtest-beta": 25
    },
    "is_active": true
  }
}
```

---

### Step 8: Test Higher Limits

Now you can make 35 AI Assistant requests instead of 15!

**POST** `http://localhost:5000/api/nextgenchat`

Make multiple requests and check headers:
```
X-RateLimit-Limit: 35
X-RateLimit-Remaining: 34
```

---

### Step 9: Reset Usage (Admin)

**POST** `http://localhost:5000/api/admin/reset-usage`

**Headers:**
```
Authorization: Bearer YOUR_ADMIN_TOKEN
Content-Type: application/json
```

**Body (Reset specific feature):**
```json
{
  "user_id": "67234abc123def456789",
  "feature": "welth-ai-assistant"
}
```

**OR (Reset all features):**
```json
{
  "user_id": "67234abc123def456789"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Reset usage for welth-ai-assistant"
}
```

---

## Mode 2: Testing Payment Flow (With Disabled Gateway)

### Test Create Order Endpoint

**POST** `http://localhost:5000/api/payment/create-order`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**
```json
{
  "plan": "PRO",
  "duration": "monthly"
}
```

**Response (Gateway Disabled):**
```json
{
  "success": false,
  "error": "Payment gateway is currently disabled. Please contact support for manual purchase."
}
```
**Status:** `403 Forbidden`

---

## Mode 3: Real Cashfree Testing

### Prerequisites

1. Get Cashfree credentials from https://www.cashfree.com/
2. Update `.env`:
```bash
IS_PAYMENT_GATEWAY_ENABLED=true
CASHFREE_ENV=sandbox
CASHFREE_APP_ID_SANDBOX=CF123456789ABCDEF
CASHFREE_SECRET_KEY_SANDBOX=sk_sandbox_actual_key_here
CASHFREE_WEBHOOK_SECRET=whsec_actual_secret_here
```

3. Restart server

---

### Step 1: Create Payment Order

**POST** `http://localhost:5000/api/payment/create-order`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**
```json
{
  "plan": "PRO",
  "duration": "monthly"
}
```

**Success Response:**
```json
{
  "success": true,
  "order_id": "WW_67234ABC_PRO_MONTHLY_A1B2C3D4",
  "transaction_id": "67234def456789abc",
  "payment_session_id": "session_abc123def456",
  "payment_link": "https://sandbox.cashfree.com/pg/view/order/...",
  "amount": 499,
  "currency": "INR",
  "plan": "PRO",
  "duration": "monthly"
}
```

---

### Step 2: Check Order Status

**GET** `http://localhost:5000/api/payment/order-status/WW_67234ABC_PRO_MONTHLY_A1B2C3D4`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Response:**
```json
{
  "success": true,
  "order": {
    "order_id": "WW_67234ABC_PRO_MONTHLY_A1B2C3D4",
    "status": "PENDING",
    "plan": "PRO",
    "duration": "monthly",
    "amount": 499,
    "currency": "INR",
    "created_at": "2025-10-30T...",
    "updated_at": "2025-10-30T..."
  }
}
```

---

### Step 3: Simulate Webhook (Testing)

**For testing, you can manually trigger webhook:**

**POST** `http://localhost:5000/api/payment/webhook`

**Headers:**
```
Content-Type: application/json
x-webhook-signature: test_signature
x-webhook-timestamp: 1698765432
```

**Body (Cashfree Success Event):**
```json
{
  "type": "PAYMENT_SUCCESS_WEBHOOK",
  "data": {
    "order": {
      "order_id": "WW_67234ABC_PRO_MONTHLY_A1B2C3D4",
      "order_amount": 499,
      "order_status": "PAID",
      "customer_details": {
        "customer_email": "test@example.com",
        "customer_phone": "9999999999"
      }
    },
    "payment": {
      "cf_payment_id": "12345678",
      "payment_status": "SUCCESS",
      "payment_amount": 499,
      "payment_time": "2025-10-30T12:00:00Z",
      "payment_group": "upi"
    }
  }
}
```

**Note:** Real webhooks will have valid signature. For testing, you may need to temporarily disable signature verification.

---

### Step 4: Check Transaction History

**GET** `http://localhost:5000/api/payment/transaction-history`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Response:**
```json
{
  "success": true,
  "transactions": [
    {
      "transaction_id": "67234def456789abc",
      "order_id": "WW_67234ABC_PRO_MONTHLY_A1B2C3D4",
      "plan": "PRO",
      "duration": "monthly",
      "amount": 499,
      "currency": "INR",
      "status": "SUCCESS",
      "created_at": "2025-10-30T...",
      "updated_at": "2025-10-30T..."
    }
  ]
}
```

---

## 🧪 Testing Anonymous Users

### Step 1: Call Feature Without Auth

**POST** `http://localhost:5000/api/nextgenchat`

**Headers:**
```
Content-Type: application/json
```
*No Authorization header*

**Body:**
```json
{
  "message": "Test anonymous",
  "model": "gpt-3.5-turbo"
}
```

**First Response:**
```json
{
  "response": "...",
  ...
}
```

**Check Response Headers:**
```
X-RateLimit-Limit: 15
X-RateLimit-Remaining: 14
Set-Cookie: ww_session_id=anon_abc123...; Max-Age=2592000
```

---

### Step 2: Check Remaining (Anonymous)

**GET** `http://localhost:5000/api/premium/feature/welth-ai-assistant/remaining`

**Headers:**
```
Cookie: ww_session_id=anon_abc123...
```

**Response:**
```json
{
  "success": true,
  "remaining": 14,
  "limit": 15,
  "used": 1,
  "is_anonymous": true
}
```

---

## 📊 Monitoring in MongoDB

```bash
mongo
use welthwest

# Check plans
db.plans.find().pretty()

# Check transactions
db.transactions.find().sort({created_at: -1}).limit(5).pretty()

# Check usage logs
db.usage_logs.find().sort({created_at: -1}).limit(10).pretty()

# Check webhook events
db.webhook_events.find().sort({created_at: -1}).limit(5).pretty()

# Check user subscription
db.users.findOne({ email: "test@example.com" }, { subscription: 1 }).pretty()
```

---

## 🔍 Monitoring in Redis

```bash
redis-cli

# See all keys
KEYS *

# Check anonymous session usage
GET anon:anon_abc123...:usage:welth-ai-assistant

# Check authenticated user usage
GET user:67234abc123def456789:usage:welth-ai-assistant:20251030

# Check TTL
TTL user:67234abc123def456789:usage:welth-ai-assistant:20251030
```

---

## 🐛 Common Issues & Solutions

### Issue 1: "authentication Failed" from Cashfree

**Cause:** Invalid or missing Cashfree credentials

**Solution:**
```bash
# Check .env
echo $CASHFREE_APP_ID_SANDBOX
echo $CASHFREE_SECRET_KEY_SANDBOX

# Should NOT be empty or placeholder values
```

### Issue 2: "Payment gateway is disabled"

**Solution:**
```bash
# In .env
IS_PAYMENT_GATEWAY_ENABLED=true
```

### Issue 3: payment_link is null

**Cause:** Cashfree API error or gateway disabled

**Solution:**
1. Check backend logs for Cashfree error
2. Verify credentials are correct
3. Check Cashfree dashboard for API status

### Issue 4: Redis not available

**Solution:**
```bash
# Start Redis
redis-server

# Or install Redis
brew install redis  # macOS
sudo apt-get install redis-server  # Ubuntu
```

### Issue 5: Plans not seeded

**Solution:**
```bash
# Check server startup logs for:
"✓ Premium system initialized: X new plans, Y updated"

# Manually verify
mongo
use welthwest
db.plans.find()
```

---

## ✅ Complete Test Checklist

### Basic Flow
- [ ] Register user
- [ ] Login and get token
- [ ] Check initial subscription (FREE)
- [ ] Get all plans
- [ ] Use feature until limit reached
- [ ] Verify 403 error with upgrade message
- [ ] Check usage stats

### Admin Flow
- [ ] Make user admin
- [ ] Manually credit PRO subscription
- [ ] Verify subscription upgraded
- [ ] Test higher limits
- [ ] Reset usage

### Payment Flow (If gateway enabled)
- [ ] Create payment order
- [ ] Check order status
- [ ] Simulate/trigger webhook
- [ ] Verify subscription applied
- [ ] Check transaction history

### Anonymous Flow
- [ ] Access feature without auth
- [ ] Verify session cookie set
- [ ] Check usage counter
- [ ] Hit anonymous limit
- [ ] Verify 403 with signup CTA

---

## 🎯 Recommended Testing Order

1. **Start with Manual Credit** (Mode 1) - Get comfortable with the system
2. **Test Anonymous** - Verify session tracking works
3. **Enable Cashfree** (Mode 3) - Test real payment flow

---

## 📝 Postman Collection Export

Save this as `premium_plan_tests.postman_collection.json`:

```json
{
  "info": {
    "name": "WelthWest Premium Plan API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Auth",
      "item": [
        {
          "name": "Register",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/register",
            "body": {
              "mode": "raw",
              "raw": "{\n  \"username\": \"testuser\",\n  \"email\": \"test@example.com\",\n  \"password\": \"Test123!\"\n}"
            }
          }
        },
        {
          "name": "Login",
          "request": {
            "method": "POST",
            "url": "{{base_url}}/api/login",
            "body": {
              "mode": "raw",
              "raw": "{\n  \"email\": \"test@example.com\",\n  \"password\": \"Test123!\"\n}"
            }
          }
        }
      ]
    },
    {
      "name": "Premium",
      "item": [
        {
          "name": "Get All Plans",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/premium/plans"
          }
        },
        {
          "name": "Get User Subscription",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/premium/user/subscription",
            "header": [
              {
                "key": "Authorization",
                "value": "Bearer {{access_token}}"
              }
            ]
          }
        },
        {
          "name": "Get User Usage",
          "request": {
            "method": "GET",
            "url": "{{base_url}}/api/premium/user/usage",
            "header": [
              {
                "key": "Authorization",
                "value": "Bearer {{access_token}}"
              }
            ]
          }
        }
      ]
    }
  ],
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:5000"
    },
    {
      "key": "access_token",
      "value": ""
    }
  ]
}
```

Import this into Postman and set the `access_token` variable after login.

---

**Happy Testing! 🚀**
