"""
One-time backfill: find near-duplicate published articles and point each
duplicate's SEO canonical at the most complete article in its cluster.

Context: services/news_intelligence.py now skips writing a new article
if its topic (tags + sector + affected_stocks) overlaps something
published in the last 21 days — but that only stops NEW duplicates.
Google's Coverage report showed ~1,454 already-published articles it
crawled but declined to index, heavily clustered around a handful of
recurring narratives (Iran/oil, Bitcoin swings) covered many times over
with different headlines. This script finds those existing clusters
across the WHOLE corpus (not just a rolling window) using the exact same
topic-signature Jaccard logic, and sets `canonical_slug` on every
non-canonical article in a cluster.

This does NOT touch, hide, redirect, or delete any article — every URL
stays fully live and fully functional for anyone who visits it directly.
It only changes what welthwestnews/src/app/news/[slug]/page.tsx emits as
that page's <link rel="canonical">, telling Google "index the canonical
one instead of this near-duplicate" while leaving this page itself
untouched. See SEO_CHANGELOG.md ("Existing near-duplicate articles") for
the full decision context — canonical-tag-only was chosen over 301
redirects specifically so no existing URL stops working.

Usage:
    python backfill_dedup_canonicals.py             # dry run — prints clusters, writes nothing
    python backfill_dedup_canonicals.py --apply      # writes canonical_slug on the duplicates
"""

import argparse
import logging

from services.news_intelligence import NewsIntelligence, DUPLICATE_TOPIC_THRESHOLD

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def find_clusters(articles: list, threshold: float = DUPLICATE_TOPIC_THRESHOLD) -> list:
    """Same greedy approach as NewsIntelligence.cluster(), but run once
    across the whole corpus on topic signatures instead of per-batch on
    title tokens. O(n^2) in the number of articles — fine for a one-time
    script against a few thousand articles; re-block by shared tag first
    if this ever needs to run against a much larger corpus."""
    signed = [(a, NewsIntelligence._topic_signature(a)) for a in articles]
    used = set()
    clusters = []

    for i, (a_i, sig_i) in enumerate(signed):
        if i in used or not sig_i:
            continue
        cluster = [a_i]
        used.add(i)
        for j in range(i + 1, len(signed)):
            if j in used:
                continue
            a_j, sig_j = signed[j]
            if not sig_j:
                continue
            if NewsIntelligence._jaccard_similarity(sig_i, sig_j) >= threshold:
                cluster.append(a_j)
                used.add(j)
        if len(cluster) > 1:
            clusters.append(cluster)

    return clusters


def pick_canonical(cluster: list) -> dict:
    """Most complete (longest) article wins; most recent breaks ties."""
    return sorted(
        cluster,
        key=lambda a: (a.get('content_length', 0), a.get('published_at') or ''),
        reverse=True,
    )[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                         help='Actually write canonical_slug (default: dry run, writes nothing)')
    args = parser.parse_args()

    from database import get_db
    from models.market_article import MarketArticle
    market_article = MarketArticle(get_db())

    logger.info("Loading all published articles...")
    articles = market_article.get_all_published_for_dedup()
    logger.info(f"Loaded {len(articles)} articles. Clustering (topic-overlap threshold={DUPLICATE_TOPIC_THRESHOLD})...\n")

    clusters = find_clusters(articles)
    duplicate_count = sum(len(c) - 1 for c in clusters)
    logger.info(f"Found {len(clusters)} duplicate clusters, covering {duplicate_count} "
                f"articles that would get a canonical_slug pointing elsewhere.\n")

    for cluster in clusters:
        canonical = pick_canonical(cluster)
        others = [a for a in cluster if a['slug'] != canonical['slug']]
        logger.info(f"Cluster ({len(cluster)} articles) -> canonical: "
                    f"'{canonical['title']}' ({canonical['slug']}, {canonical.get('content_length', 0)} chars)")
        for a in others:
            logger.info(f"    duplicate: '{a['title']}' ({a['slug']}, {a.get('content_length', 0)} chars)")
            if args.apply:
                market_article.update(a['slug'], {'canonical_slug': canonical['slug']})
        logger.info("")

    if args.apply:
        logger.info(f"Done — set canonical_slug on {duplicate_count} articles.")
    else:
        logger.info(f"Dry run only — nothing written. Re-run with --apply to write "
                     f"canonical_slug on the {duplicate_count} duplicates listed above.")


if __name__ == '__main__':
    main()
