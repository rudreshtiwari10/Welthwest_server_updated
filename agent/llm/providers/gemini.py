"""
Google Gemini LLM provider.

Mirrors the existing REST call pattern from finance_orchestrator.py:502 but
adds support for:
  - Conversation history (multi-turn)
  - Tool/function calling (Gemini native)
  - Structured LLMResponse output

Key/model rotation goes through services.gemini_client.GeminiRotator (shared
across every Gemini consumer in this app) rather than a single hardcoded
key/model — see that module for GEMINI_API_KEYS config.
"""

import logging
import uuid
from typing import Any, Optional

from agent.llm.base import LLMProvider, LLMResponse, Message, ToolCall
from services.gemini_client import GeminiRotator, GeminiExhaustedError

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """LLM provider backed by Google Gemini REST API."""

    name = "gemini"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        # Explicit model/key overrides still respected (e.g. tests), but by
        # default this rotates across the full shared key/model pool.
        models = [model] if model else None
        keys = [api_key] if api_key else None
        self._rotator = GeminiRotator(models=models, keys=keys)

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
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

        # ---- Fire request (rotates across key/model pool on failure) ------
        try:
            data = self._rotator.post(payload)
        except GeminiExhaustedError as e:
            logger.error("Gemini API exhausted across all keys/models: %s", e)
            raise RuntimeError("LLM request failed") from e

        model_used = self._rotator.models[0] if len(self._rotator.models) == 1 else "gemini"
        return _parse_response(data, model_used)


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
