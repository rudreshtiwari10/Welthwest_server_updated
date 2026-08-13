"""
Text-completion helper: Gemini (full key x model rotation) first, then
OpenRouter as the final fallback once every Gemini key/model is exhausted.

Config via .env:
  GEMINI_API_KEYS / GEMINI_API_KEY  — see services/gemini_client.py
  OPENROUTER_API_KEY                — required for the final fallback to work
  OPENROUTER_MODEL                  — optional, defaults to anthropic/claude-sonnet-4

Use this instead of calling GeminiRotator directly whenever a plain-text
completion (single prompt in, single string out) with a real fallback is
what's needed. Callers that need conversation history / tool-calling should
keep using agent.llm.router.LLMRouter, which already has the same Gemini ->
OpenRouter failover built in at the provider level.
"""

import logging

from services.gemini_client import GeminiRotator, GeminiExhaustedError

logger = logging.getLogger(__name__)


def generate_text(
    prompt: str,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    gemini_models: list = None,
) -> str:
    """Try Gemini across every configured key/model; if all are exhausted,
    fall back to OpenRouter. Raises only if both are unavailable/fail."""
    gemini = GeminiRotator(models=gemini_models)
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        data = gemini.post(payload)
        return data['candidates'][0]['content']['parts'][0]['text']
    except GeminiExhaustedError as e:
        logger.warning(f"[llm_fallback] Gemini exhausted, falling back to OpenRouter: {e}")
    except Exception as e:
        logger.warning(f"[llm_fallback] Gemini call failed unexpectedly, falling back to OpenRouter: {e}")

    from agent.llm.providers.openrouter import OpenRouterProvider
    from agent.llm.base import Message

    openrouter = OpenRouterProvider()
    if not openrouter._api_key:
        raise GeminiExhaustedError(
            "Gemini exhausted and OPENROUTER_API_KEY not configured — no fallback available"
        )

    response = openrouter.chat(
        [Message(role="user", content=prompt)],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    logger.info("[llm_fallback] ✓ OpenRouter fallback responded OK")
    return response.content
