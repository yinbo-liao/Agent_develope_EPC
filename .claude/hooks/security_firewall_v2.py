#!/usr/bin/env python3
"""Security hook for local agent actions in Wave 1."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


DESTRUCTIVE_SQL = [
    re.compile(r"\bDROP\s+(DATABASE|SCHEMA|TABLE|INDEX|VIEW|SEQUENCE)\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TABLE\b.*\bDROP\s+(COLUMN|CONSTRAINT)\b", re.IGNORECASE),
]
UNSCOPED_SQL = [
    re.compile(r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bUPDATE\b(?!.*\bWHERE\b)", re.IGNORECASE | re.DOTALL),
]
DANGEROUS_PATHS = [
    re.compile(r"(^|[\\/])\.ssh([\\/]|$)", re.IGNORECASE),
    re.compile(r"(^|[\\/])\.aws([\\/]|$)", re.IGNORECASE),
    re.compile(r"\.env(\.production)?$", re.IGNORECASE),
    re.compile(r"(^|[\\/])(etc|root|proc|sys)([\\/]|$)", re.IGNORECASE),
]
DANGEROUS_COMMANDS = [
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"rm\s+--no-preserve-root", re.IGNORECASE),
    re.compile(r"curl.+\|\s*(bash|sh)", re.IGNORECASE),
    re.compile(r"wget.+\|\s*(bash|sh)", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|\:&\s*\};:", re.IGNORECASE),
]
SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),
    re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]+['\"]"),
]


class SecurityFirewall:
    def __init__(self) -> None:
        self.violations: list[dict[str, Any]] = []

    def check_command(self, command: str) -> None:
        for pattern in DANGEROUS_COMMANDS:
            if pattern.search(command):
                self.violations.append(
                    {
                        "type": "dangerous_command",
                        "severity": "critical",
                        "message": f"Dangerous command blocked: {command[:80]}",
                    }
                )

    def check_path(self, path: str) -> None:
        for pattern in DANGEROUS_PATHS:
            if pattern.search(path):
                self.violations.append(
                    {
                        "type": "dangerous_path",
                        "severity": "critical",
                        "message": f"Protected path access blocked: {path}",
                    }
                )

    def check_content(self, content: str) -> None:
        for pattern in DESTRUCTIVE_SQL + UNSCOPED_SQL:
            if pattern.search(content):
                self.violations.append(
                    {
                        "type": "destructive_sql",
                        "severity": "critical",
                        "message": "Destructive SQL pattern detected",
                    }
                )

        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                self.violations.append(
                    {
                        "type": "hardcoded_secret",
                        "severity": "critical",
                        "message": "Potential hardcoded secret detected",
                    }
                )

    def process(self, payload: str) -> dict[str, Any]:
        try:
            data = json.loads(payload or "{}")
        except json.JSONDecodeError:
            return {"block": True, "reason": "Invalid input JSON"}

        # Claude Code sends the tool arguments under `tool_input`; older examples
        # used `params`. Accept both so a hook upgrade never silently disables the
        # checks, and fail closed when neither is a mapping.
        tool_name = str(data.get("tool_name") or data.get("tool") or "")
        raw_params = data.get("tool_input")
        if raw_params is None:
            raw_params = data.get("params")
        if raw_params is None:
            raw_params = {}
        if not isinstance(raw_params, dict):
            return {"block": True, "reason": "Malformed tool input"}
        params: dict[str, Any] = raw_params

        if tool_name in {"Bash", "PowerShell"}:
            self.check_command(str(params.get("command", "")))
        elif tool_name in {"Edit", "Write"}:
            self.check_path(str(params.get("path", params.get("file", ""))))
            self.check_content(str(params.get("content", params.get("text", ""))))
        elif tool_name == "MultiEdit":
            for edit in params.get("edits", []) or []:
                if isinstance(edit, dict):
                    self.check_path(str(edit.get("path", edit.get("file", ""))))
                    self.check_content(str(edit.get("new_string", edit.get("content", ""))))
        elif tool_name == "SQL":
            self.check_content(str(params.get("query", "")))

        critical = [item for item in self.violations if item["severity"] == "critical"]
        if critical:
            return {"block": True, "reason": critical[0]["message"], "violations": self.violations}

        return {"block": False, "reason": "Passed security checks", "violations": []}


def main() -> int:
    firewall = SecurityFirewall()
    result = firewall.process(sys.stdin.read())
    print(json.dumps(result))
    return 2 if result.get("block") else 0


if __name__ == "__main__":
    raise SystemExit(main())
