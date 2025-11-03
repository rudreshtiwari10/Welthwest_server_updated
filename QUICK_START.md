# Premium Plan - Quick Start Guide

## 📋 What You Need to Do RIGHT NOW

### 1️⃣ Get Cashfree Credentials (15 minutes)

```
1. Go to: https://www.cashfree.com/
2. Sign up for Merchant Account
3. Login to Dashboard
4. Navigate to: Developers → API Keys
5. Copy these values:
   - App ID (Sandbox)
   - Secret Key (Sandbox)
6. Navigate to: Developers → Webhooks
7. Add webhook URL (for later): https://your-domain.com/api/payment/webhook
8. Copy: Webhook Secret
```

### 2️⃣ Update Your .env File (5 minutes)

Open `WelthWestServer_sharing_/.env` and add these lines:

```bash
# Copy everything from ENV_ADDITIONS_REQUIRED.txt
# Replace these three values with your actual Cashfree credentials:

CASHFREE_APP_ID_SANDBOX=paste_your_app_id_here
CASHFREE_SECRET_KEY_SANDBOX=paste_your_secret_key_here
CASHFREE_WEBHOOK_SECRET=paste_your_webhook_secret_here
```

**IMPORTANT**: Don't forget to replace the placeholder values!

### 3️⃣ Verify Prerequisites (2 minutes)

```bash
# Test Redis
redis-cli ping
# Should return: PONG

# Test MongoDB
mongo $MONGODB_URI
# Should connect successfully

# Verify your .env has these critical variables:
# - MONGODB_URI ✓
# - REDIS_HOST ✓
# - REDIS_PORT ✓
# - CASHFREE_APP_ID_SANDBOX ✓
# - CASHFREE_SECRET_KEY_SANDBOX ✓
# - CASHFREE_WEBHOOK_SECRET ✓
```

### 4️⃣ Tell Me You're Ready

Once you've completed steps 1-3, reply with:

**"Start implementation"**

And I'll begin coding Phase A (Backend Core)!

---

## 📊 Environment Variables Summary

**Total Required**: 52 new variables

**Critical Ones** (must have for basic functionality):
- `CASHFREE_APP_ID_SANDBOX` ← **MUST GET FROM CASHFREE**
- `CASHFREE_SECRET_KEY_SANDBOX` ← **MUST GET FROM CASHFREE**
- `CASHFREE_WEBHOOK_SECRET` ← **MUST GET FROM CASHFREE**
- `IS_PAYMENT_GATEWAY_ENABLED` ← Set to `false` initially
- `SERVER_TIMEZONE` ← Your server timezone (e.g., Asia/Kolkata)

**Pricing Variables** (12 total - can customize):
- PLAN_STARTER_WEEKLY, PLAN_STARTER_MONTHLY, PLAN_STARTER_ANNUAL
- PLAN_PRO_WEEKLY, PLAN_PRO_MONTHLY, PLAN_PRO_ANNUAL
- PLAN_ADVANCED_WEEKLY, PLAN_ADVANCED_MONTHLY, PLAN_ADVANCED_ANNUAL
- PLAN_ENTERPRISE_WEEKLY, PLAN_ENTERPRISE_MONTHLY, PLAN_ENTERPRISE_ANNUAL

**Limit Variables** (15 total - can customize):
- PLAN_FREE__MARKET_REGIME, PLAN_FREE__AI_ASSISTANT, PLAN_FREE__BACKTEST
- PLAN_STARTER__MARKET_REGIME, PLAN_STARTER__AI_ASSISTANT, PLAN_STARTER__BACKTEST
- PLAN_PRO__MARKET_REGIME, PLAN_PRO__AI_ASSISTANT, PLAN_PRO__BACKTEST
- PLAN_ADVANCED__MARKET_REGIME, PLAN_ADVANCED__AI_ASSISTANT, PLAN_ADVANCED__BACKTEST
- PLAN_ENTERPRISE__MARKET_REGIME, PLAN_ENTERPRISE__AI_ASSISTANT, PLAN_ENTERPRISE__BACKTEST

**Anonymous Limits** (3 total - can customize):
- ANON_MARKET_REGIME_LIMIT
- ANON_AI_ASSISTANT_LIMIT
- ANON_BACKTEST_LIMIT

---

## 🎯 Feature Mapping

Three premium features will have usage limits:

| Feature Name | Internal Key | Endpoint |
|---|---|---|
| Market Regime Classifier | `welth-market-regime` | `/api/ai_forecast/full_trade_forecast` |
| AI Assistant | `welth-ai-assistant` | `/api/nextgenchat` |
| Backtest | `backtest-beta` | `/api/backtest/run` |

---

## 💰 Default Pricing (from blueprint)

| Plan | Weekly | Monthly | Annual |
|---|---|---|---|
| FREE | ₹0 | ₹0 | ₹0 |
| STARTER | ₹149 | ₹299 | ₹2,999 |
| PRO | ₹249 | ₹499 | ₹4,999 |
| ADVANCED | ₹499 | ₹999 | ₹9,999 |
| ENTERPRISE | ₹999 | ₹1,999 | ₹19,999 |

---

## 📈 Default Limits (per day)

| Plan | Market Regime | AI Assistant | Backtest |
|---|---|---|---|
| FREE | 10 | 15 | 5 |
| STARTER | 20 | 25 | 15 |
| PRO | 30 | 35 | 25 |
| ADVANCED | 40 | 45 | 40 |
| ENTERPRISE | 50 | 55 | 45 |

**Anonymous Users**: Same as FREE (10 / 15 / 5)

---

## 🔐 Security Checklist

- [ ] Never commit `.env` to git
- [ ] Use `.gitignore` to exclude `.env`
- [ ] Keep sandbox and production credentials separate
- [ ] Test webhook signature verification thoroughly
- [ ] Use HTTPS for all webhooks in production
- [ ] Rotate secrets periodically
- [ ] Monitor webhook logs in Cashfree dashboard

---

## 🚀 Implementation Phases

### Phase A: Backend Core (4-6 hours)
- Config updates
- Services (subscription, usage, payment)
- Middleware (feature_limit decorator)
- Routes (premium, payment)
- Database seeding
- Endpoint decoration

### Phase B: Frontend (3-4 hours)
- Premium page
- Payment service
- Subscription context
- Feature page updates

### Phase C: Admin & Testing (2-3 hours)
- Admin endpoints
- Unit tests
- Integration tests
- E2E testing

---

## 📝 Files to Review

1. **PREMIUM_ENV_VARIABLES.md**
   - Complete documentation
   - Cashfree setup guide
   - Security best practices

2. **ENV_ADDITIONS_REQUIRED.txt**
   - Copy-paste ready variables
   - Just update placeholders

3. **IMPLEMENTATION_SUMMARY.txt**
   - Detailed implementation plan
   - Architectural decisions
   - Timeline estimates

4. **QUICK_START.md** (this file)
   - Quick reference
   - Action items

---

## ❓ Quick FAQ

**Q: Can I test without Cashfree credentials?**
A: Yes! Set `IS_PAYMENT_GATEWAY_ENABLED=false` and use admin endpoints for manual credits.

**Q: Can I change prices later?**
A: Yes! Just update the `.env` variables and restart the server.

**Q: Can I change limits later?**
A: Yes! Update `.env`, restart server. Changes apply to new requests immediately.

**Q: What if Redis is down?**
A: The app will fall back to MongoDB (slower but functional).

**Q: Do I need to modify the blueprint limits?**
A: No, use the defaults. You can always adjust them later.

**Q: Should I use sandbox or production first?**
A: Always start with sandbox (`CASHFREE_ENV=sandbox`) for testing.

---

## 🎬 Ready to Start?

Complete these steps:
1. ✅ Get Cashfree credentials
2. ✅ Update .env file
3. ✅ Verify Redis is running
4. ✅ Verify MongoDB is running
5. ✅ Review the three documentation files

Then reply: **"Start implementation"**

---

**Need help?** Review the detailed docs:
- `PREMIUM_ENV_VARIABLES.md` for env setup
- `IMPLEMENTATION_SUMMARY.txt` for full plan
- `ENV_ADDITIONS_REQUIRED.txt` for quick copy-paste

Let's build this! 🚀
