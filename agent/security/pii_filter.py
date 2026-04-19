"""
PII redaction — strips personally identifiable information before logging.

Redacts: phone numbers, email addresses, PAN, Aadhaar, bank account numbers,
API keys, and credit card numbers.

Usage:
    from agent.security.pii_filter import redact_pii
    safe = redact_pii("My PAN is ABCDE1234F and email is user@example.com")
    # "My PAN is [PAN_REDACTED] and email is [EMAIL_REDACTED]"
"""

import re

# Each tuple: (compiled pattern, replacement tag)
_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Indian phone numbers (10 digits, optionally with +91 or 0 prefix)
    (re.compile(r"(?:\+91[\s-]?|0)?[6-9]\d{9}\b"), "[PHONE_REDACTED]"),

    # Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL_REDACTED]"),

    # Indian PAN (5 alpha + 4 digit + 1 alpha)
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN_REDACTED]"),

    # Aadhaar (12 digits, possibly space/dash separated in groups of 4)
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[AADHAAR_REDACTED]"),

    # Bank account numbers (8-18 digits)
    (re.compile(r"\b(?:account\s*(?:no|number|#)?[\s:]*)\d{8,18}\b", re.IGNORECASE), "[ACCOUNT_REDACTED]"),

    # Credit/debit card numbers (16 digits, possibly grouped)
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CARD_REDACTED]"),

    # API keys / tokens (long alphanumeric strings that look like secrets)
    (re.compile(r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S{8,}\b", re.IGNORECASE), "[API_KEY_REDACTED]"),

    # IFSC codes (11 chars: 4 alpha + 0 + 6 alphanum) — redact when preceded by context
    (re.compile(r"\b(?:IFSC[\s:]*)[A-Z]{4}0[A-Z0-9]{6}\b", re.IGNORECASE), "[IFSC_REDACTED]"),
]


def redact_pii(text: str) -> str:
    """
    Replace PII patterns in text with redaction tags.
    Safe to call on any string — returns unchanged text if no PII found.
    """
    if not text:
        return text
    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result
