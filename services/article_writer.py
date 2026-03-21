"""
Article Writer Service - Model-swappable AI article generation
Supports Gemini Flash (default) and Grok (via .env config)

Config via .env:
  AI_ANALYSIS_PROVIDER=gemini   # gemini or grok
  AI_WRITING_PROVIDER=gemini    # gemini or grok
  GEMINI_API_KEY=...
  GROK_API_KEY=...              # only needed if using grok
"""

import os
import json
import re
import time
import logging
import requests

logger = logging.getLogger(__name__)


class ArticleWriter:
    def __init__(self):
        self.analysis_provider = os.getenv('AI_ANALYSIS_PROVIDER', 'gemini')
        self.writing_provider = os.getenv('AI_WRITING_PROVIDER', 'gemini')
        self.gemini_key = os.getenv('GEMINI_API_KEY', '')
        self.grok_key = os.getenv('GROK_API_KEY', '')

    # ── LLM Calls ──────────────────────────────────────────────

    def call_gemini(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.7) -> str:
        if not self.gemini_key:
            raise Exception("GEMINI_API_KEY not set")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={self.gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        # Retry up to 3 times on rate limit (429)
        for attempt in range(3):
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code == 429:
                wait = 15 * (attempt + 1)  # 15s, 30s, 45s
                logger.warning(f"Gemini rate limited, waiting {wait}s (attempt {attempt + 1}/3)")
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']

        raise Exception("Gemini rate limit exceeded after 3 retries")

    def call_grok(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.7) -> str:
        if not self.grok_key:
            raise Exception("GROK_API_KEY not set")

        url = "https://api.x.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.grok_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "grok-3-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']

    def _call_provider(self, provider: str, prompt: str, max_tokens: int = 4000, temperature: float = 0.7) -> str:
        if provider == 'grok':
            return self.call_grok(prompt, max_tokens, temperature)
        return self.call_gemini(prompt, max_tokens, temperature)

    # ── JSON Parsing ───────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks"""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}")

    # ── Analysis Step ──────────────────────────────────────────

    def analyze(self, news_cluster: list) -> dict:
        """Analyze a cluster of related news articles and extract structured intelligence"""
        news_text = ""
        for i, item in enumerate(news_cluster, 1):
            news_text += f"\n--- Source {i}: {item.get('source_name', 'Unknown')} ---\n"
            news_text += f"Title: {item.get('title', '')}\n"
            news_text += f"Description: {item.get('description', '')}\n"

        prompt = f"""You are a senior financial analyst at WelthWest Research Desk.

Given these news reports, analyze and extract structured intelligence with a MARKET IMPACT angle.

IMPORTANT: Even if the news is about wars, geopolitics, elections, technology, crypto, policy changes, natural disasters, or any global event — ALWAYS find and explain the connection to Indian stock markets, specific sectors, and affected companies. Every major world event impacts markets.

Examples of connections:
- War/conflict → Defence stocks, oil prices, gold, shipping
- US Fed rate decisions → IT stocks, FII flows, rupee value
- New government policy → affected industry sectors
- Tech breakthroughs (AI, chips) → Indian IT, semiconductor plays
- Crypto movements → crypto-linked stocks, exchange regulations
- Elections → infrastructure, PSU banks, defense, policy-sensitive sectors
- Natural disasters → insurance, commodities, supply chain

DO NOT summarize each article individually. Instead:
1. Identify the CORE EVENT across all sources
2. Determine WHY it matters to Indian/global financial markets
3. Identify winners and losers (companies, sectors)
4. Assess short-term vs long-term impact
5. Identify specific Indian stocks/sectors affected

NEWS ARTICLES:
{news_text}

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "core_event": "one-line catchy description of the core event",
  "why_it_matters": "2-3 sentences on market significance — be specific about how this impacts Indian markets",
  "winners": ["list of companies/sectors that benefit"],
  "losers": ["list of companies/sectors that suffer"],
  "affected_stocks": ["specific Indian stock names/tickers if applicable"],
  "sector": "primary sector affected (e.g., Banking, IT, Pharma, Energy, Auto, FMCG, Metals, Infra, Telecom, Defence, Crypto, General)",
  "sentiment": "Bullish or Bearish or Neutral",
  "impact_score": "Low or Medium or High",
  "time_horizon": "Short-term or Long-term",
  "category": "market-pulse or deep-analysis or stock-signals or global-impact",
  "tags": ["5-8 relevant trending SEO tags — include the topic name AND market-related keywords"],
  "key_risks": "1-2 sentences on risks"
}}"""

        raw = self._call_provider(self.analysis_provider, prompt, max_tokens=1500, temperature=0.4)
        return self._parse_json(raw)

    # ── Writing Step ───────────────────────────────────────────

    def write_article(self, analysis: dict, news_cluster: list) -> dict:
        """Generate a full original article from the analysis"""
        sources_summary = "\n".join(
            f"- {item.get('title', '')} ({item.get('source_name', '')})"
            for item in news_cluster
        )

        prompt = f"""You are a top financial journalist at WelthWest Research Desk. Your articles go viral because they combine trending news with sharp market insights.

Based on this analysis, write an ORIGINAL article that connects this event to financial markets. Do NOT copy any source phrasing.

ANALYSIS:
- Core Event: {analysis.get('core_event', '')}
- Why It Matters: {analysis.get('why_it_matters', '')}
- Winners: {', '.join(analysis.get('winners', []))}
- Losers: {', '.join(analysis.get('losers', []))}
- Affected Stocks: {', '.join(analysis.get('affected_stocks', []))}
- Sector: {analysis.get('sector', '')}
- Sentiment: {analysis.get('sentiment', '')}
- Impact: {analysis.get('impact_score', '')}
- Risks: {analysis.get('key_risks', '')}

SOURCE HEADLINES (for context only — do NOT copy):
{sources_summary}

Write the article with this structure:
1. CATCHY, clickable headline that includes trending keywords people are searching for
2. Key takeaway (2 lines max — the "so what" for investors)
3. What happened (brief, engaging hook)
4. Market impact analysis (detailed — connect to Indian stock market)
5. Who benefits, who loses (name specific stocks/sectors)
6. Investor insight / what to watch next
7. Risks to consider

Requirements:
- 700-1200 words
- Crispy, engaging tone — like a smart friend explaining markets to you
- Write like it's breaking news people NEED to read right now
- Add original analysis beyond the news — give insights readers can't find elsewhere
- ALWAYS connect back to Indian stock market, sectors, and specific stocks
- Use trending keywords naturally in the content for SEO
- Do NOT include any disclaimer text in the article body
- Make headings catchy and search-friendly

Respond ONLY with valid JSON:
{{
  "title": "catchy, trending, SEO-optimized headline (max 80 chars) — use keywords people actually search for",
  "meta_title": "search-engine optimized title (max 60 chars) — include key topic + 'Indian market' or 'stocks'",
  "meta_description": "compelling click-worthy description for search results (max 155 chars)",
  "key_takeaway": "2-line key takeaway for investors",
  "summary": "3-4 sentence crispy summary for cards/previews",
  "content": "full HTML article content with <h2>, <p>, <strong>, <ul>/<li> tags",
  "tags": ["8-12 SEO tags — mix of trending topic tags AND financial/market tags that people search for"]
}}"""

        raw = self._call_provider(self.writing_provider, prompt, max_tokens=4000, temperature=0.7)
        return self._parse_json(raw)

    # ── Full Pipeline for One Cluster ──────────────────────────

    def process_cluster(self, news_cluster: list) -> dict:
        """Full pipeline: analyze + write for one cluster of news"""
        logger.info(f"Analyzing cluster of {len(news_cluster)} articles...")

        analysis = self.analyze(news_cluster)
        time.sleep(10)  # Rate limiting between API calls

        logger.info(f"Writing article for: {analysis.get('core_event', 'unknown')}")
        article_data = self.write_article(analysis, news_cluster)
        time.sleep(10)

        # Merge analysis metadata into article
        article_data.update({
            'sentiment': analysis.get('sentiment', 'Neutral'),
            'impact_score': analysis.get('impact_score', 'Medium'),
            'time_horizon': analysis.get('time_horizon', 'Short-term'),
            'affected_stocks': analysis.get('affected_stocks', []),
            'sector': analysis.get('sector', 'General'),
            'category': analysis.get('category', 'deep-analysis'),
        })

        # Merge tags (dedupe)
        all_tags = list(set(
            analysis.get('tags', []) + article_data.get('tags', [])
        ))
        article_data['tags'] = all_tags[:10]

        return article_data
