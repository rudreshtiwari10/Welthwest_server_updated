"""
Finance AI Orchestrator - Intelligent Query Routing and Response Generation

This is the "brain" of the Finance AI system that:
1. Classifies user queries into categories
2. Routes to appropriate services
3. Assembles structured context for LLM
4. Generates comprehensive responses
5. Handles failures and fallbacks

Query Categories:
- stock_price: Stock prices, quotes, current data
- technical_analysis: Charts, indicators, signals
- screener: Stock screening requests
- backtest: Strategy backtesting
- document_query: Questions about uploaded PDFs
- news_analysis: Market news and sentiment
- finance_explanation: General finance concepts
- general: Non-finance queries
"""

import logging
import re
from typing import Dict, Any, List, Optional
import os
import requests
import json
from datetime import datetime, timedelta

# Import all our services
from services.indicators_service import get_indicators, get_signal_summary
from services.chart_service import generate_chart, chart_service
from services.screener_service import screen_stocks, run_screen, get_available_screens
from services.simple_backtest_service import run_backtest
from services.rag_service import get_context_for_query, rag_service
from services.stock_service import get_live_data
import yfinance as yf

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinanceOrchestrator:
    """
    Advanced orchestrator for finance AI queries
    """

    def __init__(self):
        # Load API keys
        self.gemini_api_key = os.environ.get('GEMINI_API_KEY', '')
        self.openrouter_api_key = os.environ.get('OPENROUTER_API_KEY', '')

        # System prompts
        self.finance_system_prompt = """You are a professional financial analyst AI assistant for WelthWest.

Your role:
- Provide accurate, data-driven financial analysis
- Explain technical indicators and market concepts clearly
- Help users understand stock performance and trends
- NEVER give specific buy/sell recommendations
- Always remind users that past performance doesn't guarantee future results
- Emphasize that you provide information, not financial advice

When analyzing data:
- Be objective and balanced
- Cite the specific indicators and metrics
- Explain what the data suggests, not what users should do
- Use professional but accessible language"""

    def classify_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Classify user query into a category with conversation context

        Categories:
        - stock_price: "What is the price of RELIANCE?"
        - technical_analysis: "Show me RSI for TCS", "Analyze INFY chart"
        - screener: "Find oversold stocks", "Screen for momentum stocks"
        - backtest: "Test SMA crossover on AAPL", "Backtest RSI strategy"
        - document_query: "What does the earnings report say about revenue?"
        - news_analysis: "Latest news on Tesla", "Market sentiment for tech"
        - finance_explanation: "What is RSI?", "Explain moving averages"
        - general: Everything else (default for safety)

        Args:
            query: User query string
            conversation_history: Previous conversation for context

        Returns:
            Query category
        """
        query_lower = query.lower().strip()

        # Greeting patterns and general conversational patterns
        greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you', 'bye', 'how are you', 'what\'s up']
        if any(query_lower.startswith(g) for g in greetings) or any(query_lower == g for g in greetings):
            return 'general'

        # Very short queries without clear symbols are likely conversational
        if len(query.split()) <= 3 and not self.extract_symbols(query):
            return 'general'

        # Document query patterns
        doc_keywords = ['earnings report', 'annual report', '10-k', 'prospectus', 'according to the document', 'in the report']
        if any(keyword in query_lower for keyword in doc_keywords):
            return 'document_query'

        # Backtesting patterns
        backtest_keywords = ['backtest', 'test strategy', 'simulate', 'historical performance', 'strategy performance']
        if any(keyword in query_lower for keyword in backtest_keywords):
            return 'backtest'

        # Screener patterns
        screener_keywords = ['screen', 'find stocks', 'search stocks', 'filter stocks', 'scan for', 'oversold stocks', 'momentum stocks']
        if any(keyword in query_lower for keyword in screener_keywords):
            return 'screener'

        # Technical analysis patterns
        ta_keywords = ['rsi', 'macd', 'moving average', 'sma', 'ema', 'bollinger', 'indicator', 'chart', 'technical analysis', 'analyze']
        ta_verbs = ['show', 'display', 'plot', 'draw', 'calculate']
        has_ta_keyword = any(keyword in query_lower for keyword in ta_keywords)
        has_ta_verb = any(verb in query_lower for verb in ta_verbs)

        # Check for stock symbols (exclude common words)
        common_words = {'HOW', 'ARE', 'YOU', 'THE', 'AND', 'FOR', 'CAN', 'WHAT', 'WHY',
                        'WHO', 'WHEN', 'WHERE', 'WHICH', 'WILL', 'WOULD', 'SHOULD', 'COULD',
                        'THIS', 'THAT', 'THESE', 'THOSE', 'HAVE', 'HAS', 'HAD', 'WAS', 'WERE',
                        'BEEN', 'BEING', 'DOES', 'DID', 'DOING', 'SHOW', 'TELL', 'GIVE', 'GET',
                        'INVEST', 'GOOD', 'BAD', 'BEST'}
        potential_symbols = [s for s in re.findall(r'\b[A-Z]{2,5}\b', query.upper()) if s not in common_words]
        has_stock_symbol = len(potential_symbols) > 0

        # Only classify as technical_analysis if BOTH keywords AND clear symbols exist
        if (has_ta_keyword or has_ta_verb) and has_stock_symbol and len(potential_symbols) > 0:
            return 'technical_analysis'

        # Stock price patterns - require explicit stock mention
        price_keywords = ['price', 'quote', 'current price', 'trading at', 'stock price', 'worth', 'value of']
        if any(keyword in query_lower for keyword in price_keywords) and has_stock_symbol and len(potential_symbols) > 0:
            return 'stock_price'

        # News analysis patterns
        news_keywords = ['news', 'headlines', 'latest', 'sentiment', 'market news', 'announcement']
        if any(keyword in query_lower for keyword in news_keywords):
            return 'news_analysis'

        # Finance explanation patterns
        explanation_patterns = [
            ('what is', 'what are', 'explain', 'how does', 'how do', 'tell me about'),
            ('option', 'derivative', 'stock', 'bond', 'etf', 'mutual fund', 'dividend', 'pe ratio', 'market cap')
        ]
        has_question = any(pattern in query_lower for pattern in explanation_patterns[0])
        has_finance_term = any(term in query_lower for term in explanation_patterns[1])

        if has_question and has_finance_term:
            return 'finance_explanation'

        # Default to technical analysis if stock symbol present
        if has_stock_symbol:
            return 'technical_analysis'

        # Otherwise general
        return 'general'

    def extract_symbols(self, query: str) -> List[str]:
        """
        Extract stock symbols from query

        Args:
            query: User query

        Returns:
            List of stock symbols
        """
        symbols = []
        query_upper = query.upper()

        # Indian stock mapping (both uppercase and lowercase)
        indian_stocks = {
            'RELIANCE': 'RELIANCE.NS', 'TCS': 'TCS.NS', 'INFY': 'INFY.NS',
            'HDFCBANK': 'HDFCBANK.NS', 'ICICIBANK': 'ICICIBANK.NS',
            'SBIN': 'SBIN.NS', 'ITC': 'ITC.NS', 'INFOSYS': 'INFY.NS',
            'WIPRO': 'WIPRO.NS', 'TATAMOTORS': 'TATAMOTORS.NS',
            'BHARTIAIRTEL': 'BHARTIAIRTEL.NS', 'AIRTEL': 'BHARTIAIRTEL.NS',
            'HINDUNILVR': 'HINDUNILVR.NS', 'HUL': 'HINDUNILVR.NS',
            'MARUTI': 'MARUTI.NS', 'TATASTEEL': 'TATASTEEL.NS',
            'BAJFINANCE': 'BAJFINANCE.NS', 'KOTAKBANK': 'KOTAKBANK.NS'
        }

        # First, check for symbols with .NS or .BO suffix
        ns_symbols = re.findall(r'\b([A-Z]+\.(?:NS|BO))\b', query_upper)
        symbols.extend(ns_symbols)

        # Check for known Indian company names (case insensitive)
        for stock_name, symbol in indian_stocks.items():
            if stock_name in query_upper and symbol not in symbols:
                symbols.append(symbol)

        # If no symbols found yet, find uppercase words (2-5 letters) excluding common words
        if not symbols:
            common_words = {'FOR', 'AND', 'THE', 'SHOW', 'GET', 'ME', 'OF', 'IN', 'ON', 'AT', 'TO', 'NS', 'BO'}
            potential_symbols = re.findall(r'\b([A-Z]{2,5})\b', query)

            for symbol in potential_symbols:
                if symbol not in common_words and symbol not in symbols:
                    # Check if it's a known Indian stock
                    if symbol in indian_stocks:
                        symbols.append(indian_stocks[symbol])
                    else:
                        # Assume it's a US stock
                        symbols.append(symbol)

        return list(set(symbols))  # Remove duplicates

    def handle_stock_price_query(self, query: str, symbols: List[str]) -> Dict[str, Any]:
        """Handle stock price queries"""
        try:
            if not symbols:
                # No symbol found - treat as general query instead of error
                return {
                    'category': 'general',
                    'context': {'data_type': 'general'}
                }

            # Get stock data
            symbol = symbols[0]  # Use first symbol
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period='1d')

            if hist.empty:
                return {
                    'category': 'stock_price',
                    'error': f'No data available for {symbol}'
                }

            current_price = hist['Close'].iloc[-1]
            prev_close = info.get('previousClose', current_price)
            change = current_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0

            stock_data = {
                'symbol': symbol,
                'name': info.get('longName', symbol),
                'current_price': round(current_price, 2),
                'previous_close': round(prev_close, 2),
                'change': round(change, 2),
                'change_percent': round(change_pct, 2),
                'volume': info.get('volume', 0),
                'market_cap': info.get('marketCap', 0),
                'day_high': round(hist['High'].iloc[-1], 2),
                'day_low': round(hist['Low'].iloc[-1], 2)
            }

            # Prepare context for LLM
            context = {
                'data_type': 'stock_price',
                'stock_data': stock_data
            }

            return {
                'category': 'stock_price',
                'symbols': symbols,
                'data': stock_data,
                'context': context
            }

        except Exception as e:
            logger.error(f"Error in stock price query: {e}")
            return {
                'category': 'stock_price',
                'error': str(e)
            }

    def handle_technical_analysis_query(self, query: str, symbols: List[str]) -> Dict[str, Any]:
        """Handle technical analysis queries"""
        try:
            if not symbols:
                # No symbol found - treat as general query instead of error
                return {
                    'category': 'general',
                    'context': {'data_type': 'general'}
                }

            symbol = symbols[0]

            # Get indicators
            indicators = get_indicators(symbol, period='6mo')

            if 'error' in indicators:
                return {
                    'category': 'technical_analysis',
                    'error': indicators['error']
                }

            # Generate comprehensive chart
            chart_base64 = generate_chart(
                indicators['raw_data'],
                chart_type='comprehensive',
                symbol=symbol
            )

            # Get signal summary
            signal_summary = get_signal_summary(symbol)

            # Prepare context for LLM
            context = {
                'data_type': 'technical_analysis',
                'symbol': symbol,
                'indicators': indicators['indicators'],
                'signal_summary': signal_summary,
                'current_price': indicators['current_price']
            }

            return {
                'category': 'technical_analysis',
                'symbols': symbols,
                'data': indicators,
                'signal_summary': signal_summary,
                'chart_base64': chart_base64,
                'context': context
            }

        except Exception as e:
            logger.error(f"Error in technical analysis query: {e}")
            return {
                'category': 'technical_analysis',
                'error': str(e)
            }

    def handle_screener_query(self, query: str) -> Dict[str, Any]:
        """Handle screener queries"""
        try:
            # Parse query for screening intent
            query_lower = query.lower()

            # Determine which predefined screen to use
            screens = get_available_screens()
            selected_screen = None

            if 'oversold' in query_lower or 'bounce' in query_lower:
                selected_screen = 'oversold_bounce'
            elif 'uptrend' in query_lower or 'bullish' in query_lower:
                selected_screen = 'strong_uptrend'
            elif 'momentum' in query_lower or 'breakout' in query_lower:
                selected_screen = 'momentum_breakout'
            elif 'overbought' in query_lower or 'reversal' in query_lower:
                selected_screen = 'overbought_reversal'
            elif 'downtrend' in query_lower or 'bearish' in query_lower or 'short' in query_lower:
                selected_screen = 'downtrend_short'
            else:
                # Default to oversold bounce
                selected_screen = 'oversold_bounce'

            # Run screen
            results = run_screen(selected_screen, universe='NIFTY50', top_n=10)

            # Prepare context for LLM
            context = {
                'data_type': 'screener',
                'screen_name': results.get('screen_name'),
                'description': results.get('description'),
                'num_results': results.get('total_matches', 0),
                'top_stocks': [r['symbol'] for r in results.get('results', [])[:5]]
            }

            return {
                'category': 'screener',
                'data': results,
                'context': context
            }

        except Exception as e:
            logger.error(f"Error in screener query: {e}")
            return {
                'category': 'screener',
                'error': str(e)
            }

    def handle_backtest_query(self, query: str) -> Dict[str, Any]:
        """Handle backtest queries"""
        try:
            # Parse query for symbol and strategy
            symbols = self.extract_symbols(query)
            if not symbols:
                # No symbol found - treat as general query instead of error
                return {
                    'category': 'general',
                    'context': {'data_type': 'general'}
                }

            symbol = symbols[0]
            query_lower = query.lower()

            # Determine strategy
            if 'rsi' in query_lower:
                strategy = 'rsi'
            elif 'ema' in query_lower:
                strategy = 'ema_crossover'
            else:
                strategy = 'sma_crossover'  # Default

            # Run backtest (last 1 year)
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

            results = run_backtest(
                strategy=strategy,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                initial_capital=100000
            )

            if 'error' in results:
                return {
                    'category': 'backtest',
                    'error': results['error']
                }

            # Generate equity curve chart
            chart_base64 = chart_service.create_backtest_chart(
                equity_curve=results['equity_curve']['values'],
                dates=results['equity_curve']['dates'],
                trades=results.get('trades', []),
                title=f"{results['strategy']} - {symbol}"
            )

            # Prepare context for LLM
            context = {
                'data_type': 'backtest',
                'strategy': results['strategy'],
                'symbol': symbol,
                'metrics': results['metrics'],
                'num_trades': results['metrics']['num_trades']
            }

            return {
                'category': 'backtest',
                'data': results,
                'chart_base64': chart_base64,
                'context': context
            }

        except Exception as e:
            logger.error(f"Error in backtest query: {e}")
            return {
                'category': 'backtest',
                'error': str(e)
            }

    def handle_document_query(self, query: str) -> Dict[str, Any]:
        """Handle queries about uploaded PDFs"""
        try:
            # Check if RAG service is available
            if not rag_service.is_available():
                return {
                    'category': 'document_query',
                    'error': 'Document analysis not available. Required dependencies: PyPDF2, sentence-transformers, chromadb'
                }

            # Get relevant context from documents
            doc_context = get_context_for_query(query, top_k=3)

            if "No relevant information" in doc_context:
                return {
                    'category': 'document_query',
                    'message': 'No uploaded documents found. Please upload a PDF first.',
                    'context': {'data_type': 'document_query', 'has_documents': False}
                }

            # Prepare context for LLM
            context = {
                'data_type': 'document_query',
                'document_context': doc_context,
                'has_documents': True
            }

            return {
                'category': 'document_query',
                'document_context': doc_context,
                'context': context
            }

        except Exception as e:
            logger.error(f"Error in document query: {e}")
            return {
                'category': 'document_query',
                'error': str(e)
            }

    def call_gemini(self, prompt: str, temperature: float = 0.2) -> str:
        """
        Call Google Gemini API

        Args:
            prompt: Full prompt including system message and context
            temperature: Temperature for response generation

        Returns:
            LLM response text
        """
        if not self.gemini_api_key:
            return "Gemini API key not configured."

        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={self.gemini_api_key}"

            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature,
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                }
            }

            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'candidates' in data and len(data['candidates']) > 0:
                return data['candidates'][0]['content']['parts'][0]['text']
            else:
                return "Unable to generate response."

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return f"Error calling Gemini: {str(e)}"

    def generate_response(self, query: str, context_data: Dict[str, Any], conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Generate AI response using LLM with conversation context

        Args:
            query: User query
            context_data: Structured context from services
            conversation_history: Previous messages in the conversation (optional)

        Returns:
            AI-generated response
        """
        # Build structured prompt
        prompt_parts = [self.finance_system_prompt, "\n\n"]

        # Add conversation history if available
        if conversation_history and len(conversation_history) > 0:
            prompt_parts.append("Previous Conversation:\n")
            for msg in conversation_history[-10:]:  # Use last 10 messages for context
                role = "User" if msg.get('role') == 'user' else "Assistant"
                content = msg.get('content', '')
                prompt_parts.append(f"{role}: {content}\n")
            prompt_parts.append("\n")

        # Add context based on query type
        context = context_data.get('context', {})
        data_type = context.get('data_type', 'general')

        if data_type == 'stock_price':
            stock_data = context.get('stock_data', {})
            prompt_parts.append(f"Stock Price Data for {stock_data.get('symbol')}:\n")
            prompt_parts.append(f"- Current Price: ${stock_data.get('current_price')}\n")
            prompt_parts.append(f"- Change: {stock_data.get('change')} ({stock_data.get('change_percent')}%)\n")
            prompt_parts.append(f"- Day Range: ${stock_data.get('day_low')} - ${stock_data.get('day_high')}\n")
            prompt_parts.append(f"- Volume: {stock_data.get('volume'):,}\n\n")

        elif data_type == 'technical_analysis':
            prompt_parts.append(f"Technical Analysis for {context.get('symbol')}:\n")
            prompt_parts.append(f"Current Price: ${context.get('current_price')}\n\n")

            indicators = context.get('indicators', {})
            if 'rsi' in indicators:
                rsi = indicators['rsi']
                prompt_parts.append(f"RSI: {rsi.get('value')} - {rsi.get('interpretation')}\n")

            if 'macd' in indicators:
                macd = indicators['macd']
                prompt_parts.append(f"MACD: {macd.get('interpretation')}\n")

            if 'trend_analysis' in indicators:
                trend = indicators['trend_analysis']
                prompt_parts.append(f"Trend: {trend.get('overall_trend')} - {trend.get('interpretation')}\n\n")

            signal_summary = context.get('signal_summary', {})
            if signal_summary:
                prompt_parts.append(f"Overall Signal: {signal_summary.get('summary')}\n\n")

        elif data_type == 'screener':
            prompt_parts.append(f"Stock Screener Results:\n")
            prompt_parts.append(f"Screen: {context.get('screen_name')}\n")
            prompt_parts.append(f"Description: {context.get('description')}\n")
            prompt_parts.append(f"Matches Found: {context.get('num_results')}\n")
            if 'top_stocks' in context:
                prompt_parts.append(f"Top Stocks: {', '.join(context.get('top_stocks', []))}\n\n")

        elif data_type == 'backtest':
            prompt_parts.append(f"Backtest Results:\n")
            prompt_parts.append(f"Strategy: {context.get('strategy')}\n")
            prompt_parts.append(f"Symbol: {context.get('symbol')}\n")
            metrics = context.get('metrics', {})
            prompt_parts.append(f"Total Return: {metrics.get('total_return_pct')}%\n")
            prompt_parts.append(f"Win Rate: {metrics.get('win_rate_pct')}%\n")
            prompt_parts.append(f"Number of Trades: {metrics.get('num_trades')}\n")
            prompt_parts.append(f"Max Drawdown: {metrics.get('max_drawdown_pct')}%\n")
            prompt_parts.append(f"Sharpe Ratio: {metrics.get('sharpe_ratio')}\n\n")

        elif data_type == 'document_query':
            if context.get('has_documents'):
                prompt_parts.append(f"Relevant Document Context:\n{context.get('document_context')}\n\n")
            else:
                prompt_parts.append("No documents have been uploaded yet.\n\n")

        # Add user query
        prompt_parts.append(f"User Question: {query}\n\n")
        prompt_parts.append("Please provide a clear, helpful response based on the data above. Remember to emphasize that this is information, not financial advice.")

        full_prompt = "".join(prompt_parts)

        # Call LLM
        return self.call_gemini(full_prompt, temperature=0.2)

    def process_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Main entry point - processes user query end-to-end with conversation context

        Args:
            query: User query string
            conversation_history: Previous messages in the conversation (optional)

        Returns:
            Complete response with data, charts, and AI explanation
        """
        try:
            # Classify query with conversation context
            category = self.classify_query(query, conversation_history)
            logger.info(f"Query classified as: {category}")

            # Route to appropriate handler
            if category == 'stock_price':
                symbols = self.extract_symbols(query)
                result = self.handle_stock_price_query(query, symbols)

            elif category == 'technical_analysis':
                symbols = self.extract_symbols(query)
                result = self.handle_technical_analysis_query(query, symbols)

            elif category == 'screener':
                result = self.handle_screener_query(query)

            elif category == 'backtest':
                result = self.handle_backtest_query(query)

            elif category == 'document_query':
                result = self.handle_document_query(query)

            elif category in ['news_analysis', 'finance_explanation', 'general']:
                # For these, we just use LLM without special data
                result = {
                    'category': category,
                    'context': {'data_type': category}
                }

            else:
                result = {
                    'category': 'unknown',
                    'error': 'Unable to process query'
                }

            # Check if handler changed category to 'general' (no symbols found)
            if result.get('category') == 'general' and category != 'general':
                logger.info(f"Handler converted {category} to general query (no symbols found)")

            # Generate AI response with conversation context
            # Always generate response for 'general' queries, even if they were converted from other categories
            if 'error' not in result or result.get('category') == 'general':
                ai_response = self.generate_response(query, result, conversation_history)
                result['ai_response'] = ai_response
            else:
                result['ai_response'] = f"I encountered an error: {result['error']}"

            result['query'] = query
            result['timestamp'] = datetime.now().isoformat()

            return result

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'query': query,
                'category': 'error',
                'error': str(e),
                'ai_response': "I'm sorry, I encountered an error processing your request."
            }


# Singleton instance
finance_orchestrator = FinanceOrchestrator()


# Helper function
def process_finance_query(query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Process a finance query through the orchestrator with conversation context

    Args:
        query: User query
        conversation_history: Previous messages in the conversation (optional)

    Returns:
        Complete response with data and AI explanation
    """
    return finance_orchestrator.process_query(query, conversation_history)
