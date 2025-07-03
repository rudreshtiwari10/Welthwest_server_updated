# Running the Integrated Application

This document provides instructions for running the integrated frontend and backend application.

## Backend Setup

1. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

2. (Optional) Set up environment variables for AI models:
   Create a `.env` file in the Server directory with the following content:
   ```
   # Flask configuration
   FLASK_ENV=development
   PORT=8000

   # AI API keys
   OPENAI_API_KEY=your_openai_api_key_here
   OPENROUTER_API_KEY=your_openrouter_api_key_here
   CLAUDE_API_KEY=your_claude_api_key_here
   ```
   
   Replace the placeholder values with your actual API keys. If you don't have API keys, the system will fall back to a simulated Llama model response.

3. Start the backend server:
   ```
   python run.py
   ```
   
   The server will start on port 8000 by default. You should see output like:
   ```
   Starting Stock Market Data API on port 8000
   Debug mode: ON
   Press CTRL+C to stop the server
   ```

## Frontend Setup

1. Navigate to the frontend directory:
   ```
   cd ../frontend
   ```

2. Install the required npm packages:
   ```
   npm install
   ```

3. Start the frontend development server:
   ```
   npm start
   ```
   
   The React application will start and should automatically open in your browser at http://localhost:3000.

## API Endpoints

The following API endpoints are available:

1. **Historical Data**: `/api/historical?ticker=SYMBOL&period=PERIOD&interval=INTERVAL`
   - Example: `/api/historical?ticker=RELIANCE&period=1y&interval=1d`

2. **Live Data**: `/api/live?tickers=SYMBOL1,SYMBOL2,...`
   - Example: `/api/live?tickers=RELIANCE,TCS,INFY`

3. **OHLC Data**: `/api/ohlc?ticker=SYMBOL&start_date=START&end_date=END&interval=INTERVAL`
   - Example: `/api/ohlc?ticker=RELIANCE&start_date=2023-01-01&end_date=2023-12-31&interval=1d`

4. **Compare Stocks**: `/api/compare?tickers=SYMBOL1,SYMBOL2,...&period=PERIOD&interval=INTERVAL`
   - Example: `/api/compare?tickers=RELIANCE,TCS&period=1y&interval=1d`

5. **Stock Statistics**: `/api/statistics?ticker=SYMBOL&period=PERIOD&interval=INTERVAL`
   - Example: `/api/statistics?ticker=RELIANCE&period=1y&interval=1d`

6. **Market Indices**: `/api/market-indices`

7. **Top Gainers and Losers**: `/api/top-gainers-losers`

8. **Validate Ticker**: `/api/validate?ticker=SYMBOL`
   - Example: `/api/validate?ticker=RELIANCE`

9. **AI Chat**: `/api/market/chat` (POST)
   - Request body:
     ```json
     {
       "query": "Tell me about RELIANCE stock",
       "model": "llama",  // Optional: "llama", "openai", "openrouter", or "claude"
       "user_id": "user123"  // Optional: For logging purposes
     }
     ```
   - Response:
     ```json
     {
       "analysis": "Reliance Industries Limited is one of India's largest conglomerates...",
       "model": "llama-simulated",
       "stock_data": {
         "RELIANCE.NS": {
           "current_price": 2500.0,
           "change": {
             "value": 25.0,
             "percent": 1.01
           },
           "volume": 5000000,
           "market_cap": 1500000000000,
           "day_range": {
             "low": 2480.0,
             "high": 2520.0
           }
         }
       }
     }
     ```

10. **Health Check**: `/health`

## AI Chat Integration

The AI chat feature supports multiple models:

1. **Llama (Default)**: A simulated response if no API keys are provided
2. **OpenAI**: Requires an OpenAI API key in the `.env` file
3. **OpenRouter**: Requires an OpenRouter API key in the `.env` file
4. **Claude**: Requires a Claude API key in the `.env` file

The chat interface in the frontend allows users to select their preferred model. If the API key for a selected model is not available, the system will return an appropriate error message.

The AI assistant is designed to:
- Provide information about stocks and market trends
- Explain financial concepts
- Detect stock symbols in user queries and provide relevant data
- Never give specific investment advice

## Troubleshooting

1. **CORS Issues**: If you encounter CORS issues, make sure the backend server is running and the CORS configuration in `app.py` is correct.

2. **API Connection Issues**: Check that the API URL in `frontend/src/services/api.ts` is correctly set to `http://localhost:8000/api`.

3. **Data Not Loading**: Check the browser console for any errors. Make sure the backend server is running and accessible.

4. **Port Conflicts**: If port 8000 is already in use, you can change the port in `config.py` and update the API URL in the frontend accordingly.

5. **AI Chat Not Working**: If the AI chat feature is not working:
   - Check that the API endpoint URL in `frontend/src/services/api.ts` is correct
   - Verify that the required dependencies are installed (`requests`)
   - Check the API keys in your `.env` file if using external AI models 