# WealthWest — Next-Gen Chatbot Integration Plan

## 🎯 Objective
Create a **new advanced chatbot** for WealthWest that:
- Handles **finance, trading, stock market, and general queries**.  
- Uses **multiple AI models** in a pipeline for accuracy + fallback.  
- Works in **parallel** with the old chatbot (`/welthai`).  
- Prioritizes **free or low-cost AI providers**.  

---

## 🔹 Multi-Model AI Orchestration

The chatbot should behave like a **decision-making system**, not just a single model.  
Below is the **AI Decision Tree**.

---

## 🔹 AI Decision Tree

### Step 1: Classify User Query
- **If query is about stock prices, tickers, or financial metrics** → → **Go to Path A**.  
- **If query is about financial news, headlines, or opinions** → → **Go to Path B**.  
- **If query is a general finance, trading, or stock-market explanation** → → **Go to Path C**.  
- **If query is outside finance (general knowledge)** → → **Go to Path D**.  

---

### Path A: Stock Price Queries
1. Use **yfinance** to fetch real-time price data.  
2. If available, also fetch last 5-day trend.  
3. Pass result into **OpenRouter LLM** (Mistral/LLaMA) to format answer in human-friendly language.  
4. Respond with:  
   - Current price.  
   - Short-term trend.  
   - Optional context (e.g., "Volatility is high").  

---

### Path B: Financial News / Sentiment
1. Fetch recent headlines via **NewsAPI** (if API key provided).  
   - If no key, fallback: Skip headline fetch.  
2. Run each headline through **FinBERT (Hugging Face)** for sentiment (Positive / Negative / Neutral).  
3. Pass combined sentiment + headlines into **OpenRouter LLM**.  
4. Respond with:  
   - Sentiment summary (e.g., "75% positive, 25% neutral").  
   - Example headline + explanation.  
   - Caution note if sentiment is mixed.  

---

### Path C: Finance & Trading Explanations
1. Pass query directly to **OpenRouter LLM** (Mistral preferred).  
2. If OpenRouter quota exhausted → fallback to **Gemini**.  
3. Respond with detailed yet user-friendly explanation.  
   - Example: “Explain options trading in simple terms.”  

---

### Path D: General Knowledge (Non-Finance)
1. Pass query directly to **Gemini** (since general queries don’t need finance specialization).  
2. Respond conversationally.  

---

### Failure Handling (Any Path)
- If API call fails (timeout / quota exceeded):  
  - Retry once.  
  - If still failing → fallback to next available model (Gemini > Hugging Face > Local Ollama if available).  
- If **all fail** → respond with:  
  > "⚠️ Sorry, I'm unable to fetch that right now. Please try again later."  

---

## 🔹 Conflict-Free Integration

- Old chatbot → `/welthai` (React: `WelthAIPage.tsx`, Flask: `/api/chat`).  
- New chatbot → `/nextgenchat` (React: `NextGenChatPage.tsx`, Flask: `/api/nextgenchat`).  
- New MongoDB collection → `nextgen_chat_sessions`.  
- Session & usage tracking → reuse existing `session_service`.  

---
# WealthWest — Next-Gen Chatbot Integration Plan

## 🎯 Objective
Create a **new advanced chatbot** for WealthWest that:
- Handles **finance, trading, stock market, and general queries** (not limited to DB).  
- Uses **multiple AI models** for more reliable and accurate responses.  
- Runs in **parallel** with the old chatbot (no conflict).  
- Is free or very low cost to run (priority on free-tier APIs and open-source models).  

---

## 🔹 Key Principles
1. **Multi-Model AI Orchestration**
   - Do not rely on a single model → instead, integrate a **pipeline of models**:
     - **General Reasoning (Main)**: Mistral-7B / LLaMA-2 (via OpenRouter free tier).  
     - **Finance-Specific Reasoning**: FinBERT (via Hugging Face free inference API).  
     - **Fallback**: Gemini free API (already available in Rudresh’s environment).  
     - **Optional**: Local model via Ollama (backup if internet/API not available).  

   - **Flow example**:  
     - If user asks “What’s Tesla’s stock price?” → call `yfinance`.  
     - If user asks “What does this news mean for Apple?” → pass through FinBERT sentiment + LLM summarization.  
     - If one API fails (quota exceeded) → automatically fallback to another model.  

2. **Conflict-Free Integration**
   - Old chatbot → `/welthai` (component: `WelthAIPage.tsx`, backend: `/api/chat`).  
   - New chatbot → `/nextgenchat` (component: `NextGenChatPage.tsx`, backend: `/api/nextgenchat`).  
   - Different naming → no overlap.  

3. **User Handling**
   - Logged-in users → unlimited or higher quota.  
   - Anonymous users → usage counter (limit defined in `session_service`).  
   - Chat history stored in MongoDB **separately** for the new bot.  

---

## 🔹 Architecture Overview

### Frontend (React + Tailwind)
- **New Component**: `NextGenChatPage.tsx`.  
- Mounted at route `/nextgenchat`.  
- Features:
  - Chat bubbles (user + AI).  
  - Input box.  
  - Usage counter.  
  - Typing animation.  
  - Calls `/api/nextgenchat`.  

### Backend (Flask + MongoDB)
- **New Endpoint**: `/api/nextgenchat`.  
- Flow:
  1. Receive request from frontend with `conversation` and `session_id`.  
  2. Validate session (reuse `session_service`).  
  3. Pass query into **AI Orchestration Layer**.  
  4. Orchestration decides:  
     - If query = stock price → use `yfinance`.  
     - If query = news/sentiment → call Hugging Face FinBERT.  
     - Else → use OpenRouter (Mistral).  
     - If fail → fallback to Gemini.  
  5. Save response in MongoDB (new collection, e.g., `nextgen_chat_sessions`).  
  6. Return response to frontend.  

---

## 🔹 AI Orchestration Layer

### Models to Integrate
1. **OpenRouter (Free Tier)**
   - URL: `https://openrouter.ai/api/v1/chat/completions`  
   - Models: `mistral-7b-instruct`, `llama-2-13b-chat`.  
   - Use for **general Q&A + reasoning**.  

2. **Hugging Face Inference API**
   - Example: `ProsusAI/finbert`.  
   - Use for **finance-specific sentiment analysis**.  
   - Query: “Is this headline positive, negative, or neutral?”  

3. **yfinance (Python library)**
   - Free stock market data.  
   - Use for “current price of TSLA”, “Nifty50 trend”.  

4. **Gemini API (Backup)**
   - Already available in Rudresh’s environment.  
   - Use as **fallback** if OpenRouter quota is exceeded.  

---

## 🔹 Example Query Handling

- **User asks**: “What’s Tesla’s stock price right now, and should I buy it?”  
  - Step 1: Use `yfinance` to fetch TSLA price.  
  - Step 2: Fetch recent Tesla headlines via NewsAPI.  
  - Step 3: Pass headlines → FinBERT for sentiment.  
  - Step 4: Compose final answer with Mistral (OpenRouter).  

---



## 🔹 Deliverables (After Implementation)
- New chatbot UI at `/nextgenchat`.  
- Backend route `/api/nextgenchat`.  
- Multi-model orchestration layer.  
- Parallel coexistence with old chatbot.  
- Configurable via `.env` for API keys.  

---

## 🔹 Claude Instructions (For Context)
When implementing:
- Never touch or rename old chatbot files (`WelthAIPage.tsx`, `/api/chat`).  
- Always create **new files** (`NextGenChatPage.tsx`, `ai_service.py`).  
- Use **separate MongoDB collection** (`nextgen_chat_sessions`).  
- Handle **session limits** via existing `session_service`.  
- Use **multi-model strategy**:  
  1. Check if finance-specific → FinBERT.  
  2. Check if stock price → yfinance.  
  3. Else → OpenRouter (Mistral).  
  4. If fail → Gemini fallback.  

---