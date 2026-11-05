# Enterprise Agentic AI Security Architecture — v2.0
**Stack:** React/Vite | FastAPI | LangGraph | PostgreSQL + pgvector | Celery sandbox workers
**Status:** Normative blueprint (supersedes "Agent security and compliance for web design_rev")
**Change basis:** v1 review + advanced proposal (multi-agent, output firewall, governance, evidence engine)

---

## 0. What Changed from v1 (Change Log)

| # | Area | v1 | v2 Decision | Why |
|---|------|----|-------------|-----|
| C1 | Prompt-injection defence | Regex middleware = "Guardrail 1" | Downgraded to *signal only*; real control = capability limits + Auditor + HITL | Pattern scanners are bypassable; must not be relied on as a gate |
| C2 | Sandwich defence | Primary RAG defence | Kept as hygiene; added **taint tracking** (untrusted content cannot trigger high-risk tools) | Wrapping text does not stop indirect injection |
| C3 | Security Auditor | Same LLM-style node | **Deterministic policy engine first** (OPA/Cedar or Python rules), LLM judge optional second opinion | Auditor must not be injectable itself |
| C4 | CoT streaming | Stream Chain-of-Thought | Stream **step status summaries** only | Raw reasoning leaks prompts, data, and policy logic |
| C5 | Pydantic strictness | `additionalProperties:false` | `model_config = ConfigDict(extra="forbid", strict=True)` | Correct Pydantic v2 mechanism |
| C6 | DB permissions | Agent: INSERT logs only | Role-per-function (see §6.2); agent never holds DDL; audit table append-only + hash-chained | v1 conflicted with tools that legitimately write |
| C7 | CI injection evals | Assert 50 payloads all `DENIED` | Threshold-based (e.g., ≥98% block, 0 high-risk tool executions) on a versioned, growing corpus | LLM behaviour is probabilistic; zero-execution is the hard assertion |
| C8 | Risk tiers | none/high | 5 tiers with mapped controls (§4.2) | Granularity for dual approval |
| C9 | New | — | Agent identity & delegation, Output Firewall, Model/Prompt registry, Data classification, Memory trust tiers, Evidence engine, Observability, Supply chain, Control mapping | Gaps from review |

---

## 1. Principles (Normative)

1. **Prompts guide; code enforces.** Every rule in a prompt must have an enforcing control in code, DB, or infrastructure.
2. **Least capability per run.** Tools available to a run are computed from *user scopes ∩ agent scopes ∩ task profile ∩ data taint state*.
3. **Untrusted by default.** User input, retrieved documents, emails, attachments, and tool outputs are *untrusted data*, never instructions.
4. **Deterministic gates for irreversible actions.** No irreversible action is authorised by an LLM alone.
5. **Evidence over assertion.** Any recommendation (e.g., "close comment") must cite retrievable evidence IDs or be refused.
6. **Everything replayable.** Model, prompt version, inputs, retrieved chunks, tool calls, and verdicts are recorded per step.

---

## 2. Reference Architecture

```text
┌──────────────────────────── React/Vite Portal ────────────────────────────┐
│ Safe markdown render (no raw HTML) · HITL modal (op_id + param hash)     │
│ SSE client (cursor replay) · Evidence viewer · CSP/Trusted Types          │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ OIDC (Entra ID) bearer
┌───────────────────────────────▼──────────────────────────────────────────┐
│ API Gateway / FastAPI                                                     │
│ AuthN → Identity Assertion mint (60s) · Rate/token budget · Idempotency   │
│ Input schema (extra=forbid) · Injection signal scorer · OUTPUT FIREWALL   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ X-Identity-Assertion (user) + Agent token
┌───────────────────────────────▼──────────────────────────────────────────┐
│ LangGraph Supervisor (run budget, kill switch, checkpointing)            │
│   ├─ Domain agents: TTAS Classifier · RAG/Evidence · Email · Report       │
│   ├─ POLICY DECISION POINT (deterministic) ← Tool Manifest + Taint state  │
│   ├─ Optional LLM Judge (advisory only)                                   │
│   └─ HITL interrupt (interrupt() / Command resume)                        │
└───────────────┬───────────────────────────────┬──────────────────────────┘
                │                               │
┌───────────────▼───────────┐     ┌─────────────▼────────────────────────────┐
│ Tool Execution Layer      │     │ Data Layer: PostgreSQL + pgvector        │
│ Celery workers, per-call  │     │ RLS (tenant + classification) · Memory   │
│ container, egress allowlist│    │ trust tiers · Evidence store · Audit     │
│ secrets via short-lived   │     │ (append-only, hash-chained)              │
│ workload identity         │     └──────────────────────────────────────────┘
└───────────────────────────┘
        Cross-cutting: OpenTelemetry traces · Model/Prompt registry · SIEM alerts
```

---

## 3. Identity & Delegation (Multi-Agent)

### 3.1 Two-token model
Every internal call carries **both**:

| Token | Contents | Lifetime |
|-------|----------|----------|
| `X-Identity-Assertion` (user) | `tenant_id, principal_id, scopes, classification_max, run_id` | 60 s |
| `X-Agent-Assertion` | `agent_id, agent_version, allowed_tools, parent_agent, delegation_depth, run_id` | per step |

**Effective permission = user.scopes ∩ agent.allowed_tools ∩ manifest.policy.**

### 3.2 Delegation rules
- Sub-agents inherit *at most* the parent's effective scope (scopes can only narrow).
- `delegation_depth ≤ 2`; deeper chains rejected with `DELEGATION_DEPTH_EXCEEDED`.
- Agents never receive the user's OIDC token — only the minted assertion (no token passthrough).
- Agent registry (DB table `agent_registry`): id, owner, version, allowed_tools, model binding, status (`active|suspended`). Suspending an agent revokes it at the PDP immediately.

---

## 4. Tool Governance

### 4.1 Tool Manifest v3
```yaml
name: ttas.comment.close
version: 3
owner: ttas-platform-team
side_effect_class: irreversible        # none | reversible | irreversible
idempotency: required
risk_tier: critical                    # see 4.2
data_classification_max: confidential
taint_policy: block_if_tainted         # allow | require_hitl_if_tainted | block_if_tainted
evidence_required: true                # must attach evidence_ids (see §8)
network_policy: { mode: allowlist, allowlist: ["ttas-api.internal"] }
policy:
  scopes_all: ["ttas.write", "comment.close"]
  agents_any: ["ttas-closeout-agent"]
approval:
  mode: dual                           # none | single | dual
  approver_scopes: ["ttas.approver"]
  separation_of_duties: true           # requester ≠ approver
limits: { max_calls_per_run: 20, timeout_s: 30 }
input_schema: schemas/ttas_comment_close.json
output_schema: schemas/ttas_comment_close_result.json
```

### 4.2 Risk tiers → controls

| Tier | Examples | Approval | Taint allowed | Logging |
|------|----------|----------|---------------|---------|
| T0 harmless | format, calc | none | yes | summary |
| T1 low | rag.retrieve, read register | none | yes | full |
| T2 medium | draft email, write draft file | none (user sees result) | yes | full |
| T3 high | send internal email, update register | single HITL | HITL required | full + alert on deny |
| T4 critical | close TTAS comment, external email, DB bulk update, deploy | **dual HITL + SoD** | **blocked** | full + SIEM |

### 4.3 Taint tracking (indirect-injection control)
- LangGraph state carries `taint: set[source]` (e.g., `{"email:msg123", "rag:doc456"}`).
- Any untrusted content entering context marks the run tainted.
- PDP enforces `taint_policy` per tool. A tainted run **cannot** execute T4 tools without a fresh, user-initiated, non-tainted confirmation path.
- Optional pattern: **plan-then-execute** — plan is produced before untrusted content is read; tool sequence is locked; later steps may fill parameters but not add tools.

### 4.4 HITL integrity
- Approval payload = `{operation_id, tool, canonical_params_sha256, evidence_ids, expires_at}` signed server-side.
- Resume rejected if params hash differs, approval expired (default 15 min), or approver lacks scope / equals requester (T4).

---

## 5. Input & Output Security

### 5.1 Input
- Pydantic v2 `extra="forbid", strict=True`; size limits per field; file-type allowlist with content sniffing.
- Injection scorer (classifier or heuristics) produces `injection_risk` **signal** → raises taint, may force HITL; logs `PROMPT_INJECTION_SUSPECTED`. Hard block only on high-confidence matches.

### 5.2 Output Firewall (new, mandatory)
Runs on every response and every outbound tool payload (emails, files):

| Check | Action |
|-------|--------|
| PII / credentials / secrets (regex + detector e.g. Presidio) | redact or block |
| Cross-tenant identifiers (tenant_id ≠ caller) | block + `TENANT_ISOLATION` P0 |
| Classification above caller's `classification_max` | block |
| Internal hostnames / connection strings / system prompt fragments | redact |
| Uncited factual claims in evidence-required mode | downgrade to refusal `EVIDENCE_INSUFFICIENT` |
| Markdown links/images to non-allowlisted domains | strip (prevents data-exfil via image URLs) |

---

## 6. Data Layer

### 6.1 Classification & RLS
Every row/chunk carries `tenant_id, classification (PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED), owner_id, retention_until, source_uri, content_sha256`.

```sql
CREATE POLICY doc_access ON documents
USING (
  tenant_id = current_setting('app.tenant_id')::uuid
  AND classification_rank(classification)
      <= current_setting('app.classification_max')::int
);
```
Session variables are set by the backend from the verified assertion via `SET LOCAL` inside the transaction — never from LLM output. Apply the same policy to `embeddings` (pgvector) tables so similarity search cannot bypass it.

### 6.2 Database roles

| Role | Rights |
|------|--------|
| `app_api` | DML on business tables via RLS; no DDL |
| `agent_reader` | SELECT via RLS on documents/embeddings |
| `tool_<name>` | Only the tables that tool's manifest declares |
| `audit_writer` | INSERT only on `audit_log` |
| `migrator` | DDL; CI/CD only, never at runtime |

### 6.3 Audit log
Append-only; each row stores `prev_hash` and `row_hash = sha256(prev_hash || payload)`; daily anchor hash exported to immutable storage (WORM blob).

---

## 7. Memory Security

| Tier | Written by | Used for | Controls |
|------|-----------|----------|----------|
| System memory | Admins via change control | Policies, master registers | Versioned, read-only to agents |
| Verified memory | Agent proposal + human approval | Learned rules (e.g., classification mappings) | Requires approver scope; provenance; expiry |
| User memory | User | Preferences | Scoped to principal; cannot override policy |
| Session memory | Runtime | Current run | Discarded/archived at run end |

Rules:
- Agents may **propose** but never directly write verified/system memory (prevents memory poisoning such as "always approve vendor X").
- Memory content is injected as *data* with provenance tags, never merged into system prompt.
- Expired memory is filtered at query time (`WHERE expires_at > now()`) and purged by scheduled job — not by an LLM node.

---

## 8. Evidence-Based Decision Engine (TTAS-specific)

### 8.1 Decision record
```json
{
  "decision_id": "dec_01J...",
  "subject": "TTAS comment SSOP-xxxx / C-012",
  "recommendation": "CLOSE | KEEP_OPEN | RECLASSIFY | NEED_INFO",
  "evidence": [
    {"evidence_id": "doc_123#p14", "type": "certificate", "sha256": "...", "supports": "Cert No. matches tag"},
    {"evidence_id": "pims_PL-4567", "type": "punch", "status": "closed"}
  ],
  "rule_checks": [
    {"rule": "NR13_dossier_has_PSV_cert", "result": "pass"}
  ],
  "evidence_coverage": 0.9,
  "model": {"id": "<model>", "version": "<date>", "prompt_id": "ttas-closeout", "prompt_version": "4.2"},
  "requires_approval": true
}
```

### 8.2 Rules
- `CLOSE` is permitted only if every required evidence type for that comment category is present and verified (hash matches stored document).
- Use **deterministic checklist rules** per category (manual, certificate, NR-13, Ex, training, punch) for the pass/fail; the LLM extracts and explains, it does not grade itself.
- Avoid self-reported LLM "confidence %" as a gate — use evidence coverage and rule results instead.
- Missing evidence → `NEED_INFO` with list of missing items routed to the PIC/job trade.

---

## 9. Model & Prompt Governance

- **Registry tables:** `model_registry` (provider, model, version, region, approved_use, eval_score, status) and `prompt_registry` (id, version, hash, author, approver, linked eval run).
- Prompts live in Git; deployment requires passing eval suite; runtime loads by `prompt_id@version`, never ad-hoc strings.
- Model change = change request + rerun of golden set + injection suite; canary 10% before 100%.
- Data residency: confirm the model endpoint region and no-training/data-retention terms for project data before approval.

---

## 10. Runtime Controls

| Control | Setting (default) |
|---------|-------------------|
| Run budget | max steps 25, max tokens per run, max wall time 10 min, max cost per run |
| Loop detection | same tool+params 3× → stop with `AGENT_LOOP_DETECTED` |
| Kill switch | per run, per agent, per tool, global; checked by PDP before every tool call |
| Sandbox | per-call container, non-root, read-only rootfs, seccomp, CPU/mem/time caps, no network unless manifest allowlist via egress proxy |
| Secrets | Vault / Key Vault; workload identity; tools get short-lived scoped credentials, never visible to the LLM |
| Unknown outcome | `TOOL_UNKNOWN_OUTCOME` → reconciliation job queries target system by `operation_id` before any retry |

---

## 11. Error Taxonomy v3 (additions)

| Code | Severity | Handling |
|------|----------|----------|
| PROMPT_INJECTION_SUSPECTED | P2 | taint + log |
| PROMPT_INJECTION_BLOCKED | P1 | terminate run |
| TENANT_ISOLATION | P0 | block, page on-call |
| CLASSIFICATION_VIOLATION | P0 | block output |
| POLICY_DENIED | P2 | return reason to agent (no policy internals) |
| TAINTED_HIGH_RISK_ACTION | P1 | block; offer clean HITL path |
| APPROVAL_INVALID / APPROVAL_EXPIRED | P2 | re-request |
| SOD_VIOLATION | P1 | block |
| DELEGATION_DEPTH_EXCEEDED | P2 | stop branch |
| AGENT_LOOP_DETECTED | P2 | stop run |
| BUDGET_EXCEEDED | P3 | stop, partial result |
| EVIDENCE_INSUFFICIENT | P3 | refusal with missing list |
| OUTPUT_REDACTED | P3 | log |

---

## 12. Observability

- OpenTelemetry spans per node/tool with attributes: `run_id, agent_id, model, prompt_version, tool, risk_tier, verdict, tokens, cost, latency, taint`.
- Prompt/response bodies stored in restricted store (classification-aware), referenced by ID in traces.
- Dashboards: deny rate by tool, injection signals, HITL turnaround, cost per run, evidence-insufficient rate.
- SIEM alerts: any P0/P1, approval anomalies, spike in denies, kill-switch use.

---

## 13. SSE Catalog v3
Events: `run_status, token, step_summary, tool_call, tool_progress, approval_request, approval_result, tool_result, citation, evidence, refusal, redaction_notice, error`.
- `step_summary` replaces raw CoT.
- `approval_request` includes `operation_id, params_hash, risk_tier, evidence_ids, expires_at, approvals_required`.
- Replay via `?cursor=`; 410 → snapshot GET (unchanged from v1).

---

## 14. Secure SDLC & CI Gates

| Gate | Tooling | Blocking criterion |
|------|---------|--------------------|
| Contract lint/drift | openapi-spec-validator, codegen + `git diff --exit-code` | any drift |
| SAST | CodeQL / Semgrep | high findings |
| Dependency & container | Dependabot, Trivy/Grype, SBOM (CycloneDX) | critical CVEs |
| Secrets | gitleaks | any |
| IaC | Checkov | high |
| Authz negative matrix | pytest (IDOR, tenant, mass assignment, classification) | any failure |
| Injection & exfil suite | versioned corpus (direct, indirect via RAG/email, markdown-image exfil) | 0 unauthorised T3/T4 executions; block rate ≥ threshold |
| RAG golden set | Recall@K, citation precision | below threshold |
| Evidence engine set | labelled TTAS closures | false-CLOSE rate above threshold |
| Prompt/model change | registry diff → full eval rerun | missing eval link |

Also: signed images (cosign), pinned dependencies, branch protection with required reviewers for `policies/`, `manifests/`, `prompts/`.

---

## 15. Control Framework Mapping (indicative — validate with your compliance team)

| Control | OWASP LLM Top 10 (2025) | NIST AI RMF | ISO/IEC 27001:2022 Annex A |
|---------|-------------------------|-------------|----------------------------|
| PDP + taint + HITL | LLM01 Prompt Injection, LLM06 Excessive Agency | Manage | 8.2, 8.3 |
| Output Firewall | LLM02 Sensitive Info Disclosure, LLM05 Improper Output Handling | Measure/Manage | 8.11, 8.12 |
| RLS + classification | LLM02 | Map | 5.12, 8.3 |
| Supply chain gates | LLM03 Supply Chain | Govern | 5.19–5.21, 8.28 |
| Memory trust tiers / RAG provenance | LLM04 Data & Model Poisoning, LLM08 Vector & Embedding Weaknesses | Manage | 8.10 |
| System prompt kept secret-free | LLM07 System Prompt Leakage | — | 8.4 |
| Evidence engine | LLM09 Misinformation | Measure | — |
| Budgets / rate limits | LLM10 Unbounded Consumption | Manage | 8.6 |
| Model/prompt registry, audit | — | Govern | 5.37, 8.15, 8.32 |

---

## 16. Implementation Roadmap

| Phase | Weeks | Deliverables | Exit criteria |
|-------|-------|--------------|---------------|
| P1 Foundation | 1–3 | Two-token identity, manifest v3, deterministic PDP, RLS + classification, append-only audit | Authz negative matrix green |
| P2 Agent safety | 4–6 | Taint tracking, HITL with params hash + dual approval, Output Firewall, run budgets, kill switch | Injection suite: 0 T3/T4 unauthorised executions |
| P3 TTAS value | 7–9 | Evidence engine + checklist rules per comment category, memory tiers, SSE v3 | False-CLOSE rate under agreed threshold on labelled set |
| P4 Operate | 10–12 | OTel + dashboards + SIEM, model/prompt registry, supply-chain gates, control mapping evidence pack | Pre-go-live security review sign-off |

---

## 17. Pre-Deployment Checklist v2

**Identity & Policy**
- [ ] User + agent assertions verified on every internal hop; no token passthrough
- [ ] PDP is deterministic and evaluated before every tool call; kill switch checked
- [ ] T4 tools require dual approval with SoD; approval bound to params hash and expiry

**Data**
- [ ] RLS covers documents, embeddings, memory, evidence tables (tenant + classification)
- [ ] `SET LOCAL` session vars set from assertion only
- [ ] Audit log append-only and hash-chained; daily anchor exported

**Agent behaviour**
- [ ] Taint tracking active; tainted runs cannot execute T4
- [ ] Output Firewall on responses and outbound tool payloads; external image/link stripping
- [ ] Raw CoT not streamed
- [ ] Agents cannot write verified/system memory directly

**Ops & SDLC**
- [ ] Budgets, loop detection, timeouts configured
- [ ] Sandbox hardened (non-root, read-only, seccomp, egress proxy)
- [ ] Secrets via vault + workload identity, never in LLM context
- [ ] All CI gates in §14 blocking
- [ ] Model and prompt versions registered and linked to eval runs

---

## Appendix A — PDP sketch (Python)
```python
def authorize(call: ToolCall, user: UserAssertion, agent: AgentAssertion, state: RunState) -> Verdict:
    m = MANIFESTS[call.tool]
    if kill_switch.active(run=state.run_id, agent=agent.agent_id, tool=m.name):
        return Verdict.deny("KILL_SWITCH")
    if m.name not in agent.allowed_tools:
        return Verdict.deny("POLICY_DENIED")
    if not set(m.policy.scopes_all) <= set(user.scopes):
        return Verdict.deny("POLICY_DENIED")
    if state.tainted and m.taint_policy == "block_if_tainted":
        return Verdict.deny("TAINTED_HIGH_RISK_ACTION")
    if state.calls(m.name) >= m.limits.max_calls_per_run:
        return Verdict.deny("BUDGET_EXCEEDED")
    validate_schema(call.args, m.input_schema)          # raises -> deny
    if m.evidence_required and not evidence.verify(call.args.get("evidence_ids")):
        return Verdict.deny("EVIDENCE_INSUFFICIENT")
    needs = m.approval.mode
    if state.tainted and m.taint_policy == "require_hitl_if_tainted" and needs == "none":
        needs = "single"
    return Verdict.allow(approval=needs, params_hash=canonical_sha256(call.args))
```
