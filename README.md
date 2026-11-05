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
scope; `docs/CI.md` has the one-command enablement. Backend coverage is 56% with a
55% gate; the P3 target is 70%.

## Known limitations (next phases)

- The LLM remains simulated; retrieval is keyword matching and MCP tools are stubs.
- Rate limiting remains in-process (P2 moves it to Redis).
- Remaining delivery work: end-to-end tests, complete Helm chart, real model adapter and the KPI/GATE_G contract.
- CI is a template at `ci/ci.yml` until a token with the `workflow` scope enables it.
- Helm chart is incomplete (no Service/frontend/Ingress; migrations are a no-op job).
- Backend and frontend unit tests exist; end-to-end (Playwright) coverage is still P3.

See `docs/` in the planning repository for the phase plan (P1–P4).
