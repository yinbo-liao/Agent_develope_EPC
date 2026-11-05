from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.workflows.nodes import assess_risk

CASES = [
    json.loads(line)
    for line in (Path(__file__).resolve().parents[2] / "eval" / "red_team.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
]


@pytest.mark.anyio
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_red_team_case(case):
    outcome = await assess_risk(
        SimpleNamespace(input_query=case["query"], retrieval_results=[])
    )
    assert outcome["risk_level"] == case["expected_risk"]