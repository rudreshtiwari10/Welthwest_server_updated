"""
Performance Monitoring for API Endpoints

Tracks request duration, cache hit rates, and performance trends.

Usage:
    from middleware.performance_monitor import monitor

    # Track a request
    with monitor.track('get_top_shorts', timeframe='1h', cache_hit=False):
        result = do_work()

    # Or manually
    start = time.time()
    result = do_work()
    monitor.record('endpoint_name', time.time() - start, cache_hit=True)

    # Get statistics
    stats = monitor.get_stats()
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import contextmanager
from collections import defaultdict

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Track API endpoint performance and cache efficiency
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize performance monitor

        Args:
            max_history: Maximum number of requests to keep in history
        """
        self.max_history = max_history
        self.requests = []  # List of request records
        self.endpoint_stats = defaultdict(lambda: {
            'total_requests': 0,
            'cache_hits': 0,
            'total_duration_ms': 0,
            'durations': []
        })

    @contextmanager
    def track(self, endpoint: str, cache_hit: bool = False, **metadata):
        """
        Context manager to track request duration

        Args:
            endpoint: Endpoint name
            cache_hit: Whether result was from cache
            **metadata: Additional metadata (e.g., timeframe, user_id)

        Usage:
            with monitor.track('get_top_shorts', cache_hit=False, timeframe='1h'):
                result = expensive_operation()
        """
        start_time = time.time()
        error = None

        try:
            yield
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.time() - start_time
            self.record(
                endpoint=endpoint,
                duration_seconds=duration,
                cache_hit=cache_hit,
                error=error,
                **metadata
            )

    def record(
        self,
        endpoint: str,
        duration_seconds: float,
        cache_hit: bool = False,
        error: Optional[str] = None,
        **metadata
    ):
        """
        Record a request

        Args:
            endpoint: Endpoint name
            duration_seconds: Request duration in seconds
            cache_hit: Whether result was from cache
            error: Error message if request failed
            **metadata: Additional metadata
        """
        duration_ms = duration_seconds * 1000

        # Add to requests history
        record = {
            'endpoint': endpoint,
            'duration_ms': duration_ms,
            'cache_hit': cache_hit,
            'error': error,
            'timestamp': datetime.now(),
            **metadata
        }
        self.requests.append(record)

        # Keep only recent history
        if len(self.requests) > self.max_history:
            self.requests = self.requests[-self.max_history:]

        # Update endpoint stats
        stats = self.endpoint_stats[endpoint]
        stats['total_requests'] += 1
        if cache_hit:
            stats['cache_hits'] += 1
        stats['total_duration_ms'] += duration_ms
        stats['durations'].append(duration_ms)

        # Keep only recent durations for percentile calculations
        if len(stats['durations']) > 100:
            stats['durations'] = stats['durations'][-100:]

        # Log slow requests
        if duration_ms > 2000 and not cache_hit:
            logger.warning(
                f"Slow request: {endpoint} took {duration_ms:.1f}ms. "
                f"Metadata: {metadata}"
            )

    def get_stats(self, endpoint: Optional[str] = None, last_n: int = 100) -> Dict:
        """
        Get performance statistics

        Args:
            endpoint: Specific endpoint to get stats for (None = all)
            last_n: Number of recent requests to analyze

        Returns:
            Dictionary with performance statistics
        """
        if endpoint:
            return self._get_endpoint_stats(endpoint, last_n)

        # Get overall stats
        recent_requests = self.requests[-last_n:] if last_n else self.requests

        if not recent_requests:
            return {
                'total_requests': 0,
                'cache_hit_rate': '0.0%',
                'avg_duration_ms': 0,
                'median_duration_ms': 0,
                'p95_duration_ms': 0,
                'p99_duration_ms': 0
            }

        durations = [r['duration_ms'] for r in recent_requests]
        cache_hits = sum(1 for r in recent_requests if r['cache_hit'])
        errors = sum(1 for r in recent_requests if r.get('error'))

        sorted_durations = sorted(durations)
        n = len(sorted_durations)

        stats = {
            'total_requests': len(recent_requests),
            'cache_hits': cache_hits,
            'cache_hit_rate': f"{(cache_hits / len(recent_requests)) * 100:.1f}%",
            'error_count': errors,
            'error_rate': f"{(errors / len(recent_requests)) * 100:.1f}%",
            'avg_duration_ms': sum(durations) / n,
            'median_duration_ms': sorted_durations[n // 2],
            'p95_duration_ms': sorted_durations[int(n * 0.95)] if n > 0 else 0,
            'p99_duration_ms': sorted_durations[int(n * 0.99)] if n > 0 else 0,
            'min_duration_ms': min(durations),
            'max_duration_ms': max(durations),
            'endpoints': list(self.endpoint_stats.keys())
        }

        return stats

    def _get_endpoint_stats(self, endpoint: str, last_n: int) -> Dict:
        """Get statistics for a specific endpoint"""
        endpoint_requests = [
            r for r in self.requests[-last_n:]
            if r['endpoint'] == endpoint
        ]

        if not endpoint_requests:
            return {
                'endpoint': endpoint,
                'total_requests': 0,
                'cache_hit_rate': '0.0%',
                'avg_duration_ms': 0
            }

        durations = [r['duration_ms'] for r in endpoint_requests]
        cache_hits = sum(1 for r in endpoint_requests if r['cache_hit'])
        errors = sum(1 for r in endpoint_requests if r.get('error'))

        sorted_durations = sorted(durations)
        n = len(sorted_durations)

        return {
            'endpoint': endpoint,
            'total_requests': len(endpoint_requests),
            'cache_hits': cache_hits,
            'cache_hit_rate': f"{(cache_hits / len(endpoint_requests)) * 100:.1f}%",
            'error_count': errors,
            'error_rate': f"{(errors / len(endpoint_requests)) * 100:.1f}%",
            'avg_duration_ms': sum(durations) / n,
            'median_duration_ms': sorted_durations[n // 2],
            'p95_duration_ms': sorted_durations[int(n * 0.95)] if n > 0 else 0,
            'p99_duration_ms': sorted_durations[int(n * 0.99)] if n > 0 else 0,
            'min_duration_ms': min(durations),
            'max_duration_ms': max(durations)
        }

    def get_recent_slow_requests(self, threshold_ms: float = 1000, limit: int = 10) -> List[Dict]:
        """
        Get recent slow requests

        Args:
            threshold_ms: Duration threshold in milliseconds
            limit: Maximum number of results

        Returns:
            List of slow request records
        """
        slow_requests = [
            r for r in reversed(self.requests)
            if r['duration_ms'] > threshold_ms and not r['cache_hit']
        ]

        return slow_requests[:limit]

    def get_timeline(self, minutes: int = 60, bucket_size_minutes: int = 5) -> Dict:
        """
        Get performance timeline

        Args:
            minutes: Number of minutes to look back
            bucket_size_minutes: Size of time buckets in minutes

        Returns:
            Dictionary with timeline data
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_requests = [
            r for r in self.requests
            if r['timestamp'] > cutoff_time
        ]

        if not recent_requests:
            return {'buckets': []}

        # Create time buckets
        buckets = []
        bucket_size = timedelta(minutes=bucket_size_minutes)
        current_bucket_start = cutoff_time

        while current_bucket_start < datetime.now():
            bucket_end = current_bucket_start + bucket_size

            # Filter requests in this bucket
            bucket_requests = [
                r for r in recent_requests
                if current_bucket_start <= r['timestamp'] < bucket_end
            ]

            if bucket_requests:
                durations = [r['duration_ms'] for r in bucket_requests]
                cache_hits = sum(1 for r in bucket_requests if r['cache_hit'])

                buckets.append({
                    'timestamp': current_bucket_start.isoformat(),
                    'count': len(bucket_requests),
                    'avg_duration_ms': sum(durations) / len(durations),
                    'cache_hit_rate': (cache_hits / len(bucket_requests)) * 100
                })

            current_bucket_start = bucket_end

        return {'buckets': buckets}

    def reset(self):
        """Reset all statistics"""
        self.requests.clear()
        self.endpoint_stats.clear()
        logger.info("Performance monitor reset")


# Singleton instance
_performance_monitor = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get singleton performance monitor instance"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


# Convenience instance
monitor = get_performance_monitor()
