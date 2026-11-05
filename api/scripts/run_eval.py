"""Offline red-team baseline for risk classification.

Runs the deterministic risk assessor over `eval/red_team.jsonl`. This is a
classification baseline, not an end-to-end model evaluation; it keeps known unsafe
prompts from silently drifting to lower risk tiers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflows.nodes import assess_risk

CASES_PATH = Path(__file__).resolve().parents[1] / "eval" / "red_team.jsonl"


async def evaluate(cases: list[dict]) -> list[dict]:
    results = []
    for case in cases:
        run = SimpleNamespace(
            input_query=str(case["query"]),
            retrieval_results=[],
        )
        outcome = await assess_risk(run)
        actual = str(outcome.get("risk_level"))
        results.append(
            {
                "id": case["id"],
                "expected": case["expected_risk"],
                "actual": actual,
                "passed": actual == case["expected_risk"],
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args(argv)

    import asyncio

    cases = [
        json.loads(line)
        for line in Path(args.cases).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results = asyncio.run(evaluate(cases))
    passed = sum(1 for item in results if item["passed"])
    rate = passed / len(results) if results else 0.0

    for item in results:
        state = "PASS" if item["passed"] else "FAIL"
        print(f"[{state}] {item['id']} expected={item['expected']} actual={item['actual']}")
    print(f"red-team pass rate: {passed}/{len(results)} ({rate:.0%})")
    return 0 if rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    sys.exit(main())