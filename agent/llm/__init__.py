"""
LLM provider abstraction — supports multiple models with automatic routing.

Usage:
    from agent.llm import get_llm_router
    router = get_llm_router()
    response = router.chat(messages, tools=tools)  # picks best model
"""

from agent.llm.base import LLMProvider, LLMResponse, Message, ToolCall
from agent.llm.router import LLMRouter, get_llm_router

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "Message",
    "ToolCall",
    "LLMRouter",
    "get_llm_router",
]
