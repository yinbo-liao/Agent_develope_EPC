from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models.workflow import WorkflowRun

logger = logging.getLogger(__name__)

# In-memory DLQ for Wave 2 (will be Redis-backed in Phase 2.4)
_dead_letter_entries: dict[str, dict[str, Any]] = {}


def push(run: WorkflowRun) -> str:
    """Push a failed workflow run into the dead letter queue.

    Returns the DLQ entry ID.
    """
    entry = {
        "dlq_id": run.id,  # reuse workflow ID as DLQ key
        "original_task_id": run.id,
        "user_id": run.user_id,
        "input_query": run.input_query,
        "risk_level": run.risk_level,
        "risk_factors": run.risk_factors,
        "error_info": run.error_info,
        "retry_count": run.retry_count,
        "current_step": run.current_step,
        "current_status": run.current_status,
        "token_budget": run.token_budget,
        "cost_budget_usd": run.cost_budget_usd,
        "replay_status": "pending",
        "replay_count": 0,
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    _dead_letter_entries[run.id] = entry
    logger.info("DLQ: pushed failed workflow %s", run.id)
    return run.id


def get(dlq_id: str) -> dict[str, Any] | None:
    """Retrieve a DLQ entry by ID."""
    return _dead_letter_entries.get(dlq_id)


def list_entries(user_id: str | None = None) -> list[dict[str, Any]]:
    """List all DLQ entries, optionally filtered by user_id."""
    entries = list(_dead_letter_entries.values())
    if user_id:
        entries = [e for e in entries if e.get("user_id") == user_id]
    return sorted(entries, key=lambda e: str(e.get("failed_at", "")), reverse=True)


def mark_replayed(dlq_id: str) -> None:
    """Mark a DLQ entry as having been replayed."""
    entry = _dead_letter_entries.get(dlq_id)
    if entry:
        entry["replay_status"] = "replayed"
        entry["replay_count"] = int(entry.get("replay_count", 0)) + 1
        entry["replayed_at"] = datetime.now(timezone.utc).isoformat()


def serialize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Convert a DLQ entry to a WorkflowCreateRequest payload for replay."""
    return {
        "user_id": entry.get("user_id", "unknown"),
        "input_query": entry.get("input_query", ""),
        "token_budget": entry.get("token_budget", 10000),
        "cost_budget_usd": entry.get("cost_budget_usd", 5.0),
    }
