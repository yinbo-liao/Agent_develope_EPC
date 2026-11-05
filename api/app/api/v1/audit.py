from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import require_role
from app.models.audit import AuditEvent
from app.services.audit import GENESIS_HASH, verify_chain

router = APIRouter(prefix="/audit", tags=["Audit"])

ADMIN = dict[str, object]


@router.get("/events", status_code=200)
async def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    current_user: ADMIN = Depends(require_role("admin")),
) -> dict[str, object]:
    result = await session.execute(
        select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    )
    events = list(result.scalars().all())
    return {
        "items": [
            {
                "id": event.id,
                "actor": event.actor,
                "action": event.action,
                "resource": event.resource,
                "payload": event.payload,
                "hash": event.hash,
                "prev_hash": event.prev_hash,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    }


@router.get("/verify", status_code=200)
async def verify_audit_events(
    session: AsyncSession = Depends(get_db_session),
    current_user: ADMIN = Depends(require_role("admin")),
) -> dict[str, object]:
    result = await session.execute(select(AuditEvent).order_by(AuditEvent.id.asc()))
    events = list(result.scalars().all())
    ok, error = verify_chain(events)
    return {
        "valid": ok,
        "records": len(events),
        "head": events[-1].hash if events else GENESIS_HASH,
        "error": error,
    }