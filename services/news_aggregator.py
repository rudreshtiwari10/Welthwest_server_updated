"""
News Aggregation Service - External Sources Only
NO DATABASE STORAGE - News is fetched from external APIs/RSS and cached in-memory only

Supports multiple news sources:
- NewsAPI.org (requires API key)
- RSS Feeds (Google News, MoneyControl, Economic Times)
- Alpha Vantage News (requires API key)
"""

import os
import re
import requests
import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed

# Match the first <img src="..."> in HTML (handles single/double quotes)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

# In-memory cache with TTL
class NewsCache:
    def __init__(self, ttl_minutes=10):
        self.cache = {}
        self.ttl = timedelta(minutes=ttl_minutes)

    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None

    def set(self, key, data):
        self.cache[key] = (data, datetime.now())

    def clear_expired(self):
        now = datetime.now()
        expired_keys = [k for k, (_, ts) in self.cache.items() if now - ts >= self.ttl]
        for key in expired_keys:
            del self.cache[key]

# Global cache instance
news_cache = NewsCache(ttl_minutes=60)

# News sources configuration
NEWS_API_KEY = os.getenv('NEWSAPI_KEY', '')  # Using existing env variable name
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', '')

# RSS Feed URLs
RSS_FEEDS = {
    'indian_markets': [
        'https://www.moneycontrol.com/rss/marketreports.xml',
        'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
        'https://www.livemint.com/rss/markets',
    ],
    'global_markets': [
        'https://feeds.bloomberg.com/markets/news.rss',
        'https://www.cnbc.com/id/100003114/device/rss/rss.html',
        'https://www.cnbc.com/id/100727362/device/rss/rss.html',  # CNBC World
    ],
    'nse': [
        'https://www.nseindia.com/rss/news.xml',
    ],
    'economy': [
        'https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms',
        'https://www.livemint.com/rss/economy',
    ],
    'banking': [
        'https://economictimes.indiatimes.com/industry/banking/finance/rssfeeds/13358259.cms',
    ],
    'trending': [
        'https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pKVGlnQVAB?hl=en-IN&gl=IN&ceid=IN:en',  # Google News India Top Stories
        'https://economictimes.indiatimes.com/news/rssfeeds/1715249553.cms',  # ET trending
        'https://www.livemint.com/rss/news',
    ],
    'geopolitics': [
        'https://economictimes.indiatimes.com/news/defence/rssfeeds/68597640.cms',
        'https://economictimes.indiatimes.com/news/international/rssfeeds/1715249782.cms',
    ],
    'tech': [
        'https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms',
        'https://www.livemint.com/rss/technology',
    ],
    'crypto': [
        'https://www.coindesk.com/arc/outboundfeeds/rss/',
    ],
    'ipos': [
        'https://www.moneycontrol.com/rss/ipo.xml',
    ],
}

class NewsAggregator:
    """
    Aggregates news from multiple external sources
    IMPORTANT: No news data is persisted to database
    """

    @staticmethod
    def normalize_news_item(item: Dict, source: str, category: str) -> Dict:
        """Normalize news item to common format"""
        return {
            'title': item.get('title', ''),
            'summary': item.get('summary', item.get('description', '')),
            'sourceName': source,
            'sourceUrl': item.get('url', item.get('link', '')),
            'publishedAt': item.get('publishedAt', item.get('published', datetime.now().isoformat())),
            'category': category,
            'imageUrl': item.get('urlToImage', item.get('image', None))
        }

    @staticmethod
    def fetch_from_newsapi(category: str = 'business', country: str = 'in') -> List[Dict]:
        """Fetch news from NewsAPI.org"""
        if not NEWS_API_KEY:
            print("[NewsAPI] API key not configured")
            return []

        try:
            url = 'https://newsapi.org/v2/top-headlines'
            params = {
                'apiKey': NEWS_API_KEY,
                'category': category,
                'country': country,
                'pageSize': 20
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            articles = data.get('articles', [])

            return [
                NewsAggregator.normalize_news_item(
                    {
                        'title': article.get('title'),
                        'description': article.get('description'),
                        'url': article.get('url'),
                        'urlToImage': article.get('urlToImage'),
                        'publishedAt': article.get('publishedAt')
                    },
                    article.get('source', {}).get('name', 'NewsAPI'),
                    category
                )
                for article in articles if article.get('title')
            ]
        except Exception as e:
            print(f"[NewsAPI] Error fetching news: {e}")
            return []

    @staticmethod
    def _extract_rss_image(entry) -> Optional[str]:
        """Try every common RSS image location. Indian feeds vary wildly."""
        # 1. media:content (Bloomberg, CNBC)
        media_content = entry.get('media_content') or []
        for m in media_content:
            url = m.get('url')
            if url:
                return url

        # 2. media:thumbnail (LiveMint, some ET feeds)
        media_thumb = entry.get('media_thumbnail') or []
        for m in media_thumb:
            url = m.get('url')
            if url:
                return url

        # 3. enclosures (MoneyControl, NSE)
        for enc in entry.get('enclosures', []) or []:
            url = enc.get('url') or enc.get('href')
            etype = (enc.get('type') or '').lower()
            if url and (etype.startswith('image/') or not etype):
                return url

        # 4. links with rel=enclosure
        for link in entry.get('links', []) or []:
            if link.get('rel') == 'enclosure':
                url = link.get('href')
                etype = (link.get('type') or '').lower()
                if url and (etype.startswith('image/') or not etype):
                    return url

        # 5. inline <img> in summary/description/content (ET, MoneyControl fallback)
        html_blobs = [
            entry.get('summary', ''),
            entry.get('description', ''),
        ]
        for c in entry.get('content', []) or []:
            html_blobs.append(c.get('value', ''))
        for blob in html_blobs:
            if not blob:
                continue
            m = _IMG_SRC_RE.search(blob)
            if m:
                return m.group(1)

        return None

    @staticmethod
    def fetch_from_rss(feed_url: str, category: str) -> List[Dict]:
        """Fetch news from RSS feed with timeout"""
        try:
            # Fetch with timeout to prevent hanging
            response = requests.get(feed_url, timeout=5)
            feed = feedparser.parse(response.content)
            source_name = feed.feed.get('title', 'RSS Feed')

            news_items = []
            for entry in feed.entries[:15]:  # Limit to 15 items per feed
                news_items.append(
                    NewsAggregator.normalize_news_item(
                        {
                            'title': entry.get('title'),
                            'summary': entry.get('summary', entry.get('description', '')),
                            'link': entry.get('link'),
                            'published': entry.get('published', ''),
                            'image': NewsAggregator._extract_rss_image(entry),
                        },
                        source_name,
                        category
                    )
                )

            return news_items
        except Exception as e:
            print(f"[RSS] Error fetching from {feed_url}: {e}")
            return []

    @staticmethod
    def fetch_alpha_vantage_news(tickers: Optional[str] = None) -> List[Dict]:
        """Fetch news from Alpha Vantage"""
        if not ALPHA_VANTAGE_KEY:
            print("[AlphaVantage] API key not configured")
            return []

        try:
            url = 'https://www.alphavantage.co/query'
            params = {
                'function': 'NEWS_SENTIMENT',
                'apikey': ALPHA_VANTAGE_KEY,
                'limit': 20
            }

            if tickers:
                params['tickers'] = tickers

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            feed = data.get('feed', [])

            return [
                NewsAggregator.normalize_news_item(
                    {
                        'title': item.get('title'),
                        'summary': item.get('summary'),
                        'url': item.get('url'),
                        'publishedAt': item.get('time_published'),
                        'urlToImage': item.get('banner_image')
                    },
                    item.get('source', 'Alpha Vantage'),
                    'market'
                )
                for item in feed
            ]
        except Exception as e:
            print(f"[AlphaVantage] Error fetching news: {e}")
            return []

    @staticmethod
    def get_news(category: str = 'all', region: str = 'indian', limit: int = 50) -> Dict:
        """
        Get aggregated news from all sources

        Args:
            category: News category (all, indian_markets, global_markets, nse, bse, ipos, economy, banking, corporate)
            region: indian | global
            limit: Maximum number of articles

        Returns:
            Dictionary with success status and news data
        """
        # Check cache first
        cache_key = f"news_{category}_{region}"
        cached_data = news_cache.get(cache_key)
        if cached_data:
            print(f"[NewsAggregator] Returning cached news for {cache_key}")
            return cached_data

        all_news = []

        # Build list of fetch tasks to run in parallel
        tasks = []
        if category in RSS_FEEDS:
            for feed_url in RSS_FEEDS[category]:
                tasks.append(('rss', feed_url, category))
        elif category == 'all':
            for cat, feeds in RSS_FEEDS.items():
                for feed_url in feeds:
                    tasks.append(('rss', feed_url, cat))

        if NEWS_API_KEY:
            tasks.append(('newsapi', region, 'business'))
            if category == 'all':
                # Also fetch general & technology news for trending coverage
                tasks.append(('newsapi', region, 'general'))
                tasks.append(('newsapi', region, 'technology'))
        if ALPHA_VANTAGE_KEY and category in ['nse', 'bse', 'all']:
            tasks.append(('alphavantage', None, category))

        # Fetch all sources in parallel (max 5 seconds total)
        def _fetch(task):
            source_type, arg1, arg2 = task
            if source_type == 'rss':
                return NewsAggregator.fetch_from_rss(arg1, arg2)
            elif source_type == 'newsapi':
                country = 'in' if arg1 == 'indian' else 'us'
                return NewsAggregator.fetch_from_newsapi(arg2, country)
            elif source_type == 'alphavantage':
                return NewsAggregator.fetch_alpha_vantage_news()
            return []

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_fetch, t): t for t in tasks}
            for future in as_completed(futures, timeout=8):
                try:
                    all_news.extend(future.result())
                except Exception:
                    pass

        # Remove duplicates based on title similarity
        unique_news = NewsAggregator.deduplicate_news(all_news)

        # Filter out news older than 1 month
        unique_news = NewsAggregator.filter_recent(unique_news, max_age_days=30)

        # Sort by published date (newest first)
        unique_news.sort(key=lambda x: x.get('publishedAt', ''), reverse=True)

        # Limit results
        unique_news = unique_news[:limit]

        result = {
            'success': True,
            'data': unique_news,
            'count': len(unique_news),
            'category': category,
            'region': region,
            'timestamp': datetime.now().isoformat(),
            'disclaimer': 'News content is aggregated from publicly available sources. WelthWest does not claim ownership.'
        }

        # Cache the result
        news_cache.set(cache_key, result)

        return result

    @staticmethod
    def filter_recent(news_list: List[Dict], max_age_days: int = 30) -> List[Dict]:
        """Filter out news older than max_age_days"""
        from dateutil import parser as dateparser
        cutoff = datetime.now() - timedelta(days=max_age_days)
        filtered = []
        for item in news_list:
            pub_date = item.get('publishedAt', '')
            if pub_date:
                try:
                    parsed = dateparser.parse(str(pub_date))
                    if parsed.tzinfo:
                        parsed = parsed.replace(tzinfo=None)
                    if parsed < cutoff:
                        continue
                except Exception:
                    pass  # Can't parse date — include it
            filtered.append(item)
        return filtered

    @staticmethod
    def deduplicate_news(news_list: List[Dict]) -> List[Dict]:
        """Remove duplicate news items based on title similarity"""
        seen_titles = set()
        unique_news = []

        for item in news_list:
            title_lower = item.get('title', '').lower().strip()
            if title_lower and title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_news.append(item)

        return unique_news

    @staticmethod
    def search_news(query: str, category: str = 'all', limit: int = 20) -> Dict:
        """Search news by query"""
        # Get all news first
        all_news_result = NewsAggregator.get_news(category=category, limit=100)

        if not all_news_result['success']:
            return all_news_result

        all_news = all_news_result['data']
        query_lower = query.lower()

        # Filter by query
        filtered_news = [
            item for item in all_news
            if query_lower in item.get('title', '').lower() or
               query_lower in item.get('summary', '').lower()
        ]

        filtered_news = filtered_news[:limit]

        return {
            'success': True,
            'data': filtered_news,
            'count': len(filtered_news),
            'query': query,
            'category': category,
            'disclaimer': 'News content is aggregated from publicly available sources. WelthWest does not claim ownership.'
        }


# Cleanup expired cache periodically
def cleanup_cache():
    """Clean up expired cache entries"""
    news_cache.clear_expired()
