from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    input_query: Mapped[str] = mapped_column(Text())

    current_step: Mapped[str] = mapped_column(String(128), default="created")
    current_status: Mapped[str] = mapped_column(String(64), default="pending", index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="low")

    risk_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    retrieval_results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    agent_finding: Mapped[str | None] = mapped_column(Text(), nullable=True)
    final_response: Mapped[str | None] = mapped_column(Text(), nullable=True)
    error_info: Mapped[str | None] = mapped_column(Text(), nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    token_budget: Mapped[int] = mapped_column(Integer, default=10000)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_budget_usd: Mapped[float] = mapped_column(Float, default=5.0)

    is_human_review_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    human_comment: Mapped[str | None] = mapped_column(Text(), nullable=True)
    review_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
