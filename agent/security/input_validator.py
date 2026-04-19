"""
Input validation — caps query length, detects injection attempts.

Called before the agent processes any user input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_QUERY_LENGTH = 2000
MAX_CONVERSATION_LENGTH = 200  # messages per conversation


@dataclass
class ValidationResult:
    valid: bool = True
    error: Optional[str] = None
    sanitized_query: str = ""


# Optional import for typing
from typing import Optional


# Patterns that suggest prompt injection attempts
_INJECTION_PATTERNS = [
    # Attempts to override system prompt
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|rules?|prompts?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+(?!welth)", re.IGNORECASE),
    re.compile(r"new\s+(?:system\s+)?instructions?:", re.IGNORECASE),
    re.compile(r"forget\s+(?:everything|all|your)\s+(?:you|rules?|instructions?)", re.IGNORECASE),
    re.compile(r"\bsystem\s*:\s*you\s+are\b", re.IGNORECASE),
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),

    # Attempts to extract system prompt
    re.compile(r"(?:what|show|reveal|print|output|repeat)\s+(?:is\s+)?(?:your|the)\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"(?:what|show)\s+(?:are\s+)?your\s+(?:instructions|rules|guidelines)", re.IGNORECASE),
]


def validate_input(
    query: str,
    *,
    conversation_length: int = 0,
) -> ValidationResult:
    """
    Validate a user query before processing.

    Returns ValidationResult:
      - valid=True: proceed with sanitized_query
      - valid=False: reject with error message
    """
    if not query or not query.strip():
        return ValidationResult(
            valid=False,
            error="Please enter a question or topic you'd like to know about.",
            sanitized_query="",
        )

    query = query.strip()

    # Length check
    if len(query) > MAX_QUERY_LENGTH:
        return ValidationResult(
            valid=False,
            error=f"Your message is too long (max {MAX_QUERY_LENGTH} characters). Please shorten it.",
            sanitized_query="",
        )

    # Conversation length check
    if conversation_length >= MAX_CONVERSATION_LENGTH:
        return ValidationResult(
            valid=False,
            error="This conversation has reached its limit. Please start a new conversation.",
            sanitized_query="",
        )

    # Injection detection — flag but don't hard-block (the system prompt
    # already has anti-injection rules; logging is more valuable than blocking)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            # Don't reject — the agent's system prompt handles this.
            # But log it for abuse detection (Phase 7).
            import logging
            logging.getLogger(__name__).warning(
                "Potential injection attempt detected (pattern matched)"
            )
            break

    return ValidationResult(
        valid=True,
        error=None,
        sanitized_query=query,
    )
