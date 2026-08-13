"""
Shared Gemini API key + model rotation pool.

Every Gemini consumer in this app should go through this instead of calling
requests.post directly with one hardcoded key/model — previously a single
leaked/quota-exhausted GEMINI_API_KEY took down every AI feature at once
(news pipeline, welthAI assistant, finance orchestrator, image generation),
since they all read the same env var independently.

Config via .env:
  GEMINI_API_KEYS=key1,key2,...   # preferred — comma-separated pool of keys
  GEMINI_API_KEY=...              # fallback if GEMINI_API_KEYS not set (single key)

Rotation order: for the current key, try each model in `models`; once every
model on that key is in cooldown, move to the next key and repeat. Only
raises once every model on every key is in cooldown.
"""

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

# Models confirmed live on the free tier as of Aug 2026 — keep this the
# single source of truth; don't respecify model lists ad hoc per caller.
DEFAULT_MODELS = ['gemini-2.5-flash', 'gemini-2.5-flash-lite']

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def load_gemini_keys() -> list:
    """GEMINI_API_KEYS (comma-separated) takes priority; falls back to single GEMINI_API_KEY."""
    multi = os.getenv('GEMINI_API_KEYS', '')
    keys = [k.strip() for k in multi.split(',') if k.strip()]
    if keys:
        return keys
    single = os.getenv('GEMINI_API_KEY', '').strip()
    return [single] if single else []


class GeminiExhaustedError(Exception):
    """Raised when every (key, model) slot is in cooldown / failing."""


class GeminiRotator:
    """Rotates across (API key, model) slots on failure.

    Each instance keeps its own cooldown state (not shared across processes —
    gunicorn's workers/master don't share memory), but every caller failing
    over the same pool of keys/models keeps each Gemini feature resilient to
    any single key or model being dead, instead of hard-failing immediately.
    """

    def __init__(self, models: list = None, keys: list = None):
        self.models = list(models) if models else list(DEFAULT_MODELS)
        self.keys = list(keys) if keys is not None else load_gemini_keys()
        self._cooldowns = {}  # (key_index, model) -> epoch time when retryable
        self._current_slot_idx = 0

    def _all_slots(self) -> list:
        return [
            (key_idx, model)
            for key_idx in range(len(self.keys))
            for model in self.models
        ]

    def _get_available_slot(self):
        """Next slot not in cooldown, or the soonest-to-recover one if all are
        in cooldown. Never blocks — several Gemini callers in this app run
        inside live request threads (assistant chat, finance orchestrator),
        and a long time.sleep() here would hang a user's HTTP request and tie
        up a gunicorn worker. Callers get a fast failure instead and decide
        their own fallback."""
        slots = self._all_slots()
        now = time.time()
        for _ in range(len(slots)):
            slot = slots[self._current_slot_idx % len(slots)]
            if now >= self._cooldowns.get(slot, 0):
                return slot
            self._current_slot_idx = (self._current_slot_idx + 1) % len(slots)
        return min(self._cooldowns, key=self._cooldowns.get)

    def _mark_exhausted(self, slot: tuple):
        key_idx, model = slot
        slots = self._all_slots()
        self._cooldowns[slot] = time.time() + 900  # 15 min cooldown
        self._current_slot_idx = (slots.index(slot) + 1) % len(slots)
        next_slot = slots[self._current_slot_idx]
        logger.warning(
            f"[gemini_client] key#{key_idx} {model} exhausted, cooldown 15min. "
            f"Rotating to key#{next_slot[0]} {next_slot[1]}"
        )

    def post(self, payload: dict, action: str = 'generateContent', timeout: int = 60, disable_thinking: bool = True) -> dict:
        """POST payload to Gemini, rotating across (key, model) slots on any
        failure. Returns the parsed JSON response dict from whichever slot
        succeeds. `action` lets callers hit non-generateContent endpoints
        (e.g. 'predict' for Imagen).

        `disable_thinking` (default True): Gemini 2.5 models think by
        default, and those thinking tokens count against maxOutputTokens —
        with a modest token budget (e.g. structured JSON extraction calls)
        this silently ate the entire budget on invisible reasoning and left
        nothing for the actual output, causing finishReason=MAX_TOKENS with
        no parseable content. This app's own routing already sends complex
        reasoning to OpenRouter (see agent/llm/router.py) and uses Gemini
        for fast/cheap calls, so thinking is off by default here; pass
        False to opt back in for a specific call if ever needed.
        """
        if not self.keys:
            raise GeminiExhaustedError(
                "No Gemini API key configured (set GEMINI_API_KEY or GEMINI_API_KEYS)"
            )

        if disable_thinking and action == 'generateContent':
            payload = dict(payload)
            gen_config = dict(payload.get('generationConfig', {}))
            gen_config['thinkingConfig'] = {'thinkingBudget': 0}
            payload['generationConfig'] = gen_config

        total_slots = len(self.keys) * len(self.models)
        attempts = 0
        # Try each slot once. No doubling — without the old blocking sleep,
        # a second round would just re-hit the same still-cooling-down slots
        # instantly and fail again for no benefit.
        max_attempts = total_slots

        while attempts < max_attempts:
            key_idx, model = self._get_available_slot()
            api_key = self.keys[key_idx]
            url = f"{_BASE_URL}/{model}:{action}?key={api_key}"
            attempts += 1

            try:
                response = requests.post(url, json=payload, timeout=timeout)
                if response.status_code == 429:
                    self._mark_exhausted((key_idx, model))
                    continue
                response.raise_for_status()
                data = response.json()
                logger.info(f"[gemini_client] ✓ key#{key_idx} {model} responded OK")
                return data
            except requests.exceptions.HTTPError as e:
                logger.warning(f"[gemini_client] ✗ key#{key_idx} {model} HTTP error: {e}")
                self._mark_exhausted((key_idx, model))
                continue
            except Exception as e:
                logger.warning(f"[gemini_client] ✗ key#{key_idx} {model} error: {e}")
                self._mark_exhausted((key_idx, model))
                continue

        raise GeminiExhaustedError(
            f"All {len(self.keys)} Gemini API key(s) × {len(self.models)} "
            f"models exhausted after {attempts} attempts"
        )
