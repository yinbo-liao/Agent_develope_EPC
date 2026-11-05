from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MCPToolCallAudit(Base):
    __tablename__ = "mcp_tool_call_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(String(255), index=True)
    tool_name: Mapped[str] = mapped_column(String(255), index=True)
    server_name: Mapped[str] = mapped_column(String(255), index=True)
    arguments: Mapped[str] = mapped_column(Text())
    result_summary: Mapped[str] = mapped_column(Text(), default="")
    status: Mapped[str] = mapped_column(String(64), default="pending")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only, hash-chained governance event.

    Each row commits to its predecessor: `hash = sha256(prev + canonical fields)`.
    Editing or deleting a row breaks verification from that point. The chain is
    process-serialized on append; a multi-instance deployment should move the last-row
    lock to PostgreSQL (`SELECT ... FOR UPDATE`) or a dedicated writer.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource: Mapped[str] = mapped_column(String(255), default="", index=True)
    payload: Mapped[str] = mapped_column(Text(), default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)