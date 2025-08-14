import os
import logging
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import Optional


logger = logging.getLogger(__name__)


class KeepAliveScheduler:
    """Background scheduler to ping the server periodically to keep it warm."""

    def __init__(self) -> None:
        self._scheduler: Optional[BackgroundScheduler] = None

    def _get_base_url(self) -> str | None:
        # Prefer explicit keep-alive URL if provided; otherwise try Render external URL; fallback to BASE_URL
        return (
            os.environ.get("KEEP_ALIVE_URL")
            or os.environ.get("RENDER_EXTERNAL_URL")
            or os.environ.get("BASE_URL")
        )

    def _ping(self) -> None:
        base_url = self._get_base_url()
        if not base_url:
            logger.warning("KeepAliveScheduler: No KEEP_ALIVE_URL/RENDER_EXTERNAL_URL/BASE_URL set; skipping ping")
            return
        url = base_url.rstrip("/") + "/market-indices"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                logger.info("KeepAliveScheduler: ping OK %s", url)
            else:
                logger.warning("KeepAliveScheduler: ping non-200 %s -> %s", url, resp.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.error("KeepAliveScheduler: ping failed %s -> %s", url, exc)

    def start(self, minutes: int = 10) -> None:
        if self._scheduler and self._scheduler.running:
            logger.info("KeepAliveScheduler: already running")
            return
        try:
            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                func=self._ping,
                trigger=IntervalTrigger(minutes=minutes),
                id="keep_alive_ping",
                name=f"Keep server active every {minutes} minutes",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            self._scheduler.start()
            logger.info("KeepAliveScheduler: started (interval=%s min)", minutes)
            # Fire once immediately
            self._ping()
        except Exception as exc:  # noqa: BLE001
            logger.error("KeepAliveScheduler: failed to start -> %s", exc)

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("KeepAliveScheduler: stopped")


# Singleton instance to import in app
keep_alive_scheduler = KeepAliveScheduler()


