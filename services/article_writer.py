"""
Article Writer Service - Model-swappable AI article generation
Supports Gemini Flash (default) and Grok (via .env config)

Config via .env:
  AI_ANALYSIS_PROVIDER=gemini   # gemini or grok
  AI_WRITING_PROVIDER=gemini    # gemini or grok
  GEMINI_API_KEYS=key1,key2,... # preferred — comma-separated pool of keys
  GEMINI_API_KEY=...            # fallback if GEMINI_API_KEYS not set (single key)
  GROK_API_KEY=...              # only needed if using grok

Gemini key/model rotation lives in services/gemini_client.py (shared across
every Gemini consumer in this app, not just this file).
"""

import os
import json
import re
import time
import logging
import requests

from services.gemini_client import GeminiRotator

logger = logging.getLogger(__name__)


class ArticleWriter:
    def __init__(self):
        self.analysis_provider = os.getenv('AI_ANALYSIS_PROVIDER', 'gemini')
        self.writing_provider = os.getenv('AI_WRITING_PROVIDER', 'gemini')
        self.grok_key = os.getenv('GROK_API_KEY', '')
        self._gemini = GeminiRotator()

    # ── LLM Calls ──────────────────────────────────────────────

    def call_gemini(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.7) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        data = self._gemini.post(payload)
        return data['candidates'][0]['content']['parts'][0]['text']

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

    # ── Relevance Check ────────────────────────────────────────

    def check_relevance(self, news_cluster: list) -> bool:
        """Quick check: is this news actually relevant to financial markets?"""
        titles = " | ".join(item.get('title', '') for item in news_cluster)

        prompt = f"""You are a financial news editor. Your job is to decide if a news story has REAL, MEANINGFUL impact on financial markets, stocks, or the economy.

Score this news from 1-10 on market relevance:
- 8-10: Directly about markets, stocks, economy, trade, monetary policy, corporate earnings, IPOs, commodities, crypto prices
- 5-7: Indirectly impacts markets — government policy, industry regulation, major geopolitical events (wars, sanctions), tech disruptions affecting listed companies
- 1-4: Celebrity deaths, sports, entertainment, local crime, obituaries, social media drama, lifestyle — these do NOT meaningfully impact markets even with a forced connection

NEWS: {titles}

Respond ONLY with valid JSON:
{{"score": <number 1-10>, "reason": "one line why"}}"""

        try:
            raw = self._call_provider(self.analysis_provider, prompt, max_tokens=100, temperature=0.2)
            result = self._parse_json(raw)
            score = int(result.get('score', 0))
            reason = result.get('reason', '')
            logger.info(f"Relevance check: {score}/10 — {reason} — {titles[:80]}")
            return score >= 7
        except Exception as e:
            logger.warning(f"Relevance check failed: {e}, allowing through")
            return True  # If check fails, let it through

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

This news has already been screened for market relevance. Find the REAL connection to financial markets — but be honest and specific. If the impact is indirect, say so clearly. Don't exaggerate or manufacture connections.

Examples of real connections:
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

        prompt = f"""You are a senior financial analyst and investigative journalist at WelthWest Research Desk. You write in-depth, data-driven articles that become the definitive resource on a topic. Your articles rank #1 on Google because of their depth, original analysis, and comprehensive coverage.

Based on this analysis, write a COMPREHENSIVE, ORIGINAL article. Do NOT copy any source phrasing. Every sentence must add value.

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
1. CATCHY, clickable headline with high-search-volume keywords
2. Key takeaway (2-3 lines — the "so what" for investors, make it punchy)
3. What happened — set the scene with context and background, explain WHY this matters NOW
4. Deep market impact analysis — connect to Indian stock market with specific data points, historical parallels, and sector-level breakdown
5. Stock-by-stock breakdown — name 4-6 specific NSE/BSE stocks affected, explain HOW and WHY each is impacted, include sector peers
6. Expert perspective — add contrarian views, what bears vs bulls would argue
7. Actionable investor playbook — concrete steps: what to buy/sell/watch, entry points, time horizons
8. Risk matrix — list 3-4 specific risks with probability assessment
9. What to watch next — upcoming catalysts, dates, data releases that will move this story

Requirements:
- 1200-2000 words — this is a DEEP DIVE, not a news brief
- Authoritative, data-driven tone — like a Goldman Sachs research note but readable
- Include specific numbers: market cap, P/E ratios, revenue figures, % changes where relevant
- Reference historical parallels ("last time this happened in 2022, Nifty moved X%")
- ALWAYS connect to Indian stock market with specific NSE/BSE tickers
- Use long-tail keywords naturally throughout for SEO dominance
- Include 2-3 subheadings as questions people would Google (e.g., "How will RBI rate cut affect bank stocks?")
- Do NOT include any disclaimer text in the article body
- Every paragraph must contain an insight the reader can't easily find elsewhere

Respond ONLY with valid JSON:
{{
  "title": "catchy, trending, SEO-optimized headline (max 80 chars) — use keywords people actually search for",
  "meta_title": "search-engine optimized title (max 60 chars) — include key topic + 'Indian market' or 'stocks'",
  "meta_description": "compelling click-worthy description for search results (max 155 chars)",
  "key_takeaway": "2-3 line key takeaway for investors — make it quotable",
  "summary": "3-4 sentence summary for cards/previews — hook the reader",
  "content": "full HTML article content with <h2>, <h3>, <p>, <strong>, <ul>/<li>, <blockquote> tags. Use <h2> for main sections, <h3> for subsections.",
  "tags": ["10-15 SEO tags — mix of trending topic tags, long-tail keywords, stock names, and financial terms people search for"]
}}"""

        raw = self._call_provider(self.writing_provider, prompt, max_tokens=6000, temperature=0.7)
        return self._parse_json(raw)

    # ── Full Pipeline for One Cluster ──────────────────────────

    def process_cluster(self, news_cluster: list) -> dict:
        """Full pipeline: relevance check → analyze → write for one cluster"""
        titles_preview = " | ".join(item.get('title', '')[:50] for item in news_cluster)
        logger.info(f"Checking relevance of {len(news_cluster)} articles: {titles_preview[:100]}")

        # Quick relevance gate — skip junk news
        if not self.check_relevance(news_cluster):
            raise Exception("Skipped: not market-relevant (score < 5)")
        time.sleep(5)

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
