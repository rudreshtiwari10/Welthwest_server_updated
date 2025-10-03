# Anonymous Trial Implementation - Testing Checklist

## 🧪 Testing the 10 Free Runs Per Feature

### Prerequisites
1. ✅ Backend server running: `python3 run.py`
2. ✅ Frontend server running: `npm start`
3. ✅ Redis server running: `redis-server` or check it's running
4. ✅ `.env` file has: `ANON_TRIAL_LIMIT=10`, `ENABLE_ANON_TRIALS=True`

---

## Test 1: Basic Access Without Login

### Steps:
1. Open browser in **incognito/private mode**
2. Go to `http://localhost:3000`
3. Click on any feature link:
   - `/welth-ai-assistant` (AI Chat)
   - `/backtest-beta` (Backtesting)
   - `/ai-market-analysis` (AI Market Analysis)

### Expected Results:
- ✅ Page loads WITHOUT redirect to login
- ✅ You can see the feature interface
- ✅ Usage indicator appears in top-right corner showing "10 runs left"

### ❌ If it fails:
- Check browser console for errors
- Check backend terminal for errors
- Verify `ENABLE_ANON_TRIALS=True` in `.env`
- Check CORS settings in backend

---

## Test 2: Usage Counter Decrements

### Steps:
1. Stay on a feature page (e.g., `/welth-ai-assistant`)
2. Use the feature (send a chat message, run a backtest, etc.)
3. Wait for response
4. Check the usage indicator

### Expected Results:
- ✅ Usage indicator updates to "9 runs left"
- ✅ Progress bar decreases
- ✅ Color changes as runs decrease (blue → yellow at 5 → red at 2)

### ❌ If it fails:
- Check browser console for network errors
- Check if API response includes `usage` object
- Check backend logs for Redis errors
- Verify cookies are being set (check browser dev tools > Application > Cookies)

---

## Test 3: Trial Limit Enforcement

### Steps:
1. Continue using the same feature 10 times total
2. On the 11th attempt, try to use the feature again

### Expected Results:
- ✅ Usage indicator shows "0 runs left"
- ✅ Modal appears saying "Free Trial Limit Reached"
- ✅ Modal has "Sign In" and "Create Free Account" buttons
- ✅ Feature returns error: "Your 10 free runs for [feature] are used. Please log in to continue."

### ❌ If it fails:
- Check if backend returns 403 status with `error: "trial_exceeded"`
- Check if modal component is imported in the page
- Check backend logs to see if Redis counter reached 10

---

## Test 4: Per-Feature Limits (Independent Counters)

### Steps:
1. Use **AI Chat** 10 times (exhaust limit)
2. Navigate to **Backtesting** page
3. Try to run a backtest

### Expected Results:
- ✅ Backtesting still works (has its own 10 runs)
- ✅ Usage indicator shows "10 runs left" for backtesting
- ✅ AI Chat still shows "0 runs left"

### ❌ If it fails:
- Check Redis keys: `redis-cli` then `KEYS anon:*`
- Should see separate keys like `anon:abc123:usage:welth-ai-assistant` and `anon:abc123:usage:backtest-beta`

---

## Test 5: Cookie Persistence Across Page Refreshes

### Steps:
1. Use a feature 3 times (7 runs remaining)
2. Refresh the page (F5)
3. Check usage indicator

### Expected Results:
- ✅ Usage indicator still shows "7 runs left"
- ✅ Cookie persists across page reload
- ✅ You can continue using the feature

### ❌ If it fails:
- Check browser cookies: Dev Tools > Application > Cookies > `ww_session_id`
- Check if cookie has `SameSite=Lax` and proper expiration
- Check backend CORS: `supports_credentials: True`

---

## Test 6: New Session After Clearing Cookies

### Steps:
1. Exhaust all 10 runs for a feature
2. Open browser dev tools > Application > Cookies
3. Delete `ww_session_id` cookie
4. Refresh page
5. Try to use the feature again

### Expected Results:
- ✅ New session created
- ✅ Usage indicator shows "10 runs left" again
- ✅ You can use the feature again

**Note:** This is expected behavior (trade-off for privacy). Document this for stakeholders.

---

## Test 7: Authenticated Users Bypass Limits

### Steps:
1. In a NEW incognito window (or after clearing cookies)
2. Go to feature page
3. Use it 5 times
4. Log in to your account
5. Try to use the feature again

### Expected Results:
- ✅ Usage indicator disappears after login
- ✅ Feature works unlimited times (subject to subscription limits)
- ✅ No trial limit applied to authenticated users

### ❌ If it fails:
- Check if JWT token is being sent in requests
- Check backend decorator: should detect JWT and skip anonymous logic
- Check backend logs: should say "Authenticated user [email] accessing [feature]"

---

## Test 8: Dashboard and Profile Still Protected

### Steps:
1. In incognito mode (not logged in)
2. Try to access `/dashboard`
3. Try to access `/profile`

### Expected Results:
- ✅ Both redirect to `/login`
- ✅ These pages remain protected

### ❌ If it fails:
- Check `App.tsx` - these routes should still have `<PrivateRoute>` wrapper

---

## Test 9: Cross-Browser Testing

### Test in:
- ✅ Chrome/Edge (Chromium)
- ✅ Firefox
- ✅ Safari (if on Mac)

### Expected Results:
- ✅ Cookies work in all browsers
- ✅ Usage counter works consistently
- ✅ Modal appears correctly

---

## Test 10: Mobile Web Testing

### Steps:
1. Open Chrome Dev Tools > Toggle device toolbar
2. Select a mobile device (e.g., iPhone 12)
3. Test features as above

### Expected Results:
- ✅ Usage indicator is visible and responsive
- ✅ Modal displays correctly on mobile
- ✅ Features work on mobile browsers

---

## 🐛 Common Issues and Fixes

### Issue: "Service temporarily unavailable" error

**Cause:** Redis is not running

**Fix:**
```bash
# Start Redis
redis-server

# Or on Mac with Homebrew
brew services start redis
```

---

### Issue: Usage counter not updating

**Cause:** Cookies not being sent

**Fix:**
1. Check `api.ts`: Ensure `withCredentials: true`
2. Check backend CORS: Ensure `supports_credentials: True`
3. Check frontend and backend are on same domain or proper CORS setup

---

### Issue: Compilation errors in TypeScript

**Cause:** Old function signatures

**Fix:** Already fixed in latest code. Update git and recompile.

---

### Issue: Backend returns 401 Unauthorized

**Cause:** JWT middleware blocking anonymous users

**Fix:** Already fixed - decorator uses `verify_jwt_in_request(optional=True)`

---

## 📊 Redis Inspection Commands

To check what's in Redis:

```bash
# Connect to Redis
redis-cli

# List all anonymous session keys
KEYS anon:*

# Check usage for a specific session
GET anon:abc123def456:usage:welth-ai-assistant

# Check TTL (time to live)
TTL anon:abc123def456:usage:welth-ai-assistant

# Delete all anonymous data (CAREFUL!)
FLUSHDB
```

---

## ✅ Success Criteria

All tests should pass with these results:

1. ✅ Anonymous users can access all feature pages except dashboard/profile
2. ✅ Each feature has independent 10-run limit
3. ✅ Usage indicator shows and updates correctly
4. ✅ Trial exceeded modal appears at limit
5. ✅ Cookies persist across page refreshes
6. ✅ Authenticated users bypass anonymous limits
7. ✅ Works across browsers and mobile

---

## 📝 Notes for Stakeholders

### Privacy vs. Strictness Trade-off

**Current Implementation:**
- Users can clear cookies and get 10 more runs
- This is a **privacy-friendly** approach

**Alternatives (if stricter enforcement needed):**
1. IP-based rate limiting (can be bypassed with VPN)
2. Browser fingerprinting (less privacy-friendly)
3. Require email for trial (adds friction)

**Recommendation:** Keep current approach unless abuse is detected in metrics.

---

## 🎉 Ready for Production?

Once all tests pass:

1. ✅ Update `ANON_TRIAL_LIMIT` in production `.env` if needed
2. ✅ Set `FRONTEND_URL` to production URL
3. ✅ Ensure Redis is configured in production (AWS ElastiCache, etc.)
4. ✅ Monitor metrics after launch
5. ✅ Have rollback plan ready (`ENABLE_ANON_TRIALS=False`)

---

**Last Updated:** 2025-09-30
**Status:** Ready for Testing