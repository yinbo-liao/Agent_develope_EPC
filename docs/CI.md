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

The pipeline runs two evidence jobs, a Helm validation job and a gate:

1. **backend** — ruff, pytest with coverage, bandit and pip-audit; writes
   `api/evidence/backend.json`.
2. **frontend** — production build, Vitest, npm audit; writes
   `frontend/evidence/frontend.json`.
3. **helm** — `helm lint` and `helm template` for the chart.
4. **gate** — downloads both records and runs
   `python api/scripts/evidence.py verify ... --commit $GITHUB_SHA`. Required
   checks must have passed, the commit must match, the record must be under 24h old,
   and backend coverage must be at least 55%.

SAST/SCA/audit checks are recorded as advisory for now; promote them to `--check`
once the baseline is clean. The coverage floor is 55% (current); the P3 target is 70%.