"""
News Intelligence Pipeline - Orchestrates the full news-to-article pipeline
Fetches → Dedupes → Clusters → Analyzes → Writes → Publishes
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)


class NewsIntelligence:
    def __init__(self, db):
        from models.raw_news import RawNews
        from models.market_article import MarketArticle
        from services.news_aggregator import NewsAggregator
        from services.article_writer import ArticleWriter

        self.raw_news = RawNews(db)
        self.market_article = MarketArticle(db)
        self.news_aggregator = NewsAggregator()
        self.writer = ArticleWriter()

    # ── Step 1: Ingest ─────────────────────────────────────────

    def ingest(self) -> int:
        """Fetch news from all sources and store new items"""
        logger.info("Starting news ingestion...")

        # Fetch from all categories
        all_items = []
        for category in ['all', 'indian_markets', 'global_markets', 'economy', 'banking']:
            try:
                result = self.news_aggregator.get_news(category=category, limit=30)
                if result.get('success'):
                    all_items.extend(result.get('data', []))
            except Exception as e:
                logger.warning(f"Failed to fetch category {category}: {e}")

        if not all_items:
            logger.info("No news items fetched")
            return 0

        # Filter out news older than 3 days
        cutoff = datetime.utcnow() - timedelta(days=3)
        fresh_items = []
        for item in all_items:
            pub_date = item.get('publishedAt', item.get('published_at', ''))
            if pub_date:
                try:
                    parsed = dateparser.parse(str(pub_date))
                    if parsed.tzinfo:
                        parsed = parsed.replace(tzinfo=None)
                    if parsed < cutoff:
                        continue
                except Exception:
                    pass  # If we can't parse the date, include it
            fresh_items.append(item)

        logger.info(f"Filtered to {len(fresh_items)} fresh items from {len(all_items)} total")
        all_items = fresh_items

        if not all_items:
            logger.info("No fresh news items after date filtering")
            return 0

        saved = self.raw_news.save_batch(all_items)
        logger.info(f"Ingested {saved} new items from {len(all_items)} total fetched")
        return saved

    # ── Step 2: Cluster ────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> set:
        """Simple word tokenization for clustering"""
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'in', 'on', 'at',
            'to', 'for', 'of', 'and', 'or', 'but', 'with', 'by', 'from',
            'as', 'its', 'it', 'has', 'have', 'had', 'be', 'been', 'will',
            'can', 'could', 'would', 'should', 'may', 'might', 'this', 'that',
            'these', 'those', 'not', 'no', 'so', 'than', 'after', 'before',
            'up', 'down', 'over', 'under', 'into', 'out', 'about', 'more',
        }
        words = set(text.lower().split())
        return words - stop_words

    @staticmethod
    def _jaccard_similarity(set_a: set, set_b: set) -> float:
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    def cluster(self, items: List[dict], threshold: float = 0.3) -> List[List[dict]]:
        """Cluster related news items using Jaccard similarity on titles"""
        if not items:
            return []

        # Tokenize all titles
        tokenized = [(item, self._tokenize(item.get('title', ''))) for item in items]
        used = set()
        clusters = []

        for i, (item_a, tokens_a) in enumerate(tokenized):
            if i in used:
                continue

            cluster = [item_a]
            used.add(i)

            for j, (item_b, tokens_b) in enumerate(tokenized):
                if j in used or j <= i:
                    continue
                sim = self._jaccard_similarity(tokens_a, tokens_b)
                if sim >= threshold:
                    cluster.append(item_b)
                    used.add(j)

            clusters.append(cluster)

        # Sort by cluster size (bigger clusters = more important news)
        clusters.sort(key=len, reverse=True)

        logger.info(f"Formed {len(clusters)} clusters from {len(items)} items")
        return clusters

    # ── Step 3: Process ────────────────────────────────────────

    def process_cluster(self, cluster: List[dict]) -> dict:
        """Process a single cluster: analyze + write + save"""
        cluster_id = str(uuid.uuid4())[:8]

        try:
            # AI analysis + writing
            article_data = self.writer.process_cluster(cluster)

            # Add source references
            source_ids = [str(item.get('_id', '')) for item in cluster if item.get('_id')]
            article_data['source_articles'] = source_ids

            # Quality check
            content = article_data.get('content', '')
            if len(content) < 500:
                logger.warning(f"Cluster {cluster_id}: Article too short ({len(content)} chars), skipping")
                return {'success': False, 'reason': 'too_short'}

            if not article_data.get('title'):
                logger.warning(f"Cluster {cluster_id}: No title generated, skipping")
                return {'success': False, 'reason': 'no_title'}

            # Save to database
            article = self.market_article.create(article_data)

            # Mark raw news as processed
            raw_ids = [item.get('_id') for item in cluster if item.get('_id')]
            if raw_ids:
                self.raw_news.mark_processed(raw_ids, cluster_id)

            logger.info(f"Published article: {article.get('title', '')[:60]}")
            return {'success': True, 'slug': article.get('slug'), 'title': article.get('title')}

        except Exception as e:
            logger.error(f"Cluster {cluster_id} processing failed: {e}")
            # Still mark as processed to avoid retrying bad clusters
            raw_ids = [item.get('_id') for item in cluster if item.get('_id')]
            if raw_ids:
                self.raw_news.mark_processed(raw_ids, cluster_id)
            return {'success': False, 'reason': str(e)}

    # ── Full Pipeline ──────────────────────────────────────────

    def run_pipeline(self, max_articles: int = 10) -> dict:
        """Run the full pipeline: ingest → cluster → process → publish"""
        start = datetime.utcnow()
        logger.info("=== News Intelligence Pipeline Starting ===")

        results = {
            'ingested': 0,
            'clusters': 0,
            'published': 0,
            'failed': 0,
            'articles': [],
            'errors': [],
        }

        # Step 1: Ingest
        try:
            results['ingested'] = self.ingest()
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            results['errors'].append(f"Ingestion: {str(e)}")

        # Step 2: Get unprocessed and cluster
        unprocessed = self.raw_news.get_unprocessed(limit=100)
        if not unprocessed:
            logger.info("No unprocessed news to work with")
            results['duration_seconds'] = (datetime.utcnow() - start).total_seconds()
            return results

        clusters = self.cluster(unprocessed)
        results['clusters'] = len(clusters)

        # Step 3: Process clusters (up to max_articles)
        # Prioritize clusters with 2+ articles (multi-source synthesis)
        multi_source = [c for c in clusters if len(c) >= 2]
        single_source = [c for c in clusters if len(c) == 1]

        # Process multi-source first, then fill with singles if needed
        to_process = multi_source[:max_articles]
        remaining = max_articles - len(to_process)
        if remaining > 0:
            to_process.extend(single_source[:remaining])

        for cluster in to_process:
            result = self.process_cluster(cluster)
            if result.get('success'):
                results['published'] += 1
                results['articles'].append({
                    'slug': result.get('slug'),
                    'title': result.get('title'),
                })
            else:
                results['failed'] += 1
                results['errors'].append(result.get('reason', 'unknown'))

        # Step 4: Cleanup old raw news (older than 7 days)
        try:
            self.raw_news.cleanup_old(days=7)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

        duration = (datetime.utcnow() - start).total_seconds()
        results['duration_seconds'] = duration

        logger.info(
            f"=== Pipeline Complete: {results['published']} published, "
            f"{results['failed']} failed, {duration:.1f}s ==="
        )

        return results
