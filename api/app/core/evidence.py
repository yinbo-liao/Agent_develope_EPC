"""CI evidence records and verification.

A record is a small JSON document produced by CI: the commit, timestamp, the
checks that ran, their exit status and (optionally) backend coverage. Verification
is intentionally boring: required checks must exist and have passed, the commit
must match the one being released, the record must be fresh, and coverage must
meet the recorded floor. It is not a signature; store the artifact with the release.
"""

from __future__ import annotations

import json
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

EVIDENCE_VERSION = 1
DEFAULT_MAX_AGE_HOURS = 24


@dataclass(frozen=True)
class CheckSpec:
    name: str
    command: str
    required: bool = True


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def run_checks(specs: list[CheckSpec], cwd: str | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for spec in specs:
        started = time.monotonic()
        completed = subprocess.run(
            spec.command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        duration = round(time.monotonic() - started, 2)
        tail = (completed.stdout or "")[-2000:] + (completed.stderr or "")[-2000:]
        result = {
            "name": spec.name,
            "command": spec.command,
            "required": spec.required,
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "duration_seconds": duration,
            "output_tail": tail,
        }
        results.append(result)
        state = "PASS" if completed.returncode == 0 else "FAIL"
        print(f"[{state}] {spec.name} ({duration:.1f}s): {spec.command}")
        if completed.returncode != 0 and tail.strip():
            print(tail[-1000:])
    return results


def read_coverage(coverage_xml: str | Path) -> float | None:
    path = Path(coverage_xml)
    if not path.exists():
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    line_rate = root.get("line-rate")
    return round(float(line_rate) * 100, 2) if line_rate is not None else None


def build_record(
    *,
    workflow: str,
    commit: str,
    checks: list[dict[str, Any]],
    coverage: float | None = None,
    min_coverage: float | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "version": EVIDENCE_VERSION,
        "workflow": workflow,
        "commit": commit,
        "generated_at": (generated_at or _utcnow()).isoformat(),
        "checks": checks,
        "coverage": {"lines_pct": coverage, "required_pct": min_coverage},
    }


def write_record(record: dict[str, Any], out_path: str | Path) -> None:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")


def verify_record(
    record: dict[str, Any],
    *,
    expected_commit: str,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> list[str]:
    errors: list[str] = []
    if record.get("version") != EVIDENCE_VERSION:
        errors.append(f"unsupported evidence version: {record.get('version')}")
    if record.get("commit") != expected_commit:
        errors.append(
            f"commit mismatch: record={record.get('commit')} expected={expected_commit}"
        )
    try:
        generated = _parse_time(str(record.get("generated_at", "")))
    except ValueError:
        errors.append("invalid generated_at timestamp")
    else:
        if _utcnow() - generated > timedelta(hours=max_age_hours):
            errors.append(f"evidence is older than {max_age_hours}h")

    checks = record.get("checks") or []
    names = {str(check.get("name")) for check in checks}
    for check in checks:
        if check.get("required") and check.get("status") != "passed":
            errors.append(f"required check failed: {check.get('name')}")

    coverage = record.get("coverage") or {}
    lines = coverage.get("lines_pct")
    required = coverage.get("required_pct")
    if required is not None:
        if lines is None:
            errors.append("coverage floor set but no coverage was recorded")
        elif float(lines) < float(required):
            errors.append(f"coverage {lines}% is below required {required}%")

    if not names:
        errors.append("evidence contains no checks")
    return errors


def load_record(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))