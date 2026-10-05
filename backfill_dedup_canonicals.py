"""
One-time backfill: find near-duplicate published articles and point each
duplicate's SEO canonical at the most complete article in its cluster.

Context: services/news_intelligence.py now skips writing a new article
if its topic (tags + sector + affected_stocks) overlaps something
published nearby in time — but that only stops NEW duplicates. Google's
Coverage report showed ~1,454 already-published articles it crawled but
declined to index, heavily clustered around a handful of recurring
narratives (Iran/oil, Bitcoin swings) covered many times over with
different headlines. This script finds those existing clusters across
the WHOLE corpus (not just a rolling window) using the exact same
topic-signature Jaccard + time-proximity logic, and sets
`canonical_slug` on every non-canonical article in a cluster.

Topic overlap alone is NOT enough to call two articles duplicates — a
first pass against the real corpus clustered an Nvidia AI-safety piece
with a SpaceX AI-funding piece (~0.7 tag/sector/ticker overlap) despite
them being unrelated events 105 days apart, because anything in a "hot"
recurring sector (AI/IT, oil/geopolitics) shares the same handful of
generic tags and tickers regardless of the actual triggering event. Real
duplicates (two "Middle East de-escalation" pieces) were published hours
apart. MAX_DAYS_APART (imported from news_intelligence) requires articles
to also be close in time before they're considered the same story.

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

from services.news_intelligence import NewsIntelligence, DUPLICATE_TOPIC_THRESHOLD, MAX_DAYS_APART

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def _days_apart(a: dict, b: dict) -> float:
    """Inf if either is missing published_at — never treated as close enough."""
    pa, pb = a.get('published_at'), b.get('published_at')
    if not pa or not pb:
        return float('inf')
    return abs((pa - pb).days)


def find_clusters(articles: list, threshold: float = DUPLICATE_TOPIC_THRESHOLD,
                   max_days_apart: int = MAX_DAYS_APART) -> list:
    """Same greedy approach as NewsIntelligence.cluster(), but run once
    across the whole corpus on topic signatures instead of per-batch on
    title tokens, and additionally requiring articles to be close in time
    — see module docstring for why topic overlap alone isn't enough.
    O(n^2) in the number of articles — fine for a one-time script against
    a few thousand articles; re-block by shared tag first if this ever
    needs to run against a much larger corpus."""
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
            if _days_apart(a_i, a_j) > max_days_apart:
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

    raw_clusters = find_clusters(articles)

    # find_clusters() only verifies each member against the greedy SEED it
    # was added against — not against whichever member pick_canonical()
    # ultimately chooses (longest content, which can be a different
    # article). A same-topic chain spanning up to 2x MAX_DAYS_APART can
    # pass clustering this way (A-B within range, A-C within range, but
    # B-C out of range) and silently violate the constraint once one end
    # of the chain is picked as canonical. Re-verify every duplicate
    # against the ACTUAL canonical here and drop any that fail either
    # check against it specifically, rather than trusting cluster
    # membership alone.
    clusters = []
    for cluster in raw_clusters:
        canonical = pick_canonical(cluster)
        canon_sig = NewsIntelligence._topic_signature(canonical)
        kept = [canonical]
        for a in cluster:
            if a['slug'] == canonical['slug']:
                continue
            sim = NewsIntelligence._jaccard_similarity(canon_sig, NewsIntelligence._topic_signature(a))
            if sim >= DUPLICATE_TOPIC_THRESHOLD and _days_apart(canonical, a) <= MAX_DAYS_APART:
                kept.append(a)
        if len(kept) > 1:
            clusters.append(kept)

    duplicate_count = sum(len(c) - 1 for c in clusters)
    logger.info(f"Found {len(clusters)} duplicate clusters, covering {duplicate_count} "
                f"articles that would get a canonical_slug pointing elsewhere.\n")

    all_scores = []
    for cluster in clusters:
        canonical = cluster[0]  # already the chosen canonical, from the re-verification pass above
        canon_sig = NewsIntelligence._topic_signature(canonical)
        others = cluster[1:]
        logger.info(f"Cluster ({len(cluster)} articles) -> canonical: "
                    f"'{canonical['title']}' ({canonical['slug']}, {canonical.get('content_length', 0)} chars)")
        for a in others:
            sim = NewsIntelligence._jaccard_similarity(canon_sig, NewsIntelligence._topic_signature(a))
            days = _days_apart(canonical, a)
            all_scores.append(sim)
            logger.info(f"    duplicate: '{a['title']}' ({a['slug']}, {a.get('content_length', 0)} chars, "
                        f"sim={sim:.2f}, {days:.0f}d apart)")
            if args.apply:
                market_article.update(a['slug'], {'canonical_slug': canonical['slug']})
        logger.info("")

    if all_scores:
        all_scores.sort()
        # Explicit comparisons, not arithmetic on the float, to bucket this —
        # (s - 0.4) / 0.1 looks equivalent but isn't: 0.5 - 0.4 is
        # 0.09999999999999998 in IEEE 754, not exactly 0.1, so int() truncated
        # plenty of boundary scores (0.50 itself included) into the wrong
        # bucket. Purely a display bug — the actual threshold check above
        # uses direct float comparison and was never affected by this.
        bounds = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]  # upper bound nudged past 1.0 to include an exact 1.0 score
        buckets = [0] * (len(bounds) - 1)
        for s in all_scores:
            for i in range(len(buckets)):
                if bounds[i] <= s < bounds[i + 1]:
                    buckets[i] += 1
                    break
        logger.info("Similarity score distribution (helps pick a threshold by looking at "
                    "the actual data instead of guessing):")
        for i, count in enumerate(buckets):
            logger.info(f"    {bounds[i]:.1f}-{bounds[i + 1]:.1f}: {count}")
        logger.info("")

    if args.apply:
        logger.info(f"Done — set canonical_slug on {duplicate_count} articles.")
    else:
        logger.info(f"Dry run only — nothing written. Re-run with --apply to write "
                     f"canonical_slug on the {duplicate_count} duplicates listed above.")


if __name__ == '__main__':
    main()
