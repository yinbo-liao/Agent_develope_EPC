# Enabling CI

The workflow is stored at `ci/ci.yml` because the current GitHub CLI token does not
have the `workflow` scope, and GitHub rejects pushes that create `.github/workflows/`.

Enable it with:

```bash
gh auth refresh -s workflow
mkdir -p .github/workflows
git mv ci/ci.yml .github/workflows/ci.yml
git commit -m "ci: enable evidence pipeline"
git push
```

The pipeline runs two evidence jobs, Helm and end-to-end jobs, and a gate:

1. **backend** — ruff, pytest with coverage, red-team eval, bandit and pip-audit; writes
   `api/evidence/backend.json`.
2. **frontend** — production build, Vitest, npm audit; writes
   `frontend/evidence/frontend.json`.
3. **helm** — `helm lint` and `helm template` for the chart.\n4. **e2e** — starts the compose stack and runs the Playwright smoke tests.
5. **gate** — downloads both records and runs
   `python api/scripts/evidence.py verify ... --commit $GITHUB_SHA`. Required
   checks must have passed, the commit must match, the record must be under 24h old,
   and backend coverage must be at least 70%.

SAST/SCA/audit checks are recorded as advisory for now; promote them to `--check`
once the baseline is clean. The coverage floor is 70% (current coverage is 71%).