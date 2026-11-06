"""
Test fixtures for FPSO EPC backend tests.

Uses SQLite in-memory for fast isolated test runs.
Each test gets a fresh database with the core schema tables.
"""
import sys
import os
import pytest
import pytest_asyncio

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from httpx import AsyncClient, ASGITransport


# ── In-memory SQLite test DB setup ──────────────────────────────────

TEST_DB_PATH = ":memory:"


def get_test_db_conn():
    """Create a fresh in-memory SQLite connection with schema."""
    import sqlite3
    import uuid

    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Register UUID generator function for SQLite
    conn.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))

    # Core tables needed for all tests
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY, project_code TEXT UNIQUE NOT NULL,
            project_name TEXT NOT NULL, client_name TEXT, contract_value REAL,
            planned_start_date TEXT NOT NULL, planned_finish_date TEXT NOT NULL,
            baseline_start_date TEXT, baseline_finish_date TEXT,
            current_status TEXT DEFAULT 'ACTIVE', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY, project_id TEXT, activity_code TEXT NOT NULL,
            activity_name TEXT NOT NULL, original_duration INTEGER NOT NULL,
            remaining_duration INTEGER, total_float INTEGER, is_critical INTEGER DEFAULT 0,
            physical_percent_complete REAL DEFAULT 0, status TEXT DEFAULT 'NOT_STARTED',
            work_scope_category TEXT, updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS activity_relationships (
            relationship_id TEXT PRIMARY KEY, predecessor_id TEXT, successor_id TEXT,
            relationship_type TEXT DEFAULT 'FS', lag INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS engineering_disciplines (
            discipline_id INTEGER PRIMARY KEY AUTOINCREMENT, discipline_name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS drawings (
            drawing_id TEXT PRIMARY KEY, project_id TEXT, discipline_id INTEGER NOT NULL,
            drawing_number TEXT NOT NULL, drawing_title TEXT, drawing_type TEXT,
            status TEXT DEFAULT 'WIP', planned_issue_date TEXT, actual_issue_date TEXT,
            revision TEXT, weight_kg REAL,
            issued_for_info TEXT DEFAULT 'Yes', issued_for_info_date TEXT,
            issued_for_construction TEXT DEFAULT 'No', issued_for_construction_date TEXT
        );
        CREATE TABLE IF NOT EXISTS drawing_materials (
            material_id TEXT PRIMARY KEY, drawing_id TEXT, project_id TEXT,
            piece_mark TEXT DEFAULT '-', material_grade TEXT, material_thickness TEXT,
            material_weight REAL, material_type TEXT, size TEXT, diameter TEXT,
            material_length REAL, material_category TEXT, total_weight REAL,
            po_status TEXT, material_class TEXT,
            mvr_status TEXT DEFAULT 'Info-AFI', mvr_confirmed_by TEXT, mvr_confirmed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS drawing_equipment (
            equipment_id TEXT PRIMARY KEY, drawing_id TEXT, project_id TEXT,
            equipment_tag TEXT, equipment_name TEXT, equipment_detail TEXT,
            install_location TEXT, weight REAL, equipment_type TEXT,
            certification TEXT, fat_status TEXT DEFAULT 'PENDING', test_status TEXT,
            system_code TEXT, system_name TEXT,
            schedule_delivery_date TEXT, schedule_install_date TEXT, remark TEXT
        );
        CREATE TABLE IF NOT EXISTS material_takeoff (
            mto_id TEXT PRIMARY KEY, project_id TEXT, discipline_id INTEGER,
            drawing_id TEXT, material_type TEXT, material_spec TEXT,
            quantity REAL, unit TEXT, unit_weight_kg REAL
        );
        CREATE TABLE IF NOT EXISTS procurement_purchase_orders (
            po_id TEXT PRIMARY KEY, project_id TEXT, po_number TEXT UNIQUE NOT NULL,
            vendor_name TEXT, order_date TEXT, expected_delivery_date TEXT,
            actual_delivery_date TEXT, total_amount REAL, status TEXT DEFAULT 'ORDERED'
        );
        CREATE TABLE IF NOT EXISTS purchase_items (
            purchase_item_id TEXT PRIMARY KEY, po_id TEXT, material_type TEXT,
            material_spec TEXT, quantity_ordered REAL, unit TEXT,
            unit_price REAL, quantity_received REAL, received_date TEXT
        );
        CREATE TABLE IF NOT EXISTS equipment_list (
            equipment_id TEXT PRIMARY KEY, project_id TEXT, category_id INTEGER,
            tag_number TEXT NOT NULL, equipment_name TEXT, manufacturer TEXT,
            model TEXT, specification_doc TEXT, spec_status TEXT DEFAULT 'SUBMITTED',
            order_date TEXT, delivery_date TEXT, installation_date TEXT
        );
        CREATE TABLE IF NOT EXISTS equipment_categories (
            cat_id INTEGER PRIMARY KEY AUTOINCREMENT, category_name TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS daily_manpower (
            record_id TEXT PRIMARY KEY, project_id TEXT, report_date TEXT NOT NULL,
            discipline TEXT, planned_headcount INTEGER, actual_headcount INTEGER,
            overtime_hours REAL
        );
        CREATE TABLE IF NOT EXISTS weekly_planning_tasks (
            task_id TEXT PRIMARY KEY, project_id TEXT, week_start TEXT NOT NULL,
            activity_id TEXT, planned_status TEXT, planned_completion_percent INTEGER,
            actual_completion_percent INTEGER, is_completed INTEGER DEFAULT 0,
            delay_reason TEXT, accountability_party TEXT
        );
        CREATE TABLE IF NOT EXISTS resource_shortages (
            shortage_id TEXT PRIMARY KEY, project_id TEXT, shortage_type TEXT,
            resource_name TEXT, required_quantity REAL, available_quantity REAL,
            shortfall REAL, expected_resolution_date TEXT, impact_description TEXT,
            status TEXT DEFAULT 'OPEN'
        );
        CREATE TABLE IF NOT EXISTS ndt_requests (
            ndt_id TEXT PRIMARY KEY, project_id TEXT, activity_id TEXT,
            drawing_id TEXT, discipline_name TEXT, material_class TEXT,
            ndt_method TEXT, weld_joint_id TEXT, joint_type TEXT,
            joint_length_mm REAL DEFAULT 0, weld_length_mm REAL DEFAULT 0,
            requested_date TEXT, completed_date TEXT,
            status TEXT DEFAULT 'REQUESTED', result TEXT,
            percent_complete REAL DEFAULT 0,
            acceptance_criteria TEXT, technician_name TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_inspection_focus (
            focus_id TEXT PRIMARY KEY, project_id TEXT, focus_date TEXT NOT NULL,
            discipline TEXT, focus_point TEXT, priority TEXT DEFAULT 'HIGH',
            is_achieved INTEGER DEFAULT 0, achievement_notes TEXT
        );
        CREATE TABLE IF NOT EXISTS ndt_daily_log (
            log_id TEXT PRIMARY KEY, project_id TEXT, log_date TEXT NOT NULL,
            discipline_name TEXT NOT NULL, ndt_method TEXT NOT NULL,
            rfi_total_length_mm REAL DEFAULT 0,
            ndt_complete_length_mm REAL DEFAULT 0,
            daily_length_done_mm REAL DEFAULT 0,
            team_deployed INTEGER DEFAULT 0,
            previous_status TEXT, remarks TEXT,
            updated_by TEXT, updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS schedule_alerts (
            alert_id TEXT PRIMARY KEY, project_id TEXT, alert_type TEXT NOT NULL,
            activity_id TEXT, alert_title TEXT, severity TEXT NOT NULL,
            recommended_action TEXT, is_resolved INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS change_log (
            log_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            action TEXT NOT NULL, entity_number TEXT, discipline_name TEXT,
            logged_at TEXT DEFAULT (datetime('now'))
        );

        -- New lifecycle tables
        CREATE TABLE IF NOT EXISTS sub_systems (
            sub_system_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            system_code TEXT NOT NULL, system_name TEXT, parent_system_id TEXT,
            discipline_id INTEGER, area_code TEXT,
            completion_status TEXT DEFAULT 'NOT_STARTED',
            planned_mc_date TEXT, actual_mc_date TEXT, handover_date TEXT,
            responsible_engineer TEXT, notes TEXT,
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS punch_items (
            punch_id TEXT PRIMARY KEY, project_id TEXT, sub_system_id TEXT,
            punch_number TEXT UNIQUE, category TEXT DEFAULT 'B',
            discipline_id INTEGER, area_code TEXT, description TEXT NOT NULL,
            raised_by TEXT, raised_date TEXT DEFAULT (date('now')),
            assigned_to TEXT, target_date TEXT, closeout_date TEXT,
            closeout_verified_by TEXT, status TEXT DEFAULT 'OPEN',
            priority TEXT DEFAULT 'MEDIUM', photo_ref TEXT,
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS commissioning_procedures (
            procedure_id TEXT PRIMARY KEY, sub_system_id TEXT, project_id TEXT,
            procedure_code TEXT NOT NULL, procedure_name TEXT,
            procedure_type TEXT DEFAULT 'MC_CHECK', description TEXT,
            planned_date TEXT, actual_date TEXT, status TEXT DEFAULT 'PENDING',
            responsible_party TEXT, witness_required INTEGER DEFAULT 0,
            witness_party TEXT, test_result TEXT, attachments TEXT,
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS commissioning_checklist (
            checklist_id TEXT PRIMARY KEY, procedure_id TEXT,
            item_number INTEGER NOT NULL, check_description TEXT NOT NULL,
            expected_result TEXT, actual_result TEXT, is_verified INTEGER DEFAULT 0,
            verified_by TEXT, verified_date TEXT, remarks TEXT
        );
        CREATE TABLE IF NOT EXISTS quality_ncr (
            ncr_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            ncr_number TEXT UNIQUE NOT NULL, discipline_id INTEGER,
            sub_system_id TEXT, activity_id TEXT, severity TEXT DEFAULT 'MINOR',
            category TEXT, description TEXT NOT NULL, immediate_action TEXT,
            root_cause TEXT, corrective_action TEXT, preventive_action TEXT,
            raised_by TEXT, raised_date TEXT DEFAULT (date('now')),
            target_closeout_date TEXT, actual_closeout_date TEXT,
            verified_by TEXT, status TEXT DEFAULT 'OPEN',
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS weld_tracking (
            weld_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            weld_number TEXT UNIQUE NOT NULL, drawing_id TEXT, discipline_id INTEGER,
            weld_type TEXT, joint_type TEXT, diameter_mm REAL, thickness_mm REAL,
            welder_id TEXT, weld_date TEXT, ndt_method TEXT, ndt_result TEXT,
            rejection_reason TEXT, repair_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDING_NDT'
        );
        CREATE TABLE IF NOT EXISTS safety_incidents (
            incident_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            incident_date TEXT NOT NULL, incident_time TEXT, incident_type TEXT NOT NULL,
            severity TEXT DEFAULT 'LOW', area_code TEXT, discipline_id INTEGER,
            description TEXT NOT NULL, immediate_cause TEXT,
            root_cause TEXT, corrective_action TEXT, preventive_action TEXT,
            reported_by TEXT, investigated_by TEXT, lost_time_days INTEGER DEFAULT 0,
            man_hours_at_incident INTEGER DEFAULT 0, status TEXT DEFAULT 'OPEN',
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS safety_permits (
            permit_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            permit_type TEXT NOT NULL, permit_number TEXT UNIQUE NOT NULL,
            work_description TEXT NOT NULL, area_code TEXT, discipline_id INTEGER,
            requested_by TEXT, approved_by TEXT, issue_date TEXT, expiry_date TEXT,
            isolation_required TEXT DEFAULT 'No', gas_test_required TEXT DEFAULT 'No',
            gas_test_result TEXT, status TEXT DEFAULT 'REQUESTED', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS safety_observations (
            observation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            observation_date TEXT DEFAULT (date('now')), area_code TEXT, category TEXT,
            observation TEXT NOT NULL, action_taken TEXT, observed_by TEXT,
            status TEXT DEFAULT 'OPEN', positive_observation INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS training_roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT, role_name TEXT UNIQUE NOT NULL,
            role_category TEXT
        );
        CREATE TABLE IF NOT EXISTS training_courses (
            course_id INTEGER PRIMARY KEY AUTOINCREMENT, course_code TEXT UNIQUE NOT NULL,
            course_name TEXT NOT NULL, course_category TEXT, validity_months INTEGER,
            is_mandatory INTEGER DEFAULT 0, description TEXT
        );
        CREATE TABLE IF NOT EXISTS training_role_requirements (
            requirement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER, course_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS personnel (
            personnel_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            badge_number TEXT UNIQUE, full_name TEXT NOT NULL, role_id INTEGER,
            discipline TEXT, contractor_company TEXT,
            mobilization_date TEXT, demobilization_date TEXT, status TEXT DEFAULT 'ACTIVE'
        );
        CREATE TABLE IF NOT EXISTS personnel_training (
            record_id TEXT PRIMARY KEY, personnel_id TEXT, project_id TEXT,
            course_id INTEGER, completion_date TEXT, expiry_date TEXT,
            certificate_ref TEXT, score REAL, verified_by TEXT
        );
        CREATE TABLE IF NOT EXISTS planning_periods (
            period_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            period_type TEXT NOT NULL, period_label TEXT,
            period_start TEXT NOT NULL, period_end TEXT NOT NULL,
            is_locked INTEGER DEFAULT 0, locked_by TEXT, locked_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS plan_items (
            plan_item_id TEXT PRIMARY KEY, period_id TEXT, activity_id TEXT,
            planned_weight_pct REAL, actual_weight_pct REAL,
            milestone_flag INTEGER DEFAULT 0, milestone_name TEXT,
            status TEXT DEFAULT 'ON_TRACK', variance_note TEXT
        );
        CREATE TABLE IF NOT EXISTS conflicts (
            conflict_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            conflict_type TEXT NOT NULL, title TEXT, description TEXT,
            source_entity_type TEXT, source_entity_id TEXT,
            target_entity_type TEXT, target_entity_id TEXT,
            severity TEXT DEFAULT 'MEDIUM', detected_by_agent INTEGER DEFAULT 0,
            ai_confidence REAL, ai_recommendation TEXT,
            status TEXT DEFAULT 'DETECTED', resolution_notes TEXT,
            resolved_by TEXT, created_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conflict_actions (
            action_id TEXT PRIMARY KEY, conflict_id TEXT,
            action_description TEXT NOT NULL, assigned_to TEXT,
            target_date TEXT, completion_date TEXT, status TEXT DEFAULT 'PENDING'
        );
        CREATE TABLE IF NOT EXISTS feedback_loop (
            feedback_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            source_stage TEXT NOT NULL, target_stage TEXT NOT NULL,
            feedback_type TEXT NOT NULL, reference_number TEXT,
            description TEXT NOT NULL, impact_assessment TEXT,
            impact_level TEXT DEFAULT 'MEDIUM', ai_generated_assessment INTEGER DEFAULT 0,
            is_actioned INTEGER DEFAULT 0, actioned_by TEXT,
            actioned_date TEXT, closure_notes TEXT, created_by TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS stage_gates (
            gate_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            gate_name TEXT NOT NULL, gate_sequence INTEGER NOT NULL,
            from_phase TEXT, to_phase TEXT, planned_date TEXT, actual_date TEXT,
            checklist_complete_pct REAL DEFAULT 0, ai_readiness_score REAL,
            human_approver TEXT, approval_date TEXT, approver_comments TEXT,
            status TEXT DEFAULT 'PENDING', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS stage_gate_checklist (
            checklist_item_id TEXT PRIMARY KEY, gate_id TEXT,
            item_number INTEGER NOT NULL, category TEXT, description TEXT NOT NULL,
            verification_method TEXT, is_complete INTEGER DEFAULT 0,
            verified_by TEXT, verified_date TEXT, evidence_ref TEXT, remarks TEXT
        );
    """)

    # Seed disciplines
    for name in ['STRUCTURAL', 'PIPING', 'MECHANICAL', 'ELECTRICAL', 'HVAC', 'ARCHITECTURE_DECORATION']:
        conn.execute("INSERT OR IGNORE INTO engineering_disciplines (discipline_name) VALUES (?)", (name,))

    # Seed equipment categories
    for name in ['MECHANICAL', 'ELECTRICAL', 'HVAC']:
        conn.execute("INSERT OR IGNORE INTO equipment_categories (category_name) VALUES (?)", (name,))

    # Seed test project
    conn.execute(
        "INSERT OR IGNORE INTO projects (project_id, project_code, project_name, client_name, contract_value, planned_start_date, planned_finish_date) VALUES (?,?,?,?,?,?,?)",
        ("test-project", "FPSO-TEST", "Test FPSO Project", "Test Client", 1000000000, "2025-01-01", "2028-12-31"),
    )

    # Seed test activity
    conn.execute(
        "INSERT OR IGNORE INTO activities (activity_id, project_id, activity_code, activity_name, original_duration, remaining_duration, total_float, is_critical, physical_percent_complete, status, work_scope_category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("act-test-1", "test-project", "ENG-001", "Test Activity", 100, 50, 5, 0, 50, "IN_PROGRESS", "CRITICAL"),
    )

    # Seed test drawing
    conn.execute(
        "INSERT OR IGNORE INTO drawings (drawing_id, project_id, discipline_id, drawing_number, drawing_title, drawing_type, status, weight_kg) VALUES (?,?,?,?,?,?,?,?)",
        ("draw-test-1", "test-project", 1, "STR-DWG-TEST", "Test Drawing", "GA", "IFC", 1000.0),
    )

    # Seed test training roles
    conn.execute("INSERT OR IGNORE INTO training_roles (role_id, role_name, role_category) VALUES (1, 'Welder 6G', 'TRADE')")
    conn.execute("INSERT OR IGNORE INTO training_roles (role_id, role_name, role_category) VALUES (2, 'Pipe Fitter', 'TRADE')")

    # Seed test training courses
    conn.execute("INSERT OR IGNORE INTO training_courses (course_id, course_code, course_name, validity_months, is_mandatory) VALUES (1, 'HSE-IND', 'HSE Induction', 12, 1)")
    conn.execute("INSERT OR IGNORE INTO training_courses (course_id, course_code, course_name, validity_months, is_mandatory) VALUES (2, 'WELD-6G', '6G Welding Cert', 12, 1)")

    conn.commit()
    return conn


# ── Pytest Fixtures ─────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def dispose_async_engine():
    """Dispose the lazy SQLAlchemy engine so its aiosqlite worker thread exits.

    Some authorization tests reach a route body with a valid token, which opens
    a SQLAlchemy AsyncSession. The fallback engine pools an aiosqlite
    connection, and aiosqlite's worker thread otherwise keeps the pytest
    process alive after the last test finishes.
    """
    yield
    import asyncio

    from database import engine

    if engine is None:
        return
    try:
        asyncio.run(engine.dispose())
    except Exception:
        pass


@pytest.fixture(scope="session")
def db_conn():
    """Session-scoped DB connection for all tests."""
    conn = get_test_db_conn()
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def fresh_db(db_conn):
    """
    Function-scoped — each test starts with a clean state.
    We can re-seed core data here.
    """
    yield db_conn
    # Roll back any uncommitted changes to keep tests isolated
    db_conn.rollback()


@pytest.fixture
def test_project_id():
    return "test-project"


@pytest.fixture
def test_drawing_id():
    return "draw-test-1"


@pytest.fixture
def test_activity_id():
    return "act-test-1"
