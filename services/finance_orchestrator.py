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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FinanceOrchestrator:
    """
    Advanced orchestrator for finance AI queries
    """

    # Merged common words blacklist — used by both classify_query and extract_symbols
    # to avoid false-positive symbol matches on English words
    COMMON_WORDS = {
        # Pronouns, articles, prepositions, conjunctions
        'HOW', 'ARE', 'YOU', 'THE', 'AND', 'FOR', 'CAN', 'WHAT', 'WHY',
        'WHO', 'WHEN', 'WHERE', 'WHICH', 'WILL', 'WOULD', 'SHOULD', 'COULD',
        'THIS', 'THAT', 'THESE', 'THOSE', 'HAVE', 'HAS', 'HAD', 'WAS', 'WERE',
        'BEEN', 'BEING', 'DOES', 'DID', 'DOING', 'ME', 'OF', 'IN', 'ON',
        'AT', 'TO', 'NS', 'BO', 'IS', 'IT', 'BY', 'MY', 'DO', 'BE',
        'AN', 'AS', 'UP', 'IF', 'OR', 'SO', 'NO', 'VS',
        # Verbs / adjectives common in finance queries
        'SHOW', 'TELL', 'GIVE', 'GET', 'INVEST', 'GOOD', 'BAD', 'BEST',
        'HIGH', 'LOW', 'BUY', 'SELL',
        # Finance / domain terms that aren't tickers
        'STOCK', 'SHARE', 'PRICE', 'CHART', 'DATA', 'LAST', 'DAYS',
        'WEEK', 'YEAR', 'MONTH', 'NEWS', 'HELP', 'ABOUT', 'WITH',
        'ANALYSE', 'ANALYZE', 'ANALYSIS', 'TECHNICAL',
    }

    def __init__(self):
        # LLM calls go through services/llm_fallback.py (Gemini rotation -> OpenRouter fallback)
        # System prompts
        self.finance_system_prompt = """You are Welth, the in-house research assistant built by the WelthWest team — a platform specialising in Indian stock markets.

Your role:
- Provide accurate, data-driven financial analysis for Indian and global markets
- Explain technical indicators and market concepts clearly
- Help users understand stock performance and trends
- ALWAYS use ₹ (Indian Rupees symbol) for Indian market prices, NEVER use $ or USD for Indian stocks
- NEVER give specific buy/sell recommendations
- Always remind users that past performance doesn't guarantee future results
- Emphasize that you provide information, not financial advice

When analyzing data:
- Be objective and balanced
- Cite the specific indicators and metrics
- Explain what the data suggests, not what users should do
- Use professional but accessible language

Response formatting (CRITICAL — your output renders in a markdown surface, NOT plain text):
NEVER reply with one long prose paragraph for analytical answers. Always use real markdown structure.

For ANY substantive finance / stock / market question, structure the answer as:
1. Start with `## TL;DR` followed by ONE sentence summarising the bottom line.
2. Break the body into `## ` sections. Pick from: Snapshot, Price Action, Technicals, Fundamentals, News & Sentiment, Risks, Outlook, Comparison, Key Levels. Use only the sections that apply — typically 3 to 5.
3. Inside each section use bullet lists (`- `) — short, scannable lines. Never put 3+ findings into one paragraph.
4. When comparing values (across periods, stocks, scenarios, or metrics) ALWAYS use a markdown table with `|` separators and a header row. Never describe a comparison in prose.
5. Use `### ` sub-headings inside a section when listing distinct sub-topics (e.g., `### Support`, `### Resistance`).
6. Use `**bold**` for tickers, named levels, signal verdicts (e.g., **RELIANCE**, **Support: ₹2,800**, **Bullish**).
7. Use `` `inline code` `` for ticker symbols and short technical tokens (e.g., `RSI(14)`, `RELIANCE.NS`).
8. Use `---` between major logical blocks (e.g., between analysis and caveats).
9. End every analytical answer with a `### Caveats` section — 1 to 2 short bullets max (data freshness, not advice, etc.).

Number formatting:
- Indian rupee amounts: `₹` then thousands-separated value, e.g., `₹2,847.50`, `₹18,420 Cr`. NEVER `$` for Indian stocks.
- Percentages and deltas: ALWAYS include the sign (`+2.31%`, `-1.04%`, `+₹35.20`). The sign drives green/red colouring on the client — a missing sign means it renders neutral grey, which is wrong for a delta.
- Keep numeric figures concise (2 decimals max). Round large absolute volumes (e.g., `1.2M`, `4.5 Cr`).

Length & density:
- Prefer 5 short bullets over 1 dense paragraph. Aim for roughly 150 to 350 words for a single-stock query.
- Every bullet should lead with the data point, then a brief interpretation in the same line.

Exceptions (DO NOT impose this structure on these — stay conversational):
- Greetings and small talk.
- Off-topic redirects.
- Definitional one-liner questions ("What is RSI?") — a short paragraph + 2-3 bullets is fine, no TL;DR needed.
- Error / unavailability replies.

Handling off-topic or non-finance questions:
- If a user asks something unrelated to finance, markets, investing, or economics, respond warmly and briefly explain that you are a finance-focused assistant
- Do NOT say you "encountered an error" for off-topic questions — just redirect them politely
- Suggest what finance-related things you CAN help them with
- Keep the tone conversational, helpful, and professional — never robotic or dismissive

Handling data errors:
- If stock data is unavailable, apologise briefly, suggest the user double-check the ticker symbol, and offer to help with something else
- Never expose raw technical error messages to the user"""

    def _get_yf_ticker(self, symbol: str):
        """Lazily import yfinance and return a Ticker object"""
        import yfinance as yf
        # Disable SQLite timezone cache — prevents "database or disk is full" on EC2
        try:
            yf.set_tz_cache_location('/tmp/yfinance_tz_cache')
        except Exception:
            pass
        return yf.Ticker(symbol)

    def detect_analysis_intent(self, query: str) -> dict:
        """
        Detect if query contains analysis-related keywords and return suggested tools.
        Returns a dict with 'show_buttons' (bool) and 'suggested_tools' (list).

        NOTE: Feature promotion will be rebuilt as a dynamic, YAML-driven system
        in a future phase. For now, returns empty to avoid promoting dead routes.
        """
        return {'show_buttons': False, 'suggested_tools': []}

    def classify_query(self, query: str, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Classify user query into a category with conversation context

        Categories:
        - stock_price: "What is the price of RELIANCE?"
        - technical_analysis: "Show me RSI for TCS", "Analyze INFY chart"
        - screener: "Find oversold stocks", "Screen for momentum stocks"
        - backtest: "Test SMA crossover on AAPL", "Backtest RSI strategy"
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
        potential_symbols = [s for s in re.findall(r'\b[A-Z]{2,5}\b', query.upper()) if s not in self.COMMON_WORDS]
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
        Extract stock symbols from query.
        Uses a dynamic NSE symbol map (2000+ stocks fetched from NSE's public
        equity list and cached) so any listed Indian stock is recognised.
        Falls back to defaulting to .NS suffix for unknown tokens.
        """
        from services.nse_symbols import get_nse_symbol_map

        symbols = []
        query_upper = query.upper()
        nse_map = get_nse_symbol_map()  # {SYMBOL/NAME → 'SYMBOL.NS'}, 2000+ entries

        # Known US tickers — kept as bare symbols (no .NS suffix)
        known_us_tickers = {
            'AAPL', 'TSLA', 'GOOGL', 'GOOG', 'MSFT', 'AMZN', 'META', 'NVDA',
            'NFLX', 'UBER', 'LYFT', 'AMD', 'INTC', 'CRM', 'ORCL', 'IBM',
            'QCOM', 'AVGO', 'JPM', 'BAC', 'GS', 'MS', 'WFC', 'V', 'MA',
            'PYPL', 'SQ', 'WMT', 'TGT', 'COST', 'HD', 'NKE', 'SBUX', 'MCD',
            'KO', 'PEP', 'JNJ', 'DIS', 'SPOT', 'ABNB', 'BABA', 'PDD', 'NIO',
            'XOM', 'CVX', 'PFE', 'MRNA', 'ABBV', 'LLY', 'SPY', 'QQQ', 'GLD',
        }

        # Step 1: explicit .NS / .BO suffixes in the query
        ns_symbols = re.findall(r'\b([A-Z&-]+\.(?:NS|BO))\b', query_upper)
        symbols.extend(ns_symbols)

        # Step 2: match known company names / NSE symbols via the dynamic map
        # Check multi-word company names first (longer matches take priority)
        for name, ticker in sorted(nse_map.items(), key=lambda x: -len(x[0])):
            if name in query_upper and ticker not in symbols:
                symbols.append(ticker)
                # Stop after first good match to avoid symbol explosion
                if len(symbols) >= 3:
                    break

        # Step 3: if still nothing, tokenise the uppercased query and resolve each token
        if not symbols:
            potential_symbols = re.findall(r'\b([A-Z]{2,12})\b', query_upper)

            for sym in potential_symbols:
                if sym in self.COMMON_WORDS or sym in symbols:
                    continue
                if sym in nse_map:
                    symbols.append(nse_map[sym])
                elif sym in known_us_tickers:
                    symbols.append(sym)
                else:
                    # Indian-market platform: default unrecognised tokens to .NS
                    symbols.append(f"{sym}.NS")

        return list(dict.fromkeys(symbols))  # deduplicate, preserve order

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
            ticker = self._get_yf_ticker(symbol)
            hist = ticker.history(period='5d')

            # If no data and symbol lacks exchange suffix, retry with .NS then .BO
            if hist.empty and not symbol.endswith('.NS') and not symbol.endswith('.BO'):
                logger.info(f"No data for {symbol}, retrying as {symbol}.NS")
                symbol = f"{symbol}.NS"
                ticker = self._get_yf_ticker(symbol)
                hist = ticker.history(period='5d')
            if hist.empty and symbol.endswith('.NS'):
                base = symbol[:-3]
                logger.info(f"No data for {symbol}, retrying as {base}.BO")
                symbol = f"{base}.BO"
                ticker = self._get_yf_ticker(symbol)
                hist = ticker.history(period='5d')

            if hist.empty:
                return {
                    'category': 'stock_price',
                    'error': f'No data available for {symbol}. Please verify the NSE/BSE ticker symbol.'
                }

            info = ticker.info

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
            from services.indicators_service import get_indicators, get_signal_summary
            indicators = get_indicators(symbol, period='6mo')

            if 'error' in indicators:
                return {
                    'category': 'technical_analysis',
                    'error': indicators['error']
                }

            # Generate comprehensive chart
            from services.chart_service import generate_chart
            chart_base64 = generate_chart(
                indicators['raw_data'],
                chart_type='comprehensive',
                symbol=symbol
            )

            # Get signal summary
            from services.indicators_service import get_signal_summary
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
            from services.screener_service import screen_stocks, run_screen, get_available_screens
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

            from services.simple_backtest_service import run_backtest
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
            from services.chart_service import chart_service
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

    def call_gemini(self, prompt: str, temperature: float = 0.2) -> str:
        """
        Call Google Gemini API (rotates across all configured keys/models),
        falling back to OpenRouter as a last resort if every one is exhausted.
        Live chat response, not published content — a different model
        answering is an acceptable trade for not hard-failing the user.

        Args:
            prompt: Full prompt including system message and context
            temperature: Temperature for response generation

        Returns:
            LLM response text
        """
        try:
            from services.llm_fallback import generate_text
            return generate_text(prompt, max_tokens=2048, temperature=temperature)
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return "I'm sorry, I'm having trouble processing your request right now. Please try again in a moment."

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
            prompt_parts.append(f"- Current Price: ₹{stock_data.get('current_price')}\n")
            prompt_parts.append(f"- Change: {stock_data.get('change')} ({stock_data.get('change_percent')}%)\n")
            prompt_parts.append(f"- Day Range: ₹{stock_data.get('day_low')} - ₹{stock_data.get('day_high')}\n")
            prompt_parts.append(f"- Volume: {stock_data.get('volume'):,}\n\n")

        elif data_type == 'technical_analysis':
            prompt_parts.append(f"Technical Analysis for {context.get('symbol')}:\n")
            prompt_parts.append(f"Current Price: ₹{context.get('current_price')}\n\n")

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

        elif data_type == 'error':
            error_detail = context.get('error_detail', '')
            original_category = context.get('original_category', '')
            # Give LLM enough context to respond gracefully without exposing internals
            if 'No data available' in error_detail or 'verify the NSE' in error_detail:
                prompt_parts.append(
                    "SITUATION: The system tried to look up stock market data but could not find "
                    "data for the requested ticker symbol. This could mean:\n"
                    "- The symbol is misspelled or not listed on NSE/BSE\n"
                    "- The query may not have been about a specific stock\n"
                    "- The question may be unrelated to finance entirely\n\n"
                    "INSTRUCTION: Respond warmly. If the question looks non-financial (e.g. sports, "
                    "history, general knowledge), politely explain you are a finance assistant and "
                    "redirect. If it looks like a stock query, ask the user to confirm the correct "
                    "NSE ticker symbol. Do NOT mention error codes or technical details.\n\n"
                )
            else:
                prompt_parts.append(
                    "SITUATION: A technical issue occurred while fetching data. "
                    "Apologise briefly and suggest the user try again or rephrase. "
                    "Do not expose technical error details.\n\n"
                )

        # Add user query
        prompt_parts.append(f"User Question: {query}\n\n")
        prompt_parts.append("Please provide a clear, helpful response based on the data above. Remember to emphasize that this is information, not financial advice.")

        full_prompt = "".join(prompt_parts)

        # Call LLM
        response = self.call_gemini(full_prompt, temperature=0.2)

        return response

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
            # Detect analysis intent for all queries
            analysis_intent = self.detect_analysis_intent(query)

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

            # Always generate a proper AI response — even on data errors.
            # Pass error context so the LLM responds helpfully instead of
            # exposing raw technical messages to the user.
            if 'error' in result:
                result['context'] = {
                    'data_type': 'error',
                    'error_detail': result['error'],
                    'original_category': result.get('category', 'unknown'),
                }
            ai_response = self.generate_response(query, result, conversation_history)
            result['ai_response'] = ai_response

            result['query'] = query
            result['timestamp'] = datetime.now().isoformat()
            result['analysis_buttons'] = analysis_intent

            return result

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'query': query,
                'category': 'error',
                'ai_response': (
                    "I'm sorry, something went wrong on my end while processing your request. "
                    "Could you try rephrasing your question? If you were asking about a specific "
                    "stock or market topic, feel free to ask again — I'm here to help with all "
                    "things related to Indian and global markets."
                )
            }


# Lazy singleton instance
_finance_orchestrator = None

def _get_finance_orchestrator():
    global _finance_orchestrator
    if _finance_orchestrator is None:
        _finance_orchestrator = FinanceOrchestrator()
    return _finance_orchestrator


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
    return _get_finance_orchestrator().process_query(query, conversation_history)
