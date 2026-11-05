# EPC Project — End-to-End Validation Checklist

## Prerequisites

- [ ] Backend running: `cd backend && uvicorn main:app --port 8000`
- [ ] Frontend running: `cd frontend && npm run dev`
- [ ] Database: PostgreSQL with migration `001_extended_schema.sql` applied
- [ ] Test project seeded (or use `demo-project` in dev)

## 1. Backend Health

| # | Check | Expected |
|---|-------|----------|
| 1.1 | `curl localhost:8000/health` | `{"status":"healthy"}` |
| 1.2 | `curl localhost:8000/api/reports/dashboard/demo-project` | Returns project with activities, alerts, NDT |
| 1.3 | `curl localhost:8000/api/alerts/demo-project` | Returns alert list |
| 1.4 | `curl localhost:8000/api/ai/status` | Returns `{"enabled": false, "model": "rule_based"}` |

## 2. Dashboard Navigation

| # | Tab | Expected |
|---|-----|----------|
| 2.1 | Overview | KPI cards visible (Activities, Avg Progress, Alerts, Contract Value) |
| 2.2 | Planning Board | 5 period type tabs, "Generate Plans" button |
| 2.3 | Engineering | Discipline cards with IFA/IFC progress bars |
| 2.4 | Procurement | PO list loading |
| 2.5 | Construction | MVR summary cards, weekly planner |
| 2.6 | System Completion | Sub-system list by discipline |
| 2.7 | Commissioning | Procedure type tabs, pass/fail summary |
| 2.8 | Inspection & NDT | STRUCTURAL/PIPING bar charts |
| 2.9 | Quality (NCR) | Severity summary cards, NCR table |
| 2.10 | HSE Safety | TRIR/LTIFR KPIs, incident trend chart |
| 2.11 | Training | Compliance matrix table, expiring certs |
| 2.12 | Stage Gates | 5-gate sequence visualization |
| 2.13 | Conflicts | Conflict list with severity badges |
| 2.14 | Feedback Loop | Feedback table with direction indicators |
| 2.15 | Traceability | Full matrix table, forward/backward trace inputs |
| 2.16 | AI Insights | AI status card, 4 analysis buttons |
| 2.17 | Reports | Task/NDT/manpower accountability report |

## 3. Engineering Flow

| # | Action | Expected |
|---|--------|----------|
| 3.1 | Click Engineering tab | Discipline cards render |
| 3.2 | Click STRUCTURAL card | Drawings table shows STRUCTURAL drawings |
| 3.3 | Switch to Materials tab | Material table with piece marks/grades/sizes |
| 3.4 | Verify procurement planning | Grouped material summary with PO status |
| 3.5 | Switch to Equipment tab (MECHANICAL) | Equipment with FAT status visible |
| 3.6 | Check IFA/IFC progress bars | Green/amber bars with percentages |
| 3.7 | Check change summary | Drawings/materials added/deleted counts |

## 4. Construction MVR Flow

| # | Action | Expected |
|---|--------|----------|
| 4.1 | Click Construction tab | MVR summary cards per discipline |
| 4.2 | Select STRUCTURAL discipline | Material planning tab shows drawing list |
| 4.3 | Click a drawing | Material detail table loads |
| 4.4 | Verify MVR status badges | Info-AFI (grey), Structure-requested (amber), MVR-confirm (green) |
| 4.5 | Try MVR-confirm on non-AFC | Error: "Cannot confirm MVR: drawing is not AFC" |
| 4.6 | Verify PO status highlighting | PR-Raised = green, others = default |

## 5. Error Handling

| # | Scenario | Expected |
|---|----------|----------|
| 5.1 | Navigate to `/projects/nonexistent` | "Project Not Found" or graceful fallback |
| 5.2 | Stop backend, refresh Dashboard | Error banner visible, not a blank screen |
| 5.3 | API returns 500 | Error banner with retry button |

## 6. AI Engine (Rule-Based Fallback)

| # | Action | Expected |
|---|--------|----------|
| 6.1 | Run "Schedule Risk" analysis | Returns risk_level + recommendations |
| 6.2 | Run "Conflict Detection" | Returns conflicts_found count |
| 6.3 | Run "Weekly Report" | Returns markdown report text |
| 6.4 | Verify `generated_by: "rule_based"` | Present in all responses |

## 7. Build & Test

| # | Command | Expected |
|---|---------|----------|
| 7.1 | `cd backend && pytest tests/ -q` | All tests pass |
| 7.2 | `cd frontend && npx tsc --noEmit` | Zero errors |
| 7.3 | `cd frontend && npx vitest run` | All tests pass |
| 7.4 | `cd frontend && npm run build` | Build succeeds |

## 8. Database Schema

| # | Check | Expected |
|---|-------|----------|
| 8.1 | All 36 tables exist | `\dt` in psql shows all tables |
| 8.2 | ARCHITECTURE_DECORATION discipline | Exists in engineering_disciplines |
| 8.3 | Indexes on project_id columns | Fast queries on large datasets |
| 8.4 | Migration 001 applied | `drawing_materials`, `drawing_equipment`, etc. exist |

---

**Validation Date:** _______________  
**Tester:** _______________  
**Result:** PASS / FAIL (with notes)  
