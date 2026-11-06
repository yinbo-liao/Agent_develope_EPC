# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FPSO EPC Project Control System v4.0 — a real-time monitoring dashboard for FPSO (Floating Production Storage and Offloading) EPC projects. Tracks engineering deliverables → procurement → construction → inspection/NDT → completion → commissioning, plus quality/NCR, HSE safety, training, stage gates, conflicts, feedback loops, traceability, and an AI assistant.

Current size: 18 functional router modules (~131 endpoints) + 5 main.py routes, and a 17-tab React dashboard.

## Critical: Two Backend Entry Points

- **`backend/main.py`** — the production/PostgreSQL app. asyncpg pool, auth, middleware, Prometheus, Redis WebSocket PubSub, AI/RAG. This is what Docker and tests target.
- **`backend/dev_main.py`** — a ~2,500-line **standalone SQLite reimplementation** of the API (own schema, own routers, own AI chat), for zero-dependency demos. It does **not** import the `routers/` modules and will drift from `main.py`. It now enforces JWT auth through `DevAuthMiddleware` (public: login/refresh/logout) and supports admin-only `/api/auth/register`. Changes to API behavior generally need to be mirrored here, or the two apps diverge.

`backend/database.py` is kept only for Alembic/ORM metadata and legacy sessions; the primary pool is `backend/db.py`.

## Commands

### First-time setup (Windows / PowerShell)

```powershell
# .venv is Python 3.13 (Docker uses 3.12)
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt

# Test-only deps (not in requirements.txt)
pip install pytest pytest-asyncio aiosqlite

cd frontend; npm install
```

Copy `.env.example` to `.env` and set at minimum `FPSO_DATABASE_URL` and `FPSO_SECRET_KEY`. `config.Settings` uses `env_prefix="FPSO_"`, `env_file=".env"`, `extra="forbid"`, and has **no defaults** for `database_url`/`secret_key` (startup only warns). `FPSO_API_KEY` is read directly from `os.environ` by `middleware/auth.py`, not by `Settings`.

### Run

```powershell
# Dependencies only
docker-compose up -d postgres redis

# Backend against PostgreSQL — port 8080 is required; the Vite proxy targets it
cd backend; uvicorn main:app --reload --port 8080

# Standalone SQLite backend (no PostgreSQL/Redis needed; serves on 8080)
cd backend; python dev_main.py

# Frontend (proxies /api and /ws to localhost:8080)
cd frontend; npm run dev
```

`main.py`'s `__main__` and the Dockerfile run on **8000**; always pass `--port 8080` for local Vite development.

### Tests

```powershell
# Backend — run from backend/ (pytest.ini lives in backend/tests/)
cd backend; python -m pytest tests/ -q -m "not live"

# Single test
cd backend; python -m pytest tests/test_routers/test_auth.py::TestPasswordHashing::test_hash_and_verify -v

# Endpoint connectivity suite — needs a live server on localhost:8080.
# These tests are marked `live` and excluded from the default run.
cd backend; python dev_main.py
cd backend; python -m pytest tests/test_endpoint_connectivity.py -q -m live

# Full gate (backend + connectivity + security smoke + frontend tests/tsc/build)
.\scripts\verify.ps1

# All-endpoint sweep of the running dev_main (OpenAPI-driven; exit 1 on FAIL)
python scripts\smoke_all_endpoints.py --base-url http://127.0.0.1:8080 --db backend\dev.db

# Playwright E2E — needs dev_main on :8080; Playwright starts Vite itself
cd frontend; npm run test:e2e

# Security smoke alone (needs dev_main on :8080; admin/dev-admin-password)
python scripts/security_smoke.py

# Frontend
cd frontend; npm run test                 # vitest run
cd frontend; npx vitest run src/__tests__/Dashboard.test.tsx
cd frontend; npx tsc --noEmit             # note: npm run build runs `tsc -b`
```

Test-only dependencies live in `backend/requirements-dev.txt` (`pytest`, `pytest-asyncio`, `aiosqlite`, `httpx`, `ruff`, `pip-audit`).

Backend unit tests use a **SQLite in-memory schema** built in `backend/tests/conftest.py` — they do not exercise PostgreSQL-specific SQL (`JSONB`, `gen_random_uuid`, `ROLLUP`). `test_endpoint_connectivity.py` (69 tests) makes real HTTP calls against `dev_main.py` with `PROJECT_ID = "demo-project"`; it passes only while that server is running.

### Database

```powershell
# docker-compose's one-shot `migrate` service applies init.sql and every
# database/migrations/*.sql in filename order (ledger: schema_migrations).
docker compose run --rm migrate

# Against an existing Postgres, apply the same files manually in order:
psql -U fpso_user -d fpso_db -f database/migrations/001_extended_schema.sql
psql -U fpso_user -d fpso_db -f database/migrations/002_auth_schema.sql
psql -U fpso_user -d fpso_db -f database/migrations/003_rag_schema.sql
psql -U fpso_user -d fpso_db -f database/migrations/004_auth_hardening.sql
psql -U fpso_user -d fpso_db -f database/migrations/005_reliability_constraints.sql
```

`001`–`005` are idempotent (guards / `IF NOT EXISTS`) and may be re-run. `004` adds
`project_members` (row-level authorization). `005` adds `schedule_alerts.entity_id`
and the partial unique index used by alert dedup, plus hot-join indexes.

There is no `alembic.ini` or `versions/` directory despite Alembic being in requirements; schema changes are plain SQL migration files.

## Backend Architecture (`backend/`)

```
React SPA → Vite proxy :8080 → FastAPI main.py → db.get_pool() (asyncpg) → PostgreSQL 16
                                             → Redis (WS PubSub, response cache, rate-limit backend)
```

### Core modules

| Path | Responsibility |
|------|----------------|
| `main.py` | App factory, lifespan (`init_pool`), CORS, error handlers, observability + CSRF middleware, slowapi rate limiting (120/min), router registration, `/health`, `/metrics`, `/ws/{project_id}`, alert routes |
| `config.py` | Pydantic Settings, `FPSO_` prefix; DB/Redis/security, DeepSeek + Anthropic, RAG, LangGraph |
| `db.py` | **Unified asyncpg pool** — `init_pool()`, `close_pool()`, `get_pool()` dependency. Use this for new code. |
| `database.py` | SQLAlchemy 2.0 async engine / `get_db()`; legacy + Alembic/ORM metadata only, SQLite fallback when URL is unset |
| `auth.py` | JWT (HS256, 15-min access / 7-day refresh), bcrypt, role hierarchy `admin > project_manager > trade_lead > viewer`, `get_current_user`, `require_role`, `user_has_project_access`, `bootstrap_admin` |
| `routers/auth_router.py` | `/api/auth/login`, `/register` (admin only), `/refresh` (atomic rotation + reuse detection), `/logout`, `/logout-all`, `/me` |
| `errors.py` | `AppError` + `not_found`/`bad_request`/`unauthorized`/`forbidden`/`conflict` factories; `register_error_handlers(app)` produces `{detail, code, context}` |
| `pagination.py` | `PaginationParams` (`page`, `page_size` ≤ 500), `paginate()`, `PaginatedResponse` (`{items, pagination}`) |
| `cache.py` | `@cached(ttl_seconds, key_prefix)` Redis-backed decorator, no-op when Redis is unavailable |
| `websocket.py` | `ConnectionManager` — Redis PubSub per `project:{id}` channel with in-process fallback; tolerates dead connections |
| `middleware/observability.py` | `X-Correlation-ID`, request logging, Prometheus counters/histograms |
| `middleware/csrf.py` | Origin/Referer validation for POST/PUT/PATCH/DELETE against `cors_origins` |
| `middleware/auth.py` | Optional global `X-API-Key` dependency; disabled unless `FPSO_API_KEY` is set |

### DB access rule

- New routes should use `from db import get_pool` and raw SQL: `pool = Depends(get_pool)` then `async with pool.acquire() as conn:`.
- **16 routers still use `from database import get_db` / `AsyncSession`** (engineering, procurement, construction, inspection, reports, equipment, completion, commissioning, quality, safety, training, planning, conflict, stagegate, feedback, ai). Do not assume the pool consolidation is complete.
- ORM models: `backend/models/extended.py` now covers most extended tables (45 models total across `models/`), but there are no `relationship()` definitions and routers mostly bypass the ORM in favor of raw SQL.

### Security model

- **Global authentication:** every feature router is included with
  `dependencies=[Depends(get_current_user)]`. Public endpoints are login, refresh,
  health, and the WS handshake. `FPSO_AUTH_ENFORCEMENT=false` is an emergency
  kill switch that grants a synthetic admin — never use it in production.
- **Writes:** `WriteRoleGuardMiddleware` rejects `viewer` (and unknown roles) with
  403 on POST/PUT/PATCH/DELETE; `trade_lead`+ passes. Missing/invalid tokens are
  left to the route dependency so they still produce a consistent 401.
- **Project access:** `auth.user_has_project_access` uses `project_members`
  (migration 004); admins/PMs bypass. A project with no membership rows remains
  open to authenticated users for backward compatibility.
- **Bootstrap admin:** created on first startup from
  `FPSO_BOOTSTRAP_ADMIN_USERNAME` / `FPSO_BOOTSTRAP_ADMIN_PASSWORD` when the
  users table is empty. Production refuses to start without one, with a short or
  default `FPSO_SECRET_KEY`, without `FPSO_DATABASE_URL`, or with wildcard CORS
  (`config.validate_runtime_config`).
- **Refresh tokens** are opaque, SHA-256-hashed at rest, rotated atomically
  (`UPDATE ... WHERE revoked=FALSE RETURNING user_id`), and replay revokes the
  whole family. `POST /api/auth/logout` / `logout-all` revoke explicitly.
- **WebSocket:** the JWT travels in `Sec-WebSocket-Protocol: bearer.<jwt>` (the
  frontend sends it). `?token=` is accepted only when
  `FPSO_ENVIRONMENT=development`. Origin and project access are checked before
  `manager.connect`; rejection uses close code 1008.
- The optional `X-API-Key` dependency in `middleware/auth.py` still is **not**
  installed globally; it is unused by default.

### AI stack

```
POST /api/ai/chat/{project_id}
  → services/langgraph/graph.py::run_epc_agent
      classify_intent → route_to_tools → execute_tools → validate_results
        → compose_response  (or retry / handle_error; max iterations from config)
  → services/tools/query_tools.py — 11 registered function tools (activities, drawings,
      procurement, NCR, safety, training, stage gates, conflicts, traceability,
      KPI calculation, report generation)
  → services/llm_provider.py — Primary DeepSeek → fallback Anthropic → rule-based
```

- `services/rag/` — schema-aware retrieval: `schema_indexer.py` (hardcoded `EPC_SCHEMA` of ~16 tables), `embedder.py` (provider embeddings or keyword pseudo-embeddings), `retriever.py` (top-K), `summarizer.py` (cached project summaries).
- `services/ai_engine.py` — legacy/traditional analyses: schedule risk, conflict detection, stage-gate assessment, weekly report composition. Uses `AsyncAnthropic` and `timedelta` (previous sync/date bugs are fixed).
- `services/ai_stream.py` — async generator for WebSocket AI events (`thinking`, `tool_call`, `tool_result`, `response`, `done`).
- `services/langgraph/` — state machine (`state.py`, `nodes.py`, `graph.py`, `checkpointer.py`); falls back to a pure-Python state machine when LangGraph is unavailable.
- Chat sessions persist to `ai_sessions` / `ai_messages` (see `database/migrations/003_rag_schema.sql`). `user_id` is currently hardcoded `"anonymous"` in `routers/ai.py`.

### Router map

All routers are registered in `main.py`; counts are `@router` decorators per file.

| Router | # | Router | # |
|--------|---|--------|---|
| `engineering.py` | 12 | `completion.py` | 8 |
| `inspection.py` | 11 | `conflict.py` | 8 |
| `training.py` | 13 | `quality.py` | 8 |
| `construction.py` | 10 | `ai.py` | 7 |
| `planning.py` | 9 | `commissioning.py` | 7 |
| `safety.py` | 9 | `stagegate.py` | 7 |
| `auth_router.py` | 4 | `feedback.py` | 5 |
| `procurement.py` | 4 | `equipment.py` | 3 |
| `traceability_router.py` | 4 | `reports.py` | 2 |

Services: `alert_service.py` (critical float / material shortage / NDT overdue), `traceability_service.py` (forward/backward trace, impact analysis; N+1 queries), `planning_service.py` (**dead code** — router duplicates its date logic; only tests reference it).

## Frontend (`frontend/src/`)

- `App.tsx` — only two routes: `/projects/:projectId` → `Dashboard` (wrapped in `PanelErrorBoundary`), catch-all → `/projects/demo-project`.
- `pages/Dashboard.tsx` (277 lines) — sidebar with 17 tabs: overview, planning, engineering, procurement, construction, completion, commissioning, inspection, quality, safety, training, stagegates, conflicts, feedback, traceability, ai, reports.
- Data layer: TanStack Query (`staleTime: 30s`) + `lib/api-client.ts` (axios, attaches `Authorization: Bearer` from `localStorage`, handles 401 by clearing token). There is **no login UI or auth route** — `setStoredToken()` is exported but unused, so authenticated deployments cannot log in from the SPA.
- `hooks/useWebSocket.ts` — exponential backoff (3s → 30s) and clears its reconnect timer on unmount; however it does **not** append the `?token=` query parameter, so it will be rejected when `FPSO_SECRET_KEY` is non-default.
- Shared helpers: `lib/discipline-utils.ts` is the single source of truth for discipline ID/name mapping (was duplicated three times). UI primitives in `components/ui/` include `ErrorBoundary`, `ConfirmDialog`, `LoadingSkeleton`.
- Type safety is still weak: `types/api.ts` and `types/statuses.ts` are unused; ~112 `any`/`as any` occurrences remain in components.

## Configuration

Key `FPSO_` settings (see `backend/config.py` and `.env.example`):

| Setting | Default | Notes |
|---------|---------|-------|
| `database_url` | `""` | Must be set; `+asyncpg` stripped for the raw pool |
| `secret_key` | `""` | 32+ random chars required; production fails closed when unset/short/default |
| `environment` | `development` | `development` / `test` / `production`; production enables fail-closed config |
| `auth_enforcement` | `true` | Emergency kill switch; `false` grants synthetic admin (never in production) |
| `bootstrap_admin_username` / `bootstrap_admin_password` | `admin` / `""` | First-startup admin; production requires the password |
| `trusted_hosts` | `["localhost","127.0.0.1","testserver"]` | `TrustedHostMiddleware`; add the real hostnames for production |
| `cors_origins` | localhost:5173, :3000 | Also used by CSRF and WS Origin checks |
| `llm_primary` / `llm_fallback` | `deepseek` / `anthropic` | Multi-LLM routing |
| `deepseek_model` | `deepseek-chat` | `deepseek_api_key` required |
| `anthropic_model` | `claude-sonnet-4-20250514` | `anthropic_api_key` required |
| `ai_enabled` | `false` | Master AI toggle |
| `ai_vector_store_type` | `memory` | `memory`, `pgvector`, `qdrant` |
| `ai_rag_top_k` / `ai_rag_similarity_threshold` | 5 / 0.7 | RAG retrieval |
| `langgraph_checkpointer` | `memory` | `memory`, `postgres`, `sqlite` |
| `ai_audit_log_enabled` | `true` | AI recommendation audit trail |

## Known Issues and Gotchas

1. **Authentication is enforced, authorization is coarse.** Every feature router
   requires a valid JWT and writes require `trade_lead`+. Project-level checks
   exist (`user_has_project_access`) but most feature endpoints still accept any
   project ID from an authenticated user; a project is only closed once it has
   rows in `project_members`.
2. **Two backends drift** (`main.py` vs `dev_main.py`) — see the note at the top. `dev_main.py` also duplicates many router definitions instead of importing them. It now enforces JWT auth (including a dev-only `/api/auth/register`, admin-only) so the connectivity and smoke suites exercise the real gate.
3. **Docker schema gap is resolved by the `migrate` service** — compose applies `init.sql` + migrations `001`–`005` and records them in `schema_migrations`. Only the Postgres entrypoint's `init.sql` mount remains for dependency-only startup; run `docker compose run --rm migrate` if you start only Postgres.
4. **Ports** — compose maps frontend `5173:80` (nginx listens on 80) and backend `8000:8000`; nginx proxies `/api` and `/ws` to `backend:8000`. Local Vite dev expects the backend on `8080` (`dev_main.py` or `uvicorn main:app --port 8080`).
5. **API-key middleware is not installed** — `verify_api_key` exists but is not added in `main.py`; it only runs if a route declares it.
6. **Legacy SQLAlchemy sessions** remain in 16 routers (pool consolidation incomplete) and `services/planning_service.py` is dead code.
7. **Pagination is partial** — hot list endpoints now clamp `page_size` ≤ 500 and have LIMITs, but response shapes are still bare lists (`pagination.py` remains largely unused).
8. **Tests are SQLite-only** and will not catch PostgreSQL-specific failures (`FILTER`, `JSONB`, `ROLLUP`, `gen_random_uuid`, partial-index inference). Migrations `004`/`005` and PostgreSQL SQL were reviewed statically, not executed.
9. **Git repository** — the project root is a git repository; commit after each green verification gate.
10. **Demo project ID** — `demo-project` is not a UUID and will fail on PostgreSQL foreign keys. Use a real project UUID for `main.py`; the SQLite dev backend accepts the string.

## Reference Docs (project root)

- `RAG_AI_Assistant_Full_Implementation_Guide.md` — AI/RAG design
- `Agent_Security_Architecture_v2.md` — security architecture
- `VALIDATION.md` — validation notes
