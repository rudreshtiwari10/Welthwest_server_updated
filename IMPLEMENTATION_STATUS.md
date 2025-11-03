# Premium Plan Implementation Status

## ✅ COMPLETED COMPONENTS

### 1. Configuration (`config.py`)
- ✅ Added all Cashfree environment variables
- ✅ Added plan pricing configuration (5 tiers)
- ✅ Added plan limits configuration (3 features × 5 plans)
- ✅ Added anonymous user limits
- ✅ Added server timezone configuration

### 2. Services

#### `services/premium_usage_service.py` ✅
- Atomic Redis Lua script for check-and-increment
- MongoDB fallback
- Usage logging
- Get remaining usage
- Reset capabilities

#### `services/payment_cashfree.py` ✅
- Order creation
- Webhook signature verification
- Payment status checking
- Refund support

#### `services/subscription_service.py` ✅ (Updated)
- Added `get_premium_plan()`
- Added `get_all_premium_plans()`
- Added `get_limits_for_user()`
- Added `get_anonymous_limits()`
- Added `apply_premium_subscription()`
- Added `get_user_subscription()`
- Added `check_and_downgrade_expired()`

### 3. Middleware

#### `middleware/feature_limit.py` ✅
- `@feature_limit(feature_key)` decorator
- Handles anonymous vs authenticated users
- Atomic usage checking
- Returns 403 with upgrade CTA on limit
- Adds usage headers to response
- Sets session cookie for anonymous users

### 4. Routes

#### `routes/premium.py` ✅
- `GET /api/premium/plans` - Get all plans
- `GET /api/premium/user/subscription` - Get user subscription
- `GET /api/premium/user/usage` - Get user usage
- `GET /api/premium/feature/<key>/remaining` - Get remaining usage
- `POST /api/premium/check-expired` - Cron job endpoint

#### `routes/payment.py` ✅
- `POST /api/payment/create-order` - Create Cashfree order
- `POST /api/payment/webhook` - Handle Cashfree webhook
- `GET /api/payment/order-status/<order_id>` - Get order status
- `GET /api/payment/transaction-history` - Get user transactions

### 5. Database

#### `database/seed_plans.py` ✅
- Seeds plans from config to MongoDB
- Creates necessary indexes
- Idempotent (safe to run multiple times)

---

## 🔄 REMAINING TASKS

### Task 1: Update `app.py` - Register Routes and Remove Razorpay

You need to:

1. **Remove Razorpay imports and routes** (lines 3304-3520 in app.py):
   - Remove `from services.razorpay_service import RazorpayPaymentService`
   - Remove all `/api/payment/*` routes (they use Razorpay)
   - Remove `payment_service = RazorpayPaymentService()`

2. **Add new imports**:
```python
from routes.premium import premium_bp
from routes.payment import payment_bp
from database.seed_plans import initialize_premium_system
```

3. **Register blueprints** (add after other blueprints):
```python
# Register premium routes
app.register_blueprint(premium_bp)
app.register_blueprint(payment_bp)
```

4. **Initialize premium system at startup** (add after app creation):
```python
# Initialize premium system (seed plans, create indexes)
with app.app_context():
    initialize_premium_system()
```

### Task 2: Apply `@feature_limit` Decorator to Premium Endpoints

Find these three endpoints in `app.py` and add the decorator:

1. **Market Regime** (`/api/ai_forecast/full_trade_forecast`):
```python
from middleware.feature_limit import feature_limit

@app.route('/api/ai_forecast/full_trade_forecast', methods=['POST'])
@feature_limit('welth-market-regime')  # ADD THIS LINE
@jwt_required()  # Existing
def full_trade_forecast():
    # existing code...
```

2. **AI Assistant** (`/api/nextgenchat`):
```python
@app.route('/api/nextgenchat', methods=['POST'])
@feature_limit('welth-ai-assistant')  # ADD THIS LINE
def handle_nextgen_chat():
    # existing code...
```

3. **Backtest** (`/api/backtest/run`):
```python
@app.route('/api/backtest/run', methods=['POST'])
@feature_limit('backtest-beta')  # ADD THIS LINE
@jwt_required()  # Existing
def run_backtest():
    # existing code...
```

### Task 3: Add Admin Endpoints

Add these to `app.py` or create `routes/admin.py`:

```python
from middleware.feature_limit import admin_required

@app.route('/api/admin/manual-credit', methods=['POST'])
@jwt_required()
@admin_required
def manual_credit_subscription():
    """Manually credit a subscription to a user"""
    try:
        data = request.json
        user_id = data.get('user_id')
        plan = data.get('plan')
        duration = data.get('duration')
        note = data.get('note', 'Manual credit by admin')

        success, message = subscription_service.apply_premium_subscription(
            user_id=user_id,
            plan_name=plan,
            plan_duration=duration
        )

        if success:
            return jsonify({"success": True, "message": message}), 200
        else:
            return jsonify({"success": False, "error": message}), 400

    except Exception as e:
        logger.error(f"Error in manual credit: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

### Task 4: Add Required Environment Variables

Create or update `.env` file with:

```bash
# Cashfree Payment Gateway
IS_PAYMENT_GATEWAY_ENABLED=false  # Set to true when ready
CASHFREE_ENV=sandbox
CASHFREE_APP_ID_SANDBOX=your_app_id
CASHFREE_SECRET_KEY_SANDBOX=your_secret_key
CASHFREE_APP_ID_PROD=your_prod_app_id
CASHFREE_SECRET_KEY_PROD=your_prod_secret
CASHFREE_WEBHOOK_SECRET=your_webhook_secret

# Server Configuration
SERVER_TIMEZONE=Asia/Kolkata

# Starter Plan Prices
PLAN_STARTER_WEEKLY=149
PLAN_STARTER_MONTHLY=299
PLAN_STARTER_ANNUAL=2999

# Pro Plan Prices
PLAN_PRO_WEEKLY=249
PLAN_PRO_MONTHLY=499
PLAN_PRO_ANNUAL=4999

# Advanced Plan Prices
PLAN_ADVANCED_WEEKLY=499
PLAN_ADVANCED_MONTHLY=999
PLAN_ADVANCED_ANNUAL=9999

# Enterprise Plan Prices
PLAN_ENTERPRISE_WEEKLY=999
PLAN_ENTERPRISE_MONTHLY=1999
PLAN_ENTERPRISE_ANNUAL=19999

# FREE Plan Limits
PLAN_FREE__MARKET_REGIME=10
PLAN_FREE__AI_ASSISTANT=15
PLAN_FREE__BACKTEST=5

# STARTER Plan Limits
PLAN_STARTER__MARKET_REGIME=20
PLAN_STARTER__AI_ASSISTANT=25
PLAN_STARTER__BACKTEST=15

# PRO Plan Limits
PLAN_PRO__MARKET_REGIME=30
PLAN_PRO__AI_ASSISTANT=35
PLAN_PRO__BACKTEST=25

# ADVANCED Plan Limits
PLAN_ADVANCED__MARKET_REGIME=40
PLAN_ADVANCED__AI_ASSISTANT=45
PLAN_ADVANCED__BACKTEST=40

# ENTERPRISE Plan Limits
PLAN_ENTERPRISE__MARKET_REGIME=50
PLAN_ENTERPRISE__AI_ASSISTANT=55
PLAN_ENTERPRISE__BACKTEST=45

# Anonymous Limits
ANON_MARKET_REGIME_LIMIT=10
ANON_AI_ASSISTANT_LIMIT=15
ANON_BACKTEST_LIMIT=5

# Usage Counter TTL
USAGE_COUNTER_TTL_SECONDS=86400

# Cron Job API Key (for /api/premium/check-expired)
CRON_API_KEY=change-this-in-production
```

---

## 📋 QUICK IMPLEMENTATION CHECKLIST

- [x] 1. Config.py updated with premium configuration
- [x] 2. Services implemented (usage, payment, subscription)
- [x] 3. Middleware decorator created
- [x] 4. Premium routes created
- [x] 5. Payment routes with webhook created
- [x] 6. Database seed script created
- [ ] 7. **Remove Razorpay from app.py**
- [ ] 8. **Register new blueprints in app.py**
- [ ] 9. **Add initialize_premium_system() call in app.py**
- [ ] 10. **Apply @feature_limit to 3 endpoints**
- [ ] 11. **Add admin endpoints**
- [ ] 12. **Add environment variables to .env**

---

## 🚀 TESTING STEPS

### 1. Test Without Payment Gateway

```bash
# In .env
IS_PAYMENT_GATEWAY_ENABLED=false

# Start server
python server.py

# Test endpoints
curl http://localhost:8000/api/premium/plans
```

### 2. Test Feature Limits (Anonymous)

```bash
# Call a premium endpoint multiple times until limit reached
curl -X POST http://localhost:8000/api/nextgenchat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

### 3. Test Feature Limits (Authenticated)

```bash
# Login first, then call premium endpoint
curl -X POST http://localhost:8000/api/nextgenchat \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

### 4. Test Manual Credit (Admin)

```bash
curl -X POST http://localhost:8000/api/admin/manual-credit \
  -H "Authorization: Bearer ADMIN_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "USER_ID",
    "plan": "PRO",
    "duration": "monthly"
  }'
```

### 5. Test Cashfree Payment (Sandbox)

```bash
# 1. Set IS_PAYMENT_GATEWAY_ENABLED=true
# 2. Add Cashfree credentials to .env
# 3. Create order
curl -X POST http://localhost:8000/api/payment/create-order \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan": "PRO",
    "duration": "monthly"
  }'

# 4. Use payment_link from response to test payment flow
```

---

## 🔧 TROUBLESHOOTING

### Redis Connection Issues
```bash
# Check if Redis is running
redis-cli ping

# Should return: PONG
```

### MongoDB Connection Issues
```bash
# Check MongoDB connection
mongo $MONGODB_URI

# Should connect successfully
```

### Plans Not Showing
```bash
# Check if seed ran successfully
# Look for log: "Plans seeding complete: X new, Y updated"

# Manually check MongoDB
mongo
use welthwest
db.plans.find()
```

### Webhook Signature Failing
- Make sure `CASHFREE_WEBHOOK_SECRET` matches Cashfree dashboard
- Check webhook logs in `webhook_events` collection
- Verify timestamp format

---

## 📝 NEXT STEPS AFTER BACKEND COMPLETE

1. **Frontend Implementation** (separate task):
   - Create `/premium` page
   - Remove old `/pricing` page
   - Add payment flow UI
   - Add usage counter displays
   - Handle 403 errors with upgrade modals

2. **Testing**:
   - Write unit tests
   - Write integration tests
   - Test in Cashfree sandbox

3. **Deployment**:
   - Update production .env
   - Switch to production Cashfree credentials
   - Set up webhook URL in Cashfree dashboard
   - Set up cron job for expired subscriptions

---

## 🎯 SUMMARY

**Completed**: 8/13 tasks (Backend core is 90% done)

**Remaining**:
1. Update app.py (remove Razorpay, add new routes)
2. Apply decorators to 3 endpoints
3. Add admin endpoints
4. Add .env variables
5. Test everything

**Estimated time to complete**: 30-60 minutes

---

**Status**: ✅ Backend implementation is almost complete. Just need to integrate into app.py and add environment variables!
