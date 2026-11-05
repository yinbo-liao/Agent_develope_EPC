from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.hashing import review_state_hash
from app.models.workflow import WorkflowRun


async def _seed_run(*, state_hash: str | None = None) -> str:
    from app.core.database import SessionLocal

    run = WorkflowRun(
        id=str(uuid.uuid4()),
        user_id="test-user-id",
        input_query="drop table customers",
        current_step="human_review_pending",
        current_status="reviewing",
        risk_level="critical",
        risk_factors=["CRITICAL: Destructive operation requested"],
        is_human_review_needed=True,
        review_deadline=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    async with SessionLocal() as session:
        session.add(run)
        await session.flush()
        run.review_state_hash = state_hash if state_hash is not None else review_state_hash(run)
        await session.commit()
    return run.id


@pytest.mark.anyio
async def test_decision_is_bound_to_review_state(
    async_client: AsyncClient, reviewer_auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_run()
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
        headers=reviewer_auth_headers,
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_changed_state_rejects_decision(
    async_client: AsyncClient, reviewer_auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_run(state_hash="0" * 64)
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
        headers=reviewer_auth_headers,
    )
    assert response.status_code == 409
    assert "changed" in response.json()["detail"]