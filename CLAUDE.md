# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Workflow Platform — a multi-agent AI workflow orchestration platform that processes user queries through a graph-based pipeline with risk assessment, model routing, cost governance, and human-in-the-loop review. The platform runs Claude and other LLMs behind a FastAPI backend with real-time event streaming to a React dashboard.

The master implementation strategy and delivery status across Waves 1–4 is documented in `ai_agent_dev_strategy.md` (216 KB). Waves 1–4 are complete: backend foundation, workflow engine, realtime monitoring, and cost governance / production assets.

## Architecture

### Workflow Execution Pipeline

User queries flow through a deterministic graph (`api/app/workflows/graph.py`):
1. **validate_input** — rejects empty queries
2. **retrieve_context_node** — keyword-based context retrieval (placeholder for vector search)
3. **assess_risk** — regex-based risk scoring classifies into LOW / MEDIUM / HIGH / CRITICAL
4. **Execute** based on risk level:
   - LOW → `auto_generate_response` (fast model, high temperature)
   - MEDIUM/HIGH → `complex_analysis` (powerful model, low temperature)
   - CRITICAL → `human_review_node` (pauses workflow, awaits human decision)

Each node returns a dict of state updates that are applied to the `WorkflowRun` ORM model and broadcast via WebSocket/SSE.

### Risk Assessment

Pattern-based scoring in `assess_risk()`:
- Critical patterns (payment data, destructive ops, privilege escalation): +50 each
- High patterns (delete/remove, credential access): +20 each
- Context volume bonus: up to +10
- Thresholds: ≥50 = CRITICAL, ≥30 = HIGH, ≥10 = MEDIUM, else LOW

### Model Router & Cost Governance

`ModelRouter` selects models based on task complexity and user budget tier. `CostGovernor` enforces per-tier daily token/cost limits in memory (Free: 10K tokens/$1, Starter: 100K/$10, Professional: 1M/$100, Enterprise: 10M/$1000). Budget checks happen before every LLM call; exceeding limits fails the workflow.

### Real-time Events

Dual transport: WebSocket (primary) with SSE fallback. `RedisWebSocketManager` (`api/app/core/websocket_manager.py`) bridges Redis pub/sub for multi-instance fanout, degrades gracefully to local-only when Redis is unavailable. The frontend hook `useWorkflowEvents` auto-negotiates WebSocket → SSE fallback.

### Security Layers

1. **OPA Policy Engine** (`infrastructure/opa/agent-policies.rego`) — enforces agent read/write/execute/network scopes at the policy level
2. **Security Firewall Hook** (`.claude/hooks/security_firewall_v2.py`) — blocks dangerous shell commands, protected path access, destructive SQL, and hardcoded secrets
3. **Audit Logger** (`.claude/hooks/audit_logger_v2.py`) — structured JSONL logging with secret sanitization
4. **MCP Interceptors** (`api/app/core/mcp_interceptors.py`) — audit logging + rate limiting for MCP tool calls
5. **Middleware** — `SecurityHeadersMiddleware`, `RateLimitMiddleware` (in-memory sliding window), `CorrelationIdMiddleware`

### Database Models

Core tables on `Base` (SQLAlchemy async):
- `workflow_runs` — primary entity; tracks full workflow lifecycle, tokens, cost, risk, human review state
- `human_review_decisions` — audit trail of reviewer decisions
- `mcp_tool_call_audits` — MCP tool invocation audit log
- `audit_events` — append-only, hash-chained governance log
- `refresh_tokens` — refresh-token registry for rotation and revocation
- `idempotency_keys` — per-user replay protection for workflow creation
- `workflow_jobs` — durable execution queue with attempts, locks and visibility timeout

## Repository Layout

```
api/                          FastAPI backend (Python 3.11+)
  app/
    api/v1/                   REST endpoints: workflows, events, human-review, cost, mcp, health
    core/                     Config, database, circuit breaker, cost tracker, logging,
                              MCP client, metrics, SSE/WS managers, tracing
    middleware/               Correlation ID, security headers, rate limiting
    models/                   SQLAlchemy ORM models (workflow, human_review, audit)
    security/                 OPA policy client
    services/                 Cost governor, LLM client, model router, vector store
    workflows/                Graph executor, node implementations, runner, human review handler
  tests/unit/                 pytest async tests
frontend/                    React 19 SPA (TypeScript 5, Vite 5, Tailwind 3)
  src/
    components/               Dashboard, StepTimeline, HumanReviewPanel, CostDisplay, etc.
    hooks/                    useWorkflowEvents (WebSocket+SSE dual transport)
    lib/                      Runtime config (API/WS base URLs)
    pages/                    HomePage (workflow launcher + dashboard)
    types/                    WorkflowState, WorkflowEvent, WorkflowSummary types
infrastructure/
  docker/api/                 Dev + production Dockerfiles for backend
  docker/frontend/            Dev + production Dockerfiles, nginx.conf, security-headers.conf
  opa/agent-policies.rego     OPA agent scope policies
  prometheus/                 Alerts (high error rate, high LLM cost) + Alertmanager config
  grafana/dashboards/         Pre-built Grafana dashboard JSON
helm/aiwf/                    Kubernetes Helm chart (deployment, analysis templates, migration job)
.claude/
  agents/                     Agent role definitions (governor, frontend-dev, backend-dev, etc.)
  hooks/                      Security firewall + audit logger Python scripts
scripts/                      validate_agent_scopes.py
tests/security/               Firewall hook tests
api/.env.example              Environment variable template for local development
```

## Demo authentication

Every workflow, event and review endpoint requires a JWT. Development seeds two users
(`SEED_DEMO_USERS=true`): `demo` / `demo-pass-1234` (viewer) and `reviewer` /
`reviewer-pass-1234` (reviewer) and `admin` / `admin-pass-1234` (admin; provisioning and audit verification). The frontend signs in via `POST /api/v1/auth/token` and
sends `Authorization: Bearer`; WebSocket/SSE use a task-scoped ticket from
`POST /api/v1/events/ticket/{task_id}`.
## Commands

### Backend (from `api/`)

```bash
# Install dev dependencies
pip install -e .[dev]

# Run development server (hot reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term

# Run a single test file
pytest tests/unit/test_workflow_nodes.py

# Run a single test function
pytest tests/unit/test_workflow_nodes.py::test_assess_risk_marks_destructive_queries_critical

# Lint (ruff)
ruff check .

# Type check (mypy strict mode)
mypy .
```

### Frontend (from `frontend/`)

```bash
npm install
npm run dev          # Vite dev server on :5173
npm run build        # TypeScript check + production build
npm run typecheck    # tsc --noEmit only
npm test             # Vitest unit tests
```

### Evidence (from `api/`)

```bash
python scripts/evidence.py record   --out evidence/backend.json --workflow backend --commit "$(git rev-parse HEAD)"   --coverage-xml coverage.xml --min-coverage 55   --check "ruff=ruff check ." --check "tests=pytest -q --cov=app --cov-report=xml"
python scripts/evidence.py verify evidence/backend.json --commit "$(git rev-parse HEAD)"
```

See `docs/EVIDENCE.md`; CI template is `ci/ci.yml` and enablement is in `docs/CI.md`.

### Docker Compose (from repo root)

```bash
docker compose up -d              # Start all services (DB, Redis, OPA, backend, frontend)
docker compose up -d postgres redis opa  # Infrastructure only
docker compose logs -f backend    # Tail backend logs

# Production builds
docker build -f infrastructure/docker/api/Dockerfile.prod -t aiwf-api .
docker build -f infrastructure/docker/frontend/Dockerfile.prod -t aiwf-frontend .
```

### Kubernetes (Helm)

```bash
helm lint helm/aiwf -f helm/aiwf/values-production.yaml
helm template aiwf helm/aiwf -f helm/aiwf/values-production.yaml --namespace aiwf >/tmp/rendered.yaml
helm upgrade --install aiwf helm/aiwf -f helm/aiwf/values-production.yaml --namespace aiwf
```

The pre-install/pre-upgrade Job runs `alembic upgrade head`. Create the `aiwf-secrets`
secret first (SECRET_KEY, DATABASE_URL, REDIS_URL, optional METRICS_TOKEN); see
`docs/DEPLOYMENT.md`.

### Monitoring (local compose)

Prometheus `:9090`, Alertmanager `:9093`, Grafana `:3000` (admin/admin default).
Scrape config and SLO alerts live in `infrastructure/prometheus/`; dashboards in
`infrastructure/grafana/`. Job metrics: `workflow_jobs_total`, `workflow_job_queue_depth`.

### Pre-commit & Security

```bash
pre-commit run --all-files        # Run all hooks (trailing whitespace, YAML check, secret detection, firewall tests, scope validation)
python scripts/validate_agent_scopes.py  # Validate .claude/agents/*.md have required headings
pytest tests/security/test_firewall.py   # Run security firewall tests
```

## Key Design Decisions

- **Fail-closed OPA**: If the OPA policy engine is unreachable, access is denied (not granted)
- **Graceful Redis degradation**: WebSocket manager falls back to local-only fanout when Redis is unavailable
- **Circuit breaker on LLM calls**: 3 consecutive failures open the circuit for 30s before retrying
- **LLM client is simulated**: `LLMClient.generate()` produces placeholder responses with token/cost estimation — real provider integration is a future wave
- **Vector store is keyword-based**: `retrieve_context()` in `vector_store.py` extracts topic keywords rather than performing real embeddings search
- **MCP tools are fallback stubs**: `ResilientMCPClient` returns placeholder results for all MCP servers unless explicitly enabled via settings
- **Human review deadline**: 30-minute window; the workflow remains in REVIEWING status until a decision is posted
- **Durable execution**: workflow creation enqueues a `workflow_jobs` row; a worker claims it with a conditional update (`SKIP LOCKED` on PostgreSQL), retries with backoff and sweeps stale `running` jobs
- **Review binding**: the pending run stores `review_state_hash`; a decision is rejected if the request, risk level or risk factors changed meanwhile
- **Audit chain**: every governance event commits to the previous hash; `GET /audit/verify` detects edits and deletions
- **Refresh rotation**: refresh tokens are registered by `jti`; replay of a revoked token revokes every session for the user
- **Idempotency**: `Idempotency-Key` on workflow creation returns the original run instead of duplicating it
- **MCP policy**: runtime MCP invocations are evaluated by OPA (`aiwf/mcp`) and fail closed
- **Atomic budgets**: Redis Lua reserves tokens/cost before an LLM call; `commit_usage` reconciles the reservation to actual usage; production fails closed when the ledger is unavailable
- **Helm/ops**: chart renders Service/Ingress/HPA/PDB/NetworkPolicy and a real alembic migration hook; Prometheus scrapes `/metrics`, alerts on 5xx/p95/queue depth/job failures/cost

## Agent Definitions

The `.claude/agents/` directory defines five agent roles used by Claude Code's agent system. Each agent has scoped read/write/execute permissions enforced by the OPA policy in `infrastructure/opa/agent-policies.rego`. The `scripts/validate_agent_scopes.py` pre-commit hook ensures every agent file has `## Scope` and `## Standards` headings.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service health |
| `GET` | `/health/ready` | Readiness (DB + Redis check) |
| `POST` | `/api/v1/workflows` | Create and queue a workflow run |
| `GET` | `/api/v1/workflows` | List the caller's workflow runs |
| `GET` | `/api/v1/workflows/{task_id}` | Get workflow detail |
| `POST` | `/api/v1/human-review/decide` | Approve/reject a paused workflow (reviewer role; no self-approval; bound to review_state_hash) |
| `GET` | `/api/v1/events/state/{task_id}` | Get current workflow state snapshot |
| `POST` | `/api/v1/auth/refresh` | Rotate a refresh token (reuse revokes the family) |
| `POST` | `/api/v1/auth/logout` | Revoke a refresh token |
| `POST` | `/api/v1/auth/users` | Admin-only user provisioning |
| `GET` | `/api/v1/auth/users` | Admin-only user list |
| `GET` | `/api/v1/audit/events` | Admin-only recent audit events |
| `GET` | `/api/v1/audit/verify` | Verify the audit hash chain |
| `POST` | `/api/v1/events/ticket/{task_id}` | Issue a 2-minute, task-scoped stream ticket |
| `GET` | `/api/v1/events/sse/{task_id}?ticket=` | SSE event stream for a workflow |
| `WS` | `/api/v1/events/ws/{task_id}?ticket=` | WebSocket stream (`ping`, `status`; decisions are REST-only) |
| `GET` | `/api/v1/cost/status` | Cost governance status for the authenticated caller |
| `GET` | `/api/v1/mcp/health` | MCP server health status |
| `GET` | `/api/v1/mcp/tools` | List available MCP tools |
| `POST` | `/api/v1/mcp/invoke/{server}/{tool}` | Invoke an MCP tool |

Prometheus metrics are exposed at `GET /metrics` when enabled; in production the endpoint is hidden unless `METRICS_TOKEN` is set, and scrapers must send `X-Metrics-Token`. API docs are served only when `ENVIRONMENT=development`. Key metrics: `llm_cost_usd_total` (by model), `mcp_tool_calls_total` (by server/tool/status).

## Configuration

All backend settings live in `api/app/core/config.py` using `pydantic-settings`. Copy `api/.env.example` to `api/.env` for local development. Environment variables are case-sensitive. Key settings:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | postgresql+asyncpg://... | Async PostgreSQL connection |
| `REDIS_URL` | redis://... | Redis for pub/sub |
| `OPA_URL` | http://opa:8181 | OPA policy engine |
| `ENVIRONMENT` | development | development/test/staging/production |
| `JWT_ISSUER` | aiwf | Required JWT issuer |
| `JWT_AUDIENCE` | aiwf-api | Required JWT audience |
| `MCP_POLICY_ENFORCE` | true | Evaluate MCP calls against OPA `aiwf/mcp` |
| `WORKER_ENABLED` | true | Run the built-in workflow job worker |
| `WORKER_POLL_SECONDS` | 2.0 | Queue poll interval |
| `JOB_MAX_ATTEMPTS` | 3 | Delivery attempts before a job is failed |
| `JOB_VISIBILITY_TIMEOUT_SECONDS` | 300 | Age after which a `running` job is an orphan |
| `SEED_DEMO_USERS` | false | Seed the demo requester/reviewer (development only) |
| `METRICS_TOKEN` | unset | Required header value for `/metrics` in production |
| `REQUESTS_PER_MINUTE` | 120 | Rate limit threshold |
| `MCP_*_ENABLED` | varies | Toggle MCP server stubs |
