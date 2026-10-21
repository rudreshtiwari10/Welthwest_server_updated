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


# Placeholder values a model sometimes returns instead of an empty list
# when told to give "affected stocks ... if applicable" — filtered out
# wherever list fields like this are read, so one never ends up stored,
# served by the API, or joined into a screener deep-link URL as literal
# text (e.g. /ai-screener?q=None).
_PLACEHOLDER_VALUES = {'none', 'n/a', 'na', 'not applicable', 'null', ''}


def _clean_list(values) -> list:
    if not isinstance(values, list):
        return []
    return [
        v.strip() for v in values
        if isinstance(v, str) and v.strip().lower() not in _PLACEHOLDER_VALUES
    ]


class ArticleWriter:
    def __init__(self):
        self.analysis_provider = os.getenv('AI_ANALYSIS_PROVIDER', 'gemini')
        self.writing_provider = os.getenv('AI_WRITING_PROVIDER', 'gemini')
        self.grok_key = os.getenv('GROK_API_KEY', '')
        self._gemini = GeminiRotator()

    # ── LLM Calls ──────────────────────────────────────────────

    def call_gemini(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.7,
                    enable_thinking: bool = False) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        # Thinking tokens count against maxOutputTokens (see gemini_client's
        # disable_thinking docstring) -- only worth enabling where max_tokens
        # has real headroom beyond the expected output size, and where the
        # task benefits from actual reasoning (synthesis/judgment) rather
        # than being a fast structured-extraction call.
        data = self._gemini.post(payload, disable_thinking=not enable_thinking)
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

    def _call_provider(self, provider: str, prompt: str, max_tokens: int = 4000, temperature: float = 0.7,
                       enable_thinking: bool = False) -> str:
        if provider == 'grok':
            return self.call_grok(prompt, max_tokens, temperature)
        return self.call_gemini(prompt, max_tokens, temperature, enable_thinking=enable_thinking)

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

    # The explicit grounding for "is this financially relevant" — replaces a
    # vague holistic judgment call with a concrete, broad-but-bounded list.
    # Narrowing happens here, not at ingestion: news_aggregator.py's RSS
    # feeds are broad general-news sources (e.g. "trending" = Google News
    # India top stories), so this gate is the only thing standing between
    # raw general news and what WelthWest actually publishes.
    RELEVANT_TOPICS = """
Markets & Trading: stock markets (NSE/BSE), indices (Nifty, Sensex, Bank Nifty), IPOs/listings, mutual funds, SIPs, F&O/derivatives, commodity trading, forex/currency markets, bond/debt markets, algorithmic/quant trading
Banking & Credit: banking sector (PSU & private), RBI policy/repo rate, NPAs/bad loans, loans & interest rates, credit/debit cards, digital payments/UPI/fintech, insurance, NBFCs, microfinance
Crypto & Digital Assets: Bitcoin & major cryptocurrencies, crypto regulation, blockchain/Web3, stablecoins, crypto exchanges, central bank digital currency (digital rupee)
Macro & Policy: inflation (CPI/WPI), GDP growth, union budget/fiscal policy, tax policy (income tax/GST), monetary policy (RBI/Fed/ECB/BOJ), trade policy & tariffs, rupee/currency movements, employment/jobs data, fiscal deficit/government debt, sovereign credit ratings
Corporate & Earnings: quarterly earnings, M&A, corporate fraud/scandals, dividends/buybacks, stock splits/bonus shares, startup funding/VC, unicorns, layoffs/hiring trends, index reshuffles (Nifty/Sensex additions-removals)
Sectors: IT/technology, pharma & healthcare, auto & EV, energy/oil & gas, metals & mining, real estate, FMCG, telecom, defense, infrastructure/construction, agriculture & commodities, aviation, renewable energy
Global & Geopolitical-Economic: wars/conflicts with market impact, sanctions & trade wars, global supply chains, elections affecting markets, major central bank decisions globally, international trade data (exports/imports), global recession/growth signals
Personal Finance & Retail Investing: retail investor trends, retirement/pension planning, personal tax planning, investment scams/fraud warnings, financial literacy
""".strip()

    def check_relevance(self, news_cluster: list) -> bool:
        """Quick check: is this news actually relevant to financial markets?"""
        titles = " | ".join(item.get('title', '') for item in news_cluster)

        prompt = f"""You are a financial news editor. Your job is to decide if a news story has REAL, MEANINGFUL impact on financial markets, stocks, banking, trading, crypto, or the broader economy.

WelthWest covers these areas (use this as your grounding — a story qualifies if it's directly about one of these, or has a genuine, specific, non-forced connection to one):
{self.RELEVANT_TOPICS}

Score this news from 1-10 on market relevance:
- 8-10: Directly about one of the areas above
- 5-7: Indirectly connected with a real, specific, explainable market/economic impact — not every indirect link counts, only ones you could concretely explain in a sentence
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
  "affected_stocks": ["specific Indian stock names/tickers — empty array [] if none apply, never a placeholder like 'None' or 'N/A'"],
  "sector": "primary sector affected (e.g., Banking, IT, Pharma, Energy, Auto, FMCG, Metals, Infra, Telecom, Defence, Crypto, General)",
  "sentiment": "Bullish or Bearish or Neutral",
  "impact_score": "Low or Medium or High",
  "time_horizon": "Short-term or Long-term",
  "category": "market-pulse or deep-analysis or stock-signals or global-impact",
  "tags": ["5-8 relevant trending SEO tags — include the topic name AND market-related keywords"],
  "key_risks": "1-2 sentences on risks"
}}"""

        # Thinking enabled here deliberately: this is the step that decides
        # the real market connection, winners/losers, and sector -- the
        # synthesis quality here is what the rest of the article depends on.
        # max_tokens raised from 1500 to leave room for reasoning tokens on
        # top of the (still-small) JSON output, per call_gemini's note on
        # thinking tokens counting against the same budget.
        raw = self._call_provider(self.analysis_provider, prompt, max_tokens=3000, temperature=0.4,
                                  enable_thinking=True)
        return self._parse_json(raw)

    # ── Writing Step ───────────────────────────────────────────

    def write_article(self, analysis: dict, news_cluster: list) -> dict:
        """Generate a full original article from the analysis"""
        sources_summary = "\n".join(
            f"- {item.get('title', '')} ({item.get('source_name', '')})"
            for item in news_cluster
        )

        prompt = f"""You are a financial journalist at WelthWest who writes tight, specific, genuinely useful pieces for Indian retail investors — the kind of writing a sharp human analyst would actually publish, not a templated report.

Based on this analysis, write an ORIGINAL article. Do NOT copy any source phrasing. Do NOT pad — every sentence should earn its place.

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

Length and structure — let the STORY decide, not a template:
- Typical length is 400-800 words. A genuinely complex, multi-company story can run up to ~1100 — but only because there's real substance to cover, never to hit a quota.
- Don't force every article through the same skeleton. Some stories are a tight 400-word explainer; others genuinely need a stock-by-stock breakdown. Decide based on what THIS story actually needs.
- It's fine — good, even — for structure to vary noticeably from article to article.

What to avoid (these read as AI-generated filler and hurt both readers and search rankings):
- Generic headline patterns like "Unpacking X", "Decoding X", "Navigating the Storm", "X: What You Need to Know"
- A mandatory "expert perspective" or "bull vs bear" section that invents opinions or quotes nobody said — if there's a genuine open question in the story, just say what it is plainly, don't manufacture two sides
- A formal "risk matrix" with invented probability percentages — risks are fine, fabricated precision isn't
- Forcing a "How will X affect Y?" question as a subheading in every single article — use it occasionally if it's genuinely the clearest framing, not as a default pattern
- Stock transition words as filler ("Moreover," "Furthermore," "In conclusion") and throat-clearing openers ("In today's ever-evolving market...")
- Claiming precise numbers (P/E ratios, % moves, historical parallels) you don't actually have grounds for from the source material — only include specific figures you can reasonably infer or that were in the sources

What to do instead:
- Be specific and concrete about THIS story — names, numbers, and mechanisms you can actually support, not generic market commentary that could apply to any story in this sector
- Write like you're explaining it to a smart friend who invests but doesn't have time to read five sources — direct, confident, no ceremony
- Connect to Indian markets with real NSE/BSE tickers where there's a genuine connection — don't force a stock list if the story doesn't warrant one
- A short, punchy take is better than a long, padded one

Do NOT include any disclaimer text in the article body.

Respond ONLY with valid JSON:
{{
  "title": "specific, clear headline (max 80 chars) — describe what actually happened, use real search terms, avoid generic AI headline patterns",
  "meta_title": "search-engine optimized title (max 60 chars)",
  "meta_description": "compelling, specific description for search results (max 155 chars)",
  "key_takeaway": "1-2 line takeaway — the single most useful thing an investor should know",
  "summary": "2-3 sentence summary for cards/previews",
  "content": "full HTML article content with <h2>, <h3>, <p>, <strong>, <ul>/<li>, <blockquote> tags where they genuinely help structure — not as decoration",
  "tags": ["8-12 SEO tags — real topic/stock/financial terms people search for, no filler tags"]
}}"""

        # Thinking enabled: with output now 400-800 words instead of
        # 1200-2000, there's real budget headroom to spend on reasoning
        # about phrasing/structure/what to include, rather than on more
        # words. max_tokens kept generous so thinking tokens (which count
        # against this same budget) don't crowd out the output JSON.
        raw = self._call_provider(self.writing_provider, prompt, max_tokens=5000, temperature=0.8,
                                  enable_thinking=True)
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
            'affected_stocks': _clean_list(analysis.get('affected_stocks', [])),
            'sector': analysis.get('sector', 'General'),
            'category': analysis.get('category', 'deep-analysis'),
        })

        # Merge tags (dedupe)
        all_tags = list(set(
            _clean_list(analysis.get('tags', [])) + _clean_list(article_data.get('tags', []))
        ))
        article_data['tags'] = all_tags[:10]

        return article_data
