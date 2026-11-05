# Evidence records

`api/scripts/evidence.py` records what CI actually ran and verifies it before a
release. A record is JSON:

```json
{
  "version": 1,
  "workflow": "backend",
  "commit": "<sha>",
  "generated_at": "<iso8601>",
  "checks": [
    {
      "name": "tests",
      "command": "pytest ...",
      "required": true,
      "status": "passed",
      "exit_code": 0,
      "duration_seconds": 61.2,
      "output_tail": "..."
    }
  ],
  "coverage": {"lines_pct": 55.0, "required_pct": 55.0}
}
```

Verification rejects a record when the commit differs, a required check failed, the
record is older than 24 hours, or coverage is below the floor. The artifact is not
signed: store it with the release and protect the CI pipeline itself.

```bash
# from api/
python scripts/evidence.py record \
  --out evidence/backend.json \
  --workflow backend \
  --commit "$(git rev-parse HEAD)" \
  --coverage-xml coverage.xml \
  --min-coverage 70 \
  --check "ruff=ruff check ." \
  --check "tests=pytest -q --cov=app --cov-report=xml" \
  --advisory "bandit=bandit -r app -q -ll"

python scripts/evidence.py verify evidence/backend.json --commit "$(git rev-parse HEAD)"
```