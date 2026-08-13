"""
NextGen AI Service - Multi-model orchestration for finance-focused chatbot

This service implements the AI decision tree from NEXTGEN_CHATBOT.md:
- Path A: Stock Price Queries → yfinance + OpenRouter/Gemini
- Path B: Financial News/Sentiment → NewsAPI + FinBERT + OpenRouter/Gemini  
- Path C: Finance & Trading Explanations → OpenRouter/Gemini
- Path D: General Knowledge → Gemini
"""

import os
import json
import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import re
# yfinance and AIModelService imported lazily inside methods to avoid slow startup
import asyncio

# transformers imported lazily inside __init__ to avoid 5s+ startup delay
HAS_TRANSFORMERS = None  # Will be set on first use
_pipeline_func = None  # Will be set on first use

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NextGenAIOrchestrator:
    """
    Multi-model AI orchestration service for NextGen chatbot
    """

    # Comprehensive trigger words for analysis-related features (100+ keywords)
    ANALYSIS_TRIGGER_WORDS = {
        # General analysis keywords
        'analysis', 'analyze', 'technical analysis', 'fundamental analysis',
        'regime', 'market regime', 'rsi', 'rsa', 'macd', 'moving average', 'ma', 'ema', 'sma',
        'bollinger bands', 'fibonacci', 'candlestick', 'chart pattern', 'pattern',
        'support', 'resistance', 'trend', 'breakout', 'breakdown',
        'momentum', 'volatility', 'oscillator', 'stochastic', 'adx', 'atr',
        'volume analysis', 'price action', 'swing trading', 'day trading', 'scalping',
        'position trading', 'bull market', 'bear market', 'market trend',
        'technical indicator', 'indicator', 'signal',
        'entry point', 'exit point', 'stop loss', 'target',
        'trade setup', 'chart analysis', 'market analysis', 'stock analysis',
        'equity analysis',

        # Backtesting / Strategy engine keywords
        'backtest', 'backtesting', 'strategy test', 'strategy testing', 'test my strategy',
        'validate strategy', 'strategy', 'historical test', 'historical testing',
        'paper trading', 'simulate trades', 'trading simulator', 'performance test',
        'performance analysis', 'pnl analysis', 'profit and loss', 'drawdown',
        'max drawdown', 'sharpe ratio', 'risk reward', 'win rate', 'success rate',
        'equity curve', 'trade log', 'trade history', 'optimize strategy',
        'strategy optimization', 'parameter tuning', 'indicator test',
        'rsi strategy', 'macd strategy', 'moving average strategy',
        'trading strategy', 'test strategy', 'performance', 'historical data', 'historical analysis',

        # AI price forecasting / signals keywords
        'forecast', 'prediction', 'predict', 'price forecast', 'price prediction',
        'price predicting', 'stock forecast', 'stock prediction', 'stock signals',
        'buy signal', 'sell signal', 'trading signals', 'market forecast',
        'market prediction', 'ai forecast', 'ai signals', 'ml model',
        'machine learning forecast', 'time series forecast', 'next day price',
        'tomorrow price', 'short term forecast', 'swing trade signal',
        'regime prediction', 'bull bear signal', 'trend prediction',
        'volatility forecast', 'hmm', 'hidden markov', 'ai analysis',
        'machine learning', 'pattern recognition',

        # Generic platform-intent keywords
        'automated trading', 'trading bot', 'auto buy sell', 'quant tools',
        'analysis tools', 'trading platform', 'ai trading platform',
        'strategy builder', 'portfolio analysis'
    }

    def __init__(self):
        # Load API keys
        self.openrouter_api_key = os.environ.get('OPENROUTER_API_KEY', '')
        from services.gemini_client import GeminiRotator
        self._gemini = GeminiRotator()
        self.newsapi_key = os.environ.get('NEWSAPI_KEY', '')
        self.huggingface_token = os.environ.get('HUGGINGFACE_TOKEN', '')

        # Initialize base AI service lazily
        self._base_ai_service = None

        # Track model availability
        self.available_models = {
            "openrouter": bool(self.openrouter_api_key),
            "gemini": bool(self._gemini.keys),
            "newsapi": bool(self.newsapi_key),
            "finbert": bool(self.huggingface_token),
            "yfinance": True
        }

        # FinBERT initialized lazily on first sentiment analysis call
        self.finbert_pipeline = None
        self._finbert_loaded = False

    @property
    def base_ai_service(self):
        """Lazily initialize AIModelService on first use"""
        if self._base_ai_service is None:
            from services.ai_service import AIModelService
            self._base_ai_service = AIModelService()
        return self._base_ai_service

    def _ensure_finbert(self):
        """Load FinBERT pipeline on first use"""
        if self._finbert_loaded:
            return
        self._finbert_loaded = True
        try:
            if self.huggingface_token:
                from transformers import pipeline
                self.finbert_pipeline = pipeline(
                    "sentiment-analysis",
                    model="ProsusAI/finbert",
                    use_auth_token=self.huggingface_token
                )
        except (ImportError, Exception) as e:
            logger.warning(f"Failed to load FinBERT: {e}")

    def detect_analysis_intent(self, query: str) -> dict:
        """
        Detect if query contains analysis-related keywords and return suggested tools.
        Returns a dict with 'show_buttons' (bool) and 'suggested_tools' (list).
        """
        query_lower = query.lower().strip()

        # Check if any trigger word is present in the query
        has_trigger_word = any(
            trigger_word in query_lower
            for trigger_word in self.ANALYSIS_TRIGGER_WORDS
        )

        if not has_trigger_word:
            return {'show_buttons': False, 'suggested_tools': []}

        # Build suggested tools based on specific keywords
        suggested_tools = []

        # Market Regime & AI Analysis triggers
        regime_keywords = {
            'regime', 'market regime', 'forecast', 'prediction', 'predict',
            'hmm', 'hidden markov', 'ai analysis', 'market analysis',
            'technical analysis', 'analysis', 'pattern recognition',
            'price forecast', 'price prediction', 'stock forecast', 'stock prediction',
            'market forecast', 'market prediction', 'ai forecast', 'ai signals',
            'ml model', 'machine learning forecast', 'time series forecast',
            'next day price', 'tomorrow price', 'short term forecast',
            'swing trade signal', 'regime prediction', 'bull bear signal',
            'trend prediction', 'volatility forecast', 'stock signals',
            'trading signals', 'buy signal', 'sell signal'
        }

        # Backtesting triggers
        backtest_keywords = {
            'backtest', 'backtesting', 'strategy test', 'strategy testing',
            'test my strategy', 'validate strategy', 'strategy', 'historical test',
            'historical testing', 'paper trading', 'simulate trades',
            'trading simulator', 'performance test', 'performance analysis',
            'pnl analysis', 'profit and loss', 'drawdown', 'max drawdown',
            'sharpe ratio', 'win rate', 'success rate', 'equity curve',
            'trade log', 'trade history', 'optimize strategy',
            'strategy optimization', 'parameter tuning', 'indicator test',
            'rsi strategy', 'macd strategy', 'moving average strategy',
            'trading strategy', 'test strategy', 'performance',
            'historical data', 'historical analysis'
        }

        # Check for regime/forecast keywords
        has_regime_keywords = any(kw in query_lower for kw in regime_keywords)

        # Check for backtest keywords
        has_backtest_keywords = any(kw in query_lower for kw in backtest_keywords)

        # For general "analysis" or "technical analysis" queries, show BOTH tools
        general_analysis_keywords = {'analysis', 'analyze', 'technical analysis', 'fundamental analysis', 'chart analysis', 'stock analysis'}
        has_general_analysis = any(kw in query_lower for kw in general_analysis_keywords)

        # Add Market Regime button if relevant keywords found OR general analysis
        if has_regime_keywords or has_general_analysis:
            suggested_tools.append({
                'name': 'AI Market Regime & Forecast',
                'description': 'Get AI-powered market regime analysis and trade forecasts',
                'url': '/welth-market-regime',
                'icon': 'chart'
            })

        # Add Backtesting button if relevant keywords found OR general analysis
        if has_backtest_keywords or has_general_analysis:
            suggested_tools.append({
                'name': 'Advanced Backtesting',
                'description': 'Test your trading strategies with historical data',
                'url': '/backtest-beta',
                'icon': 'backtest'
            })

        # If no specific match but general trigger words detected, suggest both
        if not suggested_tools:
            suggested_tools = [
                {
                    'name': 'AI Market Regime & Forecast',
                    'description': 'Get AI-powered market regime analysis and trade forecasts',
                    'url': '/welth-market-regime',
                    'icon': 'chart'
                },
                {
                    'name': 'Advanced Backtesting',
                    'description': 'Test your trading strategies with historical data',
                    'url': '/backtest-beta',
                    'icon': 'backtest'
                }
            ]

        logger.info(f"Analysis intent detected! Showing {len(suggested_tools)} tool suggestions")
        return {
            'show_buttons': True,
            'suggested_tools': suggested_tools
        }

    def classify_query(self, query: str) -> str:
        """
        Classify user query into one of four paths:
        - stock_price: Stock prices, tickers, financial metrics
        - news_analysis: Financial news, headlines, opinions  
        - finance_explanation: General finance, trading, stock-market explanation
        - general: Outside finance (general knowledge)
        """
        query_lower = query.lower().strip()
        
        # First check for common general greetings and small talk
        general_greetings = [
            'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening',
            'how are you', 'whats up', 'what\'s up', 'how\'s it going', 'greetings',
            'thank you', 'thanks', 'bye', 'goodbye', 'see you', 'nice to meet you'
        ]
        
        # Check for exact matches or simple variations of greetings
        if any(greeting in query_lower for greeting in general_greetings):
            return 'general'
        
        # Check for non-finance general knowledge patterns
        general_patterns = [
            'how to', 'what is the weather', 'tell me about', 'help me with',
            'can you help', 'i need help', 'what\'s the time', 'what time is it'
        ]
        
        if any(pattern in query_lower for pattern in general_patterns) and not any(finance_term in query_lower for finance_term in ['stock', 'trade', 'invest', 'market', 'financial', 'money']):
            return 'general'
        
        # Keywords for different query types
        stock_price_keywords = [
            'price', 'stock price', 'current price', 'share price', 'ticker',
            'trading at', 'worth', 'cost', 'value', 'quote', 'market cap',
            'pe ratio', 'eps', '52 week', 'volume', 'nifty', 'sensex'
        ]
        
        news_keywords = [
            'news', 'headline', 'recent news', 'latest news', 'opinion',
            'announcement', 'earnings', 'results', 'sentiment', 'buzz',
            'market sentiment', 'bullish', 'bearish', 'analyst'
        ]
        
        finance_keywords = [
            'explain options', 'explain derivatives', 'what are options', 'what are derivatives',
            'options trading', 'derivatives', 'portfolio', 'diversification',
            'risk management', 'investment strategy', 'fundamental analysis',
            'technical analysis', 'candlestick', 'moving average'
        ]
        
        # More robust stock symbol detection - only if in finance context
        has_finance_context = any(keyword in query_lower for keyword in stock_price_keywords + news_keywords + finance_keywords)
        
        # Check for stock symbols only if there's finance context or explicit ticker format
        potential_tickers = re.findall(r'\b[A-Z]{2,5}\b', query.upper())
        valid_tickers = []
        
        for ticker in potential_tickers:
            # More selective ticker validation
            if (ticker.startswith('$') or 
                has_finance_context or 
                ticker in ['TCS', 'INFY', 'RELIANCE', 'AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN', 'NIFTY', 'SENSEX']):
                valid_tickers.append(ticker)
        
        has_stock_symbols = len(valid_tickers) > 0
        
        # Check for finance explanations first (more specific)
        if any(keyword in query_lower for keyword in finance_keywords):
            return 'finance_explanation'
        
        # Check for specific finance explanation patterns
        if (('explain' in query_lower or 'what is' in query_lower or 'what are' in query_lower or 'how does' in query_lower) and 
            any(term in query_lower for term in ['stock', 'trading', 'option', 'derivative', 'investment', 'portfolio', 'market', 'financial'])):
            return 'finance_explanation'
        
        # Classification logic for other types
        if any(keyword in query_lower for keyword in stock_price_keywords) or has_stock_symbols:
            return 'stock_price'
        elif any(keyword in query_lower for keyword in news_keywords):
            return 'news_analysis'
        else:
            # Check if it's finance-related at all
            general_finance_keywords = [
                'invest', 'trading', 'stock', 'market', 'financial', 'money',
                'profit', 'loss', 'bull', 'bear', 'equity', 'bond', 'mutual fund'
            ]
            if any(keyword in query_lower for keyword in general_finance_keywords):
                return 'finance_explanation'
            else:
                return 'general'
    
    def extract_stock_symbols(self, query: str) -> List[str]:
        """Extract stock symbols from query"""
        # Common Indian stock symbols
        indian_symbols = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
            'SBIN', 'HINDUNILVR', 'BHARTIARTL', 'ITC', 'KOTAKBANK',
            'WIPRO', 'ASIANPAINT', 'MARUTI', 'BAJFINANCE', 'HCLTECH'
        ]
        
        # Extract potential symbols (2-5 uppercase letters)
        symbols = re.findall(r'\b[A-Z]{2,5}\b', query.upper())
        
        # Add .NS suffix for NSE symbols
        formatted_symbols = []
        for symbol in symbols:
            if symbol in ['NIFTY', 'NIFTY50']:
                formatted_symbols.append('^NSEI')
            elif symbol in ['SENSEX', 'BSE']:
                formatted_symbols.append('^BSESN')
            elif symbol == 'BANKNIFTY':
                formatted_symbols.append('^NSEBANK')
            elif symbol in indian_symbols:
                formatted_symbols.append(f"{symbol}.NS")
            else:
                formatted_symbols.append(symbol)  # US stocks
        
        return formatted_symbols
    
    def fetch_stock_data(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch stock data using yfinance with enhanced price information"""
        stock_data = {}

        for symbol in symbols:
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                info = ticker.info

                # Fetch more data for charts - last 30 days with 1-day interval
                hist = ticker.history(period="1mo", interval="1d")

                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                    change = current_price - prev_price
                    change_percent = (change / prev_price) * 100 if prev_price != 0 else 0

                    # Get the timestamp of the last data point
                    last_updated = hist.index[-1].strftime('%Y-%m-%d %H:%M:%S UTC')

                    # Prepare chart data (last 30 days)
                    chart_data = {
                        'dates': [date.strftime('%Y-%m-%d') for date in hist.index],
                        'prices': [round(float(price), 2) for price in hist['Close'].tolist()],
                        'volumes': [int(vol) for vol in hist['Volume'].tolist()] if 'Volume' in hist else []
                    }

                    # Get day range
                    day_high = round(float(hist['High'].iloc[-1]), 2) if 'High' in hist else None
                    day_low = round(float(hist['Low'].iloc[-1]), 2) if 'Low' in hist else None

                    stock_data[symbol] = {
                        'symbol': symbol,
                        'current_price': round(float(current_price), 2),
                        'previous_close': round(float(prev_price), 2),
                        'change': round(float(change), 2),
                        'change_percent': round(change_percent, 2),
                        'volume': int(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0,
                        'company_name': info.get('longName', symbol),
                        'market_cap': info.get('marketCap', 'N/A'),
                        'pe_ratio': info.get('forwardPE', 'N/A'),
                        'sector': info.get('sector', 'N/A'),
                        'day_high': day_high,
                        'day_low': day_low,
                        'last_updated': last_updated,
                        'chart_data': chart_data
                    }

                    logger.info(f"Fetched data for {symbol}: ₹{current_price} (updated: {last_updated})")

            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                stock_data[symbol] = {'error': str(e)}

        return stock_data
    
    def fetch_financial_news(self, query: str, symbols: List[str] = None) -> List[Dict]:
        """Fetch financial news using NewsAPI"""
        if not self.newsapi_key:
            return []
        
        try:
            # Build search query
            if symbols:
                search_terms = ' OR '.join([s.replace('.NS', '') for s in symbols])
            else:
                # Extract key terms from query
                search_terms = query
            
            url = f"https://newsapi.org/v2/everything"
            params = {
                'q': search_terms,
                'domains': 'economictimes.com,moneycontrol.com,business-standard.com,livemint.com',
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 5,
                'apiKey': self.newsapi_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            articles = data.get('articles', [])
            
            # Format articles
            news_items = []
            for article in articles[:5]:  # Limit to 5 articles
                news_items.append({
                    'title': article['title'],
                    'description': article['description'],
                    'url': article['url'],
                    'published_at': article['publishedAt'],
                    'source': article['source']['name']
                })
            
            logger.info(f"Fetched {len(news_items)} news articles")
            return news_items
            
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment using FinBERT"""
        self._ensure_finbert()
        if not self.finbert_pipeline:
            return {'sentiment': 'neutral', 'confidence': 0.5}
        
        try:
            result = self.finbert_pipeline(text)
            return {
                'sentiment': result[0]['label'].lower(),
                'confidence': round(result[0]['score'], 3)
            }
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return {'sentiment': 'neutral', 'confidence': 0.5}
    
    def clean_ai_response(self, text: str) -> str:
        """Clean AI response by removing model artifacts and prefixes/suffixes"""
        if not text:
            return text

        # Remove common LLM artifacts
        cleaned = text.strip()

        # Remove <s> prefix and </s> suffix (Mistral/LLama artifacts)
        cleaned = re.sub(r'^<s>\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*</s>$', '', cleaned, flags=re.IGNORECASE)

        # Remove [OUT] and [/OUT] tags
        cleaned = re.sub(r'\[OUT\]\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[/OUT\]\s*', '', cleaned, flags=re.IGNORECASE)

        # Remove [INST] and [/INST] tags (instruction tags)
        cleaned = re.sub(r'\[INST\]\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[/INST\]\s*', '', cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def call_openrouter_api(self, messages: List[Dict], model: str = "mistralai/mistral-7b-instruct") -> str:
        """Call OpenRouter API"""
        if not self.openrouter_api_key:
            raise Exception("OpenRouter API key not available")

        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 1000,
                "temperature": 0.7
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            raw_response = data['choices'][0]['message']['content']

            # Clean the response before returning
            return self.clean_ai_response(raw_response)

        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            raise
    
    def call_gemini_api(self, prompt: str) -> str:
        """Call Gemini API as fallback"""
        if not self._gemini.keys:
            raise Exception("Gemini API key not available")

        try:
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1000
                }
            }

            data = self._gemini.post(payload)
            raw_response = data['candidates'][0]['content']['parts'][0]['text']

            # Clean the response before returning
            return self.clean_ai_response(raw_response)

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
    
    async def process_query(self, query: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        Main orchestration method - routes query through appropriate AI decision path
        """
        query_type = self.classify_query(query)
        logger.info(f"Query classified as: {query_type}")

        # Detect analysis intent for all queries
        analysis_intent = self.detect_analysis_intent(query)

        try:
            if query_type == 'stock_price':
                result = await self._handle_stock_price_query(query)
            elif query_type == 'news_analysis':
                result = await self._handle_news_analysis_query(query)
            elif query_type == 'finance_explanation':
                result = await self._handle_finance_explanation_query(query, conversation_history)
            else:  # general
                result = await self._handle_general_query(query, conversation_history)

            # Add analysis intent metadata to result
            result['analysis_buttons'] = analysis_intent
            return result

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'response': "⚠️ Sorry, I'm unable to process that right now. Please try again later.",
                'query_type': query_type,
                'model_used': 'error',
                'confidence': 0.0,
                'error': str(e),
                'analysis_buttons': {'show_buttons': False, 'suggested_tools': []}
            }
    
    async def _handle_stock_price_query(self, query: str) -> Dict[str, Any]:
        """Path A: Stock Price Queries"""
        symbols = self.extract_stock_symbols(query)
        
        if not symbols:
            # Try to extract company names and convert to symbols
            response_text = "I couldn't identify any stock symbols in your query. Please specify a stock ticker (e.g., RELIANCE, TCS, INFY) or ask about a specific company."
            return {
                'response': response_text,
                'query_type': 'stock_price',
                'model_used': 'rule_based',
                'confidence': 0.8
            }
        
        # Fetch stock data
        stock_data = self.fetch_stock_data(symbols)
        
        if not stock_data or all('error' in data for data in stock_data.values()):
            return {
                'response': "Sorry, I couldn't fetch stock data at the moment. Please try again later.",
                'query_type': 'stock_price',
                'model_used': 'yfinance',
                'confidence': 0.0
            }
        
        # Format response using AI
        try:
            # Prepare context for AI
            stock_info = []
            for symbol, data in stock_data.items():
                if 'error' not in data:
                    stock_info.append(
                        f"{data['company_name']} ({symbol}): "
                        f"₹{data['current_price']} "
                        f"({data['change']:+.2f}, {data['change_percent']:+.2f}%)"
                    )
            
            context = f"Stock Data: {'; '.join(stock_info)}"
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a financial assistant for Indian markets. ALWAYS use ₹ (Rupees symbol) when mentioning prices, never use $ or USD. Provide clear, concise stock price information with brief context. Include current prices, changes, and simple analysis. Keep responses under 200 words."
                },
                {
                    "role": "user",
                    "content": f"User asked: '{query}'\n\n{context}\n\nPlease provide a helpful response about these stock prices. Remember to use ₹ symbol for all prices."
                }
            ]

            # Try OpenRouter first, fallback to Gemini
            model_used = "openrouter"
            try:
                response_text = self.call_openrouter_api(messages)
            except:
                model_used = "gemini"
                prompt = f"User asked about stock prices: '{query}'\n\nStock data: {context}\n\nProvide a helpful, concise response about these stock prices. IMPORTANT: Always use ₹ (Rupees symbol) for prices, never use $ or USD."
                response_text = self.call_gemini_api(prompt)
            
            return {
                'response': response_text,
                'query_type': 'stock_price',
                'model_used': model_used,
                'stock_data': stock_data,
                'confidence': 0.9
            }
            
        except Exception as e:
            # Fallback to simple formatted response
            response_lines = []
            for symbol, data in stock_data.items():
                if 'error' not in data:
                    change_indicator = "📈" if data['change'] >= 0 else "📉"
                    response_lines.append(
                        f"{change_indicator} **{data['company_name']} ({symbol})**\n"
                        f"Current Price: ₹{data['current_price']}\n"
                        f"Change: {data['change']:+.2f} ({data['change_percent']:+.2f}%)"
                    )
            
            response_text = "\n\n".join(response_lines)
            if not response_text:
                response_text = "Unable to fetch stock data at the moment."
            
            return {
                'response': response_text,
                'query_type': 'stock_price',
                'model_used': 'fallback',
                'stock_data': stock_data,
                'confidence': 0.7
            }
    
    async def _handle_news_analysis_query(self, query: str) -> Dict[str, Any]:
        """Path B: Financial News/Sentiment Analysis"""
        symbols = self.extract_stock_symbols(query)
        
        # Fetch news
        news_items = self.fetch_financial_news(query, symbols)
        
        if not news_items:
            response_text = "I couldn't fetch recent financial news at the moment. Please try again later or ask about specific companies."
            return {
                'response': response_text,
                'query_type': 'news_analysis',
                'model_used': 'newsapi',
                'confidence': 0.3
            }
        
        # Analyze sentiment of headlines
        sentiment_results = []
        for article in news_items:
            sentiment = self.analyze_sentiment(article['title'])
            sentiment_results.append(sentiment)
        
        # Calculate overall sentiment
        positive_count = sum(1 for s in sentiment_results if s['sentiment'] == 'positive')
        negative_count = sum(1 for s in sentiment_results if s['sentiment'] == 'negative')
        total_count = len(sentiment_results)
        
        # Format response using AI
        try:
            # Prepare context
            headlines = [f"- {article['title']}" for article in news_items[:3]]
            headlines_text = "\n".join(headlines)
            
            sentiment_summary = f"Sentiment Analysis: {positive_count}/{total_count} positive, {negative_count}/{total_count} negative"
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a financial news analyst. Summarize recent financial news and sentiment. Be objective and highlight key market trends. Keep responses under 250 words."
                },
                {
                    "role": "user",
                    "content": f"User asked: '{query}'\n\nRecent Headlines:\n{headlines_text}\n\n{sentiment_summary}\n\nProvide an analysis of the current market sentiment and key trends."
                }
            ]
            
            # Try OpenRouter first, fallback to Gemini
            model_used = "openrouter"
            try:
                response_text = self.call_openrouter_api(messages)
            except:
                model_used = "gemini"
                prompt = f"Analyze these financial news headlines for sentiment and trends:\n{headlines_text}\n\n{sentiment_summary}\n\nUser asked: '{query}'"
                response_text = self.call_gemini_api(prompt)
            
            return {
                'response': response_text,
                'query_type': 'news_analysis',
                'model_used': model_used,
                'sentiment': f"{positive_count}P/{negative_count}N/{total_count-positive_count-negative_count}Neu",
                'confidence': 0.85
            }
            
        except Exception as e:
            # Fallback response
            sentiment_text = f"📊 **Market Sentiment**: {positive_count} positive, {negative_count} negative out of {total_count} recent headlines"
            
            headlines_text = "\n".join([f"📰 {article['title']}" for article in news_items[:3]])
            
            response_text = f"{sentiment_text}\n\n**Recent Headlines:**\n{headlines_text}"
            
            return {
                'response': response_text,
                'query_type': 'news_analysis',
                'model_used': 'fallback',
                'sentiment': f"{positive_count}P/{negative_count}N",
                'confidence': 0.6
            }
    
    async def _handle_finance_explanation_query(self, query: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Path C: Finance & Trading Explanations"""
        try:
            # Build conversation context
            messages = [
                {
                    "role": "system",
                    "content": """You are a knowledgeable financial educator for Indian markets. Explain financial concepts clearly and practically.
                    Focus on Indian markets when relevant. When mentioning prices or amounts, ALWAYS use ₹ (Rupees symbol), never $ or USD.
                    Always include risk warnings for investment advice. Keep explanations beginner-friendly but comprehensive. Limit responses to 300 words."""
                }
            ]
            
            # Add conversation history if available
            if conversation_history:
                for msg in conversation_history[-3:]:  # Last 3 messages for context
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            messages.append({
                "role": "user",
                "content": query
            })
            
            # Try OpenRouter first, fallback to Gemini
            model_used = "openrouter"
            try:
                response_text = self.call_openrouter_api(messages)
            except:
                model_used = "gemini"
                context = f"Previous conversation: {conversation_history}" if conversation_history else ""
                prompt = f"Explain this financial concept clearly and practically: '{query}'\n{context}"
                response_text = self.call_gemini_api(prompt)
            
            return {
                'response': response_text,
                'query_type': 'finance_explanation',
                'model_used': model_used,
                'confidence': 0.9
            }
            
        except Exception as e:
            logger.error(f"Error in finance explanation: {e}")
            response_text = """I'm having trouble accessing my knowledge base right now. For financial education, I recommend:

📚 **Resources:**
- NSE Academy for Indian markets
- Zerodha Varsity for free trading education
- RBI's financial literacy resources

💡 **General Advice:** Always research thoroughly and consult certified financial advisors before making investment decisions."""
            
            return {
                'response': response_text,
                'query_type': 'finance_explanation',
                'model_used': 'fallback',
                'confidence': 0.4
            }
    
    async def _handle_general_query(self, query: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Path D: General Knowledge (Non-Finance)"""
        try:
            # Build messages for conversation context
            messages = [
                {
                    "role": "system",
                    "content": "You are NextGen Assistant — friendly, concise. For greetings and small talk, reply in 1–3 sentences. Be helpful and conversational. If user requests personalized investment advice, politely refuse and provide general educational guidance."
                }
            ]
            
            # Add conversation history if available
            if conversation_history:
                for msg in conversation_history[-4:]:  # Last 4 messages for context
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            messages.append({
                "role": "user",
                "content": query
            })
            
            # Try Gemini first (primary for general queries)
            model_used = "gemini"
            try:
                # Convert messages to simple prompt for Gemini
                context = ""
                if conversation_history:
                    recent_msgs = conversation_history[-2:]
                    context = f"\nPrevious conversation: {recent_msgs}"
                
                prompt = f"You are a friendly assistant. Please respond to this message concisely and helpfully: '{query}'{context}"
                response_text = self.call_gemini_api(prompt)
                
            except Exception as gemini_error:
                logger.warning(f"Gemini failed, trying OpenRouter fallback: {gemini_error}")
                
                # Fallback to OpenRouter
                try:
                    model_used = "openrouter"
                    response_text = self.call_openrouter_api(messages, "mistralai/mistral-7b-instruct")
                except Exception as openrouter_error:
                    logger.error(f"OpenRouter also failed: {openrouter_error}")
                    raise Exception("Both Gemini and OpenRouter failed")
            
            return {
                'response': response_text,
                'query_type': 'general',
                'model_used': model_used,
                'confidence': 0.85
            }
            
        except Exception as e:
            logger.error(f"Error in general query: {e}")
            
            # Friendly fallback response based on query type
            query_lower = query.lower()
            if any(greeting in query_lower for greeting in ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']):
                response_text = "Hello! 👋 I'm NextGen Assistant. I'm here to help with financial questions, stock data, market news, and general conversations. How can I assist you today?"
            elif any(thanks in query_lower for thanks in ['thank you', 'thanks']):
                response_text = "You're welcome! Feel free to ask me anything about finance, markets, or if you just want to chat."
            elif 'how are you' in query_lower:
                response_text = "I'm doing well, thank you for asking! I'm ready to help with any questions you have about finance, trading, or just general conversation."
            else:
                response_text = "I'm having trouble processing your request right now. Please try asking again or rephrase your question."
            
            return {
                'response': response_text,
                'query_type': 'general',
                'model_used': 'fallback',
                'confidence': 0.6
            }

# Initialize the orchestrator
_nextgen_orchestrator = None

def get_nextgen_orchestrator():
    """Lazily initialize NextGenAIOrchestrator on first use"""
    global _nextgen_orchestrator
    if _nextgen_orchestrator is None:
        _nextgen_orchestrator = NextGenAIOrchestrator()
    return _nextgen_orchestrator