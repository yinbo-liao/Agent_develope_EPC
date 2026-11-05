-- =============================================================================
-- FPSO EPC Project Control System — Migration 001: Extended Schema
-- Adds: Full lifecycle support (completion, commissioning, quality, safety,
--       training, multi-level planning, conflicts, feedback, stage gates)
-- Also aligns production PostgreSQL with dev SQLite features
-- Run: psql -U fpso_user -d fpso_db -f database/migrations/001_extended_schema.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- Part A: Dev-to-Production Schema Alignment
-- Tables that exist in dev_main.py (SQLite) but not in production init.sql
-- =============================================================================

-- Extended drawings columns (IFA/IFC workflow)
ALTER TABLE drawings
    ADD COLUMN IF NOT EXISTS issued_for_info VARCHAR(10) DEFAULT 'Yes',
    ADD COLUMN IF NOT EXISTS issued_for_info_date DATE,
    ADD COLUMN IF NOT EXISTS issued_for_construction VARCHAR(10) DEFAULT 'No',
    ADD COLUMN IF NOT EXISTS issued_for_construction_date DATE;

-- Drawing materials (piece marks, grades, MVR workflow)
CREATE TABLE IF NOT EXISTS drawing_materials (
    material_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drawing_id UUID REFERENCES drawings(drawing_id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id),
    piece_mark VARCHAR(50) DEFAULT '-',
    material_grade VARCHAR(50),
    material_thickness VARCHAR(50),
    material_weight DECIMAL(12,3),
    material_type VARCHAR(100),
    size VARCHAR(50),
    diameter VARCHAR(50),
    material_length DECIMAL(12,3),
    material_category VARCHAR(50),
    total_weight DECIMAL(12,3),
    po_status VARCHAR(50),
    material_class VARCHAR(50),
    mvr_status VARCHAR(30) DEFAULT 'Info-AFI',
    mvr_confirmed_by VARCHAR(100),
    mvr_confirmed_at TIMESTAMP
);

-- Drawing equipment (tags, FAT status, system codes)
CREATE TABLE IF NOT EXISTS drawing_equipment (
    equipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drawing_id UUID REFERENCES drawings(drawing_id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id),
    equipment_tag VARCHAR(100),
    equipment_name VARCHAR(200),
    equipment_detail TEXT,
    install_location VARCHAR(200),
    weight DECIMAL(12,2),
    equipment_type VARCHAR(100),
    certification VARCHAR(200),
    fat_status VARCHAR(30) DEFAULT 'PENDING',
    test_status VARCHAR(50),
    system_code VARCHAR(50),
    system_name VARCHAR(200),
    schedule_delivery_date DATE,
    schedule_install_date DATE,
    remark TEXT
);

-- NDT Daily Log
CREATE TABLE IF NOT EXISTS ndt_daily_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    log_date DATE NOT NULL,
    discipline_name VARCHAR(50) NOT NULL,
    ndt_method VARCHAR(20) NOT NULL,
    rfi_total_length_mm DECIMAL(12,1) DEFAULT 0,
    ndt_complete_length_mm DECIMAL(12,1) DEFAULT 0,
    daily_length_done_mm DECIMAL(12,1) DEFAULT 0,
    team_deployed INT DEFAULT 0,
    previous_status TEXT,
    remarks TEXT,
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Change Log for audit trail
CREATE TABLE IF NOT EXISTS change_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id),
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('drawing', 'material', 'equipment')),
    entity_id UUID NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('create', 'delete', 'update')),
    entity_number VARCHAR(100),
    discipline_name VARCHAR(50),
    logged_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- Part B: New Discipline — Architecture Decoration
-- =============================================================================

INSERT INTO engineering_disciplines (discipline_name)
VALUES ('ARCHITECTURE_DECORATION')
ON CONFLICT (discipline_name) DO NOTHING;

-- =============================================================================
-- Part C: System Completion
-- =============================================================================

CREATE TABLE IF NOT EXISTS sub_systems (
    sub_system_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    system_code VARCHAR(50) NOT NULL,
    system_name VARCHAR(200),
    parent_system_id UUID REFERENCES sub_systems(sub_system_id),
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    area_code VARCHAR(50),
    completion_status VARCHAR(30) DEFAULT 'NOT_STARTED',
    planned_mc_date DATE,
    actual_mc_date DATE,
    handover_date DATE,
    responsible_engineer VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, system_code)
);

CREATE TABLE IF NOT EXISTS punch_items (
    punch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_system_id UUID REFERENCES sub_systems(sub_system_id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id),
    punch_number VARCHAR(50) UNIQUE,
    category VARCHAR(20) NOT NULL DEFAULT 'B',
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    area_code VARCHAR(50),
    description TEXT NOT NULL,
    raised_by VARCHAR(100),
    raised_date DATE DEFAULT CURRENT_DATE,
    assigned_to VARCHAR(100),
    target_date DATE,
    closeout_date DATE,
    closeout_verified_by VARCHAR(100),
    status VARCHAR(20) DEFAULT 'OPEN',
    priority VARCHAR(10) DEFAULT 'MEDIUM',
    photo_ref VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_punch_category CHECK (category IN ('A', 'B', 'C')),
    CONSTRAINT chk_punch_status CHECK (status IN ('OPEN', 'IN_PROGRESS', 'READY_FOR_REVIEW', 'CLOSED', 'CANCELLED'))
);

-- =============================================================================
-- Part D: Commissioning
-- =============================================================================

CREATE TABLE IF NOT EXISTS commissioning_procedures (
    procedure_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_system_id UUID REFERENCES sub_systems(sub_system_id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id),
    procedure_code VARCHAR(50) NOT NULL,
    procedure_name VARCHAR(200),
    procedure_type VARCHAR(30) NOT NULL DEFAULT 'MC_CHECK',
    description TEXT,
    planned_date DATE,
    actual_date DATE,
    status VARCHAR(20) DEFAULT 'PENDING',
    responsible_party VARCHAR(100),
    witness_required BOOLEAN DEFAULT FALSE,
    witness_party VARCHAR(100),
    test_result VARCHAR(20),
    attachments TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_procedure_type CHECK (procedure_type IN ('MC_CHECK', 'PRE_COMM', 'COMM_PROCEDURE', 'PERFORMANCE_TEST')),
    CONSTRAINT chk_comm_status CHECK (status IN ('PENDING', 'SCHEDULED', 'IN_PROGRESS', 'PASSED', 'FAILED', 'REVALIDATED'))
);

CREATE TABLE IF NOT EXISTS commissioning_checklist (
    checklist_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    procedure_id UUID REFERENCES commissioning_procedures(procedure_id) ON DELETE CASCADE,
    item_number INT NOT NULL,
    check_description TEXT NOT NULL,
    expected_result TEXT,
    actual_result TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    verified_by VARCHAR(100),
    verified_date TIMESTAMP,
    remarks TEXT
);

-- =============================================================================
-- Part E: Quality Management
-- =============================================================================

CREATE TABLE IF NOT EXISTS quality_ncr (
    ncr_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    ncr_number VARCHAR(50) UNIQUE NOT NULL,
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    sub_system_id UUID REFERENCES sub_systems(sub_system_id),
    activity_id UUID REFERENCES activities(activity_id),
    severity VARCHAR(10) DEFAULT 'MINOR',
    category VARCHAR(50),
    description TEXT NOT NULL,
    immediate_action TEXT,
    root_cause TEXT,
    corrective_action TEXT,
    preventive_action TEXT,
    raised_by VARCHAR(100),
    raised_date DATE DEFAULT CURRENT_DATE,
    target_closeout_date DATE,
    actual_closeout_date DATE,
    verified_by VARCHAR(100),
    status VARCHAR(20) DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_ncr_severity CHECK (severity IN ('CRITICAL', 'MAJOR', 'MINOR', 'OBSERVATION')),
    CONSTRAINT chk_ncr_status CHECK (status IN ('OPEN', 'UNDER_INVESTIGATION', 'CORRECTIVE_ACTION', 'PENDING_VERIFICATION', 'CLOSED'))
);

CREATE TABLE IF NOT EXISTS weld_tracking (
    weld_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    weld_number VARCHAR(50) UNIQUE NOT NULL,
    drawing_id UUID REFERENCES drawings(drawing_id),
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    weld_type VARCHAR(50),
    joint_type VARCHAR(50),
    diameter_mm DECIMAL(8,1),
    thickness_mm DECIMAL(8,1),
    welder_id VARCHAR(50),
    weld_date DATE,
    ndt_method VARCHAR(20),
    ndt_result VARCHAR(20),
    rejection_reason TEXT,
    repair_count INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'PENDING_NDT',
    CONSTRAINT chk_weld_status CHECK (status IN ('WELDED', 'PENDING_NDT', 'NDT_PASSED', 'NDT_FAILED', 'REPAIRED', 'ACCEPTED'))
);

-- =============================================================================
-- Part F: Safety Management (HSE)
-- =============================================================================

CREATE TABLE IF NOT EXISTS safety_incidents (
    incident_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    incident_date DATE NOT NULL,
    incident_time TIME,
    incident_type VARCHAR(30) NOT NULL,
    severity VARCHAR(10) DEFAULT 'LOW',
    area_code VARCHAR(50),
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    description TEXT NOT NULL,
    immediate_cause TEXT,
    root_cause TEXT,
    corrective_action TEXT,
    preventive_action TEXT,
    reported_by VARCHAR(100),
    investigated_by VARCHAR(100),
    lost_time_days INT DEFAULT 0,
    man_hours_at_incident BIGINT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'OPEN',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_incident_type CHECK (incident_type IN ('LTI', 'MTI', 'RWC', 'FA', 'NEAR_MISS', 'OBSERVATION', 'FIRST_AID')),
    CONSTRAINT chk_incident_severity CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW'))
);

CREATE TABLE IF NOT EXISTS safety_permits (
    permit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    permit_type VARCHAR(30) NOT NULL,
    permit_number VARCHAR(50) UNIQUE NOT NULL,
    work_description TEXT NOT NULL,
    area_code VARCHAR(50),
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    requested_by VARCHAR(100),
    approved_by VARCHAR(100),
    issue_date DATE,
    expiry_date DATE,
    isolation_required VARCHAR(10) DEFAULT 'No',
    gas_test_required VARCHAR(10) DEFAULT 'No',
    gas_test_result TEXT,
    status VARCHAR(20) DEFAULT 'REQUESTED',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_permit_type CHECK (permit_type IN ('HOT_WORK', 'COLD_WORK', 'CONFINED_SPACE', 'ELECTRICAL_ISOLATION', 'EXCAVATION', 'LIFTING', 'RADIOGRAPHY', 'DIVING')),
    CONSTRAINT chk_permit_status CHECK (status IN ('REQUESTED', 'APPROVED', 'ISSUED', 'SUSPENDED', 'CLOSED', 'CANCELLED'))
);

CREATE TABLE IF NOT EXISTS safety_observations (
    observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    observation_date DATE DEFAULT CURRENT_DATE,
    area_code VARCHAR(50),
    category VARCHAR(30),
    observation TEXT NOT NULL,
    action_taken TEXT,
    observed_by VARCHAR(100),
    status VARCHAR(20) DEFAULT 'OPEN',
    positive_observation BOOLEAN DEFAULT FALSE
);

-- =============================================================================
-- Part G: Training Management
-- =============================================================================

CREATE TABLE IF NOT EXISTS training_roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(100) UNIQUE NOT NULL,
    role_category VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS training_courses (
    course_id SERIAL PRIMARY KEY,
    course_code VARCHAR(50) UNIQUE NOT NULL,
    course_name VARCHAR(200) NOT NULL,
    course_category VARCHAR(50),
    validity_months INT,
    is_mandatory BOOLEAN DEFAULT FALSE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS training_role_requirements (
    requirement_id SERIAL PRIMARY KEY,
    role_id INT REFERENCES training_roles(role_id) ON DELETE CASCADE,
    course_id INT REFERENCES training_courses(course_id) ON DELETE CASCADE,
    UNIQUE(role_id, course_id)
);

CREATE TABLE IF NOT EXISTS personnel (
    personnel_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    badge_number VARCHAR(50) UNIQUE,
    full_name VARCHAR(200) NOT NULL,
    role_id INT REFERENCES training_roles(role_id),
    discipline VARCHAR(50),
    contractor_company VARCHAR(200),
    mobilization_date DATE,
    demobilization_date DATE,
    status VARCHAR(20) DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS personnel_training (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    personnel_id UUID REFERENCES personnel(personnel_id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(project_id),
    course_id INT REFERENCES training_courses(course_id),
    completion_date DATE,
    expiry_date DATE,
    certificate_ref VARCHAR(100),
    score DECIMAL(5,2),
    verified_by VARCHAR(100)
);

-- =============================================================================
-- Part H: Multi-Level Planning
-- =============================================================================

CREATE TABLE IF NOT EXISTS planning_periods (
    period_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    period_type VARCHAR(20) NOT NULL,
    period_label VARCHAR(100),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    is_locked BOOLEAN DEFAULT FALSE,
    locked_by VARCHAR(100),
    locked_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, period_type, period_start),
    CONSTRAINT chk_period_type CHECK (period_type IN ('WEEKLY', 'BI_WEEKLY', 'MONTHLY', 'BI_MONTHLY', 'FOUR_MONTH'))
);

CREATE TABLE IF NOT EXISTS plan_items (
    plan_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_id UUID REFERENCES planning_periods(period_id) ON DELETE CASCADE,
    activity_id UUID REFERENCES activities(activity_id),
    planned_weight_pct DECIMAL(5,2),
    actual_weight_pct DECIMAL(5,2),
    milestone_flag BOOLEAN DEFAULT FALSE,
    milestone_name VARCHAR(100),
    status VARCHAR(20) DEFAULT 'ON_TRACK',
    variance_note TEXT,
    CONSTRAINT unique_period_activity UNIQUE(period_id, activity_id),
    CONSTRAINT chk_plan_status CHECK (status IN ('ON_TRACK', 'AT_RISK', 'DELAYED', 'COMPLETED'))
);

-- =============================================================================
-- Part I: Conflict Detection & Feedback Loop
-- =============================================================================

CREATE TABLE IF NOT EXISTS conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    conflict_type VARCHAR(30) NOT NULL,
    title VARCHAR(200),
    description TEXT,
    source_entity_type VARCHAR(50),
    source_entity_id UUID,
    target_entity_type VARCHAR(50),
    target_entity_id UUID,
    severity VARCHAR(10) DEFAULT 'MEDIUM',
    detected_by_agent BOOLEAN DEFAULT FALSE,
    ai_confidence DECIMAL(3,2),
    ai_recommendation TEXT,
    status VARCHAR(20) DEFAULT 'DETECTED',
    resolution_notes TEXT,
    resolved_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    CONSTRAINT chk_conflict_type CHECK (conflict_type IN (
        'SCHEDULE_CLASH', 'RESOURCE_CONFLICT', 'DESIGN_CLASH',
        'INTERFACE_GAP', 'SCOPE_CHANGE', 'MATERIAL_DELAY',
        'MANPOWER_SHORTAGE', 'VENDOR_ISSUE', 'SAFETY_RISK'
    )),
    CONSTRAINT chk_conflict_severity CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT chk_conflict_status CHECK (status IN ('DETECTED', 'ACKNOWLEDGED', 'IN_RESOLUTION', 'RESOLVED', 'CLOSED'))
);

CREATE TABLE IF NOT EXISTS conflict_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conflict_id UUID REFERENCES conflicts(conflict_id) ON DELETE CASCADE,
    action_description TEXT NOT NULL,
    assigned_to VARCHAR(100),
    target_date DATE,
    completion_date DATE,
    status VARCHAR(20) DEFAULT 'PENDING',
    CONSTRAINT chk_action_status CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'))
);

CREATE TABLE IF NOT EXISTS feedback_loop (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    source_stage VARCHAR(30) NOT NULL,
    target_stage VARCHAR(30) NOT NULL,
    feedback_type VARCHAR(30) NOT NULL,
    reference_number VARCHAR(100),
    description TEXT NOT NULL,
    impact_assessment TEXT,
    impact_level VARCHAR(10) DEFAULT 'MEDIUM',
    ai_generated_assessment BOOLEAN DEFAULT FALSE,
    is_actioned BOOLEAN DEFAULT FALSE,
    actioned_by VARCHAR(100),
    actioned_date TIMESTAMP,
    closure_notes TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_feedback_source CHECK (source_stage IN ('ENGINEERING', 'PROCUREMENT', 'CONSTRUCTION', 'SYSTEM_COMPLETION', 'COMMISSIONING')),
    CONSTRAINT chk_feedback_target CHECK (target_stage IN ('ENGINEERING', 'PROCUREMENT', 'CONSTRUCTION', 'SYSTEM_COMPLETION', 'COMMISSIONING')),
    CONSTRAINT chk_feedback_type CHECK (feedback_type IN ('DESIGN_CHANGE', 'MATERIAL_SUBSTITUTION', 'SCHEDULE_ADJUSTMENT', 'SCOPE_VARIATION', 'QUALITY_ISSUE', 'SAFETY_CONCERN', 'TECHNICAL_QUERY'))
);

-- =============================================================================
-- Part J: Stage Gates
-- =============================================================================

CREATE TABLE IF NOT EXISTS stage_gates (
    gate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) NOT NULL,
    gate_name VARCHAR(100) NOT NULL,
    gate_sequence INT NOT NULL,
    from_phase VARCHAR(30),
    to_phase VARCHAR(30),
    planned_date DATE,
    actual_date DATE,
    checklist_complete_pct DECIMAL(5,2) DEFAULT 0,
    ai_readiness_score DECIMAL(3,1),
    human_approver VARCHAR(100),
    approval_date DATE,
    approver_comments TEXT,
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(project_id, gate_sequence),
    CONSTRAINT chk_gate_status CHECK (status IN ('PENDING', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'CONDITIONAL'))
);

CREATE TABLE IF NOT EXISTS stage_gate_checklist (
    checklist_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gate_id UUID REFERENCES stage_gates(gate_id) ON DELETE CASCADE,
    item_number INT NOT NULL,
    category VARCHAR(50),
    description TEXT NOT NULL,
    verification_method VARCHAR(50),
    is_complete BOOLEAN DEFAULT FALSE,
    verified_by VARCHAR(100),
    verified_date TIMESTAMP,
    evidence_ref TEXT,
    remarks TEXT
);

-- =============================================================================
-- Part K: Indexes for new tables
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_drawing_materials_drawing ON drawing_materials(drawing_id);
CREATE INDEX IF NOT EXISTS idx_drawing_materials_project ON drawing_materials(project_id);
CREATE INDEX IF NOT EXISTS idx_drawing_equipment_drawing ON drawing_equipment(drawing_id);
CREATE INDEX IF NOT EXISTS idx_ndt_daily_log_project_date ON ndt_daily_log(project_id, log_date);
CREATE INDEX IF NOT EXISTS idx_change_log_project ON change_log(project_id);
CREATE INDEX IF NOT EXISTS idx_sub_systems_project ON sub_systems(project_id);
CREATE INDEX IF NOT EXISTS idx_sub_systems_status ON sub_systems(project_id, completion_status);
CREATE INDEX IF NOT EXISTS idx_punch_items_subsystem ON punch_items(sub_system_id);
CREATE INDEX IF NOT EXISTS idx_punch_items_status ON punch_items(project_id, status);
CREATE INDEX IF NOT EXISTS idx_commissioning_subsystem ON commissioning_procedures(sub_system_id);
CREATE INDEX IF NOT EXISTS idx_commissioning_status ON commissioning_procedures(project_id, status);
CREATE INDEX IF NOT EXISTS idx_ncr_project ON quality_ncr(project_id);
CREATE INDEX IF NOT EXISTS idx_ncr_status ON quality_ncr(project_id, status);
CREATE INDEX IF NOT EXISTS idx_ncr_discipline ON quality_ncr(project_id, discipline_id);
CREATE INDEX IF NOT EXISTS idx_weld_tracking_project ON weld_tracking(project_id);
CREATE INDEX IF NOT EXISTS idx_weld_tracking_drawing ON weld_tracking(drawing_id);
CREATE INDEX IF NOT EXISTS idx_incidents_project ON safety_incidents(project_id);
CREATE INDEX IF NOT EXISTS idx_incidents_date ON safety_incidents(project_id, incident_date);
CREATE INDEX IF NOT EXISTS idx_permits_project ON safety_permits(project_id);
CREATE INDEX IF NOT EXISTS idx_permits_status ON safety_permits(project_id, status);
CREATE INDEX IF NOT EXISTS idx_personnel_project ON personnel(project_id);
CREATE INDEX IF NOT EXISTS idx_personnel_training_person ON personnel_training(personnel_id);
CREATE INDEX IF NOT EXISTS idx_personnel_training_expiry ON personnel_training(expiry_date);
CREATE INDEX IF NOT EXISTS idx_planning_periods_project ON planning_periods(project_id, period_type);
CREATE INDEX IF NOT EXISTS idx_plan_items_period ON plan_items(period_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_project ON conflicts(project_id);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(project_id, status);
CREATE INDEX IF NOT EXISTS idx_feedback_loop_project ON feedback_loop(project_id);
CREATE INDEX IF NOT EXISTS idx_stage_gates_project ON stage_gates(project_id);

-- =============================================================================
-- Part L: Seed data for reference tables
-- =============================================================================

-- Seed training roles
INSERT INTO training_roles (role_name, role_category) VALUES
    ('Welder 6G', 'TRADE'),
    ('Welder 3G', 'TRADE'),
    ('Pipe Fitter', 'TRADE'),
    ('Structural Fitter', 'TRADE'),
    ('Rigger Level 1', 'TRADE'),
    ('Rigger Level 2', 'TRADE'),
    ('Electrician', 'TRADE'),
    ('Instrument Technician', 'TRADE'),
    ('NDT Technician UT', 'INSPECTION'),
    ('NDT Technician RT', 'INSPECTION'),
    ('NDT Technician MT', 'INSPECTION'),
    ('NDT Technician PT', 'INSPECTION'),
    ('Painting/Coating Applicator', 'TRADE'),
    ('Scaffolding Inspector', 'SUPPORT'),
    ('HSE Officer', 'HSE'),
    ('Site Supervisor', 'SUPERVISION'),
    ('Construction Manager', 'MANAGEMENT'),
    ('QA/QC Inspector', 'QUALITY'),
    ('Commissioning Engineer', 'ENGINEERING'),
    ('HVAC Technician', 'TRADE')
ON CONFLICT (role_name) DO NOTHING;

-- Seed training courses
INSERT INTO training_courses (course_code, course_name, course_category, validity_months, is_mandatory, description) VALUES
    ('HSE-IND', 'HSE Induction', 'HSE', 12, TRUE, 'Basic site safety induction for all personnel'),
    ('PTW-AW', 'Permit to Work — Authorized Worker', 'HSE', 12, TRUE, 'PTW system awareness for workers'),
    ('PTW-AA', 'Permit to Work — Authorized Applicant', 'HSE', 12, TRUE, 'PTW application and management'),
    ('CS-ENTRY', 'Confined Space Entry', 'HSE', 24, TRUE, 'Safe confined space entry procedures'),
    ('W@H', 'Working at Height', 'HSE', 24, TRUE, 'Fall protection and safe work at height'),
    ('HOT-WORK', 'Hot Work Safety', 'HSE', 12, TRUE, 'Hot work permit requirements and fire watch'),
    ('LIFT-OP', 'Lifting Operations & Rigging', 'HSE', 24, TRUE, 'Safe lifting practices and rigging inspection'),
    ('WELD-6G', '6G Welding Certification', 'TECHNICAL', 12, TRUE, 'All-position pipe welding certification'),
    ('WELD-3G', '3G Welding Certification', 'TECHNICAL', 12, TRUE, 'Vertical groove welding certification'),
    ('NDT-UT-L2', 'Ultrasonic Testing Level 2', 'TECHNICAL', 36, FALSE, 'UT method qualification — ASNT Level II'),
    ('NDT-RT-L2', 'Radiographic Testing Level 2', 'TECHNICAL', 36, FALSE, 'RT method qualification — ASNT Level II'),
    ('NDT-MT-L2', 'Magnetic Particle Testing Level 2', 'TECHNICAL', 36, FALSE, 'MT method qualification — ASNT Level II'),
    ('NDT-PT-L2', 'Penetrant Testing Level 2', 'TECHNICAL', 36, FALSE, 'PT method qualification — ASNT Level II'),
    ('QA-NCR', 'NCR Management & Root Cause Analysis', 'QUALITY', 24, FALSE, 'Non-conformance reporting and RCA fundamentals'),
    ('COMM-PROC', 'Commissioning Procedure Writing', 'TECHNICAL', 36, FALSE, 'System commissioning procedure development'),
    ('FAT-PROC', 'Factory Acceptance Test Procedure', 'TECHNICAL', 36, FALSE, 'FAT planning, execution, and reporting'),
    ('SCAFF-INSP', 'Scaffold Inspection', 'HSE', 24, TRUE, 'Scaffold tag system and inspection criteria'),
    ('FIRST-AID', 'First Aid at Work', 'HSE', 36, TRUE, 'Basic first aid and emergency response'),
    ('FIRE-WATCH', 'Fire Watch & Prevention', 'HSE', 12, TRUE, 'Fire watch duties during hot work'),
    ('E-ISOL', 'Electrical Isolation (LOTO)', 'HSE', 24, TRUE, 'Lock-out tag-out procedures and verification')
ON CONFLICT (course_code) DO NOTHING;

-- Seed default stage gates for EPC lifecycle
INSERT INTO stage_gates (gate_id, project_id, gate_name, gate_sequence, from_phase, to_phase, status)
SELECT gen_random_uuid(), project_id,
       'Engineering→Procurement', 1,
       'ENGINEERING', 'PROCUREMENT', 'PENDING'
FROM projects
WHERE NOT EXISTS (
    SELECT 1 FROM stage_gates WHERE gate_sequence = 1
);

INSERT INTO stage_gates (gate_id, project_id, gate_name, gate_sequence, from_phase, to_phase, status)
SELECT gen_random_uuid(), project_id,
       'Procurement→Construction', 2,
       'PROCUREMENT', 'CONSTRUCTION', 'PENDING'
FROM projects
WHERE NOT EXISTS (
    SELECT 1 FROM stage_gates WHERE gate_sequence = 2
);

INSERT INTO stage_gates (gate_id, project_id, gate_name, gate_sequence, from_phase, to_phase, status)
SELECT gen_random_uuid(), project_id,
       'Construction→System Completion', 3,
       'CONSTRUCTION', 'SYSTEM_COMPLETION', 'PENDING'
FROM projects
WHERE NOT EXISTS (
    SELECT 1 FROM stage_gates WHERE gate_sequence = 3
);

INSERT INTO stage_gates (gate_id, project_id, gate_name, gate_sequence, from_phase, to_phase, status)
SELECT gen_random_uuid(), project_id,
       'System Completion→Commissioning', 4,
       'SYSTEM_COMPLETION', 'COMMISSIONING', 'PENDING'
FROM projects
WHERE NOT EXISTS (
    SELECT 1 FROM stage_gates WHERE gate_sequence = 4
);

INSERT INTO stage_gates (gate_id, project_id, gate_name, gate_sequence, from_phase, to_phase, status)
SELECT gen_random_uuid(), project_id,
       'Commissioning→Handover', 5,
       'COMMISSIONING', 'OPERATIONS', 'PENDING'
FROM projects
WHERE NOT EXISTS (
    SELECT 1 FROM stage_gates WHERE gate_sequence = 5
);

COMMIT;
