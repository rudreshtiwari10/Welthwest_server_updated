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

# How much topic overlap (Jaccard, on tags + sector + affected_stocks) a
# new article needs with an already-published one before it's skipped as
# a duplicate. Checked on topic signature, not title wording — see
# _topic_signature() and process_cluster().
#
# MAX_DAYS_APART matters more than the threshold above: run against the
# real corpus (backfill_dedup_canonicals.py), topic overlap alone
# clustered genuinely different stories — e.g. an Nvidia AI-safety piece
# and a SpaceX AI-funding piece, ~0.7 overlap on shared tags/sector/
# tickers, but 105 days apart and about unrelated events. A real
# same-story duplicate (two "Middle East de-escalation" pieces) was
# published hours apart, same day, 0.88 overlap. Time proximity is what
# actually separates "same recurring sector" from "same specific event" —
# topic overlap alone can't.
DUPLICATE_TOPIC_THRESHOLD = 0.4
MAX_DAYS_APART = 5
DUPLICATE_LOOKBACK_DAYS = 21


class NewsIntelligence:
    def __init__(self, db):
        from models.raw_news import RawNews
        from models.market_article import MarketArticle
        from services.news_aggregator import NewsAggregator
        from services.article_writer import ArticleWriter
        from services.image_service import ImageService

        self.raw_news = RawNews(db)
        self.market_article = MarketArticle(db)
        self.news_aggregator = NewsAggregator()
        self.writer = ArticleWriter()
        self.image_service = ImageService()

    # ── Step 1: Ingest ─────────────────────────────────────────

    def ingest(self) -> int:
        """Fetch news from all sources and store new items"""
        logger.info("Starting news ingestion...")

        # Fetch from all categories (including trending, geopolitics, tech, crypto, ipos)
        all_items = []
        for category in ['all', 'indian_markets', 'global_markets', 'economy', 'banking', 'trending', 'geopolitics', 'tech', 'crypto', 'ipos']:
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

    @staticmethod
    def _topic_signature(article_data: dict) -> set:
        """Tags + sector + affected stocks, lowercased, as a set.

        Title wording alone is a weak duplication signal here — the writer
        rephrases freely, so two articles about the same recurring macro
        story (e.g. Iran tensions -> oil -> Indian stocks) can share almost
        no words in their headlines. Tags/sector/affected_stocks describe
        WHAT the article is actually about, and are far more stable across
        independently-written coverage of the same underlying story.
        """
        sig = set()
        for tag in article_data.get('tags', []) or []:
            sig.add(str(tag).strip().lower())
        sector = article_data.get('sector')
        if sector:
            sig.add(str(sector).strip().lower())
        for stock in article_data.get('affected_stocks', []) or []:
            sig.add(str(stock).strip().lower())
        return sig

    def process_cluster(self, cluster: List[dict], recent_articles: List[dict] = None) -> dict:
        """Process a single cluster: analyze + write + save.

        `recent_articles` (tags/sector/affected_stocks/title/slug for
        everything published in the last DUPLICATE_LOOKBACK_DAYS) lets this
        catch a recurring macro story that resurfaces in the source feed
        every few days — `cluster()` below only de-dupes items within a
        single ingest batch, so without this a story like "Iran tensions"
        or "Bitcoin price move" gets written up fresh every single time it
        recurs, with no awareness of WelthWest's own prior near-identical
        coverage. Checked after writing (not before) because the topic
        signature this relies on — tags/sector/affected_stocks — only
        exists once the writer has analysed the cluster.
        """
        cluster_id = str(uuid.uuid4())[:8]

        try:
            # AI analysis + writing
            article_data = self.writer.process_cluster(cluster)

            # Add source references
            source_ids = [str(item.get('_id', '')) for item in cluster if item.get('_id')]
            article_data['source_articles'] = source_ids

            # Quality check
            content = article_data.get('content', '')
            if len(content) < 1500:
                logger.warning(f"Cluster {cluster_id}: Article too short ({len(content)} chars), skipping")
                return {'success': False, 'reason': 'too_short'}

            if not article_data.get('title'):
                logger.warning(f"Cluster {cluster_id}: No title generated, skipping")
                return {'success': False, 'reason': 'no_title'}

            # De-dup against our own recent coverage by topic, not title
            # wording — see _topic_signature() and process_cluster() docstring.
            # Also requires the match to be within MAX_DAYS_APART: topic
            # overlap alone can't tell "same specific event" from "same
            # recurring sector" (see module-level comment) — time proximity
            # is the signal that actually distinguishes them.
            if recent_articles:
                new_sig = self._topic_signature(article_data)
                if new_sig:
                    now = datetime.utcnow()
                    for recent in recent_articles:
                        published_at = recent.get('published_at')
                        if published_at and (now - published_at).days > MAX_DAYS_APART:
                            continue
                        sim = self._jaccard_similarity(new_sig, self._topic_signature(recent))
                        if sim >= DUPLICATE_TOPIC_THRESHOLD:
                            logger.info(
                                f"Cluster {cluster_id}: skipping '{article_data.get('title')}' — "
                                f"{sim:.2f} topic overlap with recently published "
                                f"'{recent.get('title')}' ({recent.get('slug')})"
                            )
                            raw_ids = [item.get('_id') for item in cluster if item.get('_id')]
                            if raw_ids:
                                self.raw_news.mark_processed(raw_ids, cluster_id)
                            return {'success': False, 'reason': 'duplicate_of_recent'}

            # Source and upload article image
            try:
                image_url = self.image_service.get_article_image(cluster, article_data)
                if image_url:
                    article_data['image_url'] = image_url
                    logger.info(f"Cluster {cluster_id}: Image sourced → {image_url[:80]}")
            except Exception as e:
                logger.warning(f"Cluster {cluster_id}: Image sourcing failed (non-fatal): {e}")

            # Save to database
            article = self.market_article.create(article_data)

            # Mark raw news as processed
            raw_ids = [item.get('_id') for item in cluster if item.get('_id')]
            if raw_ids:
                self.raw_news.mark_processed(raw_ids, cluster_id)

            logger.info(f"Published article: {article.get('title', '')[:60]}")
            return {
                'success': True,
                'slug': article.get('slug'),
                'title': article.get('title'),
                'tags': article.get('tags', []),
                'sector': article.get('sector'),
                'affected_stocks': article.get('affected_stocks', []),
            }

        except Exception as e:
            logger.error(f"Cluster {cluster_id} processing failed: {e}")
            # Still mark as processed to avoid retrying bad clusters
            raw_ids = [item.get('_id') for item in cluster if item.get('_id')]
            if raw_ids:
                self.raw_news.mark_processed(raw_ids, cluster_id)
            return {'success': False, 'reason': str(e)}

    # ── Full Pipeline ──────────────────────────────────────────

    def run_pipeline(self, max_articles: int = 5) -> dict:
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

        # Process multi-source first, then fill with trending singles
        to_process = multi_source[:max_articles]
        remaining = max_articles - len(to_process)
        if remaining > 0:
            # Pick single-source items that are likely trending/important
            to_process.extend(single_source[:remaining])

        # Recent published articles' topic data, so a recurring story
        # (Iran/oil, Bitcoin swings, ...) that resurfaces in the feed
        # doesn't get written up as "new" every time — see
        # process_cluster() / _topic_signature(). Fetched once per run and
        # extended below as this run publishes, so two similar clusters
        # processed in the same run also catch each other even if
        # cluster() didn't merge them.
        try:
            recent_articles = self.market_article.get_recent_topics(days=DUPLICATE_LOOKBACK_DAYS)
        except Exception as e:
            logger.warning(f"Could not load recent articles for de-dup, proceeding without it: {e}")
            recent_articles = []

        for cluster in to_process:
            result = self.process_cluster(cluster, recent_articles=recent_articles)
            if result.get('success'):
                results['published'] += 1
                results['articles'].append({
                    'slug': result.get('slug'),
                    'title': result.get('title'),
                })
                recent_articles.append({
                    'title': result.get('title'),
                    'slug': result.get('slug'),
                    'tags': result.get('tags', []),
                    'sector': result.get('sector'),
                    'affected_stocks': result.get('affected_stocks', []),
                    'published_at': datetime.utcnow(),
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
