# WelthWest Server Optimization - Complete API Call & Feature Mapping

## Current Active Features (Frontend)
1. `/ai-screener` - AI Stock Screener
2. `/welth-ai-assistant` - WelthWest Bot Button (Chat)
3. Strategy Button (Navbar) - Market Regime / HMM
4. Top Gainer/Loser
5. Backtesting
6. News & Blogs
7. Profile Page
8. Index Data on Home Page (NIFTY, SENSEX, BANK NIFTY)

---

## SECTION 1: STARTUP API CALLS (Run when server starts)

These execute automatically when you run `python server.py` or `python app.py`:

| # | What Runs | File:Line | External API Called | Time Impact | Feature | Verdict |
|---|-----------|-----------|---------------------|-------------|---------|---------|
| S1 | `warm_market_indices_cache()` | `app.py:322` -> `stock_service.py:768` | Yahoo Finance (yf.download for ^NSEI, ^BSESN, ^NSEBANK, ^CNXIT, ^CNXPHARMA, ^CNXFMCG, ^CNXAUTO, ^CNXMETAL) | **5-15s** (downloads 8+ index tickers) | Home Page Index Data | **KEEP** - needed for home page |
| S2 | `_maybe_start_keep_alive_scheduler()` | `app.py:391-400` -> `scheduler_service.py:41-59` | Self-ping to `/market-indices` every 10 min | **Ongoing background** | Keeps Render server alive | **KEEP** on Render, **REMOVE** locally |
| S3 | `initialize_premium_system()` | `app.py:289` -> `database/seed_plans.py:126` | MongoDB (seed plans + create indexes) | **1-3s** | Subscription system | **KEEP** |
| S4 | `refresh_top_gainers_losers()` (server.py only) | `server.py:37-46,49-58` | Yahoo Finance (yf.download for 50 NIFTY stocks) | **15-30s** (downloads ALL 50 stocks) | Top Gainer/Loser | **KEEP** but slow |
| S5 | `MarketRegimeService.__init__()` -> `_start_scheduler()` | `services/market_regime_service.py:25-69` | Starts scheduler: daily retrain at 18:00 + hourly updates | **Background threads** | Strategy Button | **KEEP** |
| S6 | `HMMService.__init__()` -> `_load_existing_model()` | `hmm_model/hmm_service.py:15-38` | Loads pickle model from disk | **1-2s** | Strategy / HMM | **KEEP** |
| S7 | `LSTMHMMForecastService.__init__()` | `lstm_model/lstm_hmm_forecast_service.py:746-757` | Initializes 7 AI engines in memory | **1-2s** | AI Forecast | **REVIEW** - is this used in frontend? |
| S8 | `email_service.init_app(app)` | `app.py:175` | None (just config) | **<0.1s** | Email sending | **KEEP** |
| S9 | `InMemorySessionService()` init | `services/session_service.py` | Starts cleanup thread | **<0.1s** | Anonymous sessions | **KEEP** |
| S10 | Redis connection attempt | `middleware/cache_manager.py:39-65` | Redis server | **0.5-2s** (timeout if no Redis) | Caching | **KEEP** |

**Total Startup Time Estimate: 25-55 seconds** (mostly from S1 + S4)

---

## SECTION 2: SCHEDULED / BACKGROUND API CALLS (Run periodically)

| # | Task | File:Line | External API | Schedule | Feature | Verdict |
|---|------|-----------|--------------|----------|---------|---------|
| B1 | Keep-alive ping | `scheduler_service.py:26-39` | Self `/market-indices` (which triggers Yahoo Finance) | Every 10 min | Server warmth | **KEEP** on prod |
| B2 | Refresh top gainers/losers | `server.py:37-58` | Yahoo Finance (50 stocks download) | Every 15 min during market hours | Top Gainer/Loser | **KEEP** |
| B3 | Market regime scheduled retrain | `market_regime_service.py:55` | Yahoo Finance (via `get_historical_data`) | Daily at 18:00 | Strategy Button | **KEEP** |
| B4 | Market regime scheduled update | `market_regime_service.py:58` | Yahoo Finance (via `get_historical_data`) | Every 1 hour | Strategy Button | **KEEP** |
| B5 | Session cleanup | `session_service.py:184` | None (memory cleanup) | Background thread | Sessions | **KEEP** |

---

## SECTION 3: ON-DEMAND API CALLS - BY FEATURE

### 3.1 Home Page - Index Data
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `GET /api/market-indices` | `app.py:2317` | Yahoo Finance via `get_market_indices()` | `stock_service.py:802` - uses cache, falls back to yf.download | **KEEP** |
| `GET /api/market-indices-new` | `app.py:4613` | Yahoo Finance via `get_market_indices_yfinance()` | `stock_service.py` | **REMOVE** - duplicate of above |
| `GET /health` | `app.py:352` | Triggers `warm_cache_on_startup()` if cache cold | `stock_service.py:768` | **KEEP** |

### 3.2 Top Gainer/Loser
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `GET /api/top-gainers-losers` | `app.py:2506` | Yahoo Finance `yf.download()` for 50 stocks | `stock_service.py:1266` | **KEEP** |

### 3.3 AI Screener (`/ai-screener`)
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `POST /api/ai-screener/screen` | `routes/ai_screener_routes.py:52` | Yahoo Finance (yfinance) for all screened stocks | `ai_screener/screener/engine.py` | **KEEP** |
| `POST /api/ai-screener/screen/quick` | `routes/ai_screener_routes.py:83` | Yahoo Finance (max 10 stocks) | Same engine | **KEEP** |
| `GET /api/ai-screener/screen/cached` | `routes/ai_screener_routes.py:110` | None (cache only) | Cache lookup | **KEEP** |
| `GET /api/ai-screener/screen/<symbol>` | `routes/ai_screener_routes.py:119` | Yahoo Finance (single stock) | Provider fetch | **KEEP** |
| `GET /api/ai-screener/regime` | `routes/ai_screener_routes.py:143` | Yahoo Finance (NIFTY index) | Regime detector | **KEEP** |
| `GET /api/ai-screener/regime/vix` | `routes/ai_screener_routes.py:166` | Yahoo Finance (India VIX) | Provider | **KEEP** |
| `GET /api/ai-screener/signals/<symbol>` | `routes/ai_screener_routes.py:197` | Yahoo Finance | Signal generation | **KEEP** |
| `GET /api/ai-screener/price/<symbol>` | `routes/ai_screener_routes.py:271` | Yahoo Finance | Price history | **KEEP** |
| `GET /api/ai-screener/health` | `routes/ai_screener_routes.py:30` | None | Health check | **KEEP** |

### 3.4 WelthWest AI Assistant (Bot/Chat)
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `POST /api/chat` | `app.py:1357` | OpenAI / OpenRouter / Claude API (based on model param) | `app.py:1949-2093` (inline class) | **KEEP** |
| `POST /api/nextgenchat` | `app.py:1470` | Gemini API + OpenRouter + yfinance + NewsAPI | `nextgen_ai_service.py:543` | **KEEP** - this is the main chat |
| `POST /api/market/chat` | `app.py:2580` | OpenAI / OpenRouter / Claude | `ai_service.py:325` | **REVIEW** - is this used or duplicate of /api/chat? |

**External APIs used by chat:**
| API | URL | File:Line | Purpose |
|-----|-----|-----------|---------|
| OpenAI | `https://api.openai.com/v1/chat/completions` | `app.py:1973`, `ai_service.py:170` | GPT-3.5 responses |
| OpenRouter | `https://openrouter.ai/api/v1/chat/completions` | `app.py:2017`, `ai_service.py:224`, `nextgen_ai_service.py:484` | Llama/Claude responses |
| Anthropic Claude | `https://api.anthropic.com/v1/messages` | `app.py:2064`, `ai_service.py:279` | Claude responses |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent` | `nextgen_ai_service.py:516` | Primary for nextgenchat |
| Google Gemini (v1) | `https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent` | `finance_orchestrator.py:651` | Finance AI queries |
| NewsAPI | `https://newsapi.org/v2/everything` | `nextgen_ai_service.py:407` | News for chat context |
| Yahoo Finance | yfinance library | `nextgen_ai_service.py:337-392` | Stock data for chat |
| HuggingFace FinBERT | `ProsusAI/finbert` model | `nextgen_ai_service.py:107-117` | Sentiment analysis |

### 3.5 Strategy Button (Market Regime)
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `POST /api/market-regime/train` | `app.py:3813` | Yahoo Finance (via `get_historical_data`) | `market_regime_service.py` | **KEEP** (admin) |
| `GET/POST /api/market-regime/predict` | `app.py:3841` | Yahoo Finance (via service) | `market_regime_service.py` | **KEEP** |
| `GET /api/market-regime/analysis` | `app.py:3891` | Yahoo Finance | `market_regime_service.py` | **KEEP** |
| `GET /api/market-regime/recommendations` | `app.py:3929` | None (uses cached prediction) | `market_regime_service.py` | **KEEP** |
| `POST /api/market-regime/multiple` | `app.py:3950` | Yahoo Finance (multiple stocks) | `market_regime_service.py` | **KEEP** |
| `GET /api/market-regime/model-info` | `app.py:3974` | None | Model metadata | **KEEP** |
| `GET /api/market-regime/evaluate` | `app.py:3986` | Yahoo Finance | Model evaluation | **KEEP** (admin) |
| `GET /api/market-regime/definitions` | `app.py:4010` | None | Static definitions | **KEEP** |
| `POST /api/hmm_model/train` | `app.py:4026` | Yahoo Finance | `hmm_model/hmm_service.py` | **KEEP** (admin) |
| `GET/POST /api/hmm_model/predict` | `app.py:4057` | Yahoo Finance | `hmm_model/hmm_service.py` | **KEEP** |
| `GET /api/hmm_model/analysis` | `app.py:4082` | Yahoo Finance | `hmm_model/hmm_service.py` | **KEEP** |
| `POST /api/hmm_model/multiple` | `app.py:4103` | Yahoo Finance | `hmm_model/hmm_service.py` | **KEEP** |
| `GET /api/hmm_model/model-info` | `app.py:4127` | None | Model metadata | **KEEP** |
| `GET /api/hmm_model/evaluate` | `app.py:4139` | Yahoo Finance | `hmm_model/hmm_service.py` | **KEEP** (admin) |

### 3.6 Backtesting
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `POST /api/backtest/run` | `app.py:1571` | Yahoo Finance (via `get_historical_data`) | `backtesting_service.py` | **KEEP** |
| `POST /api/backtesting/generate-signals` | `app.py:3001` | Yahoo Finance | `backtesting_service.py` | **KEEP** |
| `POST /api/backtesting/newrun` | `app.py:3205` | Yahoo Finance | `backtesting_service.py` | **KEEP** |

### 3.7 News & Blogs
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `GET /api/news` | `app.py:4626` | NewsAPI + RSS Feeds + Alpha Vantage | `news_aggregator.py` | **KEEP** |
| `GET /api/news/search` | `app.py:4651` | Same aggregator | `news_aggregator.py` | **KEEP** |
| `GET /api/blogs` | `app.py:4682` | MongoDB only (no external) | `news_service.py` | **KEEP** |
| `GET /api/news/<id>` | `app.py:4717` | MongoDB | `news_service.py` | **KEEP** |
| `GET /api/blogs/<id>` | `app.py:4735` | MongoDB | `news_service.py` | **KEEP** |
| `GET /api/featured-posts` | `app.py:4753` | MongoDB | `news_service.py` | **KEEP** |
| `GET /api/search-posts` | `app.py:4772` | MongoDB | `news_service.py` | **KEEP** |
| `POST /api/news` | `app.py:4806` | None (admin create) | `news_service.py` | **KEEP** (admin) |
| `POST /api/blogs` | `app.py:4858` | None (admin create) | `news_service.py` | **KEEP** (admin) |

**News Aggregator External Sources:**
| Source | URL | File:Line | Type |
|--------|-----|-----------|------|
| NewsAPI | `https://newsapi.org/v2/top-headlines` | `news_aggregator.py:97` | REST API |
| MoneyControl RSS | `https://www.moneycontrol.com/rss/marketreports.xml` | `news_aggregator.py:52` | RSS Feed |
| Economic Times RSS | `https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms` | `news_aggregator.py:53` | RSS Feed |
| NSE RSS | `https://www.nseindia.com/rss/news.xml` | `news_aggregator.py:60` | RSS Feed |
| Economy RSS | `https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms` | `news_aggregator.py:63` | RSS Feed |
| Banking RSS | `https://economictimes.indiatimes.com/industry/banking/finance/rssfeeds/13358259.cms` | `news_aggregator.py:66` | RSS Feed |
| Bloomberg RSS | `https://feeds.bloomberg.com/markets/news.rss` | `news_aggregator.py:56` | RSS Feed |
| CNBC RSS | `https://www.cnbc.com/id/100003114/device/rss/rss.html` | `news_aggregator.py:57` | RSS Feed |
| Alpha Vantage | `https://www.alphavantage.co/query?function=NEWS_SENTIMENT` | `news_aggregator.py:165` | REST API |

### 3.8 Profile Page
| Endpoint | File:Line | External API | Service Function | Verdict |
|----------|-----------|--------------|------------------|---------|
| `GET /api/auth/me` | `app.py:795` | MongoDB | `user_service.py` | **KEEP** |
| `PUT /api/auth/profile` | `app.py:807` | MongoDB | `user_service.py` | **KEEP** |
| `GET /api/user/subscription` | `app.py:3319` | MongoDB | `subscription_service.py` | **KEEP** |
| `GET /api/user/usage` | `app.py:3451` | MongoDB/Redis | `premium_usage_service.py` | **KEEP** |
| `GET /api/user/billing-details` | `app.py:3584` | MongoDB | `user_service.py` | **KEEP** |
| `POST /api/user/billing-details` | `app.py:3610` | MongoDB | `user_service.py` | **KEEP** |

---

## SECTION 4: POTENTIALLY UNNECESSARY ENDPOINTS (NOT in current features)

These endpoints exist but may NOT be used by the current frontend:

### 4.1 LIKELY UNUSED - Can be removed/disabled

| Endpoint | File:Line | What it does | Why likely unused |
|----------|-----------|--------------|-------------------|
| `GET /api/market-indices-new` | `app.py:4613` | Duplicate market indices endpoint | Duplicate of `/api/market-indices` |
| `POST /startup` | `app.py:328` | Manual cache warming trigger | Not called by frontend |
| `GET /api/blogs/debug/count` | `app.py:4910` | Debug endpoint - blog count | Development only |
| `GET /api/blogs/debug/test` | `app.py:4940` | Debug endpoint - test blogs | Development only |
| `POST /api/email/send` | `app.py:3661` | Generic email sending | Admin only, likely unused |
| `POST /api/email/send-welcome` | `app.py:3712` | Manual welcome email | Admin only, called internally |
| `POST /api/email/send-subscription-upgrade` | `app.py:3761` | Manual upgrade email | Admin only |

### 4.2 FEATURES TO REVIEW (May not be in current frontend)

| Endpoint Group | File | # Endpoints | External APIs | Review Reason |
|----------------|------|-------------|---------------|---------------|
| **LSTM Model** (`/api/lstm_model/*`) | `app.py:4168-4266` | 4 | Yahoo Finance | Is LSTM prediction shown anywhere in frontend? |
| **AI Forecast** (`/api/ai_forecast/*`) | `app.py:4267-4327` | 2 | Yahoo Finance + all AI engines | Is full trade forecast in frontend? |
| **Finance AI** (`/api/finance-ai/*`) | `routes/finance_ai_routes.py` | 8 | yfinance + Gemini + RAG | Is this separate from the main chat? |
| **MTF Screener** (`/api/mtf-screener/*`) | `routes/mtf_screener_routes.py` | 20 | yfinance + NSE API | Is this separate from `/ai-screener`? |
| **Risk Calculator** (`/api/risk-calculator/*`) | `routes/risk_calculator_routes.py` + phases 2-9 | ~50+ | None (computation only) | Are risk calculator phases 2-9 used? |
| **Pattern Analysis** (`/api/pattern-analysis/*`) | `routes/pattern_analysis_routes.py` | 3 | None | Is pattern analysis in frontend? |
| **Trade Simulator** (`/api/trade-simulator/*`) | `routes/trade_simulator_routes.py` | 7 | None | Is paper trading in frontend? |
| **Risk Calc Extended** (`/api/risk-calculator/calculate-position`, `ai-suggestions`) | `routes/risk_calculator_extended_routes.py` | 3 | None | Is extended risk calc used? |
| **LSTM API** (`/api/lstm/*`) | `routes/lstm_api_routes.py` | 4 | Yahoo Finance | Separate from `/api/lstm_model/*`? |
| **Upstox Integration** (`/api/upstox/*`) | `app.py:1751-1818` | 5 | Upstox API | Is Upstox broker integration active? |
| **Correlation** (`/api/correlation`) | `app.py:2937` | 1 | Yahoo Finance | Is this in frontend? |
| **Market Breadth** (`/api/market-breadth`) | `app.py:2957` | 1 | Yahoo Finance (many stocks) | Is this in frontend? |
| **Screener** (`/api/screener`) | `app.py:2694` | 1 | Yahoo Finance | Different from `/ai-screener`? |
| **Intraday** (`/api/intraday`) | `app.py:2721` | 1 | Yahoo Finance | Is intraday chart in frontend? |
| **Signals** (`/api/signals`) | `app.py:2757` | 1 | Yahoo Finance | Is signals page in frontend? |
| **Technical Analysis** (`/api/technical-analysis`) | `app.py:2771` | 1 | Yahoo Finance | Is TA page in frontend? |
| **Levels** (`/api/levels`) | `app.py:2821` | 1 | Yahoo Finance | Support/resistance in frontend? |
| **Patterns** (`/api/patterns`) | `app.py:2835` | 1 | Yahoo Finance | Pattern page in frontend? |
| **Portfolio** (`/api/portfolio/*`) | `app.py:2850-2869` | 2 | Yahoo Finance | Portfolio tracker in frontend? |
| **Stock Fundamentals** (`/api/stock/fundamentals`) | `app.py:2519` | 1 | Yahoo Finance | Fundamentals page in frontend? |
| **Indicators** (`/api/indicators`) | `app.py:2666` | 1 | Yahoo Finance | Indicators page in frontend? |
| **Compare** (`/api/compare`) | `app.py:2247` | 1 | Yahoo Finance | Stock comparison in frontend? |
| **Statistics** (`/api/statistics`) | `app.py:2294` | 1 | Yahoo Finance | Stats page in frontend? |

### 4.3 ADMIN-ONLY ENDPOINTS (Keep but not performance concern)

| Endpoint Group | File | # Endpoints | Notes |
|----------------|------|-------------|-------|
| Admin Dashboard | `routes/admin.py` | 17 | MongoDB only, no external APIs |
| Admin Content | `routes/admin_content.py` | 22 | MongoDB only |
| Admin Monitoring | `routes/admin_monitoring.py` | 12 | MongoDB only |
| Admin Support | `routes/admin_support.py` | 11 | MongoDB only |
| Admin Credit/Reset | `app.py:5076-5191` | 2 | MongoDB only |
| News Blog Routes (admin) | `routes/news_blog_routes.py` | 12 | MongoDB only (commented out in app.py) |

---

## SECTION 5: ALL EXTERNAL API DEPENDENCIES (Master List)

| # | API Provider | URL/Library | Used By | Feature | Required? |
|---|-------------|-------------|---------|---------|-----------|
| 1 | **Yahoo Finance** | `yfinance` library | stock_service, ai_screener, backtesting, market_regime, hmm, lstm, nextgen_chat | ALL market data | **YES** - core |
| 2 | **Google Gemini** | `generativelanguage.googleapis.com` | nextgen_ai_service, finance_orchestrator | AI Chat (primary) | **YES** - for chat |
| 3 | **OpenRouter** | `openrouter.ai/api/v1` | ai_service, nextgen_ai_service | AI Chat (fallback) | **YES** - for chat |
| 4 | **OpenAI** | `api.openai.com/v1` | ai_service, app.py inline | AI Chat (option) | **OPTIONAL** |
| 5 | **Anthropic Claude** | `api.anthropic.com/v1` | ai_service, app.py inline | AI Chat (option) | **OPTIONAL** |
| 6 | **NewsAPI** | `newsapi.org/v2` | news_aggregator, nextgen_ai_service | News page + chat context | **YES** - for news |
| 7 | **Alpha Vantage** | `alphavantage.co/query` | news_aggregator | News sentiment | **OPTIONAL** |
| 8 | **NSE India** | `nseindia.com/api` | nifty_fetcher, nse_provider | NIFTY 50 list, FII/DII | **YES** - for screener |
| 9 | **RSS Feeds** (7 sources) | MoneyControl, ET, NSE, Bloomberg, CNBC | news_aggregator | News page | **YES** - for news |
| 10 | **Cashfree** | `api.cashfree.com/pg` | payment_cashfree | Payments | **YES** - for payments |
| 11 | **Razorpay** | Razorpay SDK | razorpay_service | Payments (legacy?) | **REVIEW** - duplicate of Cashfree? |
| 12 | **Google OAuth** | Google SDK | google_auth_service | Google login | **YES** - for auth |
| 13 | **SMTP (Gmail)** | `smtp.gmail.com` | email_service | Email sending | **YES** - for auth/notifications |
| 14 | **Upstox** | `api.upstox.com/v2` | upstox_service | Broker integration | **REVIEW** - is this active? |
| 15 | **HuggingFace** | `ProsusAI/finbert` | nextgen_ai_service | Sentiment analysis | **OPTIONAL** |
| 16 | **MongoDB** | PyMongo | All services | Database | **YES** - core |
| 17 | **Redis** | redis-py | cache_service, usage tracking | Caching | **OPTIONAL** (has fallback) |
| 18 | **Wikipedia** | `en.wikipedia.org` | nifty_fetcher | NIFTY 50 fallback | **OPTIONAL** (fallback only) |

---

## SECTION 6: REGISTERED BLUEPRINTS

All blueprints registered in `app.py:243-284`:

| Blueprint | Module | Feature | Used in Frontend? | Verdict |
|-----------|--------|---------|-------------------|---------|
| `premium_bp` | `routes/premium.py` | Subscription plans | Yes (profile) | **KEEP** |
| `payment_bp` | `routes/payment.py` | Cashfree payments | Yes (payment) | **KEEP** |
| `subscription_bp` | `routes/subscription.py` | Subscription mgmt | Yes (profile) | **KEEP** |
| `admin_bp` | `routes/admin.py` | Admin dashboard | Admin only | **KEEP** |
| `support_bp` | `routes/support.py` | Support tickets | Maybe | **REVIEW** |
| `admin_content_bp` | `routes/admin_content.py` | Content mgmt | Admin only | **KEEP** |
| `admin_support_bp` | `routes/admin_support.py` | Support mgmt | Admin only | **KEEP** |
| `admin_monitoring_bp` | `routes/admin_monitoring.py` | Monitoring | Admin only | **KEEP** |
| `mtf_screener_bp` | `routes/mtf_screener_routes.py` | MTF Screener | **REVIEW** | **REVIEW** - separate from ai-screener? |
| `risk_calculator_bp` | `routes/risk_calculator_routes.py` | Risk calc phase 1 | **REVIEW** | **REVIEW** |
| `risk_phase2_bp` | `routes/risk_calculator_phase2_routes.py` | Risk calc phase 2 | **REVIEW** | **REVIEW** |
| `risk_phase3_bp` | `routes/risk_calculator_phase3_routes.py` | Risk calc phase 3 | **REVIEW** | **REVIEW** |
| `risk_phase4_bp` | `routes/risk_calculator_phase4_routes.py` | Risk calc phase 4 | **REVIEW** | **REVIEW** |
| `risk_phase5_bp` | `routes/risk_calculator_phase5_routes.py` | Risk calc phase 5 | **REVIEW** | **REVIEW** |
| `risk_phase6_bp` | `routes/risk_calculator_phase6_routes.py` | Risk calc phase 6 | **REVIEW** | **REVIEW** |
| `risk_phase7_bp` | `routes/risk_calculator_phase7_routes.py` | Risk calc phase 7 | **REVIEW** | **REVIEW** |
| `risk_phase8_bp` | `routes/risk_calculator_phase8_routes.py` | Risk calc phase 8 | **REVIEW** | **REVIEW** |
| `risk_phase9_bp` | `routes/risk_calculator_phase9_routes.py` | Risk calc phase 9 | **REVIEW** | **REVIEW** |
| `pattern_analysis_bp` | `routes/pattern_analysis_routes.py` | Pattern analysis | **REVIEW** | **REVIEW** |
| `risk_calc_ext_bp` | `routes/risk_calculator_extended_routes.py` | Extended risk | **REVIEW** | **REVIEW** |
| `trade_simulator_bp` | `routes/trade_simulator_routes.py` | Paper trading | **REVIEW** | **REVIEW** |
| `ai_screener_bp` | `routes/ai_screener_routes.py` | AI Screener | Yes | **KEEP** |
| Finance AI routes | `routes/finance_ai_routes.py` (registered via function) | Finance AI | **REVIEW** | **REVIEW** |

---

## SECTION 7: PERFORMANCE BOTTLENECKS

### Slowest Operations (by estimated time):

| Rank | Operation | Est. Time | Cause | Fix |
|------|-----------|-----------|-------|-----|
| 1 | `get_top_gainers_losers()` | 15-30s | Downloads ALL 50 NIFTY stocks via yfinance | Cache aggressively, reduce to top 20 |
| 2 | `warm_market_indices_cache()` | 5-15s | Downloads 8+ index tickers | Already cached, but slow on cold start |
| 3 | `ai_screener/screen` (full) | 10-30s | Downloads 50 stocks + computes features | Use quick screen, cache results |
| 4 | `/api/market-breadth` | 5-15s | Downloads many stocks for breadth calculation | Cache or remove if unused |
| 5 | `nextgenchat` with stock query | 3-8s | yfinance fetch + Gemini API call | Expected latency |
| 6 | yfinance calls on Render | +3-8s per call | `_sleep_before_yf_call()` adds delay to avoid rate limits | Unavoidable on cloud |
| 7 | Market regime predict | 2-5s | Fetches historical data + runs model | Cache predictions |
| 8 | Backtesting | 5-20s | Fetches historical data + runs strategy | Expected, user-triggered |

### Rate Limiting Delays:
- **Local:** 0.5-2s random delay before each yfinance call (`stock_service.py:47-48`)
- **Render/Cloud:** 3-8s random delay before each yfinance call (`stock_service.py:45-46`)
- **NSE API:** Cookie refresh every 300s (`ai_screener/data/providers/nse_provider.py:35`)

---

## SECTION 8: OPTIMIZATION RECOMMENDATIONS

### Quick Wins:
1. **Remove `/api/market-indices-new`** - duplicate endpoint (`app.py:4613`)
2. **Remove debug endpoints** - `/api/blogs/debug/count` and `/api/blogs/debug/test` (`app.py:4910,4940`)
3. **Remove `/startup` endpoint** - not needed (`app.py:328`)
4. **Disable unused blueprints** - comment out registration for unused features in `app.py:258-284`

### Medium Effort:
5. **Verify Razorpay vs Cashfree** - keep only one payment gateway
6. **Verify Upstox usage** - if not using broker integration, remove upstox_service imports
7. **Reduce top gainers download** - download top 20 instead of all 50
8. **Lazy-load LSTM/HMM services** - don't initialize at import if not used

### Architecture:
9. **Remove risk_calculator phases 2-9** if not in frontend (saves ~8 blueprint registrations)
10. **Remove trade_simulator** if not in frontend
11. **Remove pattern_analysis** if not in frontend
12. **Consolidate chat endpoints** - `/api/chat`, `/api/nextgenchat`, `/api/market/chat` - keep only what frontend uses

---

## SECTION 9: ENDPOINT COUNT SUMMARY

| Category | Count | External API Calls |
|----------|-------|--------------------|
| Auth endpoints | 13 | Google OAuth, SMTP |
| Market Data | 12 | Yahoo Finance |
| AI Chat | 3 | OpenAI, Gemini, OpenRouter, Claude, NewsAPI |
| AI Screener | 9 | Yahoo Finance, NSE |
| Market Regime + HMM | 14 | Yahoo Finance |
| LSTM + Forecast | 6 | Yahoo Finance |
| Backtesting | 3 | Yahoo Finance |
| News/Blogs | 12 | NewsAPI, RSS, Alpha Vantage |
| Subscription/Premium | 12 | MongoDB only |
| Payment | 4 | Cashfree |
| User Profile/Data | 13 | MongoDB only |
| Risk Calculator (all phases) | ~50+ | None (computation) |
| MTF Screener | 20 | Yahoo Finance, NSE |
| Finance AI | 8 | Yahoo Finance, Gemini |
| Admin | 62 | MongoDB only |
| Trade Simulator | 7 | None |
| Pattern Analysis | 3 | None |
| Technical Analysis | 6 | Yahoo Finance |
| Upstox | 5 | Upstox API |
| Health/Utility | 5 | Self-ping |
| **TOTAL** | **~270+** | |

---

*Generated on: 2026-02-11*
*Server: Welthwest_server_updated*
*Total files analyzed: 80+ Python files*
