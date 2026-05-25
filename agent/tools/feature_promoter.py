"""
Tool: suggest_welthwest_feature — recommend WelthWest platform features.

Loads the feature registry from agent/config/features.yaml and matches
user intent keywords to relevant features. Returns deep-linked URLs with
pre-filled parameters.

Adding a new feature = edit features.yaml, no code change.
Disabled features (enabled: false) are never promoted.
"""

import logging
import os
from typing import Optional

import yaml

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

# ---- Feature registry loading -----------------------------------------------

_FEATURES: list[dict] = []
_LOADED = False

_YAML_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "features.yaml",
)


def _load_features() -> list[dict]:
    """Load and cache features from YAML. Only enabled features."""
    global _FEATURES, _LOADED
    if _LOADED:
        return _FEATURES
    try:
        with open(_YAML_PATH, "r") as f:
            data = yaml.safe_load(f)
        all_features = data.get("features", [])
        _FEATURES = [f for f in all_features if f.get("enabled", True)]
        _LOADED = True
        logger.info("Feature registry loaded: %d enabled features", len(_FEATURES))
    except Exception as e:
        logger.warning("Failed to load features.yaml: %s", e)
        _FEATURES = []
        _LOADED = True
    return _FEATURES


_STOPWORDS = {
    "a", "an", "and", "the", "is", "it", "of", "to", "in", "on", "for", "with",
    "what", "whats", "which", "how", "do", "i", "me", "my", "we", "us", "you",
    "your", "this", "that", "these", "those", "show", "tell", "give", "find",
    "want", "would", "could", "should", "can", "please", "any", "some", "about",
    "now", "today", "current", "currently", "best", "good", "ok", "okay",
    "from", "by", "as", "are", "be", "was", "were", "or", "but", "also", "just",
}


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip non-alnum, drop stopwords + 1-char tokens."""
    import re
    raw = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    return [t for t in raw if len(t) > 1 and t not in _STOPWORDS]


def _match_features(
    query: str,
    *,
    symbol: Optional[str] = None,
    limit: int = 3,
) -> list[dict]:
    """
    Score features against the user query across four signal sources:

    1. keywords     — substring match on the query (strongest direct signal)
    2. use_cases    — token overlap with concrete example user-queries
    3. trigger_intents — token overlap with snake_case intents
    4. name         — substring match on the feature name
    plus a small bump from description overlap.

    Features are only returned if their score crosses a sensible threshold,
    so generic words like "stock" don't pull in everything.
    """
    features = _load_features()
    if not features:
        return []

    query_lower = (query or "").lower()
    query_tokens = set(_tokenize(query_lower))
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for feat in features:
        score = 0.0

        # 1. Keywords — direct substring match on the query
        for kw in feat.get("keywords") or []:
            kw_lower = kw.lower()
            if kw_lower in query_lower:
                # Longer keyword phrases score more (more specific match)
                score += 0.6 + 0.05 * max(0, len(kw_lower.split()) - 1)
            else:
                # Token-level overlap with the keyword
                kw_tokens = set(_tokenize(kw_lower))
                overlap = query_tokens & kw_tokens
                if overlap:
                    score += 0.15 * len(overlap)

        # 2. Use-cases — overlap with example user questions
        for uc in feat.get("use_cases") or []:
            uc_tokens = set(_tokenize(uc))
            overlap = query_tokens & uc_tokens
            if overlap:
                # Normalise by use-case length so a short example doesn't dominate
                score += 0.4 * len(overlap) / max(3, len(uc_tokens))

        # 3. Intents — token + substring match
        for intent in feat.get("trigger_intents") or []:
            intent_phrase = intent.lower().replace("_", " ")
            if intent_phrase in query_lower:
                score += 0.5
            intent_tokens = set(_tokenize(intent_phrase))
            overlap = query_tokens & intent_tokens
            if overlap:
                score += 0.25 * len(overlap)

        # 4. Name + tagline + description (weak signals)
        name_lower = (feat.get("name") or "").lower()
        if name_lower and name_lower in query_lower:
            score += 0.7
        tagline_tokens = set(_tokenize(feat.get("tagline") or ""))
        score += 0.1 * len(query_tokens & tagline_tokens)
        desc_tokens = set(_tokenize(feat.get("description") or ""))
        score += 0.05 * len(query_tokens & desc_tokens)

        # Threshold — drops generic "stock" / "news" mentions that scored < 0.35
        if score >= 0.4:
            scored.append((score, feat))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def _build_url(feature: dict, symbol: Optional[str] = None, **params) -> str:
    """Build a deep-linked URL with pre-filled params."""
    url = feature.get("url_template", "/")
    if symbol and "{symbol}" in url:
        url = url.replace("{symbol}", symbol.upper())
    for key, val in params.items():
        if val and f"{{{key}}}" in url:
            url = url.replace(f"{{{key}}}", str(val))
    # Clean up un-filled placeholders
    import re
    url = re.sub(r"\{[^}]+\}", "", url)
    return url


# ---- Tool implementation ----------------------------------------------------


class SuggestFeatureTool(Tool):
    name = "suggest_welthwest_feature"
    description = (
        "Suggest a relevant WelthWest platform feature based on what the user "
        "is trying to do. Returns the feature name, description, and a "
        "deep-linked URL. Use this when the user's query naturally relates to "
        "a platform capability (e.g., user asks about charts → suggest Stock "
        "Detail Page, user asks to find stocks → suggest AI Screener)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A short description of what the user wants to do",
            },
            "symbol": {
                "type": "string",
                "description": "Stock symbol if relevant (for deep-linking), optional",
            },
        },
        "required": ["query"],
    }

    def execute(self, *, query: str, symbol: str = None, **_) -> ToolResult:
        try:
            matches = _match_features(query, symbol=symbol, limit=3)
            if not matches:
                return ToolResult(
                    success=True,
                    data={"suggestions": [], "note": "No matching features found."},
                )

            suggestions = []
            for feat in matches:
                url = _build_url(feat, symbol=symbol)
                suggestions.append({
                    "key": feat["key"],
                    "name": feat["name"],
                    "description": feat["description"],
                    "url": url,
                    "plan_tier": feat.get("plan_tier", "FREE"),
                })

            return ToolResult(
                success=True,
                data={"suggestions": suggestions},
                display_hint="feature_suggestion",
            )
        except Exception as e:
            logger.warning("Feature promoter failed: %s", e)
            return ToolResult(success=False, error="Feature suggestion failed")
