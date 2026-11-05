"""Append-only audit chain.

Every governance event commits to its predecessor. Verification walks the chain and
recomputes each digest, so an edit or deletion is detectable from the first broken row.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json, sha256_hex
from app.models.audit import AuditEvent

GENESIS_HASH = "0" * 64

_append_lock = asyncio.Lock()


def _event_digest(
    *,
    actor: str,
    action: str,
    resource: str,
    payload: str,
    prev_hash: str,
    created_at: datetime,
) -> str:
    return sha256_hex(
        canonical_json(
            {
                "actor": actor,
                "action": action,
                "resource": resource,
                "payload": payload,
                "prev_hash": prev_hash,
                "created_at": created_at.isoformat(),
            }
        )
    )


async def append_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    resource: str = "",
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to the chain. Caller commits the transaction."""
    async with _append_lock:
        last = await session.scalar(
            select(AuditEvent)
            .order_by(AuditEvent.id.desc())
            .limit(1)
            .with_for_update()
        )
        prev_hash = last.hash if last is not None else GENESIS_HASH
        created_at = datetime.now(timezone.utc)
        payload_json = canonical_json(payload or {})
        event = AuditEvent(
            actor=actor,
            action=action,
            resource=resource,
            payload=payload_json,
            prev_hash=prev_hash,
            hash=_event_digest(
                actor=actor,
                action=action,
                resource=resource,
                payload=payload_json,
                prev_hash=prev_hash,
                created_at=created_at,
            ),
            created_at=created_at,
        )
        session.add(event)
        await session.flush()
        return event


def verify_chain(events: list[AuditEvent]) -> tuple[bool, str | None]:
    """Verify ordering and every digest. Returns (ok, first_error)."""
    prev_hash = GENESIS_HASH
    for event in events:
        if event.prev_hash != prev_hash:
            return False, f"event {event.id}: previous hash mismatch"
        created = event.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        expected = _event_digest(
            actor=event.actor,
            action=event.action,
            resource=event.resource,
            payload=event.payload,
            prev_hash=event.prev_hash,
            created_at=created,
        )
        if expected != event.hash:
            return False, f"event {event.id}: digest mismatch"
        prev_hash = event.hash
    return True, None