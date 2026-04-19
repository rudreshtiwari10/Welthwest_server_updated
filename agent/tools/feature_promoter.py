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


def _match_features(
    query: str,
    *,
    symbol: Optional[str] = None,
    limit: int = 3,
) -> list[dict]:
    """Match a query/intent to features by keyword overlap."""
    features = _load_features()
    if not features:
        return []

    query_lower = query.lower()
    query_words = set(query_lower.split())

    scored: list[tuple[float, dict]] = []
    for feat in features:
        score = 0.0
        # Check intent overlap
        for intent in feat.get("trigger_intents", []):
            intent_words = set(intent.lower().replace("_", " ").split())
            overlap = query_words & intent_words
            if overlap:
                score += len(overlap) * 0.3
            # Substring match on intent
            if intent.lower().replace("_", " ") in query_lower:
                score += 0.5

        # Check description keyword overlap
        desc_words = set(feat.get("description", "").lower().split())
        desc_overlap = query_words & desc_words
        score += len(desc_overlap) * 0.1

        # Check name match
        if feat.get("name", "").lower() in query_lower:
            score += 0.4

        if score > 0:
            scored.append((score, feat))

    # Sort by score descending, take top N
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
            )
        except Exception as e:
            logger.warning("Feature promoter failed: %s", e)
            return ToolResult(success=False, error="Feature suggestion failed")
