-- =============================================================================
-- Migration 005 — Reliability & data-integrity constraints
--
-- Idempotent: safe to run repeatedly. All DDL is wrapped in one transaction so
-- a failure leaves the database unchanged.
--
-- Contents:
--   1. schedule_alerts.entity_id — source-row identity for alert deduplication
--   2. Duplicate cleanup for unresolved alerts
--   3. Partial unique index guarding alert generation against duplicates
--   4. Hot-join indexes used by traceability / construction / AI queries
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. schedule_alerts.entity_id
--    Identifies the source row an alert was generated from (activity_id,
--    shortage_id, ndt_id, ...). NULL for legacy rows and alert types that have
--    no single source row. PostgreSQL unique indexes treat NULLs as distinct,
--    so legacy rows never collide.
-- -----------------------------------------------------------------------------
ALTER TABLE IF EXISTS schedule_alerts
    ADD COLUMN IF NOT EXISTS entity_id UUID;

-- Backfill what can be recovered from the pre-005 schema.
DO $$
BEGIN
    IF to_regclass('public.schedule_alerts') IS NOT NULL THEN
        UPDATE schedule_alerts
           SET entity_id = activity_id
         WHERE entity_id IS NULL
           AND alert_type = 'CRITICAL_FLOAT'
           AND activity_id IS NOT NULL;
    END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 2. Duplicate cleanup
--    Keep the oldest unresolved alert per (project_id, alert_type, entity_id);
--    remove the rest. Only rows with an entity_id are considered, since rows
--    without one cannot be identified as duplicates safely.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.schedule_alerts') IS NOT NULL THEN
        DELETE FROM schedule_alerts sa
         WHERE sa.entity_id IS NOT NULL
           AND sa.is_resolved = FALSE
           AND sa.ctid <> (
                -- ctid has no MIN() aggregate; cast through text to pick a stable keeper.
                SELECT MIN(keep.ctid::text)::tid
                  FROM schedule_alerts keep
                 WHERE keep.project_id = sa.project_id
                   AND keep.alert_type = sa.alert_type
                   AND keep.entity_id = sa.entity_id
                   AND keep.is_resolved = FALSE
           );
    END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 3. Partial unique index — the conflict target used by alert_service.py
--    ON CONFLICT (project_id, alert_type, entity_id) WHERE is_resolved = FALSE
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.schedule_alerts') IS NOT NULL THEN
        -- Predicate must match the ON CONFLICT inference specification exactly.
        -- NULL entity_id values do not collide (PostgreSQL treats NULLs as
        -- distinct in unique indexes), so legacy rows remain unaffected.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_alerts_unresolved_entity
            ON schedule_alerts (project_id, alert_type, entity_id)
            WHERE is_resolved = FALSE;
    END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 4. Hot-join indexes
--    Each is guarded by to_regclass because optional tables (from migrations
--    001/003) may be absent in a fresh deployment that only ran init.sql.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    stmt TEXT;
BEGIN
    -- Procurement: PO ↔ material rollups (construction enrichment, traceability)
    IF to_regclass('public.purchase_items') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_purchase_items_po_material
            ON purchase_items (po_id, material_type);
    END IF;

    -- Engineering: drawing detail panels and cascade deletes
    IF to_regclass('public.drawing_materials') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_drawing_materials_drawing_project
            ON drawing_materials (drawing_id, project_id);
    END IF;

    IF to_regclass('public.material_takeoff') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_material_takeoff_drawing_project
            ON material_takeoff (drawing_id, project_id);
    END IF;

    -- Inspection / NDT traceability
    IF to_regclass('public.ndt_requests') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_ndt_requests_drawing
            ON ndt_requests (drawing_id);
    END IF;

    IF to_regclass('public.weld_tracking') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_weld_tracking_drawing
            ON weld_tracking (drawing_id);
    END IF;

    -- AI chat history lookups
    IF to_regclass('public.ai_messages') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_ai_messages_session
            ON ai_messages (session_id);
    END IF;

    -- Conflict board filters
    IF to_regclass('public.conflicts') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_conflicts_project_status
            ON conflicts (project_id, status);
    END IF;

    -- Completion punch list filters
    IF to_regclass('public.punch_items') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_punch_items_project_status
            ON punch_items (project_id, status);
    END IF;

    -- Planning board period rollups
    IF to_regclass('public.plan_items') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_plan_items_period
            ON plan_items (period_id);
    END IF;
END
$$;

COMMIT;
