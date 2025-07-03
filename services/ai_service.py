import os
import json
import requests
from typing import Dict, Any, Optional
import logging
from services.stock_service import get_live_data, format_indian_ticker, validate_ticker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIModelService:
    """Service for handling interactions with various AI models"""
    
    def __init__(self):
        # Load API keys from environment variables
        self.openai_api_key = os.environ.get('OPENAI_API_KEY', '')
        self.openrouter_api_key = os.environ.get('OPENROUTER_API_KEY', '')
        self.claude_api_key = os.environ.get('CLAUDE_API_KEY', '')
        
        # Default system prompt for financial context
        self.default_system_prompt = """
        You are a helpful AI assistant for a financial platform called WelthWest. 
        Your primary role is to provide accurate information and insights about stocks, 
        market trends, investment strategies, and financial concepts.
        
        When discussing stocks:
        - Provide balanced perspectives on potential investments
        - Explain market concepts clearly without jargon
        - Never make specific buy/sell recommendations
        - Always remind users that all investments carry risk
        - Clarify that you're providing information, not financial advice
        
        If asked about specific stocks, provide general information about the company, 
        its sector, and recent market performance if available.
        """
    
    def extract_stock_symbols(self, query: str) -> list:
        """
        Extract potential stock symbols from the query
        This is a simple implementation - in production, you'd want a more robust approach
        """
        # Common Indian stock symbols to look for
        common_symbols = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
            'SBIN', 'HINDUNILVR', 'BHARTIARTL', 'ITC', 'KOTAKBANK',
            'NIFTY', 'SENSEX', 'BANKNIFTY'
        ]
        
        # Convert query to uppercase for case-insensitive matching
        upper_query = query.upper()
        
        # Check for common symbols in the query
        found_symbols = []
        for symbol in common_symbols:
            if symbol in upper_query.split():
                # For indices, handle special formatting
                if symbol == 'NIFTY':
                    found_symbols.append('^NSEI')
                elif symbol == 'SENSEX':
                    found_symbols.append('^BSESN')
                elif symbol == 'BANKNIFTY':
                    found_symbols.append('^NSEBANK')
                else:
                    # For regular stocks, add .NS suffix for NSE
                    found_symbols.append(f"{symbol}.NS")
        
        return found_symbols
    
    def get_stock_data_for_query(self, query: str) -> Dict[str, Any]:
        """
        Extract stock symbols from query and fetch their data
        """
        symbols = self.extract_stock_symbols(query)
        stock_data = {}
        
        if symbols:
            try:
                # Get live data for the symbols
                live_data = get_live_data(symbols)
                
                # Process the data into a more usable format
                for symbol in symbols:
                    if symbol in live_data.index:
                        data = live_data.loc[symbol]
                        stock_data[symbol] = {
                            'current_price': data.get('price'),
                            'change': {
                                'value': data.get('previousClose', 0) - data.get('price', 0),
                                'percent': ((data.get('price', 0) / data.get('previousClose', 0)) - 1) * 100 if data.get('previousClose', 0) else 0
                            },
                            'volume': data.get('volume'),
                            'market_cap': data.get('marketCap'),
                            'day_range': {
                                'low': data.get('dayLow'),
                                'high': data.get('dayHigh')
                            }
                        }
            except Exception as e:
                logger.error(f"Error fetching stock data: {str(e)}")
        
        return stock_data
    
    def chat_with_llama(self, query: str) -> Dict[str, Any]:
        """
        Simulate a response from a local Llama model
        In production, you would connect to an actual Llama model API or local instance
        """
        # This is a mock implementation
        response = {
            "analysis": f"Based on your query about {query}, I can provide some general information. "
                       f"This is a simulated response as if from a Llama model. "
                       f"In a real implementation, this would connect to an actual Llama model API or local instance. "
                       f"For specific financial advice, please consult with a financial advisor.",
            "model": "llama-simulated"
        }
        
        return response
    
    def chat_with_openai(self, query: str) -> Dict[str, Any]:
        """
        Send query to OpenAI API and get response
        """
        if not self.openai_api_key:
            return {"analysis": "OpenAI API key not configured. Please contact support.", "model": "openai-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": "gpt-3.5-turbo"
                }
            else:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from OpenAI. Status code: {response.status_code}", "model": "openai-error"}
                
        except Exception as e:
            logger.error(f"Exception in OpenAI chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "openai-error"}
    
    def chat_with_openrouter(self, query: str) -> Dict[str, Any]:
        """
        Send query to OpenRouter API and get response
        """
        if not self.openrouter_api_key:
            return {"analysis": "OpenRouter API key not configured. Please contact support.", "model": "openrouter-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "HTTP-Referer": "https://welthwest.com"  # Replace with your actual domain
            }
            
            payload = {
                "model": "anthropic/claude-3-opus",  # You can change this to any model supported by OpenRouter
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                used_model = result.get("model", "unknown")
                return {
                    "analysis": result["choices"][0]["message"]["content"],
                    "model": used_model
                }
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from OpenRouter. Status code: {response.status_code}", "model": "openrouter-error"}
                
        except Exception as e:
            logger.error(f"Exception in OpenRouter chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "openrouter-error"}
    
    def chat_with_claude(self, query: str) -> Dict[str, Any]:
        """
        Send query to Anthropic's Claude API and get response
        """
        if not self.claude_api_key:
            return {"analysis": "Claude API key not configured. Please contact support.", "model": "claude-error"}
        
        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.claude_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": "claude-3-opus-20240229",
                "messages": [
                    {"role": "system", "content": self.default_system_prompt},
                    {"role": "user", "content": query}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "analysis": result["content"][0]["text"],
                    "model": "claude-3-opus"
                }
            else:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return {"analysis": f"Error: Unable to get response from Claude. Status code: {response.status_code}", "model": "claude-error"}
                
        except Exception as e:
            logger.error(f"Exception in Claude chat: {str(e)}")
            return {"analysis": f"Error: {str(e)}", "model": "claude-error"}
    
    def process_chat_query(self, query: str, model: str = "llama", user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a chat query using the specified model
        """
        # Get any relevant stock data
        stock_data = self.get_stock_data_for_query(query)
        
        # Select the appropriate model handler
        if model == "openai":
            response = self.chat_with_openai(query)
        elif model == "openrouter":
            response = self.chat_with_openrouter(query)
        elif model == "claude":
            response = self.chat_with_claude(query)
        else:
            # Default to llama
            response = self.chat_with_llama(query)
        
        # Add stock data to the response
        response["stock_data"] = stock_data
        
        # In a production system, you might want to log this interaction
        if user_id:
            # Log the interaction for the user
            logger.info(f"Chat query from user {user_id}: {query}")
        
        return response 