"""
OpenRouter LLM provider.

Mirrors the existing REST call pattern from ai_service.py:195 but adds:
  - Conversation history (multi-turn)
  - Tool/function calling (OpenAI-compatible)
  - Structured LLMResponse output
  - Configurable model selection

OpenRouter is preferred for complex multi-step reasoning and calculations
because it routes to powerful models (Claude, GPT-4o, Llama 3, etc.)
while Gemini handles fast general responses.
"""

import json
import logging
import os
import uuid
from typing import Any, Optional

import requests

from agent.llm.base import LLMProvider, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)

# Default to a capable model for complex reasoning.
# User can override via OPENROUTER_MODEL env var.
_DEFAULT_MODEL = "anthropic/claude-sonnet-4"


class OpenRouterProvider(LLMProvider):
    """LLM provider backed by OpenRouter (OpenAI-compatible API)."""

    name = "openrouter"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self._model = model or os.environ.get("OPENROUTER_MODEL", _DEFAULT_MODEL)
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._referer = os.environ.get("FRONTEND_URL", "https://welthwest.com")

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if not self._api_key:
            raise RuntimeError("OpenRouter API key not configured")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": self._referer,
        }

        # ---- Build OpenAI-format messages -----------------------------------
        oai_messages = _build_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # ---- Add tools if provided (OpenAI function-calling format) ---------
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in tools
            ]

        # ---- Fire request ---------------------------------------------------
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            body = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    body = e.response.text[:500]
                except Exception:
                    pass
            logger.error("OpenRouter API request failed: %s | body: %s", e, body)
            raise RuntimeError("LLM request failed") from e

        return _parse_response(data, self._model)


# ---- OpenAI format helpers --------------------------------------------------


def _build_messages(messages: list[Message]) -> list[dict]:
    """Convert our Message list to OpenAI chat-completions format."""
    out: list[dict] = []
    for msg in messages:
        entry: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}

        # Tool response
        if msg.role == "tool":
            entry["tool_call_id"] = msg.tool_call_id or ""
            entry["name"] = msg.name or ""

        # Assistant message with tool calls
        if msg.role == "assistant" and msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]

        out.append(entry)
    return out


def _parse_response(data: dict, model: str) -> LLMResponse:
    """Parse OpenAI-compatible response into LLMResponse."""
    choices = data.get("choices", [])
    if not choices:
        return LLMResponse(content="Unable to generate response.", model=model)

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""
    finish_reason = choice.get("finish_reason", "stop") or "stop"

    # Parse tool calls
    tool_calls: list[ToolCall] = []
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            ToolCall(
                id=tc.get("id", str(uuid.uuid4())[:8]),
                name=fn.get("name", ""),
                arguments=args,
            )
        )

    # Token counts
    usage = data.get("usage", {})
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)

    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=model,
        raw=data,
    )
