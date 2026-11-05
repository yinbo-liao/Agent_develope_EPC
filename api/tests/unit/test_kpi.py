from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.human_review import HumanReviewDecision
from app.models.workflow import WorkflowRun
from app.services.kpi import compute_kpi


async def _reset() -> None:
    from sqlalchemy import delete

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await session.execute(delete(HumanReviewDecision))
        await session.execute(delete(WorkflowRun))
        await session.commit()


async def _seed(*, completed: int = 6, failed: int = 1, unsafe: bool = False) -> list[str]:
    from app.core.database import SessionLocal

    now = datetime.now(timezone.utc)
    ids: list[str] = []
    async with SessionLocal() as session:
        for index in range(completed):
            run_id = str(uuid.uuid4())
            ids.append(run_id)
            session.add(
                WorkflowRun(
                    id=run_id,
                    user_id="owner-1",
                    input_query="q",
                    current_status="completed",
                    cost_usd=0.1,
                    created_at=now - timedelta(hours=1),
                    completed_at=now - timedelta(hours=1) + timedelta(seconds=30),
                )
            )
        for index in range(failed):
            session.add(
                WorkflowRun(
                    id=str(uuid.uuid4()),
                    user_id="owner-1",
                    input_query="q",
                    current_status="failed",
                    created_at=now - timedelta(hours=1),
                )
            )
        await session.flush()
        if unsafe:
            session.add(
                HumanReviewDecision(
                    workflow_id=ids[0],
                    reviewer_id="owner-1",  # self-approval
                    decision="approved",
                    created_at=now,
                )
            )
        await session.commit()
    return ids


@pytest.mark.anyio
async def test_kpi_gate_g_allows_expansion(async_client):
    await _reset()
    await _seed()

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        report = await compute_kpi(session)
    assert report["metrics"]["total_runs"] == 7
    assert report["metrics"]["completion_rate"] == pytest.approx(6 / 7, abs=0.001)
    assert report["metrics"]["unsafe_approvals"] == 0
    assert report["gate_g"]["expansion_allowed"] is True


@pytest.mark.anyio
async def test_kpi_gate_g_holds_on_unsafe_approval(async_client):
    await _reset()
    await _seed(unsafe=True)

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        report = await compute_kpi(session)
    assert report["metrics"]["unsafe_approvals"] == 1
    assert report["gate_g"]["expansion_allowed"] is False
    assert any("unsafe approval" in reason for reason in report["gate_g"]["reasons"])


@pytest.mark.anyio
async def test_kpi_gate_g_holds_on_small_sample(async_client):
    await _reset()
    await _seed(completed=2, failed=0)

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        report = await compute_kpi(session)
    assert report["gate_g"]["expansion_allowed"] is False
    assert any("insufficient sample" in reason for reason in report["gate_g"]["reasons"])


@pytest.mark.anyio
async def test_kpi_endpoints(async_client, auth_headers, viewer_auth_headers):
    await _reset()
    await _seed()

    summary = await async_client.get("/api/v1/kpi/summary", headers=auth_headers)
    assert summary.status_code == 200
    assert "gate_g" in summary.json()

    gate = await async_client.get("/api/v1/kpi/gate-g", headers=auth_headers)
    assert gate.status_code == 200
    assert gate.json()["gate_g"]["expansion_allowed"] is True

    denied = await async_client.get("/api/v1/kpi/gate-g", headers=viewer_auth_headers)
    assert denied.status_code == 403