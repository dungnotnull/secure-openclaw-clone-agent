from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._jobs: list[dict] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def add_job(
        self,
        func,
        *,
        interval_seconds: int = 3600,
        run_immediately: bool = False,
        name: str = "job",
    ) -> None:
        self._jobs.append({
            "func": func,
            "interval": interval_seconds,
            "name": name,
            "last_run": None if run_immediately else datetime.now(timezone.utc),
        })
        logger.info("Scheduler: registered job '%s' (every %ds)", name, interval_seconds)

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="scheduler-loop")
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            now = datetime.now(timezone.utc)
            for job in self._jobs:
                should_run = False
                if job["last_run"] is None:
                    should_run = True
                else:
                    elapsed = (now - job["last_run"]).total_seconds()
                    if elapsed >= job["interval"]:
                        should_run = True
                if should_run:
                    try:
                        await job["func"]()
                    except Exception as exc:
                        logger.error(
                            "Scheduler job '%s' failed: %s", job["name"], exc
                        )
                    job["last_run"] = now
            await asyncio.sleep(10)


_scheduler: Scheduler | None = None


def get_scheduler() -> Scheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


async def weekly_crawl_job() -> None:
    from backend.core.knowledge.crawler import get_knowledge_crawler
    crawler = get_knowledge_crawler()
    papers = await crawler.crawl()
    if papers:
        count = crawler.append_to_brain(papers)
        logger.info("Weekly crawl: added %d papers", count)
    else:
        logger.info("Weekly crawl: no new papers found")
