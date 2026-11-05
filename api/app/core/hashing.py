"""Canonical hashing helpers used by audit events and review binding."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Stable JSON: sorted keys, compact separators, no ASCII escaping dependence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_json(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def review_state_hash(run: Any) -> str:
    """Hash the facts a human decision is bound to.

    If any of these change while review is pending, the decision must be rejected:
    the reviewer approved a specific request at a specific risk, not just a task id.
    """
    return hash_json(
        {
            "id": run.id,
            "user_id": run.user_id,
            "input_query": run.input_query,
            "risk_level": run.risk_level,
            "risk_factors": run.risk_factors,
        }
    )