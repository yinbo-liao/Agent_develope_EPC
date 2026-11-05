# RAG AI Assistant — Full Implementation Guide
## Production-Grade RAG System with Loop Engineering, LangGraph, Function Calling & Multi-LLM Orchestration

**Version:** 2.0 | **Date:** 2026-07-13 | **Philosophy:** Map -> Learn -> Test -> Compress -> Repeat

---

## Table of Contents

1. Executive Summary
2. Architecture Overview
3. Core Concepts
4. Technology Stack
5. System Architecture
6. Directory Structure
7. Database Design
8. Backend Implementation
9. LangGraph Integration
10. Loop Engineering Engine
11. Function Calling & Tool Orchestration
12. Multi-LLM Strategy
13. Frontend Implementation
14. Security Architecture
15. Deployment & DevOps
16. Testing Strategy
17. Performance Optimization
18. Monitoring & Observability
19. Best Practices
20. Appendix

---

## 1. Executive Summary

### 1.1 What This Guide Delivers

This guide provides a complete, production-ready implementation of a RAG AI Assistant integrating:

- **Loop Engineering** — Self-improving feedback cycles
- **LangGraph** — Stateful, cyclic agent workflows
- **Function Calling** — Structured tool invocation
- **Multi-LLM Orchestration** — Intelligent model selection
- **Enterprise Security** — Adaptive threat detection
- **Professional UX** — React + Vite with real-time streaming

### 1.2 Key Differentiators

| Feature | Traditional RAG | This Implementation |
|---------|----------------|---------------------|
| Query Routing | Static rules | Self-learning with A/B testing |
| Quality Assurance | One-shot | Iterative with human-in-the-loop |
| Memory | Simple vector store | Compressed, weighted, time-decayed |
| Security | Fixed regex | Adaptive, evolving threat detection |
| Failure Recovery | Fixed retry | Intelligent strategy adaptation |
| Cost Optimization | None | Dynamic model selection |
| Performance | Degrades with scale | Improves with usage |

### 1.3 Target Use Cases

- Database-aware code generation (FastAPI CRUD, Pydantic models, React components)
- Intelligent SQL assistant with schema-aware query generation
- Automated API documentation from database schemas
- Multi-step task automation with goal tracking
- Enterprise knowledge base with semantic search

---

## 2. Architecture Overview

### 2.1 High-Level Architecture

The system follows a three-layer architecture:

**Layer 1: User Interface (React + Vite)**
- Chat Interface with SSE streaming
- Schema Explorer with ER diagrams
- Goal Dashboard (Kanban board)
- Code Preview (Monaco Editor)
- Loop Metrics & Feedback Panel
- Security Audit Log

**Layer 2: FastAPI Application**
- Security Gate (Adaptive, multi-layer)
- LangGraph Agent Workflow (cyclic, stateful)
- Function Calling Engine (OpenAI-compatible)
- Multi-LLM Orchestrator (gpt-4o, gpt-4o-mini, claude-sonnet-4)
- Loop Engineering Engine (feedback, A/B testing, compression)

**Layer 3: PostgreSQL + pgvector**
- Business Tables (users, orders, etc.)
- Vector Store (documents, embeddings)
- Agent Estate (memory, patterns, lessons)
- Goal State Machine (tasks, checkpoints)
- Loop State (compressed rules, metrics)
- Audit Logs (security events)
- Feedback Queue (human & system)

### 2.2 Data Flow

```
User Query
    |
    v
[Security Gate] --> Blocked? --> Audit Log --> Alert
    |
    v
[LangGraph START] --> classify_query --> Intent + Complexity
    |
    v
[LangGraph CLASSIFY] --> determine_route --> Route + Confidence
    |                      (Loop: check compressed rules)
    v
[LangGraph ROUTE] --> execute_route --> Tool Call / LLM Call
    |                      (Function Calling)
    v
[LangGraph VALIDATE] --> schema_validate --> Pass / Fail
    |
    +-- Pass --> evaluate_quality --> Score
    |              |
    |              +-- Score >= 0.8 --> LEARN
    |              |
    |              +-- Score < 0.8 --> ADAPT
    |
    +-- Fail --> adapt_strategy --> Retry
                   |
                   +-- Max iterations? --> Mark Failed
    |
    v
[LangGraph LEARN] --> Record to Agent Estate --> Compress Rules
    |
    v
[LangGraph END] --> Return result --> Stream to frontend
```

---

## 3. Core Concepts

### 3.1 Loop Engineering (Map -> Learn -> Test -> Compress -> Repeat)

Every interaction is a learning opportunity. The five stages:

1. **MAP**: Define workflow, success criteria, metrics
2. **LEARN**: Collect feedback (ratings, success, quality, latency, tokens)
3. **TEST**: Execute with measurement, A/B test alternatives
4. **COMPRESS**: Distill successful patterns into lightweight rules
5. **REPEAT**: Apply improved strategy next iteration

### 3.2 LangGraph Integration

Stateful, cyclic workflows with explicit graph topology. Key nodes:
- START: Initialize state
- CLASSIFY: Intent recognition
- ROUTE: Path selection
- EXECUTE: Tool/LLM invocation
- VALIDATE: Output verification
- EVALUATE: Quality scoring
- ADAPT: Strategy adjustment
- LEARN: Memory recording
- END: Finalize response

### 3.3 Function Calling Architecture

Tools defined with OpenAI-compatible schemas:
- Schema Tools: get_table_schema, list_tables, get_relationships
- Data Tools: query_table, execute_sql, aggregate_data
- Code Tools: generate_fastapi_crud, generate_pydantic_model
- Analysis Tools: analyze_data, compare_tables, detect_anomalies
- Security Tools: audit_query, check_permissions, scan_for_secrets

### 3.4 Multi-LLM Strategy

| Model | Use Case | Cost | Latency |
|-------|----------|------|---------|
| gpt-4o | Complex generation | High | Medium |
| gpt-4o-mini | Classification, simple queries | Low | Fast |
| claude-sonnet-4 | Long document analysis | Medium | Medium |
| custom-finetuned | Repetitive patterns | Low | Fast |

---

## 4. Technology Stack

### Backend
- FastAPI >=0.110 (async API, auto-docs)
- PostgreSQL >=15 (JSONB, full-text search)
- pgvector >=0.6 (vector similarity)
- SQLAlchemy >=2.0 (async ORM, Alembic migrations)
- LangGraph >=0.1 (stateful workflows)
- OpenAI + Anthropic APIs (multi-provider)
- text-embedding-3 (embeddings)
- APScheduler >=3.10 (background jobs)
- Redis (optional: session cache, rate limiting)

### Frontend
- React >=18, TypeScript >=5.0
- Vite >=5 (build tool)
- Tailwind CSS >=3.4 (styling)
- Zustand >=4.5 (state management)
- React Query >=5 (server state)
- Monaco Editor (code preview)
- React Markdown (rich text)
- Recharts (visualization)
- Lucide React (icons)

### DevOps
- Docker + Docker Compose
- Kubernetes (optional)
- GitHub Actions (CI/CD)
- Prometheus + Grafana (monitoring)
- OpenTelemetry (tracing)

---

## 5. System Architecture

### 5.1 Goal State Machine

```
DRAFT --create--> PENDING --execute--> IN_PROGRESS
                                        |
                                        | all tasks done
                                        v
                                   VALIDATE
                                        |
                        +-------------+-------------+
                        |                           |
                        v                           v
                   validation pass            validation fail
                        |                           |
                        v                           v
                   EVALUATE_QUALITY            ADAPT_STRATEGY
                        |                           |
            +-----------+-----------+               |
            |                       |               |
            v                       v               |
      score >= 0.8           score < 0.8           |
            |                       |               |
            v                       v               |
         COMPLETE                 ADAPT <-----------+
            |                       |
            | archive               | max iterations?
            v                       v
        ARCHIVED                 FAILED
```

---

## 6. Directory Structure

```
rag-ai-assistant/
|-- backend/
|   |-- app/
|   |   |-- main.py                    # FastAPI entry
|   |   |-- config.py                  # Pydantic settings
|   |   |-- database.py                # Async engine + session
|   |   |-- core/                      # Exceptions, security, logging
|   |   |-- models/                    # SQLAlchemy models (12 tables)
|   |   |-- schemas/                   # Pydantic DTOs
|   |   |-- api/routes/                # 8 route modules
|   |   |-- services/                  # 11 service modules
|   |   |-- loops/                     # 6 Loop Engineering loops
|   |   |-- langgraph/                 # Graph, nodes, edges, state
|   |   |-- middleware/                # Security gate, logger, rate limiter
|   |   |-- templates/                 # Jinja2 code templates
|   |-- alembic/                       # DB migrations
|   |-- tests/                         # API, service, loop, LangGraph tests
|   |-- requirements.txt, Dockerfile
|
|-- frontend/
|   |-- src/
|   |   |-- main.tsx, App.tsx
|   |   |-- components/                # Chat, Schema, Goal, Code, Loop, Security
|   |   |-- pages/                     # 7 route pages
|   |   |-- hooks/                     # 8 custom hooks
|   |   |-- services/                  # API clients
|   |   |-- types/                     # TypeScript definitions
|   |   |-- store/                     # Zustand stores
|   |   |-- styles/
|   |-- package.json, vite.config.ts, Dockerfile
|
|-- docker-compose.yml, .env.example, Makefile
|-- docs/                              # Architecture, API, deployment guides
```

---

## 7. Database Design

### 7.1 Tables (12 total)

**goals** — Goal state machine with task trees, token budgets, quality tracking
**agent_estate** — Vector memory with learning metrics (success_rate, usage_count, weight)
**schema_registry** — Table metadata with vector embeddings, access control
**vector_store** — RAG documents with versioning, tagging
**sessions** — Conversation context with vector summaries, expiration
**messages** — Chat history with tool calls, token usage, metadata
**tool_calls** — Execution logging with performance metrics
**audit_logs** — Security & compliance with resolution tracking
**loop_state** — Loop execution tracking with improvements
**feedback_queue** — Human & system feedback with processing status
**compressed_rules** — Loop Engineering output with evidence, confidence
**security_rules** — Adaptive security with false positive tracking

### 7.2 Key Indexes

- IVFFlat vector indexes on agent_estate.embedding, schema_registry.embedding, vector_store.embedding
- GIN indexes on JSONB arrays (related_tables, tags)
- Partial indexes for active records, unprocessed feedback, blocked events
- Composite indexes for common query patterns

---

## 8. Backend Implementation

### 8.1 Configuration (config.py)

Key settings:
- Multi-LLM: DEFAULT_MODEL, FAST_MODEL, DEEP_MODEL, ANALYSIS_MODEL
- Loop Engineering: LOOP_ENABLED, LOOP_COMPRESSION_INTERVAL_HOURS, LOOP_AB_TEST_RATIO
- Security: SECURITY_AUTO_LEARN, SQL_DANGEROUS_PATTERNS, SQL_ALLOWED_TABLES
- Token Budget: DEFAULT_TOKEN_BUDGET, MAX_TOKEN_BUDGET, TOKEN_BUDGET_ESCALATION
- Quality: GOAL_QUALITY_THRESHOLD=0.8

### 8.2 Core Models

**Goal Model**: State machine with get_next_pending_task(), complete_task(), is_all_tasks_completed()
**AgentEstate Model**: Vector memory with query_pattern_embedding, success_rate, is_compressed flags
**CompressedRule Model**: Pattern + action with evidence_count, confidence, is_reviewed gates
**LoopState Model**: Execution tracking with iterations_completed, improvements_found, rules_compressed
**Feedback Model**: Queue with is_processed, processed_by, loop_type_applied
**SecurityRule Model**: Adaptive rules with false_positive_count, true_positive_count, is_auto_generated

### 8.3 Database Connection

Async SQLAlchemy with connection pooling, auto-commit/rollback, init_db() for table creation.

---

## 9. LangGraph Integration

### 9.1 State (RAGState)

TypedDict with: query, user_id, session_id, query_type, complexity, route, route_confidence, retrieved_docs, context, tool_calls, llm_output, validation_result, quality_score, evaluation_details, iteration, max_iterations, token_budget, tokens_used, history, feedback, compressed_rules, error, final_output, final_metadata

### 9.2 Graph Nodes

- **start_node**: Initialize iteration=0, tokens_used=0, history=[]
- **classify_node**: TableRAGAgent.classify_query() -> intent + complexity
- **route_node**: Check compressed rules first (confidence > 0.9), fallback to agent.determine_route()
- **execute_node**: agent.execute_route(), catch exceptions
- **validate_node**: schema_validate() based on query_type
- **evaluate_node**: LLM quality evaluation with weighted scoring
- **adapt_node**: agent.adapt_strategy() with failure_info, increment iteration, record history
- **learn_node**: Record to AgentEstate, collect auto-feedback
- **end_node**: Format final_output and final_metadata

### 9.3 Edge Conditions

- **validation_router**: Pass if is_valid, else Fail
- **quality_router**: Good if score >= 0.8, else Poor
- **should_continue**: Stop if iteration >= max or error after 3 retries
- **error_router**: Error if state.error exists

---

## 10. Loop Engineering Engine

### 10.1 Base Loop Class

```python
class BaseLoop(ABC):
    async def run(self):
        map_result = await self._map()
        learn_result = await self._learn(map_result)
        test_result = await self._test(learn_result)
        compress_result = await self._compress(test_result)
        repeat_result = await self._repeat(compress_result)
        return {"loop_type": self.loop_type, "map": map_result, ...}

    @abstractmethod
    async def _map(self): pass
    @abstractmethod
    async def _learn(self, map_result): pass
    @abstractmethod
    async def _test(self, learn_result): pass
    @abstractmethod
    async def _compress(self, test_result): pass
    @abstractmethod
    async def _repeat(self, compress_result): pass
```

### 10.2 Classification Loop

- **MAP**: Define classification accuracy metrics
- **LEARN**: Collect (query, predicted_intent, actual_outcome) tuples
- **TEST**: A/B test keyword vs LLM classification
- **COMPRESS**: Extract patterns for "obvious" classifications (e.g., "Generate CRUD for X" -> always CODE_GENERATION)
- **REPEAT**: Update classification rules, reduce LLM calls by 60-80%

### 10.3 Route Optimization Loop

- **MAP**: Define route performance metrics (quality, latency, cost)
- **LEARN**: Retrieve historical performance per route per query pattern
- **TEST**: Multi-armed bandit (90% exploitation, 10% exploration)
- **COMPRESS**: Hardcode rules when confidence > 0.95
- **REPEAT**: Update route statistics, achieve 95%+ optimal selection

### 10.4 Quality Evaluation Loop

- **MAP**: Define evaluation dimensions (syntax, schema, security, completeness, quality)
- **LEARN**: Collect human feedback on evaluations
- **TEST**: Compare strict vs lenient evaluators
- **COMPRESS**: Update base weights when patterns emerge
- **REPEAT**: Save evolved evaluation prompt templates

### 10.5 Security Loop

- **MAP**: Define security metrics (false positive rate, detection rate)
- **LEARN**: Analyze false positive/negative history
- **TEST**: New rules in shadow mode (log but don't block)
- **COMPRESS**: Proven rules become hardcoded (no LLM needed)
- **REPEAT**: Update security rule set with human review gate

### 10.6 Memory Compression Loop

- **MAP**: Identify memory clusters with high success rates
- **LEARN**: Analyze what made memories successful
- **TEST**: Replace 100 similar memories with 1 rule
- **COMPRESS**: Archive raw memories, keep distilled rules
- **REPEAT**: Apply compressed rules, verify they still work

---

## 11. Function Calling & Tool Orchestration

### 11.1 Tool Registry

```python
class ToolRegistry:
    def __init__(self):
        self.tools = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition):
        self.tools[tool.name] = tool

    def get_openai_schema(self) -> List[Dict]:
        return [{"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.parameters
        }} for t in self.tools.values()]

    async def execute(self, name: str, arguments: Dict, db: AsyncSession) -> Dict:
        tool = self.tools.get(name)
        if not tool.is_safe:
            security_check = await self._security_check(tool, arguments)
            if not security_check["passed"]:
                return {"success": False, "error": security_check["reason"]}
        result = await tool.handler(db=db, **arguments)
        return {"success": True, "data": result, "tool": name}
```

### 11.2 Default Tools

| Tool | Category | Safety | Handler |
|------|----------|--------|---------|
| get_table_schema | schema | Safe | _handle_get_schema |
| query_table | data | Unsafe | _handle_query_table |
| generate_code | code | Safe | _handle_generate_code |
| list_tables | schema | Safe | _handle_list_tables |
| execute_sql | data | Unsafe | _handle_execute_sql |
| analyze_data | analysis | Safe | _handle_analyze_data |
| audit_query | security | Safe | _handle_audit_query |

---

## 12. Multi-LLM Strategy

### 12.1 Model Selection Algorithm

```python
def select_model(task_type: str, complexity: float, budget: int, latency_sla: int) -> str:
    # Check learned preferences from Loop memory
    learned = memory.get_optimal_model(task_type, complexity)
    if learned and learned.confidence > 0.9:
        return learned.model

    # Fallback to rule-based selection
    if complexity < 0.3 and latency_sla < 2000:
        return "gpt-4o-mini"
    elif complexity > 0.7 or task_type == "CODE_GENERATION":
        return "gpt-4o"
    elif task_type == "ANALYSIS" and complexity > 0.5:
        return "claude-sonnet-4"
    else:
        return "gpt-4o-mini"
```

### 12.2 LLM Client

```python
class LLMClient:
    def __init__(self):
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate(self, prompt: str, model: str, **kwargs) -> str:
        if model.startswith("gpt"):
            return await self._openai_generate(prompt, model, **kwargs)
        elif model.startswith("claude"):
            return await self._anthropic_generate(prompt, model, **kwargs)

    async def generate_with_tools(self, prompt: str, model: str, tools: List[Dict], **kwargs):
        # OpenAI function calling
        response = await self.openai.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}],
            tools=tools, tool_choice="auto", **kwargs
        )
        return response.choices[0].message
```

---

## 13. Frontend Implementation

### 13.1 Key Components

**ChatInterface**: Main chat with SSE streaming, suggestion chips, tool call cards
**SchemaViewer**: Table browser with ER diagrams, column details, search
**GoalDashboard**: Kanban board with progress bars, timeline, filters
**CodePreview**: Monaco editor with syntax highlighting, file tree, download
**LoopMetrics**: Charts showing loop performance, A/B test results, rule compression
**SecurityLog**: Audit log viewer with severity filtering, resolution tracking

### 13.2 State Management (Zustand)

```typescript
interface AppState {
    selectedTable: string | null;
    sessionId: string | null;
    activeGoalId: string | null;
    previewCode: string | null;
    previewLanguage: string;
    notifications: Array<{id: number; type: string; message: string}>;
    setSelectedTable: (table: string | null) => void;
    setSessionId: (id: string | null) => void;
    setActiveGoalId: (id: string | null) => void;
    setPreviewCode: (code: string | null, language?: string) => void;
    addNotification: (type: string, message: string) => void;
    removeNotification: (id: number) => void;
}
```

### 13.3 Custom Hooks

- **useChat**: Chat state, sendMessage, SSE connection, tool call handling
- **useGoals**: Goal CRUD, progress tracking, filter/sort
- **useSchema**: Table queries, schema details, relationship mapping
- **useLoops**: Loop metrics, feedback submission, rule viewing
- **useSecurity**: Audit logs, threat dashboard, rule management
- **useSSE**: Server-sent events connection, auto-reconnect
- **useWebSocket**: Real-time updates for goal progress

---

## 14. Security Architecture

### 14.1 Multi-Layer Security

| Layer | Component | Description |
|-------|-----------|-------------|
| 1 | Regex Filter | Static dangerous pattern matching (DROP, TRUNCATE, etc.) |
| 2 | Pattern Learning | Evolving rules based on attack logs |
| 3 | Semantic Analysis | LLM-based intent analysis for novel attacks |
| 4 | Behavioral Analysis | Anomaly detection for user behavior |

### 14.2 Adaptive Security

```python
class SecurityEngine:
    async def check(self, request, body_str) -> Dict:
        # Layer 1: Regex (fast, deterministic)
        for pattern in self.dangerous_patterns:
            if pattern.search(body_str):
                return {"blocked": True, "reason": "Regex match", "layer": 1}

        # Layer 2: Learned patterns
        learned = await self.get_learned_rules(body_str)
        if learned and learned.confidence > 0.9:
            return {"blocked": True, "reason": "Learned pattern", "layer": 2}

        # Layer 3: Semantic analysis (LLM, slower)
        if self.should_use_semantic(body_str):
            semantic = await self.semantic_analysis(body_str)
            if semantic.risk_score > 0.8:
                return {"blocked": True, "reason": "Semantic risk", "layer": 3}

        # Layer 4: Behavioral anomaly
        if self.is_anomalous(request):
            return {"blocked": True, "reason": "Behavioral anomaly", "layer": 4}

        return {"blocked": False}
```

### 14.3 Security Rule Evolution

- New rules start in shadow mode (log only)
- After 10 true positives and < 2 false positives, activate
- After 5 false positives, disable and retrain
- Auto-generated rules require human review before activation

---

## 15. Deployment & DevOps

### 15.1 Docker Compose

```yaml
version: '3.8'
services:
  postgres:
    image: ankane/pgvector:latest
    environment:
      POSTGRES_USER: rag_user
      POSTGRES_PASSWORD: rag_password
      POSTGRES_DB: rag_assistant
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag_user -d rag_assistant"]
      interval: 10s, timeout: 5s, retries: 5

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://rag_user:rag_password@postgres:5432/rag_assistant
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    ports: ["8000:8000"]
    depends_on:
      postgres: {condition: service_healthy}
    volumes: ["./generated:/app/generated"]
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports: ["5173:80"]
    depends_on: [backend]
    restart: unless-stopped

volumes:
  postgres_data:
```

### 15.2 Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://rag_user:rag_password@localhost:5432/rag_assistant

# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Security
SQL_ALLOWED_TABLES=users,orders,products
SQL_BLOCKED_TABLES=admin_config,system_settings

# Loop Engineering
LOOP_ENABLED=true
LOOP_COMPRESSION_INTERVAL_HOURS=24
LOOP_AB_TEST_RATIO=0.1

# App
DEBUG=false
LOG_LEVEL=INFO
```

---

## 16. Testing Strategy

### 16.1 Test Categories

| Category | Scope | Tools |
|----------|-------|-------|
| Unit Tests | Individual functions | pytest, mock |
| Integration Tests | API endpoints | httpx, TestClient |
| Loop Tests | Self-improvement cycles | pytest-asyncio |
| LangGraph Tests | Graph execution | pytest, fixtures |
| Security Tests | Threat scenarios | pytest, parameterized |
| E2E Tests | Full user flows | Playwright |

### 16.2 Key Test Cases

- Query classification accuracy > 90%
- Route selection optimality > 85%
- Quality evaluation correlation with human ratings > 0.8
- Security gate: 100% block rate for known attacks, < 5% false positive
- Loop compression: 10+ memories -> 1 rule with > 0.9 confidence
- Token budget: Never exceed max budget, graceful degradation

---

## 17. Performance Optimization

### 17.1 Strategies

| Optimization | Method | Impact |
|-------------|--------|--------|
| Intent Classification | Compressed rules (O(1) lookup) | 60-80% LLM call reduction |
| Route Selection | Hardcoded rules after compression | 5-10x retrieval speedup |
| Vector Retrieval | IVFFlat index + batching | 5x speedup |
| Context Caching | Cache common schemas | 30% token reduction |
| Tool Result Caching | Cache deterministic queries | 50% repeat query reduction |
| Model Selection | gpt-4o-mini for 80% of tasks | 70% cost reduction |

### 17.2 Expected Improvements Over Time

```
Week 1: Baseline (static rules) - latency 5s, cost $0.05/query, quality 0.72
Week 2: Initial learning - latency 4s, cost $0.04/query, quality 0.78
Week 3: Pattern compression - latency 2.5s, cost $0.025/query, quality 0.85
Week 4: Mature rules - latency 1.5s, cost $0.015/query, quality 0.91
Week 8: Continuous refinement - latency 1.2s, cost $0.012/query, quality 0.94
```

---

## 18. Monitoring & Observability

### 18.1 Metrics

**System Metrics**: API latency, error rate, throughput, DB connection pool
**LLM Metrics**: Token usage per model, cost per query, latency per model
**Loop Metrics**: Compression rate, rule accuracy, A/B test results, feedback volume
**Security Metrics**: Blocked requests, false positive rate, threat detection rate
**Quality Metrics**: Average quality score, human rating correlation, completion rate

### 18.2 Alerting

| Condition | Severity | Action |
|-----------|----------|--------|
| Security blocks > 10/hour | Critical | Alert security team |
| API error rate > 5% | Warning | Page on-call |
| DB connection pool > 90% | Warning | Scale horizontally |
| Loop divergence detected | Critical | Disable auto-learning |
| Cost per query > $0.10 | Warning | Review model selection |

---

## 19. Best Practices

### 19.1 Development
- Always use parameterized queries (prevent SQL injection)
- Version control prompts and templates
- A/B test all changes to evaluation criteria
- Human review gate for compressed rules before activation
- Structured logging with correlation IDs

### 19.2 Operations
- Daily backup of database and vector indexes
- Weekly review of compressed rules
- Monthly security rule audit
- Quarterly model performance review
- Graceful degradation: if LLM fails, fall back to cached rules

### 19.3 Security
- Never hardcode API keys
- Encrypt sensitive data at rest
- Rate limit all endpoints
- Audit all database operations
- Principle of least privilege for table access

---

## 20. Appendix

### 20.1 Terminology

| Term | Definition |
|------|-----------|
| RAG | Retrieval-Augmented Generation |
| Loop Engineering | Self-improving feedback cycles |
| Goal | User-defined task with subtasks and success criteria |
| Agent Estate | Persistent memory system with vector search |
| Route | Execution path (DIRECT_SQL, LLM_RAG, LLM_RAG_DEEP, PARALLEL_BOTH) |
| Compressed Rule | Distilled pattern from multiple successful memories |
| Function Calling | Structured tool invocation via LLM |
| LangGraph | Stateful, cyclic agent workflow framework |

### 20.2 References

- Loop Engineering: WeChat article "2026 10 Real Scenarios"
- Project Agent: Original RAG implementation guide
- LangGraph: https://github.com/langchain-ai/langgraph
- FastAPI: https://fastapi.tiangolo.com/
- pgvector: https://github.com/pgvector/pgvector
- OpenAI Function Calling: https://platform.openai.com/docs/guides/function-calling

### 20.3 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-07-10 | Initial RAG implementation |
| 2.0 | 2026-07-13 | Added Loop Engineering, LangGraph, Multi-LLM, Adaptive Security |

---

*This document integrates Loop Engineering principles with production-grade RAG architecture. The system is designed to improve continuously through the Map -> Learn -> Test -> Compress -> Repeat cycle, making it more secure, reliable, stable, and performant with every interaction.*
