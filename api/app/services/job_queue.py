"""Durable workflow job queue.

PostgreSQL uses `SELECT ... FOR UPDATE SKIP LOCKED`; SQLite (tests/dev without
Postgres) falls back to a conditional update. The conditional update is also the
final arbiter on Postgres, so two workers can never both own a job.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.job import WorkflowJob

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def enqueue_job(
    session: AsyncSession,
    workflow_id: str,
    *,
    delay_seconds: float = 0.0,
) -> WorkflowJob:
    job = WorkflowJob(
        id=str(uuid.uuid4()),
        workflow_id=workflow_id,
        status="queued",
        attempts=0,
        max_attempts=settings.JOB_MAX_ATTEMPTS,
        available_at=_now() + timedelta(seconds=delay_seconds),
    )
    session.add(job)
    return job


async def claim_job(session: AsyncSession, worker_id: str) -> WorkflowJob | None:
    """Claim one due job atomically. Returns None when the queue is empty."""
    candidate = await session.scalar(
        select(WorkflowJob)
        .where(
            WorkflowJob.status == "queued",
            WorkflowJob.available_at <= _now(),
            WorkflowJob.attempts < WorkflowJob.max_attempts,
        )
        .order_by(WorkflowJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if candidate is None:
        return None

    result = await session.execute(
        update(WorkflowJob)
        .where(WorkflowJob.id == candidate.id, WorkflowJob.status == "queued")
        .values(
            status="running",
            attempts=WorkflowJob.attempts + 1,
            locked_at=_now(),
            locked_by=worker_id,
            updated_at=_now(),
        )
    )
    if result.rowcount != 1:
        await session.rollback()
        return None
    await session.commit()
    await session.refresh(candidate)
    return candidate


async def complete_job(
    session: AsyncSession,
    job_id: str,
    *,
    error: str | None = None,
) -> None:
    job = await session.get(WorkflowJob, job_id)
    if job is None:
        return
    if error is None:
        job.status = "succeeded"
        job.last_error = None
        job.locked_at = None
        job.locked_by = None
    elif job.attempts >= job.max_attempts:
        job.status = "failed"
        job.last_error = error[:2000]
        job.locked_at = None
        job.locked_by = None
    else:
        job.status = "queued"
        job.last_error = error[:2000]
        job.locked_at = None
        job.locked_by = None
        job.available_at = _now() + timedelta(seconds=min(2 ** job.attempts, 300))
    job.updated_at = _now()
    await session.commit()


async def sweep_orphans(
    session: AsyncSession,
    *,
    timeout_seconds: int | None = None,
) -> int:
    """Return stale `running` jobs to the queue; fail the ones out of attempts.

    Comparison is done in Python so SQLite and PostgreSQL agree on timezone
    semantics (SQLite drops tzinfo on round-trip).
    """
    timeout = timeout_seconds or settings.JOB_VISIBILITY_TIMEOUT_SECONDS
    now = _now()
    result = await session.execute(
        select(WorkflowJob).where(WorkflowJob.status == "running")
    )
    recovered = 0
    for job in result.scalars().all():
        if job.locked_at is None:
            continue
        if (now - _aware(job.locked_at)).total_seconds() < timeout:
            continue
        job.locked_at = None
        job.locked_by = None
        job.updated_at = now
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.last_error = "Worker disappeared; attempts exhausted"
        else:
            job.status = "queued"
            job.available_at = now
        recovered += 1
    await session.commit()
    if recovered:
        logger.warning("Recovered %d stale workflow job(s)", recovered)
    return recovered