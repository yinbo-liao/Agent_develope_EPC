from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.workflow import WorkflowRun
from app.workflows import runner


async def _seed_run(*, retries: int = 0) -> str:
    from app.core.database import SessionLocal

    run = WorkflowRun(
        id=str(uuid.uuid4()),
        user_id="test-user-id",
        input_query="run the workflow",
        current_step="pending",
        current_status="pending",
        max_retries=retries,
    )
    async with SessionLocal() as session:
        session.add(run)
        await session.commit()
    return run.id


@pytest.mark.anyio
async def test_execute_workflow_success(async_client, monkeypatch):
    run_id = await _seed_run()
    steps = [
        {
            "current_step": "done",
            "current_status": "completed",
            "final_response": "finished",
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        }
    ]
    monkeypatch.setattr(runner.workflow_graph, "execute", AsyncMock(return_value=steps))

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        result = await runner.execute_workflow(session, run_id)
    assert result.current_status == "completed"
    assert result.final_response == "finished"


@pytest.mark.anyio
async def test_execute_workflow_fatal_error_goes_to_dlq(async_client, monkeypatch):
    run_id = await _seed_run()
    monkeypatch.setattr(
        runner.workflow_graph, "execute", AsyncMock(side_effect=ValueError("bad input"))
    )
    pushed = []
    monkeypatch.setattr(runner, "dlq_push", lambda run: pushed.append(run.id))

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        result = await runner.execute_workflow(session, run_id)
    assert result.current_status == "failed"
    assert pushed == [run_id]


@pytest.mark.anyio
async def test_execute_workflow_retries_transient_error(async_client, monkeypatch):
    run_id = await _seed_run(retries=1)
    success = [{"current_step": "done", "current_status": "completed"}]
    monkeypatch.setattr(
        runner.workflow_graph,
        "execute",
        AsyncMock(side_effect=[TimeoutError("slow"), success]),
    )
    monkeypatch.setattr(runner.asyncio, "sleep", AsyncMock())

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        result = await runner.execute_workflow(session, run_id)
    assert result.current_status == "completed"
    assert result.retry_count == 1


def test_remediation_and_updates():
    assert runner._remediation_for(TimeoutError("x")) == "timeout"
    assert runner._remediation_for(RuntimeError("circuit open")) == "circuit_open"
    assert runner._remediation_for(RuntimeError("budget limit exceeded")) == "budget"
    assert runner._remediation_for(RuntimeError("connection refused")) == "connection"
    run = WorkflowRun(id="x", user_id="u", input_query="q")
    runner.apply_updates(run, {"current_step": "step"})
    assert run.current_step == "step"