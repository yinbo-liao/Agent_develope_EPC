from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.core.evidence import (
    CheckSpec,
    build_record,
    read_coverage,
    run_checks,
    verify_record,
    write_record,
)


def _record(commit: str = "abc123", checks: list[dict] | None = None, **kwargs):
    default_checks = [
        {
            "name": "tests",
            "command": "pytest",
            "required": True,
            "status": "passed",
            "exit_code": 0,
            "duration_seconds": 1.0,
            "output_tail": "",
        }
    ]
    return build_record(
        workflow="backend",
        commit=commit,
        checks=checks or default_checks,
        **kwargs,
    )


def test_valid_record_passes() -> None:
    assert verify_record(_record(), expected_commit="abc123") == []


def test_commit_mismatch_is_rejected() -> None:
    errors = verify_record(_record(commit="old"), expected_commit="new")
    assert any("commit mismatch" in error for error in errors)


def test_failed_required_check_is_rejected() -> None:
    checks = [
        {
            "name": "tests",
            "command": "pytest",
            "required": True,
            "status": "failed",
            "exit_code": 1,
        }
    ]
    errors = verify_record(_record(checks=checks), expected_commit="abc123")
    assert any("required check failed" in error for error in errors)


def test_advisory_failure_is_allowed() -> None:
    checks = [
        {
            "name": "sast",
            "command": "bandit",
            "required": False,
            "status": "failed",
            "exit_code": 1,
        }
    ]
    assert verify_record(_record(checks=checks), expected_commit="abc123") == []


def test_stale_record_is_rejected() -> None:
    record = _record(generated_at=datetime.now(timezone.utc) - timedelta(hours=48))
    errors = verify_record(record, expected_commit="abc123", max_age_hours=24)
    assert any("older than" in error for error in errors)


def test_coverage_below_floor_is_rejected() -> None:
    record = _record(coverage=54.0, min_coverage=70.0)
    errors = verify_record(record, expected_commit="abc123")
    assert any("below required" in error for error in errors)


def test_run_checks_records_status() -> None:
    results = run_checks(
        [
            CheckSpec("ok", f'"{sys.executable}" -c "print(1)"'),
            CheckSpec("bad", f'"{sys.executable}" -c "raise SystemExit(2)"'),
        ]
    )
    assert [item["status"] for item in results] == ["passed", "failed"]


def test_coverage_xml_parsing(tmp_path) -> None:
    path = tmp_path / "coverage.xml"
    path.write_text('<coverage line-rate="0.6125"></coverage>', encoding="utf-8")
    assert read_coverage(path) == 61.25


def test_write_record_round_trip(tmp_path) -> None:
    path = tmp_path / "evidence.json"
    write_record(_record(), path)
    assert path.exists()
    assert '"workflow": "backend"' in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad", [{}, {"version": 99}])
def test_malformed_record_is_rejected(bad: dict) -> None:
    errors = verify_record(bad, expected_commit="abc123")
    assert errors