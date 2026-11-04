from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.workflow import WorkflowRun


async def _seed_reviewing_run(
    owner_id: str = "test-user-id",
    *,
    status: str = "reviewing",
    decision: str | None = None,
    deadline_minutes: int = 30,
) -> str:
    """Insert a workflow already waiting for review, using the test database."""
    from app.core.database import SessionLocal  # patched by the async_client fixture

    run_id = str(uuid.uuid4())
    async with SessionLocal() as session:
        session.add(
            WorkflowRun(
                id=run_id,
                user_id=owner_id,
                input_query="drop table customers",
                current_step="human_review_pending",
                current_status=status,
                risk_level="critical",
                risk_factors=["CRITICAL: Destructive operation requested"],
                is_human_review_needed=status == "reviewing",
                human_decision=decision,
                review_deadline=datetime.now(timezone.utc)
                + timedelta(minutes=deadline_minutes),
            )
        )
        await session.commit()
    return run_id


@pytest.mark.anyio
async def test_reviewer_can_approve(
    async_client: AsyncClient, reviewer_auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_reviewing_run()
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved", "comment": "checked"},
        headers=reviewer_auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["current_status"] == "completed"
    assert response.json()["human_decision"] == "approved"


@pytest.mark.anyio
async def test_second_decision_is_rejected(
    async_client: AsyncClient, reviewer_auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_reviewing_run()
    first = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
        headers=reviewer_auth_headers,
    )
    assert first.status_code == 200
    second = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "rejected"},
        headers=reviewer_auth_headers,
    )
    assert second.status_code == 409


@pytest.mark.anyio
async def test_requester_cannot_approve_own_run(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_reviewing_run(owner_id="test-user-id")
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
        headers=auth_headers,  # admin role, but the same user
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_viewer_cannot_decide(
    async_client: AsyncClient, viewer_auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_reviewing_run()
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
        headers=viewer_auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_expired_review_is_rejected(
    async_client: AsyncClient, reviewer_auth_headers: dict[str, str]
) -> None:
    run_id = await _seed_reviewing_run(deadline_minutes=-5)
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
        headers=reviewer_auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.anyio
async def test_decision_requires_authentication(async_client: AsyncClient) -> None:
    run_id = await _seed_reviewing_run()
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_decision_rejects_reviewer_identity_in_body(
    async_client: AsyncClient, reviewer_auth_headers: dict[str, str]
) -> None:
    """The reviewer identity comes from the token; a body field is a schema error."""
    run_id = await _seed_reviewing_run()
    response = await async_client.post(
        "/api/v1/human-review/decide",
        json={"task_id": run_id, "decision": "approved", "reviewer_id": "someone-else"},
        headers=reviewer_auth_headers,
    )
    assert response.status_code == 422