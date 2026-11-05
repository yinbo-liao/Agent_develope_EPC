from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.models.audit import AuditEvent
from app.services.audit import append_audit


async def _append(action: str, resource: str = "res-1") -> None:
    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await append_audit(
            session,
            actor="test-user-id",
            action=action,
            resource=resource,
            payload={"step": action},
        )
        await session.commit()


@pytest.mark.anyio
async def test_audit_chain_verifies(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _append("workflow.create")
    await _append("human_review.decide")

    response = await async_client.get("/api/v1/audit/verify", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["records"] >= 2
    assert body["error"] is None


@pytest.mark.anyio
async def test_audit_chain_detects_tampering(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _append("workflow.create")
    await _append("human_review.decide")

    from app.core.database import SessionLocal

    async with SessionLocal() as session:
        await session.execute(
            update(AuditEvent).where(AuditEvent.action == "workflow.create").values(
                payload='{"step":"tampered"}'
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/audit/verify", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert "digest mismatch" in response.json()["error"]


@pytest.mark.anyio
async def test_audit_verify_requires_admin(
    async_client: AsyncClient, viewer_auth_headers: dict[str, str]
) -> None:
    response = await async_client.get("/api/v1/audit/verify", headers=viewer_auth_headers)
    assert response.status_code == 403