"""Background worker that drains the durable workflow job queue."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from collections.abc import Awaitable, Callable

from app.core.config import settings
from app.core import database
from app.services.job_queue import claim_job, complete_job, sweep_orphans
from app.workflows.runner import run_workflow_in_new_session

logger = logging.getLogger(__name__)

Executor = Callable[[str], Awaitable[None]]


class WorkflowWorker:
    """Claim and execute jobs; one worker loop per process by default."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._executor: Executor = executor or run_workflow_in_new_session
        self._stop = asyncio.Event()
        self._last_sweep = 0.0

    async def run_once(self) -> bool:
        async with database.SessionLocal() as session:
            job = await claim_job(session, self.worker_id)
        if job is None:
            return False

        try:
            await self._executor(job.workflow_id)
        except Exception as exc:
            logger.exception("Workflow job %s failed", job.id)
            async with database.SessionLocal() as session:
                await complete_job(session, job.id, error=str(exc))
        else:
            async with database.SessionLocal() as session:
                await complete_job(session, job.id)
        return True

    async def _maybe_sweep(self) -> None:
        now = time.monotonic()
        if now - self._last_sweep < settings.JOB_SWEEP_SECONDS:
            return
        self._last_sweep = now
        try:
            async with database.SessionLocal() as session:
                await sweep_orphans(session)
        except Exception:
            logger.exception("Workflow job sweep failed")

    async def run_forever(self) -> None:
        logger.info("Workflow worker %s started", self.worker_id)
        try:
            while not self._stop.is_set():
                try:
                    processed = await self.run_once()
                    await self._maybe_sweep()
                    if not processed:
                        await asyncio.wait_for(
                            self._stop.wait(), timeout=settings.WORKER_POLL_SECONDS
                        )
                except (asyncio.TimeoutError, TimeoutError):
                    continue
                except Exception:
                    logger.exception("Workflow worker loop error")
                    await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("Workflow worker %s cancelled", self.worker_id)
            raise
        finally:
            logger.info("Workflow worker %s stopped", self.worker_id)

    def stop(self) -> None:
        self._stop.set()