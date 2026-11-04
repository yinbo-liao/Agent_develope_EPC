from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    RETRIEVING = "retrieving"
    ASSESSING = "assessing"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowEvent(BaseModel):
    event_type: str
    task_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreateRequest(BaseModel):
    """Create a run. Identity comes from the token, never from the body."""

    model_config = ConfigDict(extra="forbid")

    input_query: str = Field(min_length=3, max_length=10_000)
    session_id: str | None = None
    token_budget: int = Field(default=10_000, ge=1000, le=200_000)
    cost_budget_usd: float = Field(default=5.0, ge=0.0, le=500.0)


class WorkflowDecisionRequest(BaseModel):
    """Decide a paused run. The reviewer identity comes from the token."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    decision: Literal["approved", "rejected"]
    comment: str = ""


class WorkflowSummary(BaseModel):
    id: str
    user_id: str
    session_id: str | None
    current_step: str
    current_status: WorkflowStatus
    risk_level: RiskLevel
    is_human_review_needed: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowDetail(WorkflowSummary):
    input_query: str
    risk_factors: list[str]
    retrieval_results: list[dict[str, Any]] | None
    final_response: str | None
    agent_finding: str | None
    error_info: str | None
    total_tokens_used: int
    token_budget: int
    cost_usd: float
    cost_budget_usd: float
    human_decision: str | None
    human_comment: str | None
    review_deadline: datetime | None

    model_config = {"from_attributes": True}