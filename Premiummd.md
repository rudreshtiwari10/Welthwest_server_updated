Nice — I’ll produce a single, long, detailed implementation blueprint you can save as a .md and hand to Claude (or any engineer). I’ll assume the facts you already gave (Flask backend, React + TypeScript frontend, MongoDB, Redis, Gunicorn, JWT auth, the three premium features and the exact limits you gave). I’ll not ask anything else — I’ll make reasonable engineering choices and call out where you might want to change details later.

Below is the full, ready-to-use Markdown implementation plan. Save it as premium-plan-blueprint.md and hand to Claude for implementation. It’s organized so every section is actionable (objectives, requirements, data model, endpoints, middleware, env variables, Cashfree flow, tests, manual tasks, timeline of “what you do vs what Claude/automation does”, and more).

Premium Plan Blueprint — WelthWest

Version: 1.0
Prepared for: WelthWest (Flask backend, React/TypeScript frontend)
Scope: Implement premium plans (Free / Starter / Pro / Advanced / Enterprise) with per-feature, per-day usage limits configurable via .env, Cashfree payment integration with webhook verification, Redis/Mongo usage counters, replacement of /pricing with /premium, and a full operations/testing/deploy checklist.

⸻

Table of contents
	1.	Objective
	2.	High-level design & assumptions
	3.	Functional requirements
	4.	Non-functional requirements
	5.	Environment & config (.env) specification
	6.	Data model (MongoDB collections + sample documents)
	7.	Redis usage & key patterns
	8.	Backend architecture & API endpoints (Flask)
	9.	Middleware & rate-limiting logic (implementation detail)
	10.	Cashfree integration (order flow, webhook, signature verification)
	11.	Frontend changes (React/TSX) — /premium page + UX flows
	12.	Billing & subscription lifecycle (purchase, upgrade, downgrade, expiry)
	13.	Admin & maintenance interfaces
	14.	Security considerations
	15.	Testing strategy (unit, integration, E2E, payment sandbox)
	16.	Monitoring, logging, and metrics
	17.	Deployment & CI/CD checklist
	18.	Rollback & incident response plan
	19.	Manual tasks you must perform (ordered)
	20.	Tasks for Claude (what to implement) — step-by-step
	21.	Edge cases & business policy decisions to confirm later
	22.	Appendix: code snippets, sample .env, Redis Lua atomic script, sample responses

⸻

1. Objective

Add a premium subscription system to WelthWest that:
	•	Provides Free, Starter, Pro, Advanced, and Enterprise plans with per-feature, daily-use limits.
	•	Limits apply to three premium features: /welth-market-regime, /welth-ai-assistant, /backtest-beta.
	•	Limits (per-plan, per-feature) are configurable from .env (no hardcoding).
	•	Anonymous visitors get a limited number of free uses per feature (session-based).
	•	Authentication remains JWT + Google OAuth; limits for authenticated users are tied to user accounts.
	•	Payment processing via Cashfree; purchases upgrade user plans after webhook verification.
	•	/pricing page is removed and replaced by a dynamic /premium page that reads plan limits/prices from backend (which loads env at runtime).
	•	Use Redis for counters (fast), and MongoDB for persistent records (users, subscriptions, transactions, audit logs).
	•	Provide admin/manual fallback: if payment gateway disabled (IS_PAYMENT_GATEWAY_ENABLED=false), site honors .env manual totals or admin-created orders.

⸻

2. High-level design & assumptions
	•	Backend: Flask app (existing). We’ll add middleware decorators and services. Use Gunicorn for production unchanged.
	•	DB: MongoDB for persistent data; users, plans, transactions, usage_logs collections.
	•	Cache/fast counters: Redis already exists — continue to use it for anonymous session counters and authenticated daily counters.
	•	Auth: JWT (flask_jwt_extended) remains in use; get_jwt_identity() gives user id.
	•	Times: daily limits reset at server midnight (server timezone). Optionally implement sliding-window — blueprint uses fixed-window per-day.
	•	Feature names and internal IDs:
	•	market-regime => endpoint tag welth-market-regime
	•	ai-assistant => endpoint tag welth-ai-assistant
	•	backtest => endpoint tag backtest-beta
	•	Plans and per-feature limits are stored in .env and optionally written to plans collection at startup to make them queryable via API.

⸻

3. Functional requirements
	•	Replace /pricing with /premium page that shows plan names, prices, and per-feature limits (values read from backend which reads .env).
	•	Anonymous users:
	•	Session cookie ww_session_id for identification.
	•	Anonymous limits (per feature) default: Market Regime: 10, AI Assistant: 15, Backtest: 5 (as provided).
	•	Authenticated users:
	•	Each user has a subscription object with plan name, start_date, expiry_date, and custom limits if applicable.
	•	Limits applied per-feature per-day, configured by plan and from .env.
	•	Limit enforcement:
	•	Middleware checks Redis (fast) or Mongo (fall back) for the current count; if exceeded respond with 403 + CTA to /premium.
	•	Payment Flow (Cashfree):
	•	Create order on backend with plan and amount.
	•	Redirect user to Cashfree checkout (hosted or embedded).
	•	Cashfree calls webhook on success; verify signature and update user subscription and creation of transaction record.
	•	After upgrade, user limits should immediately reflect the new plan (after webhook).
	•	Manual mode:
	•	When IS_PAYMENT_GATEWAY_ENABLED=false, provide a UI + admin endpoint to mark a user as paid manually (for testing or manual orders). This uses .env prices or admin input.

⸻

4. Non-functional requirements
	•	Performance: Limit checks must be low-latency (<20ms typical).
	•	Scalability: Redis counters must be safe under multi-instance deployment.
	•	Idempotency: Webhook handlers must be idempotent to avoid double-upgrades.
	•	Observability: All payment and limit events logged for auditing.
	•	Security: Webhook signatures verified, secrets never exposed to frontend.
	•	Maintainability: Clear separation of services: services/payment.py, services/subscription.py, middleware/feature_limit.py.

⸻

5. Environment & config (.env) specification

All keys will be loaded via config.py (you already use python-dotenv). Add the following variables.

Required environment variables (examples)

# Basic app / DB
MONGODB_URI=mongodb://localhost:27017/
DB_NAME=welthwest
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
JWT_SECRET_KEY=supersecret
SERVER_TIMEZONE=Asia/Kolkata

# Cashfree
IS_PAYMENT_GATEWAY_ENABLED=true
CASHFREE_APP_ID_SANDBOX=your_sandbox_app_id
CASHFREE_SECRET_KEY_SANDBOX=your_sandbox_secret
CASHFREE_APP_ID_PROD=your_prod_app_id
CASHFREE_SECRET_KEY_PROD=your_prod_secret
CASHFREE_WEBHOOK_SECRET=cashfree_webhook_signing_secret
CASHFREE_ENV=sandbox  # or production

# Plan prices (example)
PLAN_STARTER_WEEKLY=149
PLAN_STARTER_MONTHLY=299
PLAN_STARTER_ANNUAL=2999

PLAN_PRO_WEEKLY=249
PLAN_PRO_MONTHLY=499
PLAN_PRO_ANNUAL=4999

PLAN_ADVANCED_WEEKLY=499
PLAN_ADVANCED_MONTHLY=999
PLAN_ADVANCED_ANNUAL=9999

PLAN_ENTERPRISE_WEEKLY=999
PLAN_ENTERPRISE_MONTHLY=1999
PLAN_ENTERPRISE_ANNUAL=19999

# Per-feature limits per plan (values from user)
# Format: <PLAN>__<FEATURE>=<limit>
# FEATURES: MARKET_REGIME, AI_ASSISTANT, BACKTEST

PLAN_FREE__MARKET_REGIME=10
PLAN_FREE__AI_ASSISTANT=15
PLAN_FREE__BACKTEST=5

PLAN_STARTER__MARKET_REGIME=20
PLAN_STARTER__AI_ASSISTANT=25
PLAN_STARTER__BACKTEST=15

PLAN_PRO__MARKET_REGIME=30
PLAN_PRO__AI_ASSISTANT=35
PLAN_PRO__BACKTEST=25

PLAN_ADVANCED__MARKET_REGIME=40
PLAN_ADVANCED__AI_ASSISTANT=45
PLAN_ADVANCED__BACKTEST=40

PLAN_ENTERPRISE__MARKET_REGIME=50
PLAN_ENTERPRISE__AI_ASSISTANT=55
PLAN_ENTERPRISE__BACKTEST=45

# Anonymous limits (session-based)
ANON_MARKET_REGIME_LIMIT=10
ANON_AI_ASSISTANT_LIMIT=15
ANON_BACKTEST_LIMIT=5

# Feature keys TTL & behavior
USAGE_COUNTER_TTL_SECONDS=86400  # 24 hours

NOTE: Naming convention uses __ to make parsing simple. You can also provide JSON in env (e.g., PLAN_LIMITS_JSON) but keep it simple.

⸻

6. Data model (MongoDB)

Collections
	1.	users
	2.	plans (optional but recommended — mirrors env)
	3.	transactions
	4.	usage_logs (audit)
	5.	webhook_events (optional — raw webhook payloads & verification status)

users sample document

{
  "_id": ObjectId("..."),
  "email": "user@example.com",
  "username": "rudresh",
  "password_hash": "...",
  "is_google_user": false,
  "role": "user",
  "created_at": ISODate("2025-10-29T00:00:00Z"),
  "subscription": {
    "plan": "FREE",            // FREE | STARTER | PRO | ADVANCED | ENTERPRISE
    "plan_duration": "monthly",// "monthly" | "annual" | "weekly"
    "start_date": ISODate(...),
    "expiry_date": ISODate(...),
    "custom_limits": {         // optional overrides
      "welth-market-regime": 25,
      "welth-ai-assistant": 30
    }
  }
}

plans sample document (recommended; loaded at app start from env)

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
  },
  "created_at": ISODate(...),
  "updated_at": ISODate(...)
}

transactions sample document

{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "plan_id": "PRO",
  "amount": 499,
  "currency": "INR",
  "status": "PENDING", // PENDING | SUCCESS | FAILED | REFUNDED
  "gateway": "CASHFREE",
  "gateway_order_id": "order_abc123", // Cashfree order id if created
  "gateway_payment_id": "pay_abc123", // Cashfree payment id (on success)
  "created_at": ISODate(...),
  "updated_at": ISODate(...),
  "meta": {} // raw webhook payload, etc.
}

usage_logs sample document

{
  "_id": ObjectId("..."),
  "user_id": ObjectId(...), // null for anonymous sessions
  "session_id": "anon_xxx", // only for anonymous
  "feature": "welth-market-regime",
  "action": "USE", // or "DENY"
  "result": "ALLOWED", // ALLOWED/DENIED
  "remaining": 3,
  "created_at": ISODate(...)
}

Indexes:
	•	users.email unique
	•	transactions.user_id + transactions.created_at
	•	usage_logs.user_id + usage_logs.created_at (for query by day/audit)
	•	plans._id unique

⸻

7. Redis usage & key patterns

Use Redis for all live counters. Keep short keys and TTLs.

Key patterns
	•	Anonymous session counter:
	•	anon:{session_id}:usage:{feature} → integer
	•	Authenticated user daily counter:
	•	user:{user_id}:usage:{feature}:{YYYYMMDD} → integer
	•	Optionally store a TTL or set expiry to the next midnight automatically.

Example
	•	anon:session_abc123:usage:welth-market-regime = 4 (EXPIRE in seconds to midnight)
	•	user:634b...:usage:backtest-beta:20251029 = 2 (expires after 48 hours as safety)

Best practice (set expire):

When incrementing key for the first time, set expire to seconds until next midnight (server timezone) or to USAGE_COUNTER_TTL_SECONDS (24h).

Atomic check-and-incr (Lua script recommended)

Use a Lua script to check current value, compare with limit, increment only if allowed, and return allowed+remaining. This avoids race conditions when multiple requests arrive concurrently.

(See Appendix for a sample Lua script.)

⸻

8. Backend architecture & API endpoints (Flask)

Services to add or update
	•	services/subscription_service.py — plan queries, apply plan to user, check plan limits
	•	services/usage_service.py — abstraction that reads/writes Redis counters and logs to Mongo
	•	services/payment_cashfree.py — create order, signature verify, webhook handling
	•	middleware/feature_limit.py — decorators for endpoints
	•	routes/premium.py — /api/premium/* endpoints
	•	routes/payment.py — /api/payment/* (create-order, webhook)
	•	routes/admin.py — admin endpoints for manual purchase (protected)

Core API endpoints (suggested)

GET /api/premium/plans
  - returns list of plans with prices and per-feature limits (reads from env/plans collection)

POST /api/payment/create-order
  - body: { plan: "PRO", duration: "monthly"}
  - auth: required (user must be logged in)
  - response: { order_id, redirect_url / token } // depends on Cashfree integration

POST /api/payment/webhook
  - Cashfree webhook endpoint (public)
  - Verifies signature, updates transaction status, upgrades user plan if successful
  - idempotent

POST /api/premium/manual-credit  (admin only)
  - manually credit / mark a user as having purchased a plan
  - body: { user_id, plan, duration, note }

GET /api/user/usage
  - returns the current day's usage per feature and remaining quota for the authenticated user

GET /api/feature/:feature_name/remaining
  - returns convenience remaining usage for authenticated user or anonymous session

(Existing feature endpoints e.g.)
POST /api/ai_forecast/full_trade_forecast   --> decorated by feature-limit middleware
POST /api/nextgenchat                       --> decorated
POST /api/backtest/run                      --> decorated


⸻

9. Middleware & rate-limiting logic (implementation detail)

Decorator concept: @feature_limit(feature_key)
	•	Applied on route functions for protected features.
	•	Responsibilities:
	1.	Determine actor: if JWT present -> user_id; else -> session_id from cookie ww_session_id (create if absent).
	2.	Fetch plan limits:
	•	If authenticated: read user.subscription -> plan name -> fetch per-feature limit from plans collection or env.
	•	If anonymous: use ANON_* env limits.
	3.	Use usage_service.check_and_increment(actor_key, feature_key, limit) which runs atomic check+increment in Redis (Lua script or INCR & EXPIRE with atomicity).
	4.	If allowed: log usage to usage_logs (async non-blocking) and proceed.
	5.	If denied: respond with HTTP 403 and return helpful JSON:

{
  "error": "usage_limit_reached",
  "message": "Daily limit reached for Market Regime. Upgrade to continue.",
  "premium_url": "/premium"
}



Implementation pseudocode (Flask decorator)

# middleware/feature_limit.py
from functools import wraps
from flask import request, jsonify, g
from services.usage_service import UsageService
from services.subscription_service import SubscriptionService

usage_service = UsageService()
subscription_service = SubscriptionService()

def feature_limit(feature_key):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = None
            user_id = None
            session_id = request.cookies.get("ww_session_id")
            if has_jwt(request):
                user_id = get_jwt_identity()
                plan_limits = subscription_service.get_limits_for_user(user_id)
            else:
                if not session_id:
                    session_id = create_session_cookie()
                plan_limits = subscription_service.get_anonymous_limits()
            limit = plan_limits.get(feature_key)
            allowed, remaining = usage_service.check_and_increment(
                actor_id=(user_id or session_id), feature_key=feature_key, limit=limit
            )
            if not allowed:
                return jsonify({
                    "error": "usage_limit_reached",
                    "premium_url": "/premium",
                    "remaining": 0
                }), 403
            # attach usage info to request context if useful
            g.usage_remaining = remaining
            return fn(*args, **kwargs)
        return wrapper
    return decorator


⸻

10. Cashfree integration (order flow & webhook)

Use Cashfree’s sandbox environment for testing. Keep all secrets in .env. Verify webhooks by computing HMAC with Cashfree’s webhook secret (their docs show how to compute signature; implement as per docs).

Flow (recommended)
	1.	User chooses plan on /premium and clicks “Buy” (duration selected).
	2.	Frontend calls POST /api/payment/create-order with plan + duration. Backend:
	•	Validates user
	•	Reads price from env/plans collection
	•	Creates a transactions document status PENDING
	•	Calls Cashfree Create Order API (server-to-server) and gets order_token / payment_link
	•	Returns the payment_link or order_token to frontend
	3.	Frontend redirects user to Cashfree checkout page (or launches embedded widget).
	4.	Payment completes on Cashfree; Cashfree:
	•	Redirects user back to your frontend success URL.
	•	Sends a server-to-server webhook to /api/payment/webhook with event data and signature.
	5.	Backend webhook handler:
	•	Verifies signature using CASHFREE_WEBHOOK_SECRET and rejects unmatched signatures.
	•	Idempotently updates transactions doc: set status SUCCESS, store gateway_payment_id, store raw payload in webhook_events.
	•	Upgrade user subscription: subscription_service.upgrade_user(user_id, plan, duration, transaction_id)
	•	Return 200 to Cashfree.
	6.	If webhook failed or signature mismatched: log and return 400.

Security & idempotency
	•	Use transactions.gateway_order_id or gateway_payment_id as idempotency keys.
	•	Check whether transactions already processed; if yes, do nothing and return 200.

Webhook sample handler (pseudo)

# routes/payment.py
@app.route('/api/payment/webhook', methods=['POST'])
def cashfree_webhook():
    payload = request.get_data()
    signature = request.headers.get('x-cf-signature')  # example header
    if not verify_cashfree_signature(payload, signature):
        log.warn("Invalid cashfree webhook signature")
        return "", 400
    data = request.json
    txn = find_transaction_by_gateway_order(data['order_id'])
    if not txn:
        log.error("No transaction for order id")
        return "", 404
    if txn['status'] == 'SUCCESS':
        return "", 200
    # update transaction status
    update_transaction_status(txn['_id'], 'SUCCESS', payment_id=data.get('payment_id'), meta=data)
    # upgrade user
    subscription_service.apply_subscription(txn['user_id'], txn['plan_id'], txn['duration'])
    return "", 200


⸻

11. Frontend changes (React / TypeScript)

Pages / Components to update
	•	Remove src/pages/Pricing.tsx.
	•	Create src/pages/Premium.tsx:
	•	Fetch /api/premium/plans on mount and render plan cards.
	•	Each plan card shows per-feature limits and has “Buy” buttons (weekly/monthly/annual).
	•	If user not logged in: CTA to sign in first before purchase (or allow guest purchase with email capture).
	•	Update feature pages (/welth-market-regime, /welth-ai-assistant, /backtest-beta):
	•	On 403 usage_limit_reached response, show a modal with Upgrade CTA (link to /premium) and show remaining = 0.
	•	Show a small counter in the UI that updates based on g.usage_remaining returned or via GET /api/user/usage.
	•	Payment flow:
	•	On buy click: call backend POST /api/payment/create-order → obtain payment_link → window.location.href = payment_link.
	•	After redirect back from Cashfree, show pending state until webhook confirms (GET /api/user/subscription to detect upgrade), or show “Payment processing” message and refresh subscription after webhook.

State & Context
	•	Extend SubscriptionContext to store subscription object and remaining counters (optional poll every X seconds after purchase).
	•	Add an API helper paymentService.ts for createOrder, getOrderStatus (if needed), and manualCredit (admin).

⸻

12. Billing & subscription lifecycle
	•	Create order → transactions PENDING → Cashfree success → webhook → set transactions SUCCESS → subscription updated on user → reset usage counters to 0 (or keep current day’s usage but increase limit immediately).
	•	Downgrade:
	•	If a user downgrades mid-period, set subscription to new plan at next billing cycle OR immediately (policy decision).
	•	Refund:
	•	If refunded: mark transaction.status = REFUNDED, revert subscription to prior state and create refund ledger entry.
	•	Expiration:
	•	Subscription expiry_date stored. If expired, automatically set plan to FREE.
	•	Cron job (daily) to set expired subscriptions to FREE and notify users.

⸻

13. Admin & maintenance interfaces

Create simple protected admin endpoints (admin role) to:
	•	View transactions and webhook_events.
	•	Manually mark transactions as SUCCESS/FAILED.
	•	Manually assign a plan to a user (for manual sales or testing).
	•	View usage stats per user and per feature.

Consider building a small admin dashboard in React or a CLI script.

⸻

14. Security considerations
	•	Never expose secret keys to frontend.
	•	Use HTTPS for all endpoints.
	•	Verify Cashfree webhook signature always; log attempts.
	•	Use MongoDB indexes and parameterized queries — avoid insecure string interpolation.
	•	Input validation for all endpoints (plan names, durations).
	•	Rate-limit webhook endpoint (by IP and signature) to prevent DoS.
	•	Protect admin endpoints via strong JWT and admin role checks.

⸻

15. Testing strategy
	1.	Unit tests
	•	usage_service.check_and_increment() logic (mock Redis).
	•	subscription_service.get_limits_for_user() loading from env or plan collection.
	•	payment_cashfree.create_order() mock HTTP call to Cashfree.
	•	webhook.verify_signature() with valid/invalid payloads.
	2.	Integration tests
	•	Simulate anonymous vs authenticated flows: usage counters increment, deny at limit.
	•	Simulate payment flow with Cashfree sandbox and webhook replay.
	3.	E2E tests
	•	Use Cypress or Playwright to test UI flows:
	•	Visit /premium, buy plan, return to the app, see subscription updated.
	•	Hit feature until limit and see modal.
	4.	Manual QA
	•	Test time-zone edge cases: ensure reset at midnight works in your server timezone.
	•	Test concurrency: send many parallel requests to ensure atomic counters.

⸻

16. Monitoring, logging, and metrics
	•	Log all usage_logs to Mongo (or a dedicated logging system). Include user_id, session_id, feature, allowed/denied.
	•	Capture metrics:
	•	Requests per feature per day.
	•	Number of blocked requests due to limits.
	•	Payment success/failure rates.
	•	Use Sentry/Logtail for error monitoring (optional).
	•	For Cashfree, log webhook payloads to webhook_events for auditing.

⸻

17. Deployment & CI/CD checklist
	•	Add new environment variables to your production environment (CASHFREE keys, plan prices, plan limits).
	•	Add migration script that seeds plans collection from env at startup (idempotent).
	•	Ensure Redis persistence/backup enabled.
	•	Add new endpoints to API gateways or reverse proxy rules.
	•	Add unit & integration test runs to CI (GitHub Actions / GitLab CI).
	•	Manual smoke test after deployment:
	•	Visit /premium and ensure values reflect .env.
	•	Run a sandbox payment flow.

⸻

18. Rollback & incident response plan
	•	If a bug causes overcharging or wrong limits:
	•	Immediately toggle IS_PAYMENT_GATEWAY_ENABLED=false and revert plan limits in .env.
	•	Use admin endpoint to mark pending transactions as FAILED.
	•	Notify affected users via email (template provided below).
	•	Keep backup of Mongo DB and Redis snapshots.

⸻


⸻

20. Tasks for Claude (implementation steps)

Below is an ordered list of concrete tasks you can hand to Claude to implement. Each item should be a commit or small PR.

Phase A — Backend core
	1.	Add services/subscription_service.py:
	•	Functions: get_limits_for_user(user_id), get_plan(plan_id), apply_subscription(user_id, plan_id, duration).
	2.	Add services/usage_service.py:
	•	Functions: check_and_increment(actor_id, feature_key, limit), get_remaining(actor_id, feature_key, limit).
	•	Use Redis and log to usage_logs (async if possible).
	3.	Add middleware/feature_limit.py:
	•	Implement feature_limit decorator as described.
	•	Wire to three existing endpoints (/api/backtest/run, /api/nextgenchat, /api/ai_forecast/full_trade_forecast).
	4.	Add routes/premium.py:
	•	GET /api/premium/plans reads env or plans collection and returns plan objects.
	5.	Add routes/payment.py:
	•	POST /api/payment/create-order that creates a transactions doc and calls Cashfree (if enabled).
	•	POST /api/payment/webhook (public) to verify signature and apply subscription.
	6.	Add services/payment_cashfree.py:
	•	Abstraction to create cashfree order; implement signature verification helpers.
	7.	Add migration/startup code to seed plans collection from .env (idempotent).
	8.	Unit tests for above services.

Phase B — Frontend
	1.	Create src/pages/Premium.tsx: Fetch /api/premium/plans and render plan UI, buy flows.
	2.	Add paymentService.ts for createOrder + helper methods.
	3.	Update SubscriptionContext.tsx to fetch GET /api/user/usage and refresh after checkout.
	4.	Update feature pages to show remaining counts and 403 handling.

Phase C — Admin & Misc
	1.	Admin endpoints for manual crediting in routes/admin.py.
	2.	Add logs and metrics hooks for usage_logs / transactions.
	3.	Add e2e tests for purchase + feature limits.

Phase D — Testing & Deployment
	1.	Add integration tests to CI.
	2.	Deploy to staging and run full QA with Cashfree sandbox.
	3.	Deploy to production and run manual checks.

⸻

21. Edge cases & policy decisions (please confirm)
	•	Reset behavior: Reset counters at server midnight in server timezone. Confirm if you want sliding window instead.
	•	Immediate upgrade: Should upgrade happen instantly upon user redirect success or only after webhook verified? (Recommended: only after webhook).
	•	Downgrade timing: Apply immediately or at period end? (Recommended: at period end unless admin forces immediate).
	•	Shared accounts: If users share credentials, do you want to enforce single-device or single-IP concurrency? (Default: no).
	•	Refund policy: Decide on partial refunds, refunds on demand, and automated reversal of limits.
	•	Anonymous tracking: Using cookies + IP fingerprinting for anonymous users can be used to be stricter.

⸻

22. Appendix

22.1 Sample .env (trimmed)

MONGODB_URI=mongodb://...
DB_NAME=welthwest
REDIS_HOST=localhost
REDIS_PORT=6379
JWT_SECRET_KEY=changeme
IS_PAYMENT_GATEWAY_ENABLED=true
CASHFREE_ENV=sandbox
CASHFREE_APP_ID_SANDBOX=APP123
CASHFREE_SECRET_KEY_SANDBOX=SECRET123
CASHFREE_WEBHOOK_SECRET=WEBHOOKSECRET

# prices & limits (same as earlier block)
...

22.2 Sample Redis Lua atomic script

-- KEYS[1] = counter_key
-- ARGV[1] = limit (integer)
-- ARGV[2] = ttl_seconds (expire for key if newly created)
local current = redis.call("GET", KEYS[1])
if not current then
  redis.call("SET", KEYS[1], 1, "EX", ARGV[2])
  return {1, tonumber(ARGV[1]) - 1} -- allowed, remaining
else
  current = tonumber(current)
  if current >= tonumber(ARGV[1]) then
    return {0, 0} -- denied
  else
    local val = redis.call("INCR", KEYS[1])
    return {1, tonumber(ARGV[1]) - val}
  end
end

22.3 Sample Flask check_and_increment usage

def check_and_increment(actor_id, feature_key, limit, ttl_seconds=86400):
    key = f"user:{actor_id}:usage:{feature_key}:{date_str}"
    allowed, remaining = redis_eval_lua(KEYS=[key], ARGV=[limit, ttl_seconds])
    # log to usage_logs collection asynchronously
    mongo.usage_logs.insert_one({...})
    return allowed == 1, remaining

22.4 Example API response for limit reached

{
  "error": "usage_limit_reached",
  "message": "Daily limit reached for Welth Market Regime. Upgrade to continue.",
  "premium_url": "/premium",
  "current_plan": "FREE",
  "suggested_plan": "STARTER"
}


⸻


⸻
