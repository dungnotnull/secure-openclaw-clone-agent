from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

JobFunc = Callable[..., Awaitable[Any]]


class BackgroundRunner:
    def __init__(self, max_workers: int = 4) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._max_workers = max_workers

    async def start(self) -> None:
        self._running = True
        for i in range(self._max_workers):
            task = asyncio.create_task(self._worker(i), name=f"bg-worker-{i}")
            self._workers.append(task)

    async def stop(self) -> None:
        self._running = False
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(self, job: JobFunc, *args, **kwargs) -> None:
        await self._queue.put((job, args, kwargs))

    async def _worker(self, idx: int) -> None:
        logger.info("Background worker %d started", idx)
        while self._running:
            item = await self._queue.get()
            if item is None:
                break
            job, args, kwargs = item
            try:
                await job(*args, **kwargs)
            except Exception as exc:
                logger.error("Background job failed in worker %d: %s", idx, exc)
            finally:
                self._queue.task_done()
        logger.info("Background worker %d stopped", idx)


_runner: BackgroundRunner | None = None


def get_background_runner() -> BackgroundRunner:
    global _runner
    if _runner is None:
        _runner = BackgroundRunner()
    return _runner
