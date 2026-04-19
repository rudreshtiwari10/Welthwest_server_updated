"""
Output moderation filter — runs on every LLM response before it leaves the server.

Two layers:
  1. Regex pattern matching — catches explicit directional phrases
  2. Sentence-level sanitization — replaces offending sentences with a neutral fallback

If violations are found, the offending sentences are rewritten. After 2+ violations
in the same response, a compliant fallback message replaces the entire response.

This filter is intentionally aggressive — false positives are acceptable (we'd rather
over-filter than leak directional advice). The user experience impact is minimal because
the system prompt already steers the LLM away from these patterns; the filter is a
safety net for the rare cases that slip through.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---- Banned patterns --------------------------------------------------------
# Each pattern is case-insensitive. They match phrases that constitute
# investment advice, price predictions, or directional recommendations.

BANNED_PATTERNS: list[tuple[str, str]] = [
    # Direct recommendations
    (r"\b(?:i|we|welth)\s+(?:recommend|suggest|advise)\s+(?:buying|selling|holding)\b", "direct_recommendation"),
    (r"\b(?:you\s+should|i(?:'d| would)\s+(?:recommend|suggest))\s+(?:buy|sell|hold|invest|exit|enter)\b", "should_buy_sell"),
    (r"\bshould\s+(?:buy|sell|invest|exit|enter|hold)\b", "should_directive"),

    # Good/bad stock judgements
    (r"\b(?:good|great|excellent|strong|best)\s+(?:buy|sell|entry|exit|pick|stock|investment)\b", "quality_judgement"),
    (r"\b(?:bad|poor|weak|worst|terrible)\s+(?:buy|sell|entry|exit|pick|stock|investment)\b", "quality_judgement"),
    (r"\bthis\s+(?:stock|share|scrip)\s+is\s+(?:good|great|bad|risky|safe)\b", "stock_judgement"),

    # Directional signals
    (r"\b(?:bullish|bearish)\s+(?:signal|outlook|setup|opportunity|momentum|trend)\b", "directional_signal"),
    (r"\b(?:buy|sell|long|short)\s+(?:signal|opportunity|setup)\b", "trade_signal"),
    (r"\b(?:strong\s+)?(?:uptrend|downtrend|rally|crash|correction)\s+(?:ahead|coming|expected|likely)\b", "prediction"),

    # Price targets / predictions
    (r"\b(?:target\s+price|price\s+target)\s*[:=]?\s*[₹$]?\s*[\d,]+", "price_target"),
    (r"\btarget\s+price\s+(?:is|of|for|at)\b", "price_target"),
    (r"\b(?:stock|price|share)\s+(?:will|would|shall|is\s+going\s+to)\s+(?:go\s+up|rise|fall|crash|rally|double|triple|surge|plunge)\b", "price_prediction"),
    (r"\bexpect(?:ed|ing)?\s+(?:the\s+(?:stock|price|share)\s+)?(?:to\s+)?(?:rise|fall|go\s+up|go\s+down|reach|hit)\b", "expectation"),
    (r"\b(?:stock|price|share)\s+(?:will|is\s+going\s+to|is\s+expected\s+to)\s+(?:rise|fall|crash|surge|plunge)\b", "prediction"),

    # Timing advice
    (r"\b(?:good|right|perfect|ideal)\s+time\s+to\s+(?:buy|sell|invest|enter|exit)\b", "timing_advice"),
    (r"\bbuy\s+(?:the\s+)?dip\b", "timing_advice"),
    (r"\bbook\s+(?:your\s+)?profits?\b", "timing_advice"),

    # Overbought/Oversold as advice (the indicator module already uses neutral language,
    # but the LLM synthesizer might re-introduce these terms)
    (r"\b(?:clearly\s+)?overbought\b", "directional_label"),
    (r"\b(?:clearly\s+)?oversold\b", "directional_label"),
    (r"\bbullish\s+crossover\b", "directional_label"),
    (r"\bbearish\s+crossover\b", "directional_label"),

    # Accumulate / avoid
    (r"\b(?:accumulate|avoid)\s+(?:this|the)\s+(?:stock|share|scrip)\b", "accumulate_avoid"),
    (r"\bstay\s+away\s+from\b", "avoid_advice"),
    (r"\bmust[\s-]+have\s+(?:stock|share|in\s+(?:your\s+)?portfolio)\b", "must_have"),
]

# Pre-compile all patterns
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), label)
    for pattern, label in BANNED_PATTERNS
]

# Neutral replacement for offending sentences
_NEUTRAL_REPLACEMENT = (
    "For specific investment decisions, please consult a SEBI-registered advisor."
)

# Full fallback when response has too many violations
_FALLBACK_RESPONSE = (
    "I can share factual data and analysis about this stock, but I'm unable to "
    "provide investment recommendations or directional advice. Would you like me "
    "to show you the latest price, technical indicators, or fundamental data instead?"
)

MAX_VIOLATIONS_BEFORE_FALLBACK = 3


# ---- Public API -------------------------------------------------------------


@dataclass
class ModerationResult:
    """Result of running the output filter."""
    original: str
    sanitized: str
    violations: list[dict] = field(default_factory=list)
    used_fallback: bool = False

    @property
    def is_clean(self) -> bool:
        return len(self.violations) == 0


def moderate_response(text: str) -> ModerationResult:
    """
    Run the compliance filter on an LLM response.

    Returns a ModerationResult with:
      - sanitized: the cleaned text (may be identical to original if clean)
      - violations: list of {pattern_label, matched_text, sentence}
      - used_fallback: True if the entire response was replaced
    """
    if not text or not text.strip():
        return ModerationResult(original=text, sanitized=text)

    violations: list[dict] = []
    sentences = _split_sentences(text)
    clean_sentences: list[str] = []

    for sentence in sentences:
        sentence_violations = _check_sentence(sentence)
        if sentence_violations:
            violations.extend(sentence_violations)
            # Replace the offending sentence
            clean_sentences.append(_NEUTRAL_REPLACEMENT)
            logger.info(
                "Compliance filter caught %d violation(s) in: %s",
                len(sentence_violations),
                sentence[:80],
            )
        else:
            clean_sentences.append(sentence)

    # If too many violations, replace the entire response
    if len(violations) >= MAX_VIOLATIONS_BEFORE_FALLBACK:
        return ModerationResult(
            original=text,
            sanitized=_FALLBACK_RESPONSE,
            violations=violations,
            used_fallback=True,
        )

    sanitized = " ".join(clean_sentences)

    # De-duplicate consecutive neutral replacements
    while f"{_NEUTRAL_REPLACEMENT} {_NEUTRAL_REPLACEMENT}" in sanitized:
        sanitized = sanitized.replace(
            f"{_NEUTRAL_REPLACEMENT} {_NEUTRAL_REPLACEMENT}",
            _NEUTRAL_REPLACEMENT,
        )

    return ModerationResult(
        original=text,
        sanitized=sanitized.strip(),
        violations=violations,
        used_fallback=False,
    )


# ---- Internal helpers -------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving structure."""
    # Split on sentence-ending punctuation followed by space or end
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _check_sentence(sentence: str) -> list[dict]:
    """Check a single sentence against all banned patterns."""
    violations = []
    for pattern, label in _COMPILED_PATTERNS:
        match = pattern.search(sentence)
        if match:
            violations.append({
                "pattern_label": label,
                "matched_text": match.group(0),
                "sentence": sentence[:100],
            })
    return violations
