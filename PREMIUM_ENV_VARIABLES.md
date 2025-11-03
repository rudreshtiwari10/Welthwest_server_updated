# Premium Plan Environment Variables

This document lists **ALL** environment variables required for the Premium Plan implementation as specified in `Premiummd.md`.

---

## Table of Contents
1. [Existing Variables (Already in .env)](#existing-variables)
2. [NEW Variables Required for Premium Features](#new-variables-required)
3. [Complete .env Template](#complete-env-template)
4. [Validation Checklist](#validation-checklist)

---

## Existing Variables
These are already in your `.env` and will continue to be used:

```bash
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017/
DB_NAME=welthwest

# JWT Configuration
JWT_SECRET_KEY=your-secret-key
JWT_ACCESS_TOKEN_EXPIRES=3600

# Redis Configuration (CRITICAL for premium features)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Cache Configuration
CACHE_TYPE=redis
CACHE_REDIS_DB=1
CACHE_DEFAULT_TIMEOUT=300

# Anonymous Trial Limits (These will be updated for premium)
ANON_TRIAL_LIMIT=10
ANON_AI_ANALYSIS_LIMIT=10
ANON_BACKTEST_LIMIT=10
ANON_CHAT_LIMIT=5
ANON_SESSION_COOKIE=ww_session_id
ANON_SESSION_TTL_SECONDS=2592000  # 30 days

# Server Configuration
BASE_URL=http://localhost:8000
DEBUG=False
FLASK_ENV=development
```

---

## NEW Variables Required

### 1. Payment Gateway Configuration (Cashfree)

```bash
# Enable/Disable Payment Gateway
IS_PAYMENT_GATEWAY_ENABLED=true

# Cashfree Sandbox Credentials (for testing)
CASHFREE_APP_ID_SANDBOX=your_sandbox_app_id_here
CASHFREE_SECRET_KEY_SANDBOX=your_sandbox_secret_key_here

# Cashfree Production Credentials (for production)
CASHFREE_APP_ID_PROD=your_production_app_id_here
CASHFREE_SECRET_KEY_PROD=your_production_secret_key_here

# Cashfree Environment ('sandbox' or 'production')
CASHFREE_ENV=sandbox

# Cashfree Webhook Secret (for signature verification)
CASHFREE_WEBHOOK_SECRET=your_cashfree_webhook_secret_here
```

### 2. Server Timezone Configuration

```bash
# Server Timezone (for daily limit resets at midnight)
SERVER_TIMEZONE=Asia/Kolkata
```

### 3. Plan Pricing Configuration

```bash
# ============================================
# STARTER PLAN PRICES (in INR)
# ============================================
PLAN_STARTER_WEEKLY=149
PLAN_STARTER_MONTHLY=299
PLAN_STARTER_ANNUAL=2999

# ============================================
# PRO PLAN PRICES (in INR)
# ============================================
PLAN_PRO_WEEKLY=249
PLAN_PRO_MONTHLY=499
PLAN_PRO_ANNUAL=4999

# ============================================
# ADVANCED PLAN PRICES (in INR)
# ============================================
PLAN_ADVANCED_WEEKLY=499
PLAN_ADVANCED_MONTHLY=999
PLAN_ADVANCED_ANNUAL=9999

# ============================================
# ENTERPRISE PLAN PRICES (in INR)
# ============================================
PLAN_ENTERPRISE_WEEKLY=999
PLAN_ENTERPRISE_MONTHLY=1999
PLAN_ENTERPRISE_ANNUAL=19999
```

### 4. Per-Feature Limits Per Plan

The blueprint specifies three premium features:
- **welth-market-regime** (Market Regime Classifier)
- **welth-ai-assistant** (AI Assistant / NextGen Chat)
- **backtest-beta** (Backtesting)

```bash
# ============================================
# FREE PLAN LIMITS (Authenticated Users)
# ============================================
PLAN_FREE__MARKET_REGIME=10
PLAN_FREE__AI_ASSISTANT=15
PLAN_FREE__BACKTEST=5

# ============================================
# STARTER PLAN LIMITS
# ============================================
PLAN_STARTER__MARKET_REGIME=20
PLAN_STARTER__AI_ASSISTANT=25
PLAN_STARTER__BACKTEST=15

# ============================================
# PRO PLAN LIMITS
# ============================================
PLAN_PRO__MARKET_REGIME=30
PLAN_PRO__AI_ASSISTANT=35
PLAN_PRO__BACKTEST=25

# ============================================
# ADVANCED PLAN LIMITS
# ============================================
PLAN_ADVANCED__MARKET_REGIME=40
PLAN_ADVANCED__AI_ASSISTANT=45
PLAN_ADVANCED__BACKTEST=40

# ============================================
# ENTERPRISE PLAN LIMITS
# ============================================
PLAN_ENTERPRISE__MARKET_REGIME=50
PLAN_ENTERPRISE__AI_ASSISTANT=55
PLAN_ENTERPRISE__BACKTEST=45
```

### 5. Anonymous User Limits

```bash
# ============================================
# ANONYMOUS SESSION LIMITS (Session-based)
# ============================================
ANON_MARKET_REGIME_LIMIT=10
ANON_AI_ASSISTANT_LIMIT=15
ANON_BACKTEST_LIMIT=5
```

### 6. Usage Counter Configuration

```bash
# Usage Counter TTL (Time To Live in seconds)
# Default: 86400 seconds = 24 hours
USAGE_COUNTER_TTL_SECONDS=86400
```

---

## Complete .env Template

Here's a complete `.env` file template with all variables:

```bash
# ============================================
# BASIC CONFIGURATION
# ============================================
MONGODB_URI=mongodb://localhost:27017/
DB_NAME=welthwest
JWT_SECRET_KEY=your-secret-key-change-this-in-production
JWT_ACCESS_TOKEN_EXPIRES=3600
SERVER_TIMEZONE=Asia/Kolkata

# ============================================
# REDIS CONFIGURATION
# ============================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# ============================================
# CACHE CONFIGURATION
# ============================================
CACHE_TYPE=redis
CACHE_REDIS_DB=1
CACHE_DEFAULT_TIMEOUT=300

# ============================================
# CASHFREE PAYMENT GATEWAY
# ============================================
IS_PAYMENT_GATEWAY_ENABLED=true
CASHFREE_ENV=sandbox
CASHFREE_APP_ID_SANDBOX=your_sandbox_app_id
CASHFREE_SECRET_KEY_SANDBOX=your_sandbox_secret
CASHFREE_APP_ID_PROD=your_prod_app_id
CASHFREE_SECRET_KEY_PROD=your_prod_secret
CASHFREE_WEBHOOK_SECRET=your_webhook_secret

# ============================================
# PLAN PRICES (INR)
# ============================================
# Starter Plan
PLAN_STARTER_WEEKLY=149
PLAN_STARTER_MONTHLY=299
PLAN_STARTER_ANNUAL=2999

# Pro Plan
PLAN_PRO_WEEKLY=249
PLAN_PRO_MONTHLY=499
PLAN_PRO_ANNUAL=4999

# Advanced Plan
PLAN_ADVANCED_WEEKLY=499
PLAN_ADVANCED_MONTHLY=999
PLAN_ADVANCED_ANNUAL=9999

# Enterprise Plan
PLAN_ENTERPRISE_WEEKLY=999
PLAN_ENTERPRISE_MONTHLY=1999
PLAN_ENTERPRISE_ANNUAL=19999

# ============================================
# PLAN LIMITS - FREE TIER
# ============================================
PLAN_FREE__MARKET_REGIME=10
PLAN_FREE__AI_ASSISTANT=15
PLAN_FREE__BACKTEST=5

# ============================================
# PLAN LIMITS - STARTER TIER
# ============================================
PLAN_STARTER__MARKET_REGIME=20
PLAN_STARTER__AI_ASSISTANT=25
PLAN_STARTER__BACKTEST=15

# ============================================
# PLAN LIMITS - PRO TIER
# ============================================
PLAN_PRO__MARKET_REGIME=30
PLAN_PRO__AI_ASSISTANT=35
PLAN_PRO__BACKTEST=25

# ============================================
# PLAN LIMITS - ADVANCED TIER
# ============================================
PLAN_ADVANCED__MARKET_REGIME=40
PLAN_ADVANCED__AI_ASSISTANT=45
PLAN_ADVANCED__BACKTEST=40

# ============================================
# PLAN LIMITS - ENTERPRISE TIER
# ============================================
PLAN_ENTERPRISE__MARKET_REGIME=50
PLAN_ENTERPRISE__AI_ASSISTANT=55
PLAN_ENTERPRISE__BACKTEST=45

# ============================================
# ANONYMOUS USER LIMITS
# ============================================
ANON_MARKET_REGIME_LIMIT=10
ANON_AI_ASSISTANT_LIMIT=15
ANON_BACKTEST_LIMIT=5
ANON_SESSION_COOKIE=ww_session_id
ANON_SESSION_TTL_SECONDS=2592000

# ============================================
# USAGE COUNTER CONFIGURATION
# ============================================
USAGE_COUNTER_TTL_SECONDS=86400

# ============================================
# EXISTING UPSTOX CONFIGURATION (Keep as is)
# ============================================
UPSTOX_API_KEY=your-upstox-api-key
UPSTOX_API_SECRET=your-upstox-api-secret
UPSTOX_REDIRECT_URI=http://localhost:8000/api/upstox/callback

# ============================================
# EXISTING RAZORPAY CONFIGURATION (Keep as is)
# ============================================
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_secret
RAZORPAY_WEBHOOK_SECRET=your_razorpay_webhook_secret
RAZORPAY_ENVIRONMENT=test
RAZORPAY_CURRENCY=INR

# ============================================
# APPLICATION CONFIGURATION
# ============================================
BASE_URL=http://localhost:8000
DEBUG=False
FLASK_ENV=development
LOG_LEVEL=INFO
CORS_ORIGINS=*
RATE_LIMIT=100/hour

# ============================================
# FEATURE FLAGS
# ============================================
ENABLE_CACHING=True
ENABLE_RATE_LIMITING=True
ENABLE_JWT_BLACKLIST=True
ENABLE_ANON_TRIALS=True
```

---

## Validation Checklist

Before implementing the premium system, ensure:

### Critical Requirements
- [x] **MONGODB_URI** is correctly set
- [x] **REDIS_HOST** and **REDIS_PORT** are accessible
- [ ] **CASHFREE_APP_ID_SANDBOX** obtained from Cashfree dashboard
- [ ] **CASHFREE_SECRET_KEY_SANDBOX** obtained from Cashfree dashboard
- [ ] **CASHFREE_WEBHOOK_SECRET** configured in Cashfree dashboard
- [x] **SERVER_TIMEZONE** set to your server's timezone

### Plan Configuration
- [ ] All **PLAN_*_WEEKLY** prices are defined
- [ ] All **PLAN_*_MONTHLY** prices are defined
- [ ] All **PLAN_*_ANNUAL** prices are defined
- [ ] All **PLAN_*__MARKET_REGIME** limits are defined
- [ ] All **PLAN_*__AI_ASSISTANT** limits are defined
- [ ] All **PLAN_*__BACKTEST** limits are defined

### Anonymous Limits
- [ ] **ANON_MARKET_REGIME_LIMIT** is set
- [ ] **ANON_AI_ASSISTANT_LIMIT** is set
- [ ] **ANON_BACKTEST_LIMIT** is set
- [ ] **ANON_SESSION_TTL_SECONDS** is appropriate

### Testing Setup
- [ ] Set **IS_PAYMENT_GATEWAY_ENABLED=false** for initial testing
- [ ] Set **CASHFREE_ENV=sandbox** for payment testing
- [ ] Only set **CASHFREE_ENV=production** when going live

---

## Important Notes

### 1. Naming Convention
The plan limits use a double underscore (`__`) separator:
- Format: `PLAN_{PLAN_NAME}__{FEATURE_NAME}={LIMIT}`
- Example: `PLAN_STARTER__MARKET_REGIME=20`

### 2. Feature Names
The three premium features have specific internal names:
- `MARKET_REGIME` → maps to endpoint: `/api/ai_forecast/full_trade_forecast`
- `AI_ASSISTANT` → maps to endpoint: `/api/nextgenchat`
- `BACKTEST` → maps to endpoint: `/api/backtest/run`

### 3. Plan Names
Valid plan names (case-sensitive):
- `FREE`
- `STARTER`
- `PRO`
- `ADVANCED`
- `ENTERPRISE`

### 4. Duration Options
Valid duration options for paid plans:
- `weekly`
- `monthly`
- `annual`

### 5. Cashfree Setup Steps

**Step 1: Create Cashfree Account**
1. Go to https://www.cashfree.com/
2. Sign up for a merchant account
3. Complete KYC verification

**Step 2: Get Sandbox Credentials**
1. Login to Cashfree Dashboard
2. Go to Developers → API Keys
3. Copy **App ID** and **Secret Key** for Sandbox
4. Add them to your `.env` as `CASHFREE_APP_ID_SANDBOX` and `CASHFREE_SECRET_KEY_SANDBOX`

**Step 3: Configure Webhook**
1. In Cashfree Dashboard, go to Developers → Webhooks
2. Add webhook URL: `https://your-domain.com/api/payment/webhook`
3. Enable webhook for payment events
4. Copy the **Webhook Secret Key**
5. Add it to your `.env` as `CASHFREE_WEBHOOK_SECRET`

**Step 4: Test Payment Flow**
1. Keep `CASHFREE_ENV=sandbox`
2. Use Cashfree test cards for testing
3. Monitor webhook calls in Cashfree dashboard

**Step 5: Go Live**
1. Complete production onboarding in Cashfree
2. Get production credentials
3. Add to `.env` as `CASHFREE_APP_ID_PROD` and `CASHFREE_SECRET_KEY_PROD`
4. Change `CASHFREE_ENV=production`

### 6. Redis Requirements
Redis is **CRITICAL** for this implementation:
- Used for fast atomic counter increments
- Prevents race conditions in concurrent requests
- Stores anonymous session counters
- Must be running before starting the server

**Test Redis Connection:**
```bash
redis-cli ping
# Should return: PONG
```

### 7. MongoDB Collections
The implementation will create these new collections:
- `plans` - Plan definitions and limits
- `transactions` - Payment transaction records
- `usage_logs` - Audit logs for feature usage
- `webhook_events` - Raw webhook payloads

### 8. Security Considerations
- Never commit `.env` to git
- Rotate secrets regularly
- Use strong webhook secrets
- Keep production and sandbox credentials separate
- Use HTTPS for all webhook endpoints in production

---

## What Happens Next?

After you add these environment variables to your `.env` file:

1. **Config Loading**: The `config.py` file will be updated to load these new variables
2. **Plans Seeding**: A startup script will seed the `plans` collection in MongoDB from these env variables
3. **Limit Enforcement**: Middleware will check these limits before allowing access to premium features
4. **Payment Integration**: Cashfree will handle payments and trigger webhooks
5. **Usage Tracking**: Redis will track real-time usage counters

---

## Quick Start Commands

```bash
# 1. Copy this template to your .env file
# 2. Fill in the Cashfree credentials
# 3. Verify Redis is running
redis-cli ping

# 4. Test MongoDB connection
mongo $MONGODB_URI

# 5. Start the server
python server.py

# 6. Check logs for successful plan seeding
# You should see: "Successfully seeded X plans to database"
```

---

## Support

If you encounter issues:
1. Check Redis is running: `redis-cli ping`
2. Verify MongoDB connection: Use the URI in your .env
3. Validate all plan variables are defined
4. Check Cashfree dashboard for webhook logs
5. Review application logs for errors

---

**Last Updated**: 2025-10-29
**Blueprint Version**: 1.0
**Implementation Status**: Ready for Development
