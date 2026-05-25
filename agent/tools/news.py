"""Tools: get_market_news, get_company_news, find_news — wrap services/news_service.

All three tools guarantee an item list (1+ articles) when the newsroom is non-empty:
if a query yields no matches, they fall back to the most recent articles, so the
agent / frontend always has something to show.

URLs returned by these tools point at the WelthWest Next.js newsroom app
(separate deployment from the React client). Override via NEWS_APP_URL env var
if running locally on a different port.
"""

import os
import re
from datetime import datetime

from agent.tools.base import Tool, ToolResult

# The newsroom is a separate Next.js app, mounted on the WelthWest domain.
# Override via env for local dev (e.g., NEWS_APP_URL=http://localhost:3000).
NEWS_APP_URL = os.environ.get("NEWS_APP_URL", "https://www.welthwest.com").rstrip("/")


_QUERY_STOPWORDS = {
    "a", "an", "and", "the", "is", "it", "of", "to", "in", "on", "for", "with",
    "what", "whats", "which", "how", "do", "i", "me", "my", "any", "some", "about",
    "today", "todays", "latest", "recent", "current", "currently", "news",
    "show", "tell", "give", "find", "want", "would", "could", "should", "can",
    "please", "now", "from", "by", "as", "this", "that", "these", "those",
    "happening", "happened", "going", "around",
}


def _strip_query(q: str) -> str:
    """Drop stopwords so 'latest news on RBI repo rate' becomes 'rbi repo rate'."""
    if not q:
        return ""
    tokens = re.findall(r"[A-Za-z0-9]+", q.lower())
    kept = [t for t in tokens if t not in _QUERY_STOPWORDS and len(t) > 1]
    return " ".join(kept).strip()


def _strip_html(text: str) -> str:
    """Strip HTML tags + collapse whitespace. Keep it cheap — no parser."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", str(text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _format_date(value) -> str:
    """Best-effort ISO-date formatter for whatever shape created_at has."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    s = str(value)
    return s[:10] if len(s) >= 10 else s


def _shape_post(post: dict, snippet_chars: int = 240) -> dict:
    """Project a CMS post down to the fields the LLM + frontend cards both need."""
    title = post.get("title") or ""
    raw_content = post.get("excerpt") or post.get("summary") or post.get("content") or ""
    snippet = _strip_html(raw_content)
    if len(snippet) > snippet_chars:
        snippet = snippet[:snippet_chars].rsplit(" ", 1)[0] + "…"
    slug = post.get("slug") or ""
    return {
        "title": title,
        "snippet": snippet,
        "category": post.get("category") or "",
        "tags": post.get("tags") or [],
        "published": _format_date(post.get("created_at") or post.get("publishedAt")),
        "slug": slug,
        # Absolute URL to the Next.js newsroom — works from any client (React
        # frontend, mobile webview, agent text response).
        "url": f"{NEWS_APP_URL}/news/{slug}" if slug else "",
        "image_url": post.get("image_url") or post.get("imageUrl") or "",
        "source_name": post.get("source_name") or post.get("sourceName") or "WelthWest",
    }


def _fetch_recent(limit: int, category: str = None) -> list:
    """Most-recent N news posts from the newsroom."""
    from services.news_service import news_service
    result = news_service.get_all_news(page=1, limit=limit, category=category)
    if not result.get("success"):
        return []
    return result.get("posts") or []


def _fetch_search(query: str, limit: int) -> list:
    """Search the newsroom by title / content / tags."""
    from services.news_service import news_service
    result = news_service.search_posts(query=query, post_type="all", page=1, limit=limit)
    if not result.get("success"):
        return []
    return result.get("posts") or []


def _shape_results(posts: list, *, query: str = "", fallback_used: bool = False) -> dict:
    """Shape a list of CMS posts for the agent + frontend cards."""
    items = [_shape_post(p) for p in posts]
    return {
        "count": len(items),
        "items": items,
        "query": query,
        "fallback_used": fallback_used,
        "note": (
            "No articles directly matched the query — falling back to the most recent "
            "headlines from our newsroom so the user still gets relevant context."
            if fallback_used else ""
        ),
    }


# ============================================================================

class GetMarketNewsTool(Tool):
    name = "get_market_news"
    description = (
        "Fetch news headlines from the WelthWest newsroom (2,500+ original financial articles). "
        "Supports an optional topical query — drops fluff words like 'today', 'latest', 'news' "
        "and matches the rest against article titles / content / tags. If the topic search "
        "returns nothing, the tool falls back to the most-recent N articles so the user always "
        "sees something. Use for 'today's news', 'latest IPO news', 'RBI announcements', "
        "'banking sector news', 'tech sector', or any topical news ask not tied to one ticker."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional topical query — e.g., 'RBI repo rate', 'IT sector', 'IPO'. Leave empty for the latest feed.",
            },
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g., 'markets', 'ipo', 'macro', 'banking'). Used for the fallback-recent path only.",
            },
            "limit": {
                "type": "integer",
                "description": "How many articles to return (1 to 15). Default 6 — perfect for a primary + 5 related card.",
            },
        },
    }

    def execute(self, *, query: str = "", category: str = None, limit: int = 6, **_) -> ToolResult:
        try:
            limit = max(1, min(int(limit or 6), 15))
            cleaned = _strip_query(query)
            posts: list = []
            fallback = False

            if cleaned:
                posts = _fetch_search(cleaned, limit)
            if not posts:
                # Either no query, or query yielded nothing → recent feed
                posts = _fetch_recent(limit, category=category)
                fallback = bool(cleaned)  # only "fallback" if we tried to search

            shaped = _shape_results(posts, query=cleaned, fallback_used=fallback)
            return ToolResult(
                success=True,
                data={
                    "kind": "market",
                    "category": category or "all",
                    **shaped,
                },
                display_hint="news_list",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not fetch market news: {e}")


class GetCompanyNewsTool(Tool):
    name = "get_company_news"
    description = (
        "Search the WelthWest newsroom for stories mentioning a specific company or ticker. "
        "Searches by symbol AND company name (if provided), then falls back to the latest "
        "general newsroom feed if no specific match — so the user always sees relevant context. "
        "Use for 'news on RELIANCE', 'why is TCS in the news', 'HDFC Bank latest'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "NSE ticker (e.g., 'RELIANCE', 'TCS'). The tool will also try the resolved company name.",
            },
            "company_name": {
                "type": "string",
                "description": "Optional full company name to broaden the search (e.g., 'Reliance Industries').",
            },
            "limit": {
                "type": "integer",
                "description": "How many articles to return (1 to 10). Default 6.",
            },
        },
        "required": ["symbol"],
    }

    def execute(self, *, symbol: str, company_name: str = None, limit: int = 6, **_) -> ToolResult:
        try:
            limit = max(1, min(int(limit or 6), 10))
            symbol_q = (symbol or "").strip()
            if not symbol_q:
                return ToolResult(success=False, error="Empty symbol")

            # 1. Try symbol search
            posts = _fetch_search(symbol_q, limit)
            # 2. If sparse, also try company_name and merge unique results
            if len(posts) < limit and company_name:
                more = _fetch_search(company_name.strip(), limit)
                seen = {p.get("_id") for p in posts}
                for p in more:
                    if p.get("_id") not in seen:
                        posts.append(p)
                        if len(posts) >= limit:
                            break

            fallback = False
            if not posts:
                # No specific articles → recent feed so the user gets context
                posts = _fetch_recent(limit)
                fallback = True

            shaped = _shape_results(posts, query=symbol_q, fallback_used=fallback)
            return ToolResult(
                success=True,
                data={
                    "kind": "company",
                    "symbol": symbol_q.upper(),
                    **shaped,
                },
                display_hint="news_list",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Could not search news for {symbol}: {e}")


class FindNewsTool(Tool):
    name = "find_news"
    description = (
        "One-stop news lookup. Takes a natural-language query and returns matching WelthWest "
        "newsroom articles, with a smart fallback to the most-recent feed if nothing matches "
        "the topic. The frontend renders a news card showing one primary article + up to 5 "
        "related, all clickable. Use this whenever the user mentions news / headlines / "
        "'what's happening' / a specific event — it's smarter than get_market_news or "
        "get_company_news for ambiguous queries because it strips fluff words and always "
        "returns something."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What the user wants news about — can be a topic, ticker, event, or sector. e.g., 'RBI rate hike', 'TCS earnings', 'today's market', 'IT sector'.",
            },
            "limit": {
                "type": "integer",
                "description": "How many articles to return (1 to 10). Default 6.",
            },
        },
        "required": ["query"],
    }

    def execute(self, *, query: str, limit: int = 6, **_) -> ToolResult:
        try:
            limit = max(1, min(int(limit or 6), 10))
            cleaned = _strip_query(query)
            posts: list = []
            fallback = False

            if cleaned:
                posts = _fetch_search(cleaned, limit)
            if not posts:
                posts = _fetch_recent(limit)
                fallback = bool(cleaned) or not query

            shaped = _shape_results(posts, query=cleaned, fallback_used=fallback)
            return ToolResult(
                success=True,
                data={
                    "kind": "topic",
                    "original_query": query,
                    **shaped,
                },
                display_hint="news_list",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"News lookup failed: {e}")
