"""
Google Gemini LLM provider.

Mirrors the existing REST call pattern from finance_orchestrator.py:502 but
adds support for:
  - Conversation history (multi-turn)
  - Tool/function calling (Gemini native)
  - Structured LLMResponse output

Uses gemini-2.5-flash by default (fast, cheap, good for general responses).
"""

import json
import logging
import os
import uuid
from typing import Any, Optional

import requests

from agent.llm.base import LLMProvider, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiProvider(LLMProvider):
    """LLM provider backed by Google Gemini REST API."""

    name = "gemini"

    def __init__(self, model: str = _DEFAULT_MODEL, api_key: Optional[str] = None):
        self._model = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if not self._api_key:
            raise RuntimeError("Gemini API key not configured")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )

        # ---- Build contents array (Gemini format) --------------------------
        contents = _build_contents(messages)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": max_tokens,
            },
        }

        # ---- Add tool declarations if provided ----------------------------
        if tools:
            payload["tools"] = [{"functionDeclarations": tools}]

        # ---- System instruction (Gemini supports it as a top-level field) --
        system_parts = [m.content for m in messages if m.role == "system" and m.content]
        if system_parts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }

        # ---- Fire request ---------------------------------------------------
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            body = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    body = e.response.text[:500]
                except Exception:
                    pass
            logger.error("Gemini API request failed: %s | body: %s", e, body)
            raise RuntimeError("LLM request failed") from e

        return _parse_response(data, self._model)


# ---- Gemini format helpers --------------------------------------------------


def _build_contents(messages: list[Message]) -> list[dict]:
    """Convert our Message list to Gemini 'contents' format."""
    contents: list[dict] = []
    for msg in messages:
        if msg.role == "system":
            # Handled via systemInstruction, skip in contents.
            continue

        role = "user" if msg.role == "user" else "model"

        # Tool response messages
        if msg.role == "tool" and msg.tool_call_id and msg.name:
            contents.append({
                "role": "model",
                "parts": [{
                    "functionResponse": {
                        "name": msg.name,
                        "response": {"result": msg.content},
                    }
                }],
            })
            continue

        parts: list[dict] = []
        if msg.content:
            parts.append({"text": msg.content})

        # If the assistant message had tool calls, render them.
        for tc in msg.tool_calls:
            parts.append({
                "functionCall": {
                    "name": tc.name,
                    "args": tc.arguments,
                }
            })

        if parts:
            contents.append({"role": role, "parts": parts})

    return contents


def _parse_response(data: dict, model: str) -> LLMResponse:
    """Parse Gemini generateContent response into LLMResponse."""
    candidates = data.get("candidates", [])
    if not candidates:
        return LLMResponse(content="Unable to generate response.", model=model)

    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for part in parts:
        if "text" in part:
            text_parts.append(part["text"])
        elif "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append(
                ToolCall(
                    id=str(uuid.uuid4())[:8],
                    name=fc.get("name", ""),
                    arguments=fc.get("args", {}),
                )
            )

    # Token counts (Gemini returns these in usageMetadata)
    usage = data.get("usageMetadata", {})
    tokens_in = usage.get("promptTokenCount", 0)
    tokens_out = usage.get("candidatesTokenCount", 0)

    finish_reason = candidates[0].get("finishReason", "STOP").lower()

    return LLMResponse(
        content="\n".join(text_parts),
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=model,
        raw=data,
    )
