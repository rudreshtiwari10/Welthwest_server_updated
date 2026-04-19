"""
Abstract base for LLM providers and shared data contracts.

Every provider (Gemini, OpenRouter, OpenAI, Claude) implements LLMProvider.
The agent loop depends on this interface, never on a specific provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Message:
    """A single message in a conversation."""
    role: str          # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # for role="tool" responses
    name: Optional[str] = None          # tool name for role="tool"


@dataclass
class ToolCall:
    """An LLM-requested tool invocation."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""              # internal only — never exposed to user
    raw: Optional[dict] = None   # raw provider response for debugging


class LLMProvider(ABC):
    """
    Abstract LLM provider. Each provider implements chat() which takes
    a list of messages + optional tool definitions and returns an LLMResponse.
    """

    name: str = "abstract"

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Send a conversation to the model.

        Args:
            messages: Conversation history (system + user + assistant + tool).
            tools: JSON-schema tool definitions for function-calling.
                   If None, model responds with text only.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.

        Returns:
            LLMResponse with either content (text) or tool_calls (function calls),
            or both.
        """
        raise NotImplementedError

    def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        try:
            resp = self.chat(
                [Message(role="user", content="ping")],
                max_tokens=5,
            )
            return bool(resp.content or resp.tool_calls)
        except Exception:
            return False
