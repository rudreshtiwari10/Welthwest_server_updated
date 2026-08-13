"""
LLM Router — picks the right model for each call.

Routing strategy:
  - Gemini Flash (fast, cheap) → default for most queries: single-intent
    Q&A, concept explanations, response synthesis, light tool-calling.
  - OpenRouter (powerful) → complex multi-step reasoning, multi-tool
    orchestration, comparisons across many stocks, calculations.
  - Fallback chain: if the preferred provider fails (rate-limit, key
    missing, 5xx), the other is tried automatically.

The router is transparent to the agent loop — it just calls router.chat()
and the best available model is used. The user never sees which model ran.
"""

import logging
import os
from typing import Optional

from agent.llm.base import LLMProvider, LLMResponse, Message, ToolCall

logger = logging.getLogger(__name__)

# Heuristic thresholds for routing.
_COMPLEX_TOOL_COUNT = 3     # If LLM wants >= 3 tools, escalate on next call.
_LONG_CONTEXT_TOKENS = 4000 # If conversation is long, prefer OpenRouter.


class LLMRouter(LLMProvider):
    """
    Routes LLM calls between a fast provider (Gemini) and a powerful
    provider (OpenRouter) based on query complexity.

    Also serves as a failover chain — if the preferred provider errors,
    the fallback is tried.
    """

    name = "router"

    def __init__(
        self,
        fast: Optional[LLMProvider] = None,
        powerful: Optional[LLMProvider] = None,
    ):
        self._fast = fast
        self._powerful = powerful

    def chat(
        self,
        messages: list[Message],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        prefer: str = "auto",
    ) -> LLMResponse:
        """
        Send a conversation to the best available model.

        prefer:
            "auto"     — heuristic routing (default)
            "fast"     — force Gemini
            "powerful" — force OpenRouter
        """
        primary, fallback = self._pick(messages, tools, prefer)

        # Try primary
        if primary is not None:
            try:
                return primary.chat(
                    messages, tools=tools, temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                logger.warning(
                    "LLM router: %s failed (%s), falling back",
                    primary.name, e,
                )

        # Try fallback
        if fallback is not None:
            try:
                return fallback.chat(
                    messages, tools=tools, temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                logger.error(
                    "LLM router: fallback %s also failed: %s",
                    fallback.name, e,
                )
                raise

        raise RuntimeError("No LLM providers available")

    def _pick(
        self,
        messages: list[Message],
        tools: Optional[list[dict]],
        prefer: str,
    ) -> tuple[Optional[LLMProvider], Optional[LLMProvider]]:
        """Return (primary, fallback) based on routing heuristic."""
        if prefer == "fast":
            return self._fast, self._powerful
        if prefer == "powerful":
            return self._powerful, self._fast

        # ---- Auto routing heuristic ----------------------------------------
        if self._should_use_powerful(messages, tools):
            return self._powerful, self._fast
        return self._fast, self._powerful

    def _should_use_powerful(
        self,
        messages: list[Message],
        tools: Optional[list[dict]],
    ) -> bool:
        """Heuristic: should we escalate to the powerful model?"""
        # If powerful isn't configured, always use fast.
        if self._powerful is None:
            return False
        # If fast isn't configured, always use powerful.
        if self._fast is None:
            return True

        # 1. Previous assistant turn used many tools → complex multi-step.
        #    (We check actual tool *calls* in history, not the number of
        #    tool *definitions* available — that's always 8.)
        for msg in reversed(messages):
            if msg.role == "assistant" and len(msg.tool_calls) >= _COMPLEX_TOOL_COUNT:
                return True
            if msg.role == "user":
                break

        # 2. Long conversation context → needs better context handling.
        total_chars = sum(len(m.content or "") for m in messages)
        if total_chars > _LONG_CONTEXT_TOKENS * 4:  # rough char→token ratio
            return True

        # 3. Previous turn had multiple tool calls → multi-step reasoning.
        for msg in reversed(messages):
            if msg.role == "assistant" and len(msg.tool_calls) >= 2:
                return True
            if msg.role in ("user", "system"):
                break

        # 4. Explicit complexity markers in the latest user message.
        latest_user = ""
        for msg in reversed(messages):
            if msg.role == "user":
                latest_user = (msg.content or "").lower()
                break

        complex_markers = [
            "compare", "versus", "vs", "difference between",
            "calculate", "compute", "analyze all", "deep dive",
            "portfolio", "multiple", "each of", "all of",
        ]
        if any(marker in latest_user for marker in complex_markers):
            return True

        return False

    def health_check(self) -> bool:
        fast_ok = self._fast.health_check() if self._fast else False
        powerful_ok = self._powerful.health_check() if self._powerful else False
        return fast_ok or powerful_ok


def get_llm_router() -> LLMRouter:
    """
    Build the default LLM router from environment variables.

    Gracefully handles missing API keys — if only one provider is configured,
    all calls go to that provider. If neither is configured, chat() will raise.
    """
    fast = None
    powerful = None

    if os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY"):
        from agent.llm.providers.gemini import GeminiProvider
        fast = GeminiProvider()

    if os.environ.get("OPENROUTER_API_KEY"):
        from agent.llm.providers.openrouter import OpenRouterProvider
        powerful = OpenRouterProvider()

    # If only one is available, use it for both roles.
    if fast is None and powerful is not None:
        fast = powerful
    elif powerful is None and fast is not None:
        powerful = fast

    return LLMRouter(fast=fast, powerful=powerful)
