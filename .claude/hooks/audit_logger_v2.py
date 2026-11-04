#!/usr/bin/env python3
"""Structured audit logger for local tool actions."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_file: str = ".claude/audit.jsonl") -> None:
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        sensitive_keys = ("password", "secret", "token", "key", "credential", "auth")
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if any(marker in key.lower() for marker in sensitive_keys):
                digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]
                sanitized[key] = f"[REDACTED:{digest}]"
            else:
                sanitized[key] = value
        return sanitized

    def log(self, payload: str) -> None:
        data = json.loads(payload or "{}")
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": data.get("session_id", "unknown"),
            "correlation_id": data.get("correlation_id", "unknown"),
            "tool_name": data.get("tool_name", "unknown"),
            "params": self.sanitize(data.get("tool_input") or data.get("params") or {}),
            "result_status": data.get("result", {}).get("status", "unknown"),
            "duration_ms": data.get("duration_ms", 0),
        }
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


def main() -> int:
    logger = AuditLogger()
    try:
        logger.log(sys.stdin.read())
    except Exception as exc:  # pragma: no cover - fail-safe path
        print(f"Audit logging error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
