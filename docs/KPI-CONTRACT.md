# KPI contract and GATE_G

The authoritative definition is `api/app/services/kpi.py` (`KPI_CONTRACT`). This
document describes it; do not duplicate the numbers in dashboards or release scripts.

## Primary KPI

| Field | Value |
|---|---|
| Name | `governed_completion_rate` |
| Definition | completed runs / started runs in the window |
| Target | **80%** |
| Window | 24 hours |
| Minimum sample | 5 runs |

## Guardrails (all must hold)

| Guardrail | Threshold | Source |
|---|---|---|
| Unsafe approvals | **0** | human decisions where reviewer = requester or decision time > review deadline |
| p95 run duration | **≤ 120 s** | completion timestamp − creation timestamp |
| Cost per completed run | **≤ $1.00** | accumulated `WorkflowRun.cost_usd` |

## GATE_G

GATE_G is **expansion-only**: a failing gate holds expansion of autonomy (for example,
raising auto-approval scope or lowering review thresholds). It never blocks a release
or a rollback. This is deliberate: shipping a fix must not be gated on business KPIs.

API:

```
GET /api/v1/kpi/summary     (any authenticated user)
GET /api/v1/kpi/gate-g      (admin; expansion decision)
```

The response contains the contract, metrics, guardrail reasons, and
`gate_g.expansion_allowed`. A small sample returns `hold` with an
`insufficient sample` reason even when the rate looks good.