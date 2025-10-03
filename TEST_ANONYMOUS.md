# Testing Guide for Anonymous Features

## Quick Test Steps

### 1. Restart Server
```bash
cd /Users/rudreshtiwari/welthwest2/WelthWestServer_sharing_
python app.py
```

### 2. Test in Browser (Incognito Mode)

#### Test AI Market Analysis:
1. Open browser in incognito mode
2. Go to: http://localhost:3000/ai-market-analysis
3. Enter ticker: **RELIANCE** (use Indian stock, not AAPL)
4. Click "Run Analysis"
5. **Expected:** Should work and show usage counter

#### Test Backtest:
1. Stay in same incognito session
2. Go to: http://localhost:3000/backtest-beta
3. Enter:
   - Stock: **RELIANCE**
   - Select some indicators
   - Period: 1y
4. Click "Run Backtest"
5. **Expected:** Should work and show results

### 3. Check Usage Limit

The limit is set to **10** in the backend (.env file).

If you're seeing "2" on the frontend, it means the frontend has a hardcoded value.

Check these files in the **frontend**:
- Any component showing usage limit
- Any hardcoded "2/10" or limit={2}

### 4. Important Notes

- Use **Indian stock tickers** (RELIANCE, TCS, INFY) not US stocks (AAPL)
- The backend appends .NS for NSE stocks automatically
- US stocks may timeout because Yahoo Finance data fetching is slow

## What Was Fixed

1. ✅ DataFrame serialization (was causing 500 error)
2. ✅ Method names (get_regime_analysis, get_regime_recommendations)
3. ✅ Response handling in middleware
4. ✅ Package imports (__init__.py files)
5. ✅ g.current_user handling
6. ✅ create_comprehensive_charts method

## Current Status

**Backend is working correctly.**

Limit is set to **10** in .env file.

If frontend shows "2/10", that's a **frontend issue** - check the React components.

