# AI Workflow Platform (demo)

A local demonstration of a multi-agent workflow platform: a FastAPI backend runs a
deterministic workflow graph (validate → retrieve → assess risk → route → generate →
human review), and a React dashboard streams progress over WebSocket with SSE fallback.

This is a **demo build**: the model client is simulated, retrieval is keyword-based,
and MCP tools are stubs. The security and delivery hardening in this branch (P0) is real.

## Demo sign-in

Authentication is required on every workflow, event and review endpoint. Two demo users are
seeded on startup in development (`SEED_DEMO_USERS=true`):

| User | Password | Role | Use |
|---|---|---|---|
| `demo` | `demo-pass-1234` | viewer | create and watch workflows |
| `reviewer` | `reviewer-pass-1234` | reviewer | approve/reject CRITICAL runs |
| `admin` | `admin-pass-1234` | admin | provision users, verify the audit chain |

A reviewer cannot approve a run they requested, the run must still be in review, and the
30-minute deadline is enforced. WebSocket/SSE connections use a two-minute, task-scoped
ticket issued by `POST /api/v1/events/ticket/{task_id}`.

## Quick start

```bash
docker compose up -d --build
# app:      http://localhost:5173
# API docs: http://localhost:8000/docs  (development only)
# metrics:  http://localhost:8000/metrics
```

Without Docker:

```bash
cd api
pip install -e ".[dev]"
uvicorn app.main:app --reload
# in another terminal
cd frontend
npm ci && npm run dev
```

Set `VITE_API_URL=http://localhost:8000` for the Vite dev server (docker-compose does).

## What is enforced (P0 + P1 + P1.5)

- **AuthN/AuthZ**: JWT access tokens; owner-scoped workflow reads; role-gated human review;
  no caller-supplied `user_id` or `reviewer_id`.
- **Human review**: status, deadline, self-approval and duplicate-decision guards.
- **Streams**: WebSocket/SSE require a short-lived task ticket; socket messages cannot approve runs.
- **Surface hardening**: docs are development-only, `/metrics` is hidden in production unless
  `METRICS_TOKEN` is set, HSTS in production, stricter CSP at the frontend proxy.
- **Hook**: the Claude security hook now reads `tool_input` (the schema Claude Code sends) and
  covers MultiEdit/PowerShell; negative tests assert it blocks.
- **Runtime (P1.5)**: workflow creation enqueues a durable `workflow_jobs` row; a worker claims
  jobs atomically, retries with backoff and sweeps jobs orphaned by a crashed process. Budgets are
  reserved atomically with a Redis Lua script before each LLM call and reconciled to actual usage.
- **Governance (P1)**: append-only, hash-chained audit events with `GET /api/v1/audit/verify`;
  issuer/audience-checked JWTs; refresh-token rotation with reuse detection and logout; admin-only
  user provisioning; `Idempotency-Key` replay; decisions bound to the reviewed state hash;
  OPA-evaluated MCP authorization; caller-scoped semantic cache with high-risk bypass.
- **CI**: GitHub Actions runs ruff and pytest with coverage, and builds the frontend.

## Verification

```bash
cd api
pip install -e ".[dev]"
pytest -q --cov=app --cov-report=term

cd ../frontend
npm test
npm run build
```

CI records what it ran as a verifiable evidence bundle (`api/scripts/evidence.py`):
required checks must pass, the commit must match and coverage must clear the floor.
The workflow is staged at `ci/ci.yml` because the current token lacks the `workflow`
scope; `docs/CI.md` has the one-command enablement. Backend coverage is 71% with a
70% gate.

## Deployment

```bash
helm lint helm/aiwf -f helm/aiwf/values-production.yaml
helm upgrade --install aiwf helm/aiwf -f helm/aiwf/values-production.yaml --namespace aiwf
```

The chart deploys both services, ingress, autoscaling/PDB, optional network policy and a
real `alembic upgrade head` migration hook. It expects an external PostgreSQL/Redis and
an `aiwf-secrets` secret; see `docs/DEPLOYMENT.md`.

Local compose also runs Prometheus (:9090), Alertmanager (:9093) and Grafana (:3000,
admin/admin by default). Metrics include HTTP latency/status, `workflow_jobs_total` and
`workflow_job_queue_depth`; see `infrastructure/prometheus/alerts.yml`.

## Model provider, KPI and evaluation

The LLM client supports `simulated` (default), `openai` (any OpenAI-compatible
`/chat/completions`) and `anthropic` (Messages API). Configure `LLM_PROVIDER`,
`LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`; production refuses a real provider
without a key. The default remains simulated so the demo needs no external account.

The product outcome is **`governed_completion_rate` ≥ 80%** with guardrails: zero
unsafe approvals (self-approval or after deadline), p95 run duration ≤ 120 s, and
cost ≤ $1.00 per completed run. `GET /api/v1/kpi/summary` reports it; admin-only
`GET /api/v1/kpi/gate-g` returns the expansion decision. GATE_G holds autonomy
expansion only — it never blocks a release. See `docs/KPI-CONTRACT.md`.

The red-team corpus (`api/eval/red_team.jsonl`) runs in CI:

```bash
cd api && python scripts/run_eval.py
```

## Known limitations (next phases)

- The default provider is simulated; the OpenAI/Anthropic adapters require credentials. Retrieval is still keyword matching and MCP tools are stubs.
- Rate limiting remains in-process (P2 moves it to Redis).
- Remaining delivery work: real embeddings retrieval, an end-to-end model-quality evaluation, and staging validation of the chart/migration hook.
- CI is a template at `ci/ci.yml` until a token with the `workflow` scope enables it.
- End-to-end (Playwright) tests live in `frontend/e2e`; they need the compose stack and a browser.
- Backend and frontend unit tests exist; end-to-end (Playwright) coverage is still P3.

See `docs/` in the planning repository for the phase plan (P1–P4).
