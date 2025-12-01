# Integration Instructions

## Step-by-Step: Integrating Finance AI into your existing app.py

### Step 1: Add Import at Top of app.py

Find the imports section at the top of `app.py` and add:

```python
from routes.finance_ai_routes import register_finance_ai_routes
```

### Step 2: Register Routes

After your Flask app is created (`app = Flask(__name__)`) and BEFORE `app.run()`, add:

```python
# Register enhanced Finance AI routes
register_finance_ai_routes(app)
```

### Complete Example

Here's how your app.py structure should look:

```python
from flask import Flask, request, jsonify
from flask_cors import CORS
# ... other imports ...

# NEW: Import Finance AI routes
from routes.finance_ai_routes import register_finance_ai_routes

# Create Flask app
app = Flask(__name__)
CORS(app)

# ... existing middleware, config ...

# ... existing routes ...

# NEW: Register Finance AI routes
register_finance_ai_routes(app)

# ... rest of your code ...

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)
```

### Step 3: Install Dependencies

```bash
cd /Users/rudreshtiwari/Desktop/welthwest2/WelthWestServer_sharing_
pip install -r requirements.txt
```

### Step 4: Test Installation

```bash
# Start your server
python server.py

# In another terminal, test the new endpoint
curl -X GET http://localhost:8000/api/finance-ai/status
```

Expected response:
```json
{
  "orchestrator": "active",
  "indicators": "active",
  "screener": "active",
  "backtest": "active",
  "rag": "active" or "unavailable",
  "charts": "active"
}
```

### Step 5: Test with a Query

```bash
curl -X POST http://localhost:8000/api/finance-ai/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the price of AAPL?"}'
```

## Manual Integration (Alternative)

If you prefer to add routes manually to app.py instead of using the blueprint:

```python
from services.finance_orchestrator import process_finance_query

@app.route('/api/finance-ai/query', methods=['POST'])
def enhanced_query():
    data = request.get_json()
    query = data.get('query', '')
    result = process_finance_query(query)
    return jsonify(result), 200
```

## Frontend Integration

### Update your React frontend API calls:

```javascript
// Old endpoint
const response = await fetch('/api/nextgenchat', {...});

// New enhanced endpoint
const response = await fetch('/api/finance-ai/query', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: userMessage })
});

const data = await response.json();

// Display AI response
setAiResponse(data.ai_response);

// Display chart if available
if (data.chart_base64) {
  setChartImage(`data:image/png;base64,${data.chart_base64}`);
}

// Access structured data
if (data.data) {
  console.log('Structured data:', data.data);
}
```

## Compatibility Notes

- ✅ All existing endpoints continue to work
- ✅ New routes are additive (won't break existing code)
- ✅ `/api/chat` and `/api/nextgenchat` remain functional
- ✅ New `/api/finance-ai/*` routes provide enhanced features

## Optional: Redirect Old Endpoint

If you want to redirect old chat endpoint to new one:

```python
@app.route('/api/chat', methods=['POST'])
def legacy_chat():
    """Legacy endpoint - redirects to new Finance AI"""
    data = request.get_json()
    query = data.get('message') or data.get('query', '')

    from services.finance_orchestrator import process_finance_query
    result = process_finance_query(query)

    # Return in legacy format
    return jsonify({
        'response': result['ai_response'],
        'analysis': result.get('data', {}),
        'chart': result.get('chart_base64', None)
    }), 200
```

## Verification Checklist

- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Routes imported in app.py
- [ ] Routes registered with `register_finance_ai_routes(app)`
- [ ] Server starts without errors
- [ ] `/api/finance-ai/status` returns 200
- [ ] Test query returns valid response
- [ ] Charts display correctly (if showing in frontend)

## Need Help?

1. Check server logs for errors
2. Verify all services are imported correctly
3. Ensure GEMINI_API_KEY is in .env
4. Test individual services (indicators, screener, etc.)
5. Review FINANCE_AI_UPGRADE_GUIDE.md for details
