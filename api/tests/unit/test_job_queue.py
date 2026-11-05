from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update

from app.models.job import WorkflowJob
from app.services.job_queue import claim_job, complete_job, enqueue_job, sweep_orphans
from app.services.worker import WorkflowWorker


async def _enqueue(workflow_id: str | None = None, delay: float = 0.0) -> str:
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await session.execute(delete(WorkflowJob))
        await session.commit()
        job = await enqueue_job(
            session, workflow_id or str(uuid.uuid4()), delay_seconds=delay
        )
        await session.commit()
        return job.id


@pytest.mark.anyio
async def test_enqueue_claim_complete(async_client: AsyncClient) -> None:
    job_id = await _enqueue()
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        claimed = await claim_job(session, "worker-1")
        assert claimed is not None
        assert claimed.id == job_id
        assert claimed.status == "running"
        assert claimed.attempts == 1

    async with SessionLocal() as session:
        await complete_job(session, job_id)

    async with SessionLocal() as session:
        job = await session.get(WorkflowJob, job_id)
        assert job is not None
        assert job.status == "succeeded"


@pytest.mark.anyio
async def test_delayed_job_is_not_claimable(async_client: AsyncClient) -> None:
    await _enqueue(delay=60)
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        assert await claim_job(session, "worker-1") is None


@pytest.mark.anyio
async def test_failure_requeues_with_backoff(async_client: AsyncClient) -> None:
    job_id = await _enqueue()
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await claim_job(session, "worker-1")
    async with SessionLocal() as session:
        await complete_job(session, job_id, error="transient")

    async with SessionLocal() as session:
        job = await session.get(WorkflowJob, job_id)
        assert job is not None
        assert job.status == "queued"
        assert job.attempts == 1
        assert (job.available_at if job.available_at.tzinfo else job.available_at.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc)


@pytest.mark.anyio
async def test_sweep_requeues_stale_running_job(async_client: AsyncClient) -> None:
    job_id = await _enqueue()
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await claim_job(session, "worker-1")
        await session.execute(
            update(WorkflowJob)
            .where(WorkflowJob.id == job_id)
            .values(locked_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await session.commit()

    async with SessionLocal() as session:
        assert await sweep_orphans(session, timeout_seconds=60) >= 1
        job = await session.get(WorkflowJob, job_id)
        assert job is not None
        assert job.status == "queued"
        assert job.locked_at is None


@pytest.mark.anyio
async def test_sweep_fails_exhausted_orphans(async_client: AsyncClient) -> None:
    job_id = await _enqueue()
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await claim_job(session, "worker-1")
        await session.execute(
            update(WorkflowJob)
            .where(WorkflowJob.id == job_id)
            .values(
                attempts=3,
                locked_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        assert await sweep_orphans(session, timeout_seconds=60) >= 1
        job = await session.get(WorkflowJob, job_id)
        assert job is not None
        assert job.status == "failed"


@pytest.mark.anyio
async def test_worker_executes_and_marks_success(async_client: AsyncClient) -> None:
    workflow_id = str(uuid.uuid4())
    await _enqueue(workflow_id)
    executed: list[str] = []

    async def fake_executor(task_id: str) -> None:
        executed.append(task_id)

    worker = WorkflowWorker(worker_id="test-worker", executor=fake_executor)
    assert await worker.run_once() is True
    assert executed == [workflow_id]

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        job = await session.scalar(
            select(WorkflowJob).where(WorkflowJob.workflow_id == workflow_id)
        )
        assert job is not None
        assert job.status == "succeeded"


@pytest.mark.anyio
async def test_worker_marks_failure(async_client: AsyncClient) -> None:
    workflow_id = str(uuid.uuid4())
    await _enqueue(workflow_id)

    async def failing_executor(task_id: str) -> None:
        raise RuntimeError("boom")

    worker = WorkflowWorker(worker_id="test-worker", executor=failing_executor)
    assert await worker.run_once() is True

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        job = await session.scalar(
            select(WorkflowJob).where(WorkflowJob.workflow_id == workflow_id)
        )
        assert job is not None
        assert job.status == "queued"
        assert job.last_error and "boom" in job.last_error


@pytest.mark.anyio
async def test_api_creation_enqueues_job(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "Queue wiring test."},
        headers=auth_headers,
    )
    assert response.status_code == 202
    workflow_id = response.json()["id"]

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        job = await session.scalar(
            select(WorkflowJob).where(WorkflowJob.workflow_id == workflow_id)
        )
        assert job is not None
        assert job.status == "queued"
