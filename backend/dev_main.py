"""
Development server using SQLite — no PostgreSQL needed.
Run: python dev_main.py
"""
import hashlib
import os
import sqlite3
import uuid
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers

from config import settings
from auth import (
    DUMMY_PASSWORD_HASH,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    has_role,
    verify_password,
)
from websocket import manager

DB_PATH = "dev.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY, project_code TEXT UNIQUE NOT NULL, project_name TEXT NOT NULL,
            client_name TEXT, contract_value REAL, planned_start_date TEXT NOT NULL,
            planned_finish_date TEXT NOT NULL, baseline_start_date TEXT, baseline_finish_date TEXT,
            current_status TEXT DEFAULT 'ACTIVE', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY, project_id TEXT, activity_code TEXT NOT NULL,
            activity_name TEXT NOT NULL, original_duration INTEGER NOT NULL, remaining_duration INTEGER,
            total_float INTEGER, is_critical INTEGER DEFAULT 0, physical_percent_complete REAL DEFAULT 0,
            status TEXT DEFAULT 'NOT_STARTED', work_scope_category TEXT, updated_at TEXT DEFAULT (datetime('now'))
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
            po_status TEXT DEFAULT NULL, material_class TEXT DEFAULT NULL,
            mvr_status TEXT DEFAULT 'Info-AFI', mvr_confirmed_by TEXT DEFAULT NULL, mvr_confirmed_at TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS drawing_equipment (
            equipment_id TEXT PRIMARY KEY, drawing_id TEXT, project_id TEXT,
            equipment_tag TEXT, equipment_name TEXT, equipment_detail TEXT,
            install_location TEXT, weight REAL, equipment_type TEXT,
            certification TEXT, fat_status TEXT DEFAULT 'PENDING', test_status TEXT,
            system_code TEXT, system_name TEXT,
            schedule_delivery_date TEXT, schedule_install_date TEXT,
            remark TEXT
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
        CREATE TABLE IF NOT EXISTS daily_manpower (
            record_id TEXT PRIMARY KEY, project_id TEXT, report_date TEXT NOT NULL,
            discipline TEXT, planned_headcount INTEGER, actual_headcount INTEGER,
            overtime_hours REAL, UNIQUE(project_id, report_date, discipline)
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
            entity_type TEXT NOT NULL CHECK(entity_type IN ('drawing', 'material')),
            entity_id TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('create', 'delete')),
            entity_number TEXT, discipline_name TEXT,
            logged_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_change_log_project ON change_log(project_id);
        CREATE INDEX IF NOT EXISTS idx_change_log_entity_type ON change_log(project_id, entity_type);
    """)
    # Extended schema tables (from migration 001)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS quality_ncr (
            ncr_id TEXT PRIMARY KEY, project_id TEXT, ncr_number TEXT, title TEXT, description TEXT,
            severity TEXT DEFAULT 'MINOR', status TEXT DEFAULT 'OPEN', discipline_name TEXT,
            root_cause TEXT, corrective_action TEXT, raised_date TEXT, closed_date TEXT,
            system_code TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS weld_tracking (
            weld_id TEXT PRIMARY KEY, project_id TEXT, drawing_id TEXT, ndt_method TEXT,
            joint_type TEXT, weld_joint_id TEXT, status TEXT DEFAULT 'REQUESTED',
            rejection_reason TEXT, repair_status TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS safety_incidents (
            incident_id TEXT PRIMARY KEY, project_id TEXT, incident_date TEXT, incident_type TEXT,
            severity TEXT DEFAULT 'LOW', description TEXT, investigation_status TEXT DEFAULT 'OPEN',
            corrective_actions TEXT, lost_time_days INTEGER DEFAULT 0, location TEXT,
            reported_by TEXT, man_hours_at_incident INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS safety_permits (
            permit_id TEXT PRIMARY KEY, project_id TEXT, permit_type TEXT, permit_number TEXT,
            work_description TEXT, area_code TEXT, discipline_id INTEGER, requested_by TEXT,
            approved_by TEXT, issue_date TEXT, expiry_date TEXT, isolation_required INTEGER DEFAULT 0,
            gas_test_required INTEGER DEFAULT 0, status TEXT DEFAULT 'ACTIVE'
        );
        CREATE TABLE IF NOT EXISTS safety_observations (
            observation_id TEXT PRIMARY KEY, project_id TEXT, observation_date TEXT,
            observer_name TEXT, location TEXT, category TEXT, description TEXT,
            risk_level TEXT DEFAULT 'LOW', action_taken TEXT, status TEXT DEFAULT 'OPEN'
        );
        CREATE TABLE IF NOT EXISTS training_roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT, role_name TEXT UNIQUE NOT NULL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS training_courses (
            course_id INTEGER PRIMARY KEY AUTOINCREMENT, course_name TEXT UNIQUE NOT NULL,
            course_description TEXT, validity_months INTEGER DEFAULT 36, is_mandatory INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS personnel (
            personnel_id TEXT PRIMARY KEY, project_id TEXT, full_name TEXT NOT NULL,
            role_id INTEGER, trade TEXT, discipline TEXT, email TEXT, phone TEXT, is_active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS personnel_training (
            record_id TEXT PRIMARY KEY, personnel_id TEXT, course_id INTEGER, project_id TEXT,
            completion_date TEXT, expiry_date TEXT, status TEXT DEFAULT 'PENDING', score REAL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS planning_periods (
            period_id TEXT PRIMARY KEY, project_id TEXT, period_type TEXT NOT NULL,
            period_start TEXT NOT NULL, period_end TEXT NOT NULL, period_label TEXT,
            is_locked INTEGER DEFAULT 0, locked_by TEXT, created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, period_type, period_start)
        );
        CREATE TABLE IF NOT EXISTS plan_items (
            plan_item_id TEXT PRIMARY KEY, period_id TEXT, activity_id TEXT,
            planned_weight_pct REAL DEFAULT 0, actual_weight_pct REAL, status TEXT DEFAULT 'ON_TRACK',
            variance_note TEXT, milestone_flag INTEGER DEFAULT 0, milestone_name TEXT,
            UNIQUE(period_id, activity_id)
        );
        CREATE TABLE IF NOT EXISTS sub_systems (
            sub_system_id TEXT PRIMARY KEY, project_id TEXT, system_code TEXT NOT NULL,
            system_name TEXT, parent_system_id TEXT, discipline_id INTEGER, area_code TEXT,
            completion_status TEXT DEFAULT 'NOT_STARTED', planned_mc_date TEXT, actual_mc_date TEXT,
            handover_date TEXT, responsible_engineer TEXT, notes TEXT,
            UNIQUE(project_id, system_code)
        );
        CREATE TABLE IF NOT EXISTS punch_items (
            punch_id TEXT PRIMARY KEY, sub_system_id TEXT, project_id TEXT, punch_number TEXT UNIQUE,
            category TEXT DEFAULT 'B', discipline_id INTEGER, area_code TEXT, description TEXT,
            raised_by TEXT, raised_date TEXT DEFAULT (date('now')), assigned_to TEXT,
            target_date TEXT, closeout_date TEXT, status TEXT DEFAULT 'OPEN', priority TEXT DEFAULT 'MEDIUM'
        );
        CREATE TABLE IF NOT EXISTS commissioning_procedures (
            procedure_id TEXT PRIMARY KEY, sub_system_id TEXT, project_id TEXT,
            procedure_code TEXT NOT NULL, procedure_name TEXT, procedure_type TEXT,
            status TEXT DEFAULT 'PENDING', planned_date TEXT, completed_date TEXT, result TEXT,
            executed_by TEXT, verified_by TEXT
        );
        CREATE TABLE IF NOT EXISTS commissioning_checklist (
            checklist_id TEXT PRIMARY KEY, procedure_id TEXT, item_number INTEGER,
            description TEXT, acceptance_criteria TEXT, is_complete INTEGER DEFAULT 0,
            completed_by TEXT, completed_date TEXT, remarks TEXT
        );
        CREATE TABLE IF NOT EXISTS conflicts (
            conflict_id TEXT PRIMARY KEY, project_id TEXT, conflict_type TEXT DEFAULT 'OTHER',
            title TEXT, description TEXT, severity TEXT DEFAULT 'MEDIUM', status TEXT DEFAULT 'OPEN',
            detected_by_agent INTEGER DEFAULT 0, ai_confidence REAL, ai_recommendation TEXT,
            source_entity TEXT, target_entity TEXT, created_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conflict_actions (
            action_id TEXT PRIMARY KEY, conflict_id TEXT, project_id TEXT, action_description TEXT,
            assigned_to TEXT, target_date TEXT, status TEXT DEFAULT 'OPEN', completed_date TEXT
        );
        CREATE TABLE IF NOT EXISTS stage_gates (
            gate_id TEXT PRIMARY KEY, project_id TEXT, gate_name TEXT NOT NULL,
            from_phase TEXT, to_phase TEXT, gate_sequence INTEGER, status TEXT DEFAULT 'PENDING',
            ai_readiness_score REAL, approved_by TEXT, approved_at TEXT,
            checklist_pct REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS stage_gate_checklist (
            item_id TEXT PRIMARY KEY, gate_id TEXT, item_number INTEGER, description TEXT,
            is_complete INTEGER DEFAULT 0, completed_by TEXT, completed_date TEXT, evidence_ref TEXT
        );
        CREATE TABLE IF NOT EXISTS feedback_loop (
            feedback_id TEXT PRIMARY KEY, project_id TEXT, source_stage TEXT, target_stage TEXT,
            feedback_type TEXT, description TEXT, submitted_by TEXT, is_actioned INTEGER DEFAULT 0,
            action_taken TEXT, actioned_by TEXT, actioned_date TEXT,
            ai_generated_assessment INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL, full_name TEXT, role TEXT DEFAULT 'viewer',
            is_active INTEGER DEFAULT 1, last_login TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token_id TEXT PRIMARY KEY, user_id TEXT, token_hash TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL, revoked INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            log_id TEXT PRIMARY KEY, user_id TEXT, event_type TEXT NOT NULL,
            ip_address TEXT, user_agent TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Seed a development admin when no users exist. Never in production, and
    # never with a hardcoded hash — the password comes from the environment.
    if settings.environment != "production":
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            dev_username = os.getenv("FPSO_DEV_ADMIN_USERNAME", "admin")
            dev_password = os.getenv("FPSO_DEV_ADMIN_PASSWORD") or settings.dev_admin_password
            conn.execute(
                """INSERT INTO users
                   (user_id, username, email, hashed_password, full_name, role, is_active)
                   VALUES (?,?,?,?,?,?,1)""",
                (
                    str(uuid.uuid4()),
                    dev_username,
                    f"{dev_username}@fpso.local",
                    hash_password(dev_password),
                    "Development Administrator",
                    "admin",
                ),
            )

    # Migration: add columns that may not exist in older dev databases
    try:
        conn.execute("ALTER TABLE drawing_materials ADD COLUMN material_class TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE drawing_materials ADD COLUMN po_status TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE drawing_materials ADD COLUMN mvr_status TEXT DEFAULT 'Info-AFI'")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE drawing_materials ADD COLUMN mvr_confirmed_by TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE drawing_materials ADD COLUMN mvr_confirmed_at TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    # Seed disciplines
    for name in ['STRUCTURAL', 'PIPING', 'MECHANICAL', 'ELECTRICAL', 'HVAC']:
        conn.execute("INSERT OR IGNORE INTO engineering_disciplines (discipline_name) VALUES (?)", (name,))
    # Seed demo project
    pid = "demo-project"
    conn.execute("INSERT OR IGNORE INTO projects (project_id, project_code, project_name, client_name, contract_value, planned_start_date, planned_finish_date, baseline_start_date, baseline_finish_date) VALUES (?,?,?,?,?,?,?,?,?)",
                 (pid, "FPSO-P1", "FPSO Cidade de Vitoria", "Petro-Ocean", 2500000000, "2024-01-01", "2027-12-31", "2024-01-01", "2027-12-31"))
    # Seed demo activities
    for i, (code, name, dur, rf, crit, pct, status, cat) in enumerate([
        ("ENG-001", "Structural Design", 180, 30, 1, 75, "IN_PROGRESS", "CRITICAL"),
        ("ENG-002", "Piping Design", 120, 60, 1, 50, "IN_PROGRESS", "CRITICAL"),
        ("ENG-003", "Electrical Design", 90, 45, 0, 90, "IN_PROGRESS", "MIDWARE"),
        ("PRO-001", "Steel Procurement", 200, 100, 0, 40, "IN_PROGRESS", "MIDWARE"),
        ("PRO-002", "Equipment Order", 150, 80, 0, 60, "IN_PROGRESS", "MIDWARE"),
        ("CON-001", "Hull Assembly", 365, 300, 1, 15, "IN_PROGRESS", "CRITICAL"),
        ("CON-002", "Pipe Installation", 200, 180, 0, 10, "IN_PROGRESS", "SHORTER"),
    ]):
        conn.execute("INSERT OR IGNORE INTO activities (activity_id, project_id, activity_code, activity_name, original_duration, remaining_duration, total_float, is_critical, physical_percent_complete, status, work_scope_category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (f"act-{i+1}", pid, code, name, dur, rf, 0 if crit else 5, crit, pct, status, cat))
    # Seed drawings — all 5 disciplines with IFA/IFC status
    # (discipline_id, drawing_number, title, drawing_type, revision, weight_kg, ifa, ifa_date, ifc, ifc_date)
    drawings_data = [
        # STRUCTURAL (discipline_id=1)
        (1, "STR-DWG-001", "Hull Structural GA – Main Deck", "GA", "C", 15000, "Yes", "2025-03-15", "Yes", "2025-06-20"),
        (1, "STR-DWG-002", "Hull Structural GA – Aft Section", "GA", "B", 12000, "Yes", "2025-03-20", "Yes", "2025-07-01"),
        (1, "STR-DWG-003", "Column & Stiffener Details", "DETAIL", "A", 8000, "Yes", "2025-04-10", "No", None),
        (1, "STR-DWG-004", "Deck Plate Arrangement", "DETAIL", "C", 10000, "Yes", "2025-02-28", "Yes", "2025-05-15"),
        (1, "STR-DWG-005", "Bulkhead Structural Details", "DETAIL", "B", 7500, "Yes", "2025-04-05", "No", None),
        (1, "STR-DWG-006", "Helideck Support Structure", "GA", "A", 5500, "Yes", "2025-05-12", "No", None),
        # PIPING (discipline_id=2)
        (2, "PIP-DWG-001", "Piping Layout – Main Deck", "GA", "C", 5000, "Yes", "2025-03-01", "Yes", "2025-06-10"),
        (2, "PIP-DWG-002", "Piping Isometrics – Cargo System", "ISOMETRIC", "B", 3500, "Yes", "2025-03-15", "No", None),
        (2, "PIP-DWG-003", "Piping Isometrics – Ballast System", "ISOMETRIC", "A", 3200, "Yes", "2025-04-01", "No", None),
        (2, "PIP-DWG-004", "Pipe Support Details – Main", "DETAIL", "B", 2800, "Yes", "2025-02-20", "Yes", "2025-05-30"),
        (2, "PIP-DWG-005", "P&ID – Process Flow Diagram", "P&ID", "C", 4200, "Yes", "2025-01-15", "Yes", "2025-04-20"),
        # MECHANICAL (discipline_id=3)
        (3, "MEC-DWG-001", "Process Equipment Layout", "GA", "B", 4500, "Yes", "2025-03-10", "Yes", "2025-06-15"),
        (3, "MEC-DWG-002", "Compressor Module Details", "DETAIL", "A", 3800, "Yes", "2025-04-20", "No", None),
        (3, "MEC-DWG-003", "Turret & Swivel Stack Arrangement", "GA", "C", 9200, "Yes", "2025-02-01", "Yes", "2025-05-01"),
        (3, "MEC-DWG-004", "Firewater Pump Details", "DETAIL", "B", 2200, "Yes", "2025-05-01", "No", None),
        # ELECTRICAL (discipline_id=4)
        (4, "ELE-DWG-001", "Single Line Diagram – MV Switchboard", "P&ID", "C", 2000, "Yes", "2025-03-05", "Yes", "2025-06-25"),
        (4, "ELE-DWG-002", "Single Line Diagram – LV Switchboard", "P&ID", "B", 1800, "Yes", "2025-03-10", "No", None),
        (4, "ELE-DWG-003", "Cable Tray Routing – Main Deck", "GA", "A", 3500, "Yes", "2025-04-15", "No", None),
        (4, "ELE-DWG-004", "Lighting Layout – Accommodation", "GA", "B", 1500, "Yes", "2025-04-30", "Yes", "2025-07-10"),
        (4, "ELE-DWG-005", "Earthing & Lightning Protection", "DETAIL", "A", 1200, "Yes", "2025-05-05", "No", None),
        (4, "ELE-DWG-006", "Electrical Equipment Room Layout", "GA", "B", 2800, "Yes", "2025-03-20", "No", None),
        (4, "ELE-DWG-007", "UPS & Battery System Schematic", "P&ID", "A", 900, "Yes", "2025-05-12", "No", None),
        # HVAC (discipline_id=5)
        (5, "HVAC-DWG-001", "HVAC Duct Layout – Accommodation", "GA", "B", 2200, "Yes", "2025-04-01", "No", None),
        (5, "HVAC-DWG-002", "HVAC Flow Schematic", "P&ID", "A", 1600, "Yes", "2025-05-01", "No", None),
        (5, "HVAC-DWG-003", "Ventilation Layout – Engine Room", "GA", "B", 3000, "Yes", "2025-03-20", "Yes", "2025-06-30"),
    ]
    for i, (did, dn, title, dtype, rev, wkg, ifa, ifa_date, ifc, ifc_date) in enumerate(drawings_data):
        conn.execute("INSERT OR IGNORE INTO drawings (drawing_id, project_id, discipline_id, drawing_number, drawing_title, drawing_type, status, revision, weight_kg, issued_for_info, issued_for_info_date, issued_for_construction, issued_for_construction_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"drw-{i+1}", pid, did, dn, title, dtype, "IFC" if ifc == "Yes" else ("IFA" if ifa == "Yes" else "WIP"), rev, wkg, ifa, ifa_date, ifc, ifc_date))
    # Seed drawing_materials — STRUCTURAL (discipline 1) and PIPING (discipline 2)
    # Format: (drawing_id, project_id, piece_mark, material_grade, material_thickness, material_weight, material_type, size, diameter, material_length, material_category, total_weight)
    materials_data = [
        # ===== STRUCTURAL MATERIALS =====
        # I-BEAM — per size, per grade
        ("drw-1", pid, "BM-001", "ASTM A992", "N/A", 150.0, "I-BEAM", "H300x300", None, 10.0, "I-BEAM", 1500),
        ("drw-1", pid, "BM-003", "ASTM A992", "N/A", 105.0, "I-BEAM", "H250x250", None, 12.0, "I-BEAM", 1260),
        ("drw-2", pid, "BM-004", "ASTM A572 Gr50", "N/A", 150.0, "I-BEAM", "H300x300", None, 8.0, "I-BEAM", 1200),
        ("drw-2", pid, "BM-005", "ASTM A992", "N/A", 89.0, "I-BEAM", "H250x250", None, 10.0, "I-BEAM", 890),
        ("drw-6", pid, "BM-002", "ASTM A992", "N/A", 210.0, "I-BEAM", "H350x350", None, 10.0, "I-BEAM", 2100),
        # Steel Plate — per thickness, per grade
        ("drw-1", pid, "PL-001", "ASTM A36", "30mm", 2355.0, "Steel Plate", "3000x12000mm", None, 12.0, "Steel Plate", 2355),
        ("drw-1", pid, "PL-002", "ASTM A36", "25mm", 1963.0, "Steel Plate", "2500x10000mm", None, 10.0, "Steel Plate", 1963),
        ("drw-1", pid, "PL-008", "ASTM A572 Gr50", "25mm", 1963.0, "Steel Plate", "2500x10000mm", None, 8.0, "Steel Plate", 1570),
        ("drw-2", pid, "PL-003", "ASTM A36", "20mm", 1570.0, "Steel Plate", "2000x8000mm", None, 8.0, "Steel Plate", 1570),
        ("drw-2", pid, "PL-004", "ASTM A572 Gr50", "15mm", 1178.0, "Steel Plate", "1500x6000mm", None, 6.0, "Steel Plate", 1178),
        ("drw-4", pid, "PL-005", "ASTM A36", "35mm", 2748.0, "Steel Plate", "3500x14000mm", None, 14.0, "Steel Plate", 2748),
        ("drw-4", pid, "PL-006", "ASTM A572 Gr50", "25mm", 1963.0, "Steel Plate", "2500x10000mm", None, 10.0, "Steel Plate", 1963),
        ("drw-4", pid, "PL-009", "ASTM A36", "10mm", 785.0, "Steel Plate", "2000x10000mm", None, 10.0, "Steel Plate", 785),
        ("drw-5", pid, "PL-010", "ASTM A36", "20mm", 1570.0, "Steel Plate", "2000x8000mm", None, 8.0, "Steel Plate", 1570),
        ("drw-5", pid, "PL-011", "ASTM A36", "30mm", 2355.0, "Steel Plate", "3000x12000mm", None, 6.0, "Steel Plate", 1413),
        ("drw-6", pid, "PL-007", "ASTM A36", "20mm", 1570.0, "Steel Plate", "2000x8000mm", None, 8.0, "Steel Plate", 1570),
        # Angle Bar — per size, per grade
        ("drw-1", pid, "AB-001", "ASTM A36", "N/A", 27.3, "Angle Bar", "L150x150x15", None, 12.0, "Angle Bar", 328),
        ("drw-1", pid, "AB-002", "ASTM A36", "N/A", 18.2, "Angle Bar", "L100x100x10", None, 12.0, "Angle Bar", 218),
        ("drw-2", pid, "AB-003", "ASTM A572 Gr50", "N/A", 27.3, "Angle Bar", "L150x150x15", None, 10.0, "Angle Bar", 273),
        ("drw-3", pid, "AB-004", "ASTM A36", "N/A", 11.1, "Angle Bar", "L75x75x8", None, 12.0, "Angle Bar", 133),
        ("drw-6", pid, "AB-005", "ASTM A36", "N/A", 18.2, "Angle Bar", "L100x100x10", None, 8.0, "Angle Bar", 146),
        # FlatBar — per size, per grade
        ("drw-1", pid, "FB-001", "ASTM A36", "20mm", 31.4, "FlatBar", "FB200x20", None, 12.0, "FlatBar", 377),
        ("drw-3", pid, "FB-002", "ASTM A36", "15mm", 17.7, "FlatBar", "FB150x15", None, 12.0, "FlatBar", 212),
        ("drw-3", pid, "FB-003", "ASTM A36", "10mm", 7.85, "FlatBar", "FB100x10", None, 12.0, "FlatBar", 94),
        ("drw-5", pid, "FB-004", "ASTM A572 Gr50", "20mm", 31.4, "FlatBar", "FB200x20", None, 8.0, "FlatBar", 251),
        ("drw-6", pid, "FB-005", "ASTM A36", "15mm", 17.7, "FlatBar", "FB150x15", None, 10.0, "FlatBar", 177),
        # Bulb Plate — per size, per grade
        ("drw-1", pid, "BP-001", "ASTM A36", "N/A", 89.5, "Bulb Plate", "BP260x10", None, 12.0, "Bulb Plate", 1074),
        ("drw-2", pid, "BP-002", "ASTM A36", "N/A", 71.3, "Bulb Plate", "BP220x9", None, 10.0, "Bulb Plate", 713),
        ("drw-3", pid, "BP-003", "ASTM A572 Gr50", "N/A", 89.5, "Bulb Plate", "BP260x10", None, 8.0, "Bulb Plate", 716),
        ("drw-5", pid, "BP-004", "ASTM A36", "N/A", 71.3, "Bulb Plate", "BP220x9", None, 12.0, "Bulb Plate", 856),
        ("drw-6", pid, "BP-005", "ASTM A36", "N/A", 52.8, "Bulb Plate", "BP180x8", None, 10.0, "Bulb Plate", 528),
        # Pipe (Structural) — per OD, per thickness
        ("drw-2", pid, "PP-STR-01", "ASTM A53 GrB", "SCH40", 42.5, "Pipe", None, "168.3mm OD", 12.0, "Pipe", 510),
        ("drw-3", pid, "PP-STR-02", "ASTM A53 GrB", "SCH80", 54.7, "Pipe", None, "168.3mm OD", 10.0, "Pipe", 547),
        ("drw-6", pid, "PP-STR-03", "ASTM A53 GrB", "SCH40", 28.3, "Pipe", None, "114.3mm OD", 12.0, "Pipe", 340),

        # ===== PIPING MATERIALS =====
        # Pipe — per OD, per thickness, per material category
        ("drw-7", pid, "PP-CS-01", "API 5L X52", "SCH40", 28.5, "Pipe", None, "6\" OD", 50.0, "CS", 1425),
        ("drw-7", pid, "PP-CS-02", "API 5L X52", "SCH80", 42.0, "Pipe", None, "8\" OD", 30.0, "CS", 1260),
        ("drw-8", pid, "PP-CS-03", "API 5L X52", "SCH40", 16.8, "Pipe", None, "4\" OD", 24.0, "CS", 403),
        ("drw-8", pid, "PP-CS-04", "API 5L X52", "SCH80", 42.0, "Pipe", None, "8\" OD", 20.0, "CS", 840),
        ("drw-10", pid, "PP-CS-05", "API 5L X52", "SCH40", 28.5, "Pipe", None, "6\" OD", 22.0, "CS", 627),
        ("drw-7", pid, "PP-SS-01", "ASTM A312 TP316L", "SCH40S", 28.0, "Pipe", None, "6\" OD", 18.0, "SS", 504),
        ("drw-8", pid, "PP-SS-02", "ASTM A312 TP304L", "SCH10S", 12.5, "Pipe", None, "4\" OD", 24.0, "SS", 300),
        ("drw-11", pid, "PP-SS-03", "ASTM A312 TP316L", "SCH10S", 16.5, "Pipe", None, "3\" OD", 30.0, "SS", 495),
        ("drw-7", pid, "PP-DS-01", "ASTM A790 UNS S31803", "SCH40S", 28.5, "Pipe", None, "6\" OD", 12.0, "DSS", 342),
        ("drw-9", pid, "PP-DS-02", "ASTM A790 UNS S32750", "SCH40S", 42.0, "Pipe", None, "8\" OD", 10.0, "DSS", 420),
        ("drw-7", pid, "PP-CU-01", "ASTM B466 C70600", "SCH40", 25.8, "Pipe", None, "4\" OD", 8.0, "CUNI", 206),
        ("drw-11", pid, "PP-TI-01", "ASTM B861 Gr2", "SCH10", 10.2, "Pipe", None, "2\" OD", 6.0, "TI", 61),
        ("drw-11", pid, "PP-GR-01", "ASTM D2996", "N/A", 8.5, "Pipe", None, "4\" OD", 20.0, "GRE", 170),
        # Elbow (90° & 45°) — per OD, per thickness, per material category
        ("drw-7", pid, "EL-CS-01", "ASTM A234 WPB", "SCH40", 12.5, "Elbow", "90° LR", "6\" OD", 0.0, "CS", 50),
        ("drw-7", pid, "EL-CS-02", "ASTM A234 WPB", "SCH80", 18.0, "Elbow", "90° LR", "8\" OD", 0.0, "CS", 72),
        ("drw-8", pid, "EL-CS-03", "ASTM A234 WPB", "SCH40", 7.0, "Elbow", "90° SR", "4\" OD", 0.0, "CS", 28),
        ("drw-10", pid, "EL-CS-04", "ASTM A234 WPB", "SCH40", 12.5, "Elbow", "45° LR", "6\" OD", 0.0, "CS", 25),
        ("drw-9", pid, "EL-SS-01", "ASTM A403 WP316L", "SCH40S", 12.2, "Elbow", "90° LR", "6\" OD", 0.0, "SS", 49),
        ("drw-8", pid, "EL-SS-02", "ASTM A403 WP304L", "SCH10S", 5.5, "Elbow", "90° LR", "4\" OD", 0.0, "SS", 22),
        ("drw-9", pid, "EL-DS-01", "ASTM A815 UNS S31803", "SCH40S", 12.3, "Elbow", "90° LR", "6\" OD", 0.0, "DSS", 49),
        ("drw-7", pid, "EL-CU-01", "ASTM B466 C70600", "SCH40", 11.2, "Elbow", "90° LR", "4\" OD", 0.0, "CUNI", 45),
        # Tee (Equal & Reducing) — per OD, per material category
        ("drw-7", pid, "TE-CS-01", "ASTM A234 WPB", "SCH40", 18.5, "Tee", "Equal", "6\"x6\" OD", 0.0, "CS", 56),
        ("drw-8", pid, "TE-CS-02", "ASTM A234 WPB", "SCH40", 10.2, "Tee", "Equal", "4\"x4\" OD", 0.0, "CS", 31),
        ("drw-7", pid, "TE-CS-03", "ASTM A234 WPB", "SCH80", 27.5, "Tee", "Reducing", "8\"x6\" OD", 0.0, "CS", 55),
        ("drw-10", pid, "TE-CS-04", "ASTM A234 WPB", "SCH40", 13.8, "Tee", "Reducing", "6\"x4\" OD", 0.0, "CS", 42),
        ("drw-9", pid, "TE-SS-01", "ASTM A403 WP316L", "SCH40S", 18.0, "Tee", "Equal", "6\"x6\" OD", 0.0, "SS", 54),
        ("drw-11", pid, "TE-DS-01", "ASTM A815 UNS S31803", "SCH40S", 18.2, "Tee", "Equal", "6\"x6\" OD", 0.0, "DSS", 55),
        ("drw-8", pid, "TE-CU-01", "ASTM B466 C70600", "SCH40", 15.5, "Tee", "Reducing", "4\"x3\" OD", 0.0, "CUNI", 47),
        # Reducer (Concentric & Eccentric) — per OD, per material category
        ("drw-7", pid, "RD-CS-01", "ASTM A234 WPB", "SCH40", 8.5, "Reducer", "Conc", "8\"x6\" OD", 0.0, "CS", 26),
        ("drw-8", pid, "RD-CS-02", "ASTM A234 WPB", "SCH40", 5.8, "Reducer", "Conc", "6\"x4\" OD", 0.0, "CS", 18),
        ("drw-10", pid, "RD-CS-03", "ASTM A234 WPB", "SCH40", 3.5, "Reducer", "Ecc", "4\"x3\" OD", 0.0, "CS", 11),
        ("drw-9", pid, "RD-SS-01", "ASTM A403 WP316L", "SCH40S", 5.6, "Reducer", "Conc", "6\"x4\" OD", 0.0, "SS", 17),
        ("drw-11", pid, "RD-DS-01", "ASTM A815 UNS S31803", "SCH40S", 5.7, "Reducer", "Conc", "6\"x4\" OD", 0.0, "DSS", 17),
        # Flange (WN, RF, Blind) — per OD, per rating, per material category
        ("drw-7", pid, "FL-CS-01", "ASTM A105", "SCH40", 35.0, "Flange", "WN 150#", "8\" OD", 0.0, "CS", 105),
        ("drw-7", pid, "FL-CS-02", "ASTM A105", "SCH40", 22.5, "Flange", "WN 150#", "6\" OD", 0.0, "CS", 68),
        ("drw-8", pid, "FL-CS-03", "ASTM A105", "SCH40", 14.0, "Flange", "WN 300#", "4\" OD", 0.0, "CS", 42),
        ("drw-10", pid, "FL-CS-04", "ASTM A105", "SCH40", 35.0, "Flange", "RF 150#", "8\" OD", 0.0, "CS", 70),
        ("drw-9", pid, "FL-SS-01", "ASTM A182 F316L", "SCH40S", 22.2, "Flange", "WN 150#", "6\" OD", 0.0, "SS", 67),
        ("drw-8", pid, "FL-SS-02", "ASTM A182 F304L", "SCH10S", 13.8, "Flange", "WN 150#", "4\" OD", 0.0, "SS", 41),
        ("drw-9", pid, "FL-DS-01", "ASTM A182 F51", "SCH40S", 35.2, "Flange", "WN 300#", "8\" OD", 0.0, "DSS", 106),
        ("drw-7", pid, "FL-CU-01", "ASTM B466 C70600", "SCH40", 13.5, "Flange", "WN 150#", "4\" OD", 0.0, "CUNI", 41),
        ("drw-11", pid, "FL-TI-01", "ASTM B381 Gr2", "SCH10", 8.8, "Flange", "WN 150#", "3\" OD", 0.0, "TI", 26),
        ("drw-11", pid, "FL-GR-01", "ASTM D2996", "N/A", 10.5, "Flange", "RF 150#", "6\" OD", 0.0, "GRE", 32),
        # Weldolet — per branch size, per material category
        ("drw-7", pid, "WO-CS-01", "ASTM A105", "SCH40", 5.2, "Weldolet", "6\"x2\"", "2\" branch", 0.0, "CS", 16),
        ("drw-8", pid, "WO-CS-02", "ASTM A105", "SCH40", 3.8, "Weldolet", "4\"x1.5\"", "1.5\" branch", 0.0, "CS", 12),
        ("drw-10", pid, "WO-CS-03", "ASTM A105", "SCH80", 5.5, "Weldolet", "6\"x2\"", "2\" branch", 0.0, "CS", 17),
        ("drw-9", pid, "WO-SS-01", "ASTM A182 F316L", "SCH40S", 5.0, "Weldolet", "6\"x2\"", "2\" branch", 0.0, "SS", 15),
        ("drw-11", pid, "WO-DS-01", "ASTM A182 F51", "SCH40S", 5.1, "Weldolet", "6\"x2\"", "2\" branch", 0.0, "DSS", 15),
        # Blank / Spectacle Blind — per OD, per rating
        ("drw-7", pid, "BL-CS-01", "ASTM A516 Gr70", "N/A", 42.0, "Blank", "8\" 150#", "8\" OD", 0.0, "CS", 42),
        ("drw-8", pid, "BL-CS-02", "ASTM A516 Gr70", "N/A", 25.0, "Blank", "6\" 150#", "6\" OD", 0.0, "CS", 25),
        ("drw-10", pid, "BL-CS-03", "ASTM A516 Gr70", "N/A", 55.0, "Blank", "8\" 300#", "8\" OD", 0.0, "CS", 55),
        ("drw-9", pid, "BL-SS-01", "ASTM A240 316L", "N/A", 24.8, "Blank", "6\" 150#", "6\" OD", 0.0, "SS", 25),
        ("drw-11", pid, "BL-DS-01", "ASTM A240 UNS S31803", "N/A", 42.2, "Blank", "8\" 150#", "8\" OD", 0.0, "DSS", 42),
        # Bolt/Nuts — per size, per material
        ("drw-7", pid, "BN-CS-01", "ASTM A193 B7 / A194 2H", "N/A", 0.45, "Bolt/Nuts", "M20x100", None, 0.0, "CS", 90),
        ("drw-7", pid, "BN-CS-02", "ASTM A193 B7 / A194 2H", "N/A", 0.78, "Bolt/Nuts", "M24x120", None, 0.0, "CS", 156),
        ("drw-8", pid, "BN-CS-03", "ASTM A193 B7 / A194 2H", "N/A", 0.25, "Bolt/Nuts", "M16x90", None, 0.0, "CS", 50),
        ("drw-8", pid, "BN-CS-04", "ASTM A193 B7 / A194 2H", "N/A", 1.20, "Bolt/Nuts", "M30x150", None, 0.0, "CS", 120),
        ("drw-9", pid, "BN-SS-01", "ASTM A193 B8M / A194 8M", "N/A", 0.44, "Bolt/Nuts", "M20x100", None, 0.0, "SS", 88),
        ("drw-10", pid, "BN-SS-02", "ASTM A193 B8M / A194 8M", "N/A", 0.76, "Bolt/Nuts", "M24x120", None, 0.0, "SS", 152),
        ("drw-11", pid, "BN-TI-01", "ASTM B348 Gr2", "N/A", 0.18, "Bolt/Nuts", "M16x90", None, 0.0, "TI", 36),
        # Angle Bar (Pipe Support) — per size
        ("drw-8", pid, "AB-CS-01", "ASTM A36", "N/A", 27.3, "Angle Bar", "L150x150x15", None, 6.0, "CS", 164),
        ("drw-11", pid, "AB-CS-02", "ASTM A36", "N/A", 11.1, "Angle Bar", "L75x75x8", None, 6.0, "CS", 67),
        ("drw-10", pid, "AB-SS-01", "ASTM A276 316L", "N/A", 27.0, "Angle Bar", "L150x150x15", None, 3.0, "SS", 81),
        # Bellow (Expansion Joint) — per OD, per material
        ("drw-7", pid, "BW-CS-01", "ASTM A240 321", "N/A", 85.0, "Bellow", "Axial 8\"", "8\" OD", 0.0, "CS", 255),
        ("drw-9", pid, "BW-SS-01", "ASTM A240 316L", "N/A", 52.0, "Bellow", "Axial 6\"", "6\" OD", 0.0, "SS", 156),
        ("drw-10", pid, "BW-CS-02", "ASTM A240 321", "N/A", 35.0, "Bellow", "Axial 4\"", "4\" OD", 0.0, "CS", 105),
        ("drw-11", pid, "BW-DS-01", "ASTM A240 UNS S31803", "N/A", 53.0, "Bellow", "Axial 6\"", "6\" OD", 0.0, "DSS", 53),
    ]
    # Assign material_class and po_status for seed data
    po_statuses = ['Info-AFI', 'Structure-requested', 'PR-Raised', None]
    piping_po_statuses = ['Info-AFI', 'piping-requested', 'PR-Raised', None]
    piping_drawings = {'drw-7', 'drw-8', 'drw-9', 'drw-10', 'drw-11'}
    for i, (drw_id, pid_, pm, grade, thick, wt, mtype, sz, dia, length, cat, twt) in enumerate(materials_data):
        # Determine material_class (cycle through I, II, III)
        is_piping = drw_id in piping_drawings
        cls_idx = i % 3  # 0 → I, 1 → II, 2 → III
        suffix = ['I', 'II', 'III'][cls_idx]
        if is_piping:
            mat_class = f'pipe-class-{suffix}'
        else:
            if mtype == 'Pipe':
                mat_class = f'pipe-class-{suffix}'
            else:
                mat_class = f'Str-Pri-{suffix}'
        # Determine po_status (cycle through values)
        if is_piping:
            po_stat = piping_po_statuses[i % len(piping_po_statuses)]
        else:
            po_stat = po_statuses[i % len(po_statuses)]
        conn.execute("INSERT OR IGNORE INTO drawing_materials (material_id, drawing_id, project_id, piece_mark, material_grade, material_thickness, material_weight, material_type, size, diameter, material_length, material_category, total_weight, material_class, po_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"mat-{i+1}", drw_id, pid_, pm, grade, thick, wt, mtype, sz, dia, length, cat, twt, mat_class, po_stat))

    # Seed drawing_equipment — MECHANICAL (3), ELECTRICAL (4), HVAC (5)
    # Format: (drw_id, pid, tag, name, detail, location, wt, etype, cert, fat, test, sys_code, sys_name, del_date, inst_date, remark)
    equipment_data = [
        # ===== MECHANICAL equipment (drw-12 to drw-15) =====
        # SYS-M01: Process System
        ("drw-12", pid, "V-1001", "Process Separator Vessel", "Capacity: 5000 bbl, Upside-hook: 15T, Downside-hook: 10T", "Main Deck – Area A", 45000, "VESSEL", "ASME Sec VIII", "APPROVED", None, "SYS-M01", "Process System", "2025-08-15", "2025-10-01", "Long-lead item. FAT completed Q2 2025."),
        ("drw-12", pid, "P-2001", "Crude Oil Transfer Pump", "Capacity: 200 m³/hr, Head: 150m, Upside-hook: 5T", "Main Deck – Area A", 3200, "PUMP", "API 610", "APPROVED", None, "SYS-M01", "Process System", "2025-07-20", "2025-09-15", "Spare mechanical seal included."),
        # SYS-M02: Compression System
        ("drw-13", pid, "C-3001", "Gas Compressor Package", "Capacity: 5.2 MW, Upside-hook: 25T, Downside-hook: 15T", "Compressor Module", 58000, "COMPRESSOR", "API 618", "SUBMITTED", None, "SYS-M02", "Compression System", "2025-11-01", "2025-12-15", "Vendor: Siemens. Skid-mounted package."),
        ("drw-13", pid, "M-4001", "Compressor Drive Motor", "6.6kV, 1500 RPM, Upside-hook: 12T", "Compressor Module", 12000, "MOTOR", "IEC 60034", "PENDING", None, "SYS-M02", "Compression System", "2025-11-01", "2025-12-15", "Matched with compressor package."),
        # SYS-M03: Turret System
        ("drw-14", pid, "T-5001", "Turret Bearing Assembly", "OD: 8.5m, Upside-hook: 85T, Downside-hook: 50T", "Turret Area", 85000, "BEARING", "ASTM / DNV", "APPROVED", None, "SYS-M03", "Turret System", "2025-09-01", "2025-10-15", "Single heaviest lift. Requires 2-crane lift."),
        ("drw-14", pid, "S-6001", "Swivel Stack – 8-way", "8-way, Upside-hook: 32T", "Turret Area", 32000, "SWIVEL", "API 17D", "APPROVED", None, "SYS-M03", "Turret System", "2025-09-15", "2025-10-20", "Integrate with turret bearing."),
        # SYS-M04: Firewater System
        ("drw-15", pid, "P-7001", "Firewater Jockey Pump", "Capacity: 50 m³/hr, Head: 120m", "Firewater Station", 1800, "PUMP", "NFPA 20", "SUBMITTED", None, "SYS-M04", "Firewater System", "2025-06-30", "2025-08-15", "Diesel backup available."),
        ("drw-15", pid, "P-7002", "Firewater Main Pump – Diesel", "Capacity: 300 m³/hr, Head: 140m, Upside-hook: 8T", "Firewater Station", 5500, "PUMP", "NFPA 20", "PENDING", None, "SYS-M04", "Firewater System", "2025-07-15", "2025-08-30", "Diesel engine driven. NFPA 20 compliant."),

        # ===== ELECTRICAL equipment (drw-16 to drw-22) =====
        # SYS-E01: MV Distribution
        ("drw-16", pid, "MV-SWBD-01", "MV Switchboard 11kV", "11kV, 6300A, 50kA/3s", "Electrical Room", 8500, "SWITCHBOARD", "IEC 62271", "APPROVED", "Megger: Pass", "SYS-E01", "MV Distribution", "2025-08-01", "2025-09-10", "11kV main switchboard. ARC flash study required."),
        ("drw-16", pid, "MV-TX-01", "11kV/690V Transformer 5MVA", "11kV/690V, 5MVA, ONAN", "Electrical Room", 12000, "TRANSFORMER", "IEC 60076", "APPROVED", "Megger: Pass", "SYS-E01", "MV Distribution", "2025-08-10", "2025-09-15", "Oil-filled transformer. Bund wall required."),
        # SYS-E02: LV Distribution
        ("drw-17", pid, "LV-SWBD-01", "LV Switchboard 690V", "690V, 4000A, 65kA", "Electrical Room", 4500, "SWITCHBOARD", "IEC 61439", "SUBMITTED", "Megger: Pending", "SYS-E02", "LV Distribution", "2025-09-01", "2025-10-10", "Type-tested assembly. Form 4b construction."),
        ("drw-17", pid, "LV-MCC-01", "Motor Control Centre", "690V, 20 feeders", "Electrical Room", 3800, "MCC", "IEC 61439", "PENDING", "Loop: Pending", "SYS-E02", "LV Distribution", "2025-09-15", "2025-10-20", "20 feeders. VSD starters for 8 motors."),
        # SYS-E03: Cable Tray System
        ("drw-18", pid, "CBL-TRAY-M", "Main Cable Tray – SS316", "SS316, 600mm W, Ladder Type", "Main Deck", 25, "CABLE_TRAY", "NEMA VE-1", "SUBMITTED", None, "SYS-E03", "Cable Tray System", "2025-06-01", "2025-07-01", "Per metre weight. Total run ~800m."),
        # SYS-E04: Lighting System
        ("drw-19", pid, "LT-LED-001", "LED Lighting Fixture", "LED 40W, Ex-d, IP66", "Accommodation", 8, "LIGHTING", "IEC 60598", "SUBMITTED", None, "SYS-E04", "Lighting System", "2025-07-01", "2025-08-01", "Qty per fixture. Total 350 units."),
        ("drw-19", pid, "LT-EMG-001", "Emergency Lighting Fixture", "LED 40W, Battery Backup 3hr", "Accommodation", 10, "LIGHTING", "IEC 60598 / SOLAS", "SUBMITTED", None, "SYS-E04", "Lighting System", "2025-07-01", "2025-08-01", "SOLAS compliant. Total 80 units."),
        # SYS-E05: Earthing System
        ("drw-20", pid, "GND-ROD-01", "Earthing Rod – Copper 25mm", "Copper 25mm dia x 3m, Exothermic weld", "All Decks", 45, "EARTHING", "IEC 62561", "PENDING", None, "SYS-E05", "Earthing System", "2025-06-15", "2025-07-15", "Per rod weight. Total 200 rods."),
        # SYS-E06: E-House System
        ("drw-21", pid, "E-HOUSE-01", "E-House – Integrated", "Integrated, 12m x 6m x 4m, Upside-hook: 35T", "Topside", 35000, "E-HOUSE", "IEC 62271 / DNV", "SUBMITTED", "Megger: Pending", "SYS-E06", "E-House System", "2025-10-01", "2025-11-01", "Pre-fabricated E-House. DNV class approved."),
        ("drw-21", pid, "UPS-01", "UPS System 120kVA", "120kVA, 480V DC, Dual Redundant", "Electrical Room", 2500, "UPS", "IEC 62040", "PENDING", "Loop: Pending", "SYS-E06", "E-House System", "2025-10-15", "2025-11-15", "Dual redundant UPS modules. Battery runtime 120 min."),
        # SYS-E07: UPS/DC System
        ("drw-22", pid, "BAT-BANK-01", "Battery Bank 480V DC", "480V DC, VRLA, 200Ah", "Electrical Room", 3200, "BATTERY", "IEC 60896", "PENDING", None, "SYS-E07", "UPS/DC System", "2025-10-20", "2025-11-20", "VRLA battery bank. 10-year design life."),

        # ===== HVAC equipment (drw-23 to drw-25) =====
        # SYS-H01: Accommodation HVAC
        ("drw-23", pid, "AHU-ACCOM-01", "AHU – Accommodation 50TR", "50TR Cooling, 5000 CFM, Upside-hook: 5T", "Accommodation Block", 4500, "AHU", "ASHRAE 15", "SUBMITTED", None, "SYS-H01", "Accommodation HVAC", "2025-08-01", "2025-09-10", "DX coil type. R-513A refrigerant."),
        ("drw-23", pid, "FCU-ACCOM-01", "FCU – Cabins", "2TR, 200 CFM, Ceiling Mounted", "Accommodation Block", 120, "FCU", "ASHRAE 15", "PENDING", None, "SYS-H01", "Accommodation HVAC", "2025-08-15", "2025-09-20", "Per unit. Total 45 FCU units."),
        ("drw-23", pid, "DUCT-SS-01", "SS Ductwork – Supply", "SS316, Rect 800x400mm, Supply", "Accommodation Block", 850, "DUCTWORK", "SMACNA", "SUBMITTED", None, "SYS-H01", "Accommodation HVAC", "2025-07-15", "2025-08-15", "Per section weight. Total 120 sections."),
        # SYS-H02: Chiller System
        ("drw-24", pid, "CH-01", "Chiller Unit 200TR", "200TR, Water-Cooled, Upside-hook: 10T", "HVAC Equipment Room", 8500, "CHILLER", "ASHRAE 15 / CE", "SUBMITTED", None, "SYS-H02", "Chiller System", "2025-09-01", "2025-10-10", "Water-cooled screw chiller. R-513A."),
        ("drw-24", pid, "P-CHW-01", "Chilled Water Pump", "Capacity: 150 m³/hr, Head: 30m", "HVAC Equipment Room", 650, "PUMP", "ASHRAE / ISO", "PENDING", None, "SYS-H02", "Chiller System", "2025-09-15", "2025-10-20", "End-suction centrifugal pump."),
        # SYS-H03: Engine Room Ventilation
        ("drw-25", pid, "FAN-ER-01", "Engine Room Exhaust Fan", "Axial, 25000 CFM, Ex-d", "Engine Room", 380, "FAN", "SOLAS / ASHRAE", "SUBMITTED", None, "SYS-H03", "Engine Room Ventilation", "2025-07-01", "2025-08-01", "Ex-d rated. SOLAS compliant."),
        ("drw-25", pid, "FAN-ER-02", "Engine Room Supply Fan", "Axial, 22000 CFM", "Engine Room", 420, "FAN", "SOLAS / ASHRAE", "SUBMITTED", None, "SYS-H03", "Engine Room Ventilation", "2025-07-01", "2025-08-01", "Matched with exhaust fan for balanced ventilation."),
    ]
    for i, (drw_id, pid_, tag, name, detail, location, wt, etype, cert, fat, test, sys_code, sys_name, del_date, inst_date, remark) in enumerate(equipment_data):
        conn.execute("INSERT OR IGNORE INTO drawing_equipment (equipment_id, drawing_id, project_id, equipment_tag, equipment_name, equipment_detail, install_location, weight, equipment_type, certification, fat_status, test_status, system_code, system_name, schedule_delivery_date, schedule_install_date, remark) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"eq-{i+1}", drw_id, pid_, tag, name, detail, location, wt, etype, cert, fat, test, sys_code, sys_name, del_date, inst_date, remark))

    # Seed MTO
    for i, (did, mtype, mspec, qty, unit, uwkg) in enumerate([
        (1, "PLATE_30mm", "ASTM A36", 50000, "kg", 1),
        (1, "BEAM_H300", "ASTM A992", 30000, "kg", 1),
        (2, "PIPE_6inch_SCH40", "API 5L X52", 2000, "m", 28.5),
        (2, "PIPE_8inch_SCH80", "API 5L X52", 1500, "m", 42.0),
    ]):
        conn.execute("INSERT OR IGNORE INTO material_takeoff (mto_id, project_id, discipline_id, material_type, material_spec, quantity, unit, unit_weight_kg) VALUES (?,?,?,?,?,?,?,?)",
                     (f"mto-{i+1}", pid, did, mtype, mspec, qty, unit, uwkg))
    # Seed NDT requests — linked to AFC drawings with material piece marks
    # Format: (ndt_id, pid, drawing_id, discipline, material_class, method, weld_joint_id, joint_type, joint_len_mm, weld_len_mm, pct, status, tech)
    ndt_seed = [
        # ===== STRUCTURAL: STR-DWG-001 (drw-1, AFC) =====
        ("ndt-1", pid, "drw-1", "STRUCTURAL", "Str-Pri-I", "RT", "W-ST-001-FP", "FP", 1200, 2400, 100, "COMPLETED", "A. Rahman"),
        ("ndt-2", pid, "drw-1", "STRUCTURAL", "Str-Pri-I", "UT", "W-ST-002-FP", "FP", 800, 1600, 85, "IN_PROGRESS", "B. Santoso"),
        ("ndt-3", pid, "drw-1", "STRUCTURAL", "Str-Pri-II", "MT", "W-ST-003-FW", "FW", 0, 3500, 50, "IN_PROGRESS", "C. Wijaya"),
        # ===== STRUCTURAL: STR-DWG-002 (drw-2, AFC) =====
        ("ndt-4", pid, "drw-2", "STRUCTURAL", "Str-Pri-I", "RT", "W-ST-011-FP", "FP", 1500, 3000, 90, "IN_PROGRESS", "A. Rahman"),
        ("ndt-5", pid, "drw-2", "STRUCTURAL", "Str-Pri-II", "PT", "W-ST-012-FW", "FW", 0, 4200, 100, "COMPLETED", "D. Kusuma"),
        ("ndt-6", pid, "drw-2", "STRUCTURAL", "Str-Pri-I", "UT", "W-ST-013-FP", "FP", 600, 1200, 45, "IN_PROGRESS", "B. Santoso"),
        # ===== STRUCTURAL: STR-DWG-004 (drw-4, AFC) =====
        ("ndt-7", pid, "drw-4", "STRUCTURAL", "Str-Pri-I", "RT", "W-ST-021-FP", "FP", 2000, 4000, 30, "IN_PROGRESS", "A. Rahman"),
        ("ndt-8", pid, "drw-4", "STRUCTURAL", "Str-Pri-II", "MT", "W-ST-022-FW", "FW", 0, 2800, 0, "REQUESTED", "C. Wijaya"),
        # ===== PIPING: PIP-DWG-001 (drw-7, AFC) =====
        ("ndt-9", pid, "drw-7", "PIPING", "pipe-class-I", "RT", "W-PP-001-FP", "FP", 1800, 3600, 100, "COMPLETED", "E. Hidayat"),
        ("ndt-10", pid, "drw-7", "PIPING", "pipe-class-I", "UT", "W-PP-002-FP", "FP", 1200, 2400, 75, "IN_PROGRESS", "F. Nugroho"),
        ("ndt-11", pid, "drw-7", "PIPING", "pipe-class-II", "PT", "W-PP-003-FW", "FW", 0, 5100, 60, "IN_PROGRESS", "D. Kusuma"),
        ("ndt-12", pid, "drw-7", "PIPING", "pipe-class-II", "MT", "W-PP-004-FW", "FW", 0, 3200, 100, "COMPLETED", "C. Wijaya"),
        # ===== PIPING: PIP-DWG-004 (drw-10, AFC) =====
        ("ndt-13", pid, "drw-10", "PIPING", "pipe-class-I", "RT", "W-PP-011-FP", "FP", 900, 1800, 80, "IN_PROGRESS", "E. Hidayat"),
        ("ndt-14", pid, "drw-10", "PIPING", "pipe-class-I", "UT", "W-PP-012-FP", "FP", 600, 1200, 40, "IN_PROGRESS", "F. Nugroho"),
        ("ndt-15", pid, "drw-10", "PIPING", "pipe-class-II", "PT", "W-PP-013-FW", "FW", 0, 2400, 0, "REQUESTED", "D. Kusuma"),
        # ===== PIPING: PIP-DWG-005 (drw-11, AFC) =====
        ("ndt-16", pid, "drw-11", "PIPING", "pipe-class-I", "RT", "W-PP-021-FP", "FP", 1100, 2200, 55, "IN_PROGRESS", "E. Hidayat"),
        ("ndt-17", pid, "drw-11", "PIPING", "pipe-class-II", "MT", "W-PP-022-FW", "FW", 0, 1800, 0, "REQUESTED", "C. Wijaya"),
        ("ndt-18", pid, "drw-11", "PIPING", "pipe-class-I", "PT", "W-PP-023-FW", "FW", 0, 1600, 100, "COMPLETED", "D. Kusuma"),
    ]
    for (ndt_id, pid_, drw_id, disc, mat_cls, method, weld, jt, jlen, wlen, pct, status, tech) in ndt_seed:
        conn.execute("INSERT OR IGNORE INTO ndt_requests (ndt_id, project_id, drawing_id, discipline_name, material_class, ndt_method, weld_joint_id, joint_type, joint_length_mm, weld_length_mm, requested_date, status, percent_complete, technician_name) VALUES (?,?,?,?,?,?,?,?,?,?,date('now'),?,?,?)",
                     (ndt_id, pid_, drw_id, disc, mat_cls, method, weld, jt, jlen, wlen, status, pct, tech))
    # Seed NDT daily log
    import datetime
    today = datetime.date.today()
    ndt_log_seed = [
        # (log_id, pid, log_date, discipline, method, rfi_total, ndt_complete, daily_done, team, prev_status, remarks, updated_by)
        # STRUCTURAL
        ("ndl-1", pid, str(today - datetime.timedelta(days=3)), "STRUCTURAL", "RT", 45000, 32000, 1200, 3, "On track", "Completed main deck butt welds", "E. Hidayat"),
        ("ndl-2", pid, str(today - datetime.timedelta(days=3)), "STRUCTURAL", "UT", 28000, 15000, 800, 2, "Catching up", "UT of critical joints in progress", "F. Nugroho"),
        ("ndl-3", pid, str(today - datetime.timedelta(days=3)), "STRUCTURAL", "MT", 18000, 12000, 600, 2, "On track", "Surface inspection ongoing", "C. Wijaya"),
        ("ndl-4", pid, str(today - datetime.timedelta(days=3)), "STRUCTURAL", "PT", 15000, 8000, 400, 1, "Delayed - weather", "Need additional team tomorrow", "D. Kusuma"),
        # PIPING
        ("ndl-5", pid, str(today - datetime.timedelta(days=3)), "PIPING", "RT", 38000, 28000, 1500, 4, "On track", "Process pipe butt welds completed", "E. Hidayat"),
        ("ndl-6", pid, str(today - datetime.timedelta(days=3)), "PIPING", "UT", 22000, 12000, 900, 2, "On track", "SS pipe UT in progress", "F. Nugroho"),
        ("ndl-7", pid, str(today - datetime.timedelta(days=3)), "PIPING", "MT", 12000, 6000, 500, 2, "On track", "FW surface MT check", "C. Wijaya"),
        ("ndl-8", pid, str(today - datetime.timedelta(days=3)), "PIPING", "PT", 10000, 7000, 300, 1, "On track", "DSS pipe PT check", "D. Kusuma"),
        # Yesterday's update
        ("ndl-9", pid, str(today - datetime.timedelta(days=1)), "STRUCTURAL", "RT", 45000, 34000, 2000, 4, "Good progress", "Aft section RT done", "E. Hidayat"),
        ("ndl-10", pid, str(today - datetime.timedelta(days=1)), "STRUCTURAL", "UT", 28000, 17000, 2000, 2, "On track", "Critical joint UT passed", "F. Nugroho"),
        ("ndl-11", pid, str(today - datetime.timedelta(days=1)), "PIPING", "RT", 38000, 31000, 3000, 4, "Good progress", "Cargo pipe RT complete", "E. Hidayat"),
        ("ndl-12", pid, str(today - datetime.timedelta(days=1)), "PIPING", "UT", 22000, 14000, 2000, 3, "On track", "CUNI pipe UT in progress", "F. Nugroho"),
        # Today's plan
        ("ndl-13", pid, str(today), "STRUCTURAL", "RT", 45000, 34000, 0, 4, "Good progress - yesterday 34000/45000", "Plan: complete STR RT today", "E. Hidayat"),
        ("ndl-14", pid, str(today), "STRUCTURAL", "UT", 28000, 17000, 0, 3, "On track - yesterday 17000/28000", "Plan: finish UT by COB", "F. Nugroho"),
        ("ndl-15", pid, str(today), "PIPING", "RT", 38000, 31000, 0, 4, "Good progress - yesterday 31000/38000", "Plan: complete piping RT", "E. Hidayat"),
        ("ndl-16", pid, str(today), "PIPING", "UT", 22000, 14000, 0, 3, "On track - yesterday 14000/22000", "Plan: finish UT by COB", "F. Nugroho"),
    ]
    for (log_id, pid_, log_date, disc, method, rfi_total, ndt_complete, daily_done, team, prev_status, remarks, updated_by) in ndt_log_seed:
        conn.execute("INSERT OR IGNORE INTO ndt_daily_log (log_id, project_id, log_date, discipline_name, ndt_method, rfi_total_length_mm, ndt_complete_length_mm, daily_length_done_mm, team_deployed, previous_status, remarks, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (log_id, pid_, log_date, disc, method, rfi_total, ndt_complete, daily_done, team, prev_status, remarks, updated_by))
    # Seed weekly planning tasks
    import datetime
    ws = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())).isoformat()
    for i, (aid, ps, plp, acp) in enumerate([
        ("act-1", "Complete hull structural design review", 100, 85),
        ("act-2", "Issue piping isometrics for IFA", 80, 60),
        ("act-3", "Finalize electrical load list", 90, 90),
    ]):
        conn.execute("INSERT OR IGNORE INTO weekly_planning_tasks (task_id, project_id, week_start, activity_id, planned_status, planned_completion_percent, actual_completion_percent) VALUES (?,?,?,?,?,?,?)",
                     (f"wpt-{i+1}", pid, ws, aid, ps, plp, acp))
    # Seed resource shortages
    conn.execute("INSERT OR IGNORE INTO resource_shortages (shortage_id, project_id, shortage_type, resource_name, required_quantity, available_quantity, shortfall, impact_description) VALUES (?,?,?,?,?,?,?,?)",
                 ("sh-1", pid, "MANPOWER", "Welder", 25, 18, 7, "Delay in hull welding progress"))
    conn.execute("INSERT OR IGNORE INTO resource_shortages (shortage_id, project_id, shortage_type, resource_name, required_quantity, available_quantity, shortfall, impact_description) VALUES (?,?,?,?,?,?,?,?)",
                 ("sh-2", pid, "MATERIAL", "PIPE_6inch_SCH40", 500, 320, 180, "Waiting supplier delivery"))
    # Seed change_log entries for seed drawings and materials
    change_sql = "INSERT OR IGNORE INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name, logged_at) VALUES (?,?,?,?,?,?,?,datetime('now'))"
    disc_by_id = {1: "STRUCTURAL", 2: "PIPING", 3: "MECHANICAL", 4: "ELECTRICAL", 5: "HVAC"}
    # Build a lookup: drawing_id -> discipline_name from drawings_data
    drw_disc = {}
    for did, dn, title, dtype, rev, wkg, ifa, ifa_date, ifc, ifc_date in drawings_data:
        idx = len(drw_disc) + 1
        drw_disc[f"drw-{idx}"] = disc_by_id.get(did, "UNKNOWN")
    # Drawings
    for i, (did, dn, title, dtype, rev, wkg, ifa, ifa_date, ifc, ifc_date) in enumerate(drawings_data):
        conn.execute(change_sql, (f"clog-drw-{i+1}", pid, "drawing", f"drw-{i+1}", "create", dn, disc_by_id.get(did, "UNKNOWN")))
    # Materials
    for i, (drw_id, pid_, pm, grade, thick, wt, mtype, sz, dia, length, cat, twt) in enumerate(materials_data):
        conn.execute(change_sql, (f"clog-mat-{i+1}", pid, "material", f"mat-{i+1}", "create", pm, drw_disc.get(drw_id, "UNKNOWN")))
    conn.commit()
    conn.close()


class SQLitePool:
    """Minimal asyncpg-compatible wrapper around sqlite3 for dev."""
    def __init__(self, path):
        self.path = path

    def acquire(self):
        return SQLiteConn(self.path)

    async def close(self):
        pass


class SQLiteConn:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.conn.close()

    async def execute(self, query, params=None):
        # Translate PostgreSQL $1,$2 to SQLite ? ?
        q = query
        import re
        def replace_dollar(m):
            return "?"
        q = re.sub(r'\$\d+', '?', q)
        # Replace gen_random_uuid() with Python uuid
        q = q.replace("gen_random_uuid()", "?")
        # Replace PostgreSQL-specific functions
        q = q.replace("NOW()", "datetime('now')")
        q = q.replace("CURRENT_DATE", "date('now')")
        # Handle FILTER clause → skip for SQLite (just count all)
        if "FILTER" in q:
            # Simplify: remove FILTER clauses
            q = re.sub(r"COUNT\(\*\)\s*FILTER\s*\(WHERE\s+[^)]+\)", "COUNT(*)", q)
            q = re.sub(r"SUM\([^)]+\)\s*FILTER\s*\(WHERE\s+[^)]+\)", "SUM(1)", q)
        # Handle ON CONFLICT → UPSERT
        if "ON CONFLICT" in q and "DO UPDATE" in q:
            # Convert to INSERT OR REPLACE (simplistic)
            pass
        # NULLIF is supported by SQLite 3.x — keep as-is
        # Execute
        if params:
            # For gen_random_uuid replacement, we need to inject UUIDs
            param_list = list(params) if isinstance(params, (list, tuple)) else [params]
            if isinstance(params, dict):
                vals = {}
                for k, v in params.items():
                    vals[k] = v
                cur = self.conn.cursor()
                cur.execute(q, vals)
            else:
                cur = self.conn.cursor()
                cur.execute(q, param_list)
        else:
            cur = self.conn.cursor()
            cur.execute(q)
        self.conn.commit()
        return cur

    async def fetch(self, query, *params):
        cur = await self.execute(query, list(params) if params else None)
        return cur.fetchall()

    async def fetchrow(self, query, *params):
        cur = await self.execute(query, list(params) if params else None)
        row = cur.fetchone()
        return row

    async def fetchval(self, query, *params):
        cur = await self.execute(query, list(params) if params else None)
        row = cur.fetchone()
        return row[0] if row else None


pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    init_db()
    pool = SQLitePool(DB_PATH)
    yield
    await pool.close()


# Authentication endpoints reachable without a bearer token. /api/auth/logout
# is intentionally public (it revokes a refresh token supplied in the body).
DEV_PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/refresh", "/api/auth/logout"}
DEV_WRITE_ROLES = ("trade_lead", "project_manager", "admin")


class DevAuthMiddleware:
    """Bearer-JWT enforcement for /api/* on the standalone SQLite server.

    Mirrors the production app: 401 for missing/invalid tokens and 403 for
    mutating requests from roles below trade_lead.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if (
            method == "OPTIONS"
            or not path.startswith("/api/")
            or path in DEV_PUBLIC_API_PATHS
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        user = (
            decode_token(authorization[7:].strip())
            if authorization.lower().startswith("bearer ")
            else None
        )

        if user is None:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Not authenticated. Provide a Bearer token in the Authorization header.",
                    "code": "UNAUTHORIZED",
                    "context": None,
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        if method in {"POST", "PUT", "PATCH", "DELETE"} and user.role not in DEV_WRITE_ROLES:
            response = JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "This action requires trade_lead role or higher.",
                    "code": "forbidden",
                    "context": None,
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


app = FastAPI(title="FPSO EPC Project Control System (Dev)", version="4.0", lifespan=lifespan)
app.add_middleware(DevAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-ID"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "database": "sqlite", "mode": "development"}


def _dev_websocket_token(ws: WebSocket) -> tuple[str | None, str | None]:
    """Extract a JWT from the WS subprotocol, or ?token= outside production."""
    offered = ws.headers.get("sec-websocket-protocol", "")
    for protocol in (p.strip() for p in offered.split(",")):
        if protocol.startswith("bearer."):
            return protocol[len("bearer."):], protocol
    if settings.environment != "production":
        query_token = ws.query_params.get("token")
        if query_token:
            return query_token, None
    return None, None


@app.websocket("/ws/{project_id}")
async def websocket_endpoint(ws: WebSocket, project_id: str):
    """Authenticated WebSocket channel — mirrors main.py's contract."""
    token, subprotocol = _dev_websocket_token(ws)

    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION,
                       reason="Missing authentication token")
        return
    user = decode_token(token)
    if user is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION,
                       reason="Invalid or expired token")
        return

    # Origin validation for browser clients.
    origin = ws.headers.get("origin")
    if origin and not any(
        origin.rstrip("/") == allowed.rstrip("/") for allowed in settings.cors_origins
    ):
        if subprotocol:
            await ws.accept(subprotocol=subprotocol)
        else:
            await ws.accept()
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    # No project_members table in the SQLite dev schema: authentication (plus
    # the RBAC role carried in the token) is the access boundary here.
    await manager.connect(ws, project_id, subprotocol=subprotocol)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws, project_id)
    except Exception:
        await manager.disconnect(ws, project_id)


# ===== Engineering Routes =====
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from datetime import date
from typing import Optional
import re

eng = APIRouter(prefix="/api/engineering", tags=["engineering"])


async def get_pool():
    return pool


class DrawingCreate(BaseModel):
    drawing_number: str
    discipline_id: int
    drawing_title: Optional[str] = None
    drawing_type: Optional[str] = None
    planned_issue_date: Optional[date] = None
    revision: Optional[str] = None
    weight_kg: Optional[float] = None
    issued_for_info: str = "Yes"
    issued_for_info_date: Optional[date] = None
    issued_for_construction: str = "No"
    issued_for_construction_date: Optional[date] = None


def fix_query(q: str) -> str:
    q = re.sub(r'\$\d+', '?', q)
    q = q.replace("gen_random_uuid()", "?")
    q = q.replace("NOW()", "datetime('now')")
    q = q.replace("CURRENT_DATE", "date('now')")
    q = re.sub(r"COUNT\(\*\)\s*FILTER\s*\(WHERE\s+[^)]+\)", "COUNT(*)", q)
    return q


def uid() -> str:
    return str(uuid.uuid4())


async def log_change(conn, project_id: str, entity_type: str, entity_id: str,
                     action: str, entity_number: str = None, discipline_name: str = None):
    await conn.execute(
        "INSERT INTO change_log (log_id, project_id, entity_type, entity_id, action, entity_number, discipline_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [uid(), project_id, entity_type, entity_id, action, entity_number, discipline_name]
    )


DISCIPLINE_ID_TO_NAME = {1: "STRUCTURAL", 2: "PIPING", 3: "MECHANICAL", 4: "ELECTRICAL", 5: "HVAC"}


@eng.post("/drawings/{project_id}")
async def create_drawing(project_id: str, drawing: DrawingCreate):
    q = ("INSERT INTO drawings (drawing_id, project_id, discipline_id, drawing_number, drawing_title, drawing_type, "
         "planned_issue_date, revision, weight_kg, issued_for_info, issued_for_info_date, "
         "issued_for_construction, issued_for_construction_date) "
         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)")
    drawing_id = uid()
    disc_name = DISCIPLINE_ID_TO_NAME.get(drawing.discipline_id, "UNKNOWN")
    async with pool.acquire() as conn:
        await conn.execute(q, [drawing_id, project_id, drawing.discipline_id,
            drawing.drawing_number, drawing.drawing_title, drawing.drawing_type,
            str(drawing.planned_issue_date) if drawing.planned_issue_date else None,
            drawing.revision, drawing.weight_kg,
            drawing.issued_for_info,
            str(drawing.issued_for_info_date) if drawing.issued_for_info_date else None,
            drawing.issued_for_construction,
            str(drawing.issued_for_construction_date) if drawing.issued_for_construction_date else None])
        await log_change(conn, project_id, "drawing", drawing_id, "create", drawing.drawing_number, disc_name)
    return {"status": "created", "drawing_id": drawing_id}


@eng.delete("/drawings/{project_id}/{drawing_id}")
async def delete_drawing(project_id: str, drawing_id: str):
    async with pool.acquire() as conn:
        row = (await conn.fetch(
            "SELECT drw.drawing_number, ed.discipline_name FROM drawings drw "
            "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
            "WHERE drw.drawing_id = ? AND drw.project_id = ?",
            drawing_id, project_id
        ))
        if not row:
            return {"status": "not_found"}
        row = row[0]
        dn = row["drawing_number"]
        disc = row["discipline_name"]
        await conn.execute("DELETE FROM drawing_materials WHERE drawing_id = ?", [drawing_id])
        await conn.execute("DELETE FROM drawing_equipment WHERE drawing_id = ?", [drawing_id])
        await conn.execute("DELETE FROM material_takeoff WHERE drawing_id = ?", [drawing_id])
        await conn.execute("DELETE FROM drawings WHERE drawing_id = ? AND project_id = ?", [drawing_id, project_id])
        await log_change(conn, project_id, "drawing", drawing_id, "delete", dn, disc)
    return {"status": "deleted", "drawing_id": drawing_id}


@eng.delete("/materials/{project_id}/{material_id}")
async def delete_material(project_id: str, material_id: str):
    async with pool.acquire() as conn:
        row = (await conn.fetch(
            "SELECT dm.piece_mark, ed.discipline_name FROM drawing_materials dm "
            "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
            "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
            "WHERE dm.material_id = ? AND dm.project_id = ?",
            material_id, project_id
        ))
        if not row:
            return {"status": "not_found"}
        row = row[0]
        pm = row["piece_mark"]
        disc = row["discipline_name"]
        await conn.execute("DELETE FROM drawing_materials WHERE material_id = ? AND project_id = ?", [material_id, project_id])
        await log_change(conn, project_id, "material", material_id, "delete", pm, disc)
    return {"status": "deleted", "material_id": material_id}


@eng.get("/summary/{project_id}")
async def get_engineering_summary(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT d.discipline_id, d.discipline_name, COUNT(*) AS total_drawings, "
            "COALESCE(SUM(drw.weight_kg), 0) AS total_weight_kg, "
            "SUM(CASE WHEN drw.issued_for_info = 'Yes' THEN 1 ELSE 0 END) AS ifa_count, "
            "SUM(CASE WHEN drw.issued_for_construction = 'Yes' THEN 1 ELSE 0 END) AS ifc_count "
            "FROM drawings drw JOIN engineering_disciplines d ON drw.discipline_id = d.discipline_id "
            "WHERE drw.project_id = ? GROUP BY d.discipline_name, d.discipline_id ORDER BY d.discipline_id",
            project_id
        )
        mto_rows = await conn.fetch(
            "SELECT ed.discipline_name, COALESCE(SUM(mto.quantity * mto.unit_weight_kg), 0) AS mto_weight_kg "
            "FROM material_takeoff mto JOIN engineering_disciplines ed ON mto.discipline_id = ed.discipline_id "
            "WHERE mto.project_id = ? GROUP BY ed.discipline_name",
            project_id
        )
    drawings = []
    for r in rows:
        d = dict(r)
        total = d["total_drawings"] or 1
        d["ifa_pct"] = round(d["ifa_count"] / total * 100, 1)
        d["ifc_pct"] = round(d["ifc_count"] / total * 100, 1)
        drawings.append(d)
    return {"drawings": drawings, "mto_weights": [dict(r) for r in mto_rows]}


@eng.get("/drawings/{project_id}")
async def list_drawings(project_id: str, discipline_id: Optional[int] = None):
    query = ("SELECT drw.drawing_id, drw.drawing_number, drw.drawing_title, drw.drawing_type, "
             "drw.revision, drw.weight_kg, drw.status, "
             "drw.issued_for_info, drw.issued_for_info_date, "
             "drw.issued_for_construction, drw.issued_for_construction_date, "
             "ed.discipline_name, ed.discipline_id "
             "FROM drawings drw JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
             "WHERE drw.project_id = ?")
    params = [project_id]
    if discipline_id:
        query += " AND drw.discipline_id = ?"
        params.append(discipline_id)
    query += " ORDER BY ed.discipline_id, drw.drawing_number"
    async with pool.acquire() as conn:
        result = await conn.fetch(query, *params)
    return [dict(r) for r in result]


@eng.get("/change-summary/{project_id}")
async def get_change_summary(project_id: str):
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT entity_type, action, COUNT(*) as count "
            "FROM change_log WHERE project_id = ? "
            "GROUP BY entity_type, action",
            project_id
        )
    summary = {"drawings_added": 0, "drawings_deleted": 0, "materials_added": 0, "materials_deleted": 0}
    for r in result:
        r = dict(r)
        if r["entity_type"] == "drawing" and r["action"] == "create":
            summary["drawings_added"] = r["count"]
        elif r["entity_type"] == "drawing" and r["action"] == "delete":
            summary["drawings_deleted"] = r["count"]
        elif r["entity_type"] == "material" and r["action"] == "create":
            summary["materials_added"] = r["count"]
        elif r["entity_type"] == "material" and r["action"] == "delete":
            summary["materials_deleted"] = r["count"]
    return summary


@eng.post("/mto/{project_id}")
async def create_mto(project_id: str, data: dict):
    q = fix_query("INSERT INTO material_takeoff (mto_id, project_id, discipline_id, drawing_id, material_type, material_spec, quantity, unit, unit_weight_kg) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8)")
    async with pool.acquire() as conn:
        await conn.execute(q, [uid(), project_id, data["discipline_id"], data.get("drawing_id"), data["material_type"], data.get("material_spec"), data["quantity"], data["unit"], data.get("unit_weight_kg", 0)])
    return {"status": "created"}


@eng.get("/materials/{project_id}")
async def get_drawing_materials(project_id: str, discipline_id: Optional[int] = None, drawing_id: Optional[str] = None):
    query = ("SELECT dm.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev, "
             "drw.issued_for_info, drw.issued_for_construction, "
             "ed.discipline_name FROM drawing_materials dm "
             "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
             "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
             "WHERE dm.project_id = ?")
    params = [project_id]
    if discipline_id:
        query += " AND drw.discipline_id = ?"
        params.append(discipline_id)
    if drawing_id:
        query += " AND dm.drawing_id = ?"
        params.append(drawing_id)
    query += " ORDER BY drw.discipline_id, drw.drawing_number, dm.piece_mark"
    async with pool.acquire() as conn:
        result = await conn.fetch(query, *params)
    rows = [dict(r) for r in result]
    # Procurement planning — grouped by material_category, material_type, size, thickness, grade, material_class, po_status
    planning = []
    groups = {}
    for r in rows:
        cat = r["material_category"] or r["material_type"]
        typ = r["material_type"]
        sz = r["size"] or r["diameter"] or "-"
        thick = r["material_thickness"] or "-"
        grade = r["material_grade"] or "-"
        mat_class = r["material_class"] or "-"
        po_stat = r["po_status"] or "-"
        key = f"{cat}|{typ}|{sz}|{thick}|{grade}|{mat_class}|{po_stat}"
        if key not in groups:
            groups[key] = {
                "material_category": cat,
                "material_type": typ,
                "size": sz,
                "thickness": thick,
                "grade": grade,
                "material_class": mat_class,
                "po_status": po_stat,
                "count": 0,
                "total_length_m": 0,
                "total_weight_kg": 0,
            }
        groups[key]["count"] += 1
        groups[key]["total_length_m"] += r["material_length"] or 0
        groups[key]["total_weight_kg"] += r["total_weight"] or 0
    # Discipline-aware sorting: STRUCTURAL by category (Plate→Angle→I-BEAM), PIPING by type (Pipe→Flange→Elbow→Tee)
    str_cat_order = {"Steel Plate": 0, "Bulb Plate": 1, "Angle Bar": 2, "I-BEAM": 3, "FlatBar": 4, "Pipe": 5}
    pip_type_order = {"Pipe": 0, "Flange": 1, "Elbow": 2, "Tee": 3, "Reducer": 4, "Blank": 5, "Bellow": 6, "Bolt/Nuts": 7, "Weldolet": 8}
    mat_order = {"CS": 0, "SS": 1, "DSS": 2, "CUNI": 3, "GRE": 4, "TI": 5}
    if discipline_id == 2:
        planning = sorted(groups.values(), key=lambda x: (pip_type_order.get(x["material_type"], 99), mat_order.get(x["material_category"], 99)))
    else:
        planning = sorted(groups.values(), key=lambda x: (str_cat_order.get(x["material_category"], 99), mat_order.get(x["material_class"], 99)))
    return {
        "items": rows,
        "procurement_planning": planning,
    }


@eng.get("/equipment/{project_id}")
async def get_drawing_equipment(project_id: str, discipline_id: Optional[int] = None):
    query = ("SELECT de.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev, "
             "drw.issued_for_info, drw.issued_for_construction, "
             "ed.discipline_name FROM drawing_equipment de "
             "JOIN drawings drw ON de.drawing_id = drw.drawing_id "
             "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
             "WHERE de.project_id = ?")
    params = [project_id]
    if discipline_id:
        query += " AND drw.discipline_id = ?"
        params.append(discipline_id)
    query += " ORDER BY drw.discipline_id, drw.drawing_number, de.equipment_tag"
    async with pool.acquire() as conn:
        result = await conn.fetch(query, *params)
    rows = [dict(r) for r in result]
    # Procurement planning summary
    summary = {}
    for r in rows:
        key = r["equipment_type"]
        if key not in summary:
            summary[key] = {"equipment_type": key, "count": 0, "total_weight": 0, "fat_approved": 0}
        summary[key]["count"] += 1
        summary[key]["total_weight"] += r["weight"] or 0
        if r["fat_status"] == "APPROVED":
            summary[key]["fat_approved"] += 1
    return {
        "items": rows,
        "procurement_planning": [{"equipment_type": k, "count": v["count"], "total_weight_kg": round(v["total_weight"], 1), "fat_approved": v["fat_approved"], "fat_pending": v["count"] - v["fat_approved"]} for k, v in summary.items()]
    }


# ===== CSV Import Endpoints =====
DISCIPLINE_NAME_TO_ID = {
    "STRUCTURAL": 1, "PIPING": 2, "MECHANICAL": 3, "ELECTRICAL": 4, "HVAC": 5,
    "structure": 1, "piping": 2, "mechanical": 3, "electrical": 4, "hvac": 5,
}


@eng.post("/import-drawings/{project_id}")
async def import_drawings_csv(project_id: str, request: Request):
    """Import drawings from CSV. Columns: Drawing No, Discipline, Drawing Title, Rev, Issued for Info, Issued Date, Issued for Construction, Issued Date"""
    import csv, io
    body = await request.body()
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    imported, skipped, errors = 0, 0, []
    async with pool.acquire() as conn:
        for row_num, row in enumerate(reader, start=2):
            try:
                dn = (row.get("Drawing No") or row.get("Drawing No") or "").strip()
                if not dn:
                    skipped += 1; continue
                disc_name = (row.get("Discipline") or "").strip().upper()
                disc_id = DISCIPLINE_NAME_TO_ID.get(disc_name)
                if not disc_id:
                    errors.append(f"Row {row_num}: unknown discipline '{disc_name}'"); skipped += 1; continue
                title = (row.get("Drawing Title") or "").strip()
                rev = (row.get("Rev") or row.get("Revision") or "").strip() or None
                ifa = (row.get("Issued for Info") or "Yes").strip()
                if ifa.lower() in ("yes", "y", "1", "true"): ifa = "Yes"
                else: ifa = "No"
                ifa_date = (row.get("Issued Date") or row.get("IFA Date") or "").strip() or None
                ifc = (row.get("Issued for Construction") or "No").strip()
                if ifc.lower() in ("yes", "y", "1", "true"): ifc = "Yes"
                else: ifc = "No"
                ifc_date = (row.get("IFC Date") or row.get("Issued Date (IFC)") or "").strip() or None
                status = "IFC" if ifc == "Yes" else ("IFA" if ifa == "Yes" else "WIP")
                drw_id = uid()
                await conn.execute(
                    "INSERT OR IGNORE INTO drawings (drawing_id, project_id, discipline_id, drawing_number, drawing_title, status, revision, issued_for_info, issued_for_info_date, issued_for_construction, issued_for_construction_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [drw_id, project_id, disc_id, dn, title, status, rev, ifa, ifa_date, ifc, ifc_date])
                await log_change(conn, project_id, "drawing", drw_id, "create", dn, disc_name)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}"); skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


@eng.post("/import-materials/{project_id}")
async def import_materials_csv(project_id: str, request: Request):
    """Import materials from CSV. Columns: Drawing No, Rev, Piece Mark, Material Grade, Thickness, Material Type, Size/OD, Material Cat, Unit Wt, Length, Total Wt"""
    import csv, io
    body = await request.body()
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    imported, skipped, errors = 0, 0, []
    async with pool.acquire() as conn:
        for row_num, row in enumerate(reader, start=2):
            try:
                dn = (row.get("Drawing No") or "").strip()
                if not dn:
                    skipped += 1; continue
                # Find drawing_id from drawing_number
                result = await conn.fetch("SELECT drawing_id, discipline_id FROM drawings WHERE drawing_number = ? AND project_id = ?", dn, project_id)
                if not result:
                    errors.append(f"Row {row_num}: drawing '{dn}' not found"); skipped += 1; continue
                drawing_id = result[0]["drawing_id"]
                disc_id = result[0]["discipline_id"]
                pm = (row.get("Piece Mark") or "-").strip()
                grade = (row.get("Material Grade") or row.get("Grade") or "").strip() or None
                thick = (row.get("Thickness") or row.get("Material Thickness") or "").strip() or None
                mtype = (row.get("Material Type") or row.get("Type") or "").strip()
                sz = (row.get("Size") or "").strip() or None
                dia = (row.get("OD") or row.get("Pipe OD") or row.get("Diameter") or "").strip() or None
                mcat = (row.get("Material Cat") or row.get("Material Category") or "").strip() or None
                unit_wt = float(row.get("Unit Wt (kg/m)") or row.get("Unit Wt") or row.get("Material Weight") or 0)
                length = float(row.get("Length (m)") or row.get("Length") or 0)
                total_wt = float(row.get("Total Wt (kg)") or row.get("Total Wt") or row.get("Total Weight") or unit_wt * length)
                mat_id = uid()
                disc_name = DISCIPLINE_ID_TO_NAME.get(disc_id, "UNKNOWN")
                await conn.execute(
                    "INSERT OR IGNORE INTO drawing_materials (material_id, drawing_id, project_id, piece_mark, material_grade, material_thickness, material_weight, material_type, size, diameter, material_length, material_category, total_weight) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [mat_id, drawing_id, project_id, pm, grade, thick, unit_wt, mtype, sz, dia, length, mcat, total_wt])
                await log_change(conn, project_id, "material", mat_id, "create", pm, disc_name)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}"); skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


@eng.post("/import-equipment/{project_id}")
async def import_equipment_csv(project_id: str, request: Request):
    """Import equipment from CSV. Columns: Drawing No, Rev, Equipment Tag, Equipment Name, Equipment Detail, Install Location, Weight (kg), Equipment Type, Certification, FAT Status, Test Status, System Code, System Name, Delivery Date, Install Date, Remark"""
    import csv, io
    body = await request.body()
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    imported, skipped, errors = 0, 0, []
    async with pool.acquire() as conn:
        for row_num, row in enumerate(reader, start=2):
            try:
                dn = (row.get("Drawing No") or "").strip()
                if not dn:
                    skipped += 1; continue
                result = await conn.fetch("SELECT drawing_id FROM drawings WHERE drawing_number = ? AND project_id = ?", dn, project_id)
                if not result:
                    errors.append(f"Row {row_num}: drawing '{dn}' not found"); skipped += 1; continue
                drawing_id = result[0]["drawing_id"]
                tag = (row.get("Equipment Tag") or row.get("Equipment No") or row.get("Tag") or "").strip()
                name = (row.get("Equipment Name") or row.get("Name") or "").strip() or None
                detail = (row.get("Equipment Detail") or row.get("Detail") or "").strip() or None
                location = (row.get("Install Location") or row.get("Location") or "").strip() or None
                wt = float(row.get("Weight (kg)") or row.get("Weight") or 0)
                etype = (row.get("Equipment Type") or row.get("Type") or "").strip()
                cert = (row.get("Certification") or row.get("Equipment Certification") or row.get("Testing Report/Certs") or "").strip() or None
                fat = (row.get("FAT Status") or row.get("FAT") or "PENDING").strip().upper()
                test = (row.get("Test Status") or row.get("Mega/Loop Test") or row.get("Shop Test Status") or "").strip() or None
                sys_code = (row.get("System Code") or row.get("Sys Code") or "").strip() or None
                sys_name = (row.get("System Name") or row.get("Sys Name") or "").strip() or None
                del_date = (row.get("Delivery Date") or row.get("Shedule Deliver Date") or row.get("Schedule Delivery Date") or "").strip() or None
                inst_date = (row.get("Install Date") or row.get("Shedule Install Date") or row.get("Schedule Install Date") or "").strip() or None
                remark = (row.get("Remark") or row.get("Remarks") or "").strip() or None
                await conn.execute(
                    "INSERT OR IGNORE INTO drawing_equipment (equipment_id, drawing_id, project_id, equipment_tag, equipment_name, equipment_detail, install_location, weight, equipment_type, certification, fat_status, test_status, system_code, system_name, schedule_delivery_date, schedule_install_date, remark) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [uid(), drawing_id, project_id, tag, name, detail, location, wt, etype, cert, fat, test, sys_code, sys_name, del_date, inst_date, remark])
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}"); skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


# ===== Procurement Routes =====
proc = APIRouter(prefix="/api/procurement", tags=["procurement"])


class POItem(BaseModel):
    material_type: str
    material_spec: Optional[str] = None
    quantity_ordered: float
    unit: str
    unit_price: Optional[float] = None


class POCreate(BaseModel):
    po_number: str
    vendor_name: str
    order_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    items: list[POItem]


@proc.post("/purchase-order/{project_id}")
async def create_po(project_id: str, po_data: POCreate):
    po_id = uid()
    q = fix_query("INSERT INTO procurement_purchase_orders (po_id, project_id, po_number, vendor_name, order_date, expected_delivery_date) VALUES ($1, $2, $3, $4, $5, $6)")
    async with pool.acquire() as conn:
        await conn.execute(q, [po_id, project_id, po_data.po_number, po_data.vendor_name, str(po_data.order_date) if po_data.order_date else None, str(po_data.expected_delivery_date) if po_data.expected_delivery_date else None])
        for item in po_data.items:
            await conn.execute(fix_query("INSERT INTO purchase_items (purchase_item_id, po_id, material_type, material_spec, quantity_ordered, unit, unit_price) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6)"),
                               [uid(), po_id, item.material_type, item.material_spec, item.quantity_ordered, item.unit, item.unit_price])
    return {"po_id": po_id}


@proc.get("/purchase-orders/{project_id}")
async def list_pos(project_id: str):
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT * FROM procurement_purchase_orders WHERE project_id = ? ORDER BY order_date DESC", project_id)
    return [dict(r) for r in result]


@proc.get("/material-totals/{project_id}")
async def get_material_totals(project_id: str):
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT pi.material_type, COALESCE(SUM(pi.quantity_ordered * COALESCE(mto.unit_weight_kg, 0)), 0) AS total_weight_kg FROM purchase_items pi LEFT JOIN material_takeoff mto ON pi.material_type = mto.material_type AND pi.material_spec = mto.material_spec WHERE pi.po_id IN (SELECT po_id FROM procurement_purchase_orders WHERE project_id = ?) GROUP BY pi.material_type",
            project_id)
    return {"material_weight_totals": [dict(r) for r in result]}


@proc.patch("/material-receipt/{purchase_item_id}")
async def record_receipt(purchase_item_id: str, quantity_received: float, received_date: Optional[date] = None):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE purchase_items SET quantity_received = ?, received_date = COALESCE(?, date('now')) WHERE purchase_item_id = ?",
                           [quantity_received, str(received_date) if received_date else None, purchase_item_id])
    return {"status": "updated"}


# ===== Construction Routes =====
con = APIRouter(prefix="/api/construction", tags=["construction"])


class ManpowerRecord(BaseModel):
    project_id: str
    report_date: date
    discipline: str
    planned_headcount: int
    actual_headcount: int
    overtime_hours: Optional[float] = 0


@con.post("/daily-manpower")
async def record_manpower(data: ManpowerRecord):
    q = fix_query("INSERT INTO daily_manpower (record_id, project_id, report_date, discipline, planned_headcount, actual_headcount, overtime_hours) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6)")
    async with pool.acquire() as conn:
        try:
            await conn.execute(q, [uid(), data.project_id, str(data.report_date), data.discipline, data.planned_headcount, data.actual_headcount, data.overtime_hours])
        except Exception:
            await conn.execute("UPDATE daily_manpower SET planned_headcount=?, actual_headcount=?, overtime_hours=? WHERE project_id=? AND report_date=? AND discipline=?",
                               [data.planned_headcount, data.actual_headcount, data.overtime_hours, data.project_id, str(data.report_date), data.discipline])
    return {"status": "recorded"}


@con.get("/daily-manpower/{project_id}")
async def get_manpower(project_id: str, report_date: Optional[date] = None):
    async with pool.acquire() as conn:
        if report_date:
            result = await conn.fetch("SELECT * FROM daily_manpower WHERE project_id = ? AND report_date = ?", project_id, str(report_date))
        else:
            result = await conn.fetch("SELECT * FROM daily_manpower WHERE project_id = ? ORDER BY report_date DESC LIMIT 30", project_id)
    return [dict(r) for r in result]


@con.get("/weekly-planning/{project_id}")
async def get_weekly_planning(project_id: str, week_start: date):
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT wpt.*, a.activity_name FROM weekly_planning_tasks wpt JOIN activities a ON wpt.activity_id = a.activity_id WHERE wpt.project_id = ? AND wpt.week_start = ?",
            project_id, str(week_start))
    return [dict(r) for r in result]


@con.post("/weekly-planning")
async def create_weekly_task(data: dict):
    q = fix_query("INSERT INTO weekly_planning_tasks (task_id, project_id, week_start, activity_id, planned_status, planned_completion_percent, accountability_party) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6)")
    async with pool.acquire() as conn:
        await conn.execute(q, [uid(), data["project_id"], data["week_start"], data["activity_id"], data["planned_status"], data["planned_completion_percent"], data.get("accountability_party")])
    return {"status": "created"}


@con.patch("/weekly-planning/{task_id}")
async def update_weekly_task(task_id: str, actual_completion_percent: int, is_completed: bool = False, delay_reason: Optional[str] = None):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE weekly_planning_tasks SET actual_completion_percent = ?, is_completed = ?, delay_reason = ? WHERE task_id = ?",
                           [actual_completion_percent, 1 if is_completed else 0, delay_reason, task_id])
    return {"status": "updated"}


@con.get("/resource-shortages/{project_id}")
async def get_open_shortages(project_id: str):
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT * FROM resource_shortages WHERE project_id = ? AND status = 'OPEN' ORDER BY shortfall DESC", project_id)
    return [dict(r) for r in result]


# ===== Construction Material MVR Routes =====


@con.get("/materials/{project_id}")
async def get_construction_materials(project_id: str, discipline_id: Optional[int] = None):
    """
    Returns all materials for construction section, inherited from engineering.
    Includes MVR status, drawing status, and procurement PO status.
    For STRUCTURAL (1) and PIPING (2) disciplines, returns material records.
    For MECHANICAL (3), ELECTRICAL (4), HVAC (5), returns equipment records.
    """
    async with pool.acquire() as conn:
        # Get materials with drawing info and MVR status
        query = """
            SELECT dm.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev,
                   drw.issued_for_info, drw.issued_for_construction,
                   ed.discipline_name, ed.discipline_id
            FROM drawing_materials dm
            JOIN drawings drw ON dm.drawing_id = drw.drawing_id
            JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
            WHERE dm.project_id = ?
        """
        params = [project_id]
        if discipline_id:
            query += " AND drw.discipline_id = ?"
            params.append(discipline_id)
        query += " ORDER BY ed.discipline_id, drw.drawing_number, dm.piece_mark"
        material_rows = await conn.fetch(query, *params)

        # Get equipment with drawing info
        eq_query = """
            SELECT de.*, drw.drawing_number, drw.drawing_title, drw.revision AS drawing_rev,
                   drw.issued_for_info, drw.issued_for_construction,
                   ed.discipline_name, ed.discipline_id
            FROM drawing_equipment de
            JOIN drawings drw ON de.drawing_id = drw.drawing_id
            JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id
            WHERE de.project_id = ?
        """
        eq_params = [project_id]
        if discipline_id:
            eq_query += " AND drw.discipline_id = ?"
            eq_params.append(discipline_id)
        eq_query += " ORDER BY ed.discipline_id, drw.drawing_number, de.equipment_tag"
        equipment_rows = await conn.fetch(eq_query, *eq_params)

        # Get procurement PO status for materials (by material_id)
        po_query = """
            SELECT dm.material_id, pi.po_id, po.po_number, po.status AS po_status
            FROM drawing_materials dm
            JOIN purchase_items pi ON dm.material_type = pi.material_type
            JOIN procurement_purchase_orders po ON pi.po_id = po.po_id
            WHERE dm.project_id = ? AND po.project_id = ?
        """
        po_params = [project_id, project_id]
        po_rows = await conn.fetch(po_query, *po_params)
        po_map = {}
        for r in po_rows:
            po_map[r["material_id"]] = {
                "po_id": r["po_id"],
                "po_number": r["po_number"],
                "po_status": r["po_status"]
            }

    materials = []
    for r in material_rows:
        item = dict(r)
        mid = item["material_id"]
        if mid in po_map:
            item["po_id"] = po_map[mid]["po_id"]
            item["po_number"] = po_map[mid]["po_number"]
            item["po_status"] = po_map[mid]["po_status"]
        else:
            item["po_id"] = None
            item["po_number"] = None
            item["po_status"] = item.get("po_status") or None
        # Determine if drawing is AFC
        item["is_afc"] = item.get("issued_for_construction") == "Yes"
        item["is_afi"] = item.get("issued_for_info") == "Yes" and item.get("issued_for_construction") != "Yes"
        # Default MVR status
        if not item.get("mvr_status"):
            item["mvr_status"] = "Info-AFI"
        materials.append(item)

    equipment = []
    for r in equipment_rows:
        item = dict(r)
        item["is_afc"] = item.get("issued_for_construction") == "Yes"
        item["is_afi"] = item.get("issued_for_info") == "Yes" and item.get("issued_for_construction") != "Yes"
        equipment.append(item)

    return {
        "materials": materials,
        "equipment": equipment,
    }


@con.patch("/mvr-status/{material_id}")
async def update_mvr_status(material_id: str, data: dict):
    """
    Update MVR status for a material.
    Only allows 'MVR-confirm' if the drawing status is AFC (issued_for_construction = 'Yes').
    Body: { "mvr_status": "MVR-confirm", "confirmed_by": "trade_leader_name" }
    """
    new_status = data.get("mvr_status")
    confirmed_by = data.get("confirmed_by")
    if new_status not in ["Info-AFI", "Structure-requested", "MVR-confirm"]:
        return {"status": "error", "message": f"Invalid MVR status: {new_status}"}

    async with pool.acquire() as conn:
        # Check drawing status
        row = await conn.fetch(
            "SELECT drw.issued_for_construction, drw.issued_for_info FROM drawing_materials dm "
            "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
            "WHERE dm.material_id = ?",
            material_id
        )
        if not row:
            return {"status": "error", "message": "Material not found"}
        row = row[0]
        is_afc = row["issued_for_construction"] == "Yes"
        is_afi = row["issued_for_info"] == "Yes" and not is_afc

        # If trying to set MVR-confirm, validate AFC
        if new_status == "MVR-confirm" and not is_afc:
            return {
                "status": "error",
                "message": "Cannot confirm MVR: drawing is not AFC (Approved for Construction). Only AFC drawings can be MVR-confirmed."
            }

        # Update MVR status
        import datetime
        now = datetime.datetime.now().isoformat()
        await conn.execute(
            "UPDATE drawing_materials SET mvr_status = ?, mvr_confirmed_by = ?, mvr_confirmed_at = ? WHERE material_id = ?",
            [new_status, confirmed_by, now if new_status == "MVR-confirm" else None, material_id]
        )

    return {
        "status": "updated",
        "material_id": material_id,
        "mvr_status": new_status,
        "confirmed_by": confirmed_by,
        "confirmed_at": now if new_status == "MVR-confirm" else None,
        "warning": "AFI dwg only" if (new_status == "MVR-confirm" and is_afi) else None
    }


@con.get("/mvr-summary/{project_id}")
async def get_mvr_summary(project_id: str):
    """Returns MVR status summary per discipline."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ed.discipline_name, "
            "COUNT(dm.material_id) AS total_materials, "
            "SUM(CASE WHEN dm.mvr_status = 'Info-AFI' THEN 1 ELSE 0 END) AS info_afi_count, "
            "SUM(CASE WHEN dm.mvr_status = 'Structure-requested' THEN 1 ELSE 0 END) AS structure_requested_count, "
            "SUM(CASE WHEN dm.mvr_status = 'MVR-confirm' THEN 1 ELSE 0 END) AS mvr_confirm_count "
            "FROM drawing_materials dm "
            "JOIN drawings drw ON dm.drawing_id = drw.drawing_id "
            "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
            "WHERE dm.project_id = ? "
            "GROUP BY ed.discipline_name ORDER BY ed.discipline_id",
            project_id
        )
    return [dict(r) for r in rows]


@con.post("/resource-shortages")
async def create_shortage(data: dict):
    q = fix_query("INSERT INTO resource_shortages (shortage_id, project_id, shortage_type, resource_name, required_quantity, available_quantity, shortfall, expected_resolution_date, impact_description) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8)")
    async with pool.acquire() as conn:
        await conn.execute(q, [uid(), data["project_id"], data["shortage_type"], data["resource_name"], data["required_quantity"], data["available_quantity"], data["shortfall"], data.get("expected_resolution_date"), data.get("impact_description")])
    return {"status": "created"}


# ===== Inspection Routes =====
insp = APIRouter(prefix="/api/inspection", tags=["inspection"])


@insp.post("/ndt-request")
async def create_ndt_request(req: dict):
    q = fix_query("INSERT INTO ndt_requests (ndt_id, project_id, activity_id, ndt_method, weld_joint_id, requested_date, acceptance_criteria, technician_name) VALUES (gen_random_uuid(), $1, $2, $3, $4, COALESCE($5, date('now')), $6, $7)")
    async with pool.acquire() as conn:
        await conn.execute(q, [uid(), req["project_id"], req.get("activity_id"), req["ndt_method"], req["weld_joint_id"], str(req.get("requested_date")) if req.get("requested_date") else None, req.get("acceptance_criteria"), req.get("technician_name")])
    return {"ndt_id": "created"}


@insp.patch("/ndt-progress/{ndt_id}")
async def update_ndt_progress(ndt_id: str, percent: float, result: Optional[str] = None):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE ndt_requests SET percent_complete = ?, result = COALESCE(?, result), status = CASE WHEN ? >= 100 THEN 'COMPLETED' ELSE status END, completed_date = CASE WHEN ? >= 100 THEN date('now') ELSE completed_date END WHERE ndt_id = ?",
            [percent, result, percent, percent, ndt_id])
    return {"message": "updated"}


@insp.get("/ndt-summary/{project_id}")
async def get_ndt_summary(project_id: str):
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT ndt_method, COUNT(*) AS total, ROUND(AVG(percent_complete), 1) AS percent_complete_avg, SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed FROM ndt_requests WHERE project_id = ? GROUP BY ndt_method",
            project_id)
    return [dict(r) for r in result]


@insp.get("/ndt-requests/{project_id}")
async def list_ndt_requests(project_id: str, status: Optional[str] = None):
    q = "SELECT * FROM ndt_requests WHERE project_id = ?"; params = [project_id]
    if status:
        q += " AND status = ?"; params.append(status)
    async with pool.acquire() as conn:
        result = await conn.fetch(q, *params)
    return [dict(r) for r in result]


@insp.get("/ndt-drawing-register/{project_id}")
async def get_ndt_drawing_register(project_id: str):
    """Return AFC drawings for STRUCTURAL/PIPING that have material piece marks (NDT scope)."""
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT drw.drawing_id, drw.drawing_number, drw.drawing_title, "
            "drw.revision, drw.status, drw.issued_for_construction, drw.issued_for_construction_date, "
            "ed.discipline_name, ed.discipline_id, "
            "GROUP_CONCAT(DISTINCT dm.material_class) AS material_class, "
            "COUNT(dm.material_id) AS joint_count, "
            "COALESCE(SUM(dm.material_length), 0) AS total_length_m "
            "FROM drawings drw "
            "JOIN engineering_disciplines ed ON drw.discipline_id = ed.discipline_id "
            "JOIN drawing_materials dm ON drw.drawing_id = dm.drawing_id "
            "WHERE drw.project_id = ? "
            "AND drw.issued_for_construction = 'Yes' "
            "AND drw.discipline_id IN (1, 2) "
            "AND dm.piece_mark IS NOT NULL AND dm.piece_mark != '-' "
            "GROUP BY drw.drawing_id "
            "ORDER BY ed.discipline_id, drw.drawing_number",
            project_id)
    return [dict(r) for r in result]


@insp.get("/ndt-drawing-summary/{project_id}/{drawing_id}")
async def get_ndt_drawing_summary(project_id: str, drawing_id: str):
    """Return NDT summary for a specific drawing, grouped by ndt_method."""
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT ndt_method, COUNT(*) AS request_count, "
            "COALESCE(SUM(joint_length_mm), 0) AS total_fp_joint_mm, "
            "COALESCE(SUM(weld_length_mm), 0) AS total_weld_mm, "
            "ROUND(AVG(percent_complete), 1) AS avg_pct "
            "FROM ndt_requests "
            "WHERE project_id = ? AND drawing_id = ? "
            "GROUP BY ndt_method "
            "ORDER BY ndt_method",
            project_id, drawing_id)
    return [dict(r) for r in result]


@insp.get("/ndt-daily-log/{project_id}")
async def get_ndt_daily_log(project_id: str, log_date: Optional[str] = None):
    """Get NDT daily log entries. If log_date param provided, filter by that date. Otherwise return latest date's entries."""
    async with pool.acquire() as conn:
        if log_date:
            result = await conn.fetch(
                "SELECT * FROM ndt_daily_log WHERE project_id = ? AND log_date = ? ORDER BY discipline_name, ndt_method",
                project_id, log_date)
        else:
            result = await conn.fetch(
                "SELECT * FROM ndt_daily_log WHERE project_id = ? AND log_date = (SELECT MAX(log_date) FROM ndt_daily_log WHERE project_id = ?) ORDER BY discipline_name, ndt_method",
                project_id, project_id)
    return [dict(r) for r in result]


@insp.post("/ndt-daily-log")
async def upsert_ndt_daily_log(req: Request):
    """Create or update a daily NDT log entry. Body: {project_id, log_date, discipline_name, ndt_method, rfi_total_length_mm, ndt_complete_length_mm, daily_length_done_mm, team_deployed, previous_status, remarks, updated_by}"""
    import uuid as _uuid
    body = await req.json()
    log_id = body.get("log_id") or str(_uuid.uuid4())
    async with pool.acquire() as conn:
        existing = await conn.fetch("SELECT log_id FROM ndt_daily_log WHERE log_id = ?", log_id)
        if existing:
            await conn.execute(
                "UPDATE ndt_daily_log SET rfi_total_length_mm=?, ndt_complete_length_mm=?, daily_length_done_mm=?, team_deployed=?, previous_status=?, remarks=?, updated_by=?, updated_at=datetime('now') WHERE log_id=?",
                [body.get("rfi_total_length_mm", 0), body.get("ndt_complete_length_mm", 0), body.get("daily_length_done_mm", 0),
                 body.get("team_deployed", 0), body.get("previous_status"), body.get("remarks"), body.get("updated_by"), log_id])
        else:
            await conn.execute(
                "INSERT INTO ndt_daily_log (log_id, project_id, log_date, discipline_name, ndt_method, rfi_total_length_mm, ndt_complete_length_mm, daily_length_done_mm, team_deployed, previous_status, remarks, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [log_id, body.get("project_id"), body.get("log_date"), body.get("discipline_name"), body.get("ndt_method"),
                 body.get("rfi_total_length_mm", 0), body.get("ndt_complete_length_mm", 0), body.get("daily_length_done_mm", 0),
                 body.get("team_deployed", 0), body.get("previous_status"), body.get("remarks"), body.get("updated_by")])
    return {"log_id": log_id, "message": "saved"}


@insp.get("/ndt-progress-table/{project_id}")
async def get_ndt_progress_table(project_id: str):
    """Aggregated NDT progress: latest daily log per discipline+method with completion %."""
    async with pool.acquire() as conn:
        result = await conn.fetch(
            "SELECT ndl.* FROM ndt_daily_log ndl "
            "JOIN (SELECT discipline_name, ndt_method, MAX(log_date) AS max_date FROM ndt_daily_log WHERE project_id = ? GROUP BY discipline_name, ndt_method) latest "
            "ON ndl.discipline_name = latest.discipline_name AND ndl.ndt_method = latest.ndt_method AND ndl.log_date = latest.max_date "
            "WHERE ndl.project_id = ? "
            "ORDER BY ndl.discipline_name, ndl.ndt_method",
            project_id, project_id)
    return [dict(r) for r in result]


@insp.get("/daily-focus/{project_id}")
async def get_daily_focus(project_id: str, focus_date: date):
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT * FROM daily_inspection_focus WHERE project_id = ? AND focus_date = ?", project_id, str(focus_date))
    return [dict(r) for r in result]


@insp.post("/daily-focus")
async def create_daily_focus(data: dict):
    q = fix_query("INSERT INTO daily_inspection_focus (focus_id, project_id, focus_date, discipline, focus_point, priority) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5)")
    async with pool.acquire() as conn:
        await conn.execute(q, [uid(), data["project_id"], data["focus_date"], data["discipline"], data["focus_point"], data.get("priority", "HIGH")])
    return {"status": "created"}


@insp.patch("/daily-focus/{focus_id}")
async def complete_daily_focus(focus_id: str, achievement_notes: Optional[str] = None):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE daily_inspection_focus SET is_achieved = 1, achievement_notes = ? WHERE focus_id = ?", [achievement_notes, focus_id])
    return {"status": "completed"}


# ===== Reports Routes =====
rpt = APIRouter(prefix="/api/reports", tags=["reports"])


@rpt.get("/accountability/{project_id}")
async def accountability_report(project_id: str, week_end: date):
    from datetime import timedelta
    week_start = week_end - timedelta(days=6)
    ws = str(week_start); we = str(week_end)
    async with pool.acquire() as conn:
        tasks = await conn.fetch("SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN is_completed THEN 1 ELSE 0 END), 0) AS completed, COALESCE(AVG(actual_completion_percent), 0) AS avg_actual, COALESCE(AVG(planned_completion_percent), 0) AS avg_planned FROM weekly_planning_tasks WHERE project_id = ? AND week_start = ?", project_id, ws)
        ndt = await conn.fetch("SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END), 0) AS completed, COALESCE(AVG(percent_complete), 0) AS avg_pct FROM ndt_requests WHERE project_id = ? AND requested_date BETWEEN ? AND ?", project_id, ws, we)
        manpower = await conn.fetch("SELECT report_date, discipline, ROUND(100.0 * actual_headcount / NULLIF(planned_headcount, 0), 1) AS productivity_pct FROM daily_manpower WHERE project_id = ? AND report_date BETWEEN ? AND ?", project_id, ws, we)
        shortages = await conn.fetch("SELECT resource_name, shortfall FROM resource_shortages WHERE project_id = ? AND status = 'OPEN' ORDER BY shortfall DESC LIMIT 3", project_id)
    t = dict(tasks[0]) if tasks else {"total": 0, "completed": 0, "avg_planned": 0, "avg_actual": 0}
    n = dict(ndt[0]) if ndt else {"total": 0, "completed": 0, "avg_pct": 0}
    return {
        "week_ending": we,
        "task_summary": {"total": t["total"], "completed": t["completed"], "planned_pct": float(t["avg_planned"]), "actual_pct": float(t["avg_actual"])},
        "ndt_achievement": {"total_requests": n["total"], "completed": n["completed"], "avg_complete_pct": float(n["avg_pct"])},
        "manpower_productivity": [dict(m) for m in manpower],
        "top_shortages": [dict(s) for s in shortages],
    }


@rpt.get("/dashboard/{project_id}")
async def dashboard_summary(project_id: str):
    async with pool.acquire() as conn:
        proj = await conn.fetch("SELECT * FROM projects WHERE project_id = ?", project_id)
        act = await conn.fetch("SELECT COUNT(*) AS total, SUM(CASE WHEN is_critical THEN 1 ELSE 0 END) AS critical_count, ROUND(AVG(physical_percent_complete), 1) AS avg_progress FROM activities WHERE project_id = ?", project_id)
        alt = await conn.fetch("SELECT COUNT(*) AS open_alerts FROM schedule_alerts WHERE project_id = ? AND is_resolved = 0", project_id)
    return {
        "project": dict(proj[0]) if proj else None,
        "activities": dict(act[0]) if act else {"total": 0, "critical_count": 0, "avg_progress": 0},
        "alerts": dict(alt[0]) if alt else {"open_alerts": 0},
    }


# ===== Equipment Routes =====
eq = APIRouter(prefix="/api/equipment", tags=["equipment"])


@eq.get("/{project_id}")
async def list_equipment(project_id: str, category: Optional[str] = None):
    q = "SELECT el.* FROM equipment_list el WHERE el.project_id = ?"; params = [project_id]
    async with pool.acquire() as conn:
        result = await conn.fetch(q, *params)
        items = [dict(r) for r in result]
    approved = sum(1 for i in items if i.get("spec_status") == "APPROVED")
    return {"items": items, "total": len(items), "approved_count": approved, "conformance_pct": round(approved / len(items) * 100, 1) if items else 0}


@eq.post("/{project_id}")
async def create_equipment(project_id: str, data: dict):
    q = fix_query("INSERT INTO equipment_list (equipment_id, project_id, category_id, tag_number, equipment_name, manufacturer, model, specification_doc) VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7)")
    async with pool.acquire() as conn:
        await conn.execute(q, [uid(), project_id, data["category_id"], data["tag_number"], data["equipment_name"], data.get("manufacturer"), data.get("model"), data.get("specification_doc")])
    return {"status": "created"}


@eq.patch("/{equipment_id}/spec-status")
async def update_spec_status(equipment_id: str, status: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE equipment_list SET spec_status = ? WHERE equipment_id = ?", [status, equipment_id])
    return {"status": "updated"}


# ===== Alerts Routes =====
@app.get("/api/alerts/{project_id}")
async def get_alerts(project_id: str, severity: Optional[str] = None):
    q = "SELECT * FROM schedule_alerts WHERE project_id = ? AND is_resolved = 0"; params = [project_id]
    if severity:
        q += " AND severity = ?"; params.append(severity)
    q += " ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END"
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]


# ===== AI Routes (RAG-powered chat + status) =====
ai_router = APIRouter(prefix="/api/ai", tags=["ai"])


class AIChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


@ai_router.get("/status")
async def ai_status():
    try:
        import services.tools.query_tools  # noqa: F401 — triggers tool registration
        from services.tools.registry import tool_registry
        from services.llm_provider import llm_provider

        return {
            "enabled": True,
            "primary_provider": "deepseek" if getattr(llm_provider, 'deepseek', None) else None,
            "model": "rule_based" if not llm_provider.enabled else "deepseek+claude",
            "features": ["rag_chat", "kpi_calculation", "natural_language_query",
                        "schedule_risk_analysis", "conflict_detection", "stage_gate_assessment"],
            "available_tools": tool_registry.list_tools(),
            "database": "sqlite",
        }
    except Exception as e:
        return {"enabled": False, "error": str(e), "features": [], "available_tools": []}


@ai_router.post("/chat/{project_id}")
async def ai_chat_dev(project_id: str, request: AIChatRequest):
    """RAG-powered AI chat for development mode (SQLite)."""
    try:
        from services.langgraph.graph import run_epc_agent
        import services.tools.query_tools  # noqa: F401

        result = await run_epc_agent(
            user_query=request.query,
            project_id=project_id,
            pool=pool,
            user_id="dev-user",
        )
        return {
            "session_id": request.session_id or "dev-session",
            "query": request.query,
            "response": result.get("response", "No response generated"),
            "intent": result.get("intent", "unknown"),
            "confidence": result.get("confidence", 0.0),
            "tool_calls": result.get("tool_calls", []),
            "sources": result.get("sources", []),
            "fallback_used": result.get("fallback_used", False),
            "iterations": result.get("iterations", 0),
        }
    except Exception as e:
        return {
            "session_id": None,
            "query": request.query,
            "response": f"AI chat error: {str(e)}. Check that the project exists and has data.",
            "fallback_used": True,
            "error": str(e),
        }


class AIAnalysisRequest(BaseModel):
    analysis_type: str
    gate_id: Optional[str] = None
    week_end: Optional[str] = None


@ai_router.post("/analyze/{project_id}")
async def ai_analyze_dev(project_id: str, request: AIAnalysisRequest):
    """Run a rule-based analysis (mirrors routers/ai.py for the SQLite backend)."""
    from services import ai_engine

    if request.analysis_type == "schedule_risk":
        return await ai_engine.ai_engine.analyze_schedule_risk(project_id, pool)

    if request.analysis_type == "conflict_detection":
        conflicts = await ai_engine.ai_engine.detect_conflicts(project_id, pool)
        return {"conflicts_found": len(conflicts), "conflicts": conflicts}

    if request.analysis_type == "gate_assessment":
        if not request.gate_id:
            raise HTTPException(status_code=400,
                                detail="gate_id required for gate_assessment")
        result = await ai_engine.ai_engine.assess_stage_gate(
            project_id, request.gate_id, pool)
        if "ai_readiness_score" in result:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE stage_gates SET ai_readiness_score = ? "
                    "WHERE gate_id = ? AND project_id = ?",
                    [result["ai_readiness_score"], request.gate_id, project_id],
                )
        return result

    if request.analysis_type == "weekly_report":
        try:
            week_end = date.fromisoformat(request.week_end) if request.week_end \
                else date.today()
        except ValueError:
            raise HTTPException(status_code=400,
                                detail="week_end must be an ISO date (YYYY-MM-DD)")
        report = await ai_engine.ai_engine.compose_weekly_report(
            project_id, week_end, pool)
        return {"report": report, "week_end": week_end.isoformat()}

    raise HTTPException(status_code=400,
                        detail=f"Unknown analysis_type: {request.analysis_type}")


@ai_router.get("/insights/{project_id}")
async def get_insights_dev(project_id: str):
    return {"ai_detected_conflicts": [], "ai_assessed_feedback": [], "gate_readiness_scores": []}


# ===== Quality Routes (NCR + Welds) =====
qty = APIRouter(prefix="/api/quality", tags=["quality"])

@qty.get("/ncr/{project_id}")
async def list_ncr_dev(project_id: str, status: str = None, severity: str = None):
    q = "SELECT * FROM quality_ncr WHERE project_id = ?"
    params = [project_id]
    if status: q += " AND status = ?"; params.append(status)
    if severity: q += " AND severity = ?"; params.append(severity)
    q += " ORDER BY raised_date DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@qty.get("/ncr-summary/{project_id}")
async def ncr_summary_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT severity, status, COUNT(*) as cnt FROM quality_ncr WHERE project_id = ? GROUP BY severity, status", project_id)
    return {"by_severity": [dict(r) for r in rows]}

@qty.get("/welds/{project_id}")
async def list_welds_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM weld_tracking WHERE project_id = ?", project_id)
    return [dict(r) for r in rows]

@qty.get("/weld-summary/{project_id}")
async def weld_summary_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ndt_method, COUNT(*) as total_welds, SUM(CASE WHEN status='REJECTED' THEN 1 ELSE 0 END) as failed FROM weld_tracking WHERE project_id = ? GROUP BY ndt_method", project_id)
    return [dict(r) for r in rows]


# ===== Safety Routes =====
saf = APIRouter(prefix="/api/safety", tags=["safety"])

@saf.get("/incidents/{project_id}")
async def list_incidents_dev(project_id: str, incident_type: str = None):
    q = "SELECT * FROM safety_incidents WHERE project_id = ?"
    params = [project_id]
    if incident_type: q += " AND incident_type = ?"; params.append(incident_type)
    q += " ORDER BY incident_date DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@saf.get("/hse-stats/{project_id}")
async def hse_stats_dev(project_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as total, SUM(CASE WHEN incident_type='LTI' THEN 1 ELSE 0 END) as lti, SUM(lost_time_days) as ltd FROM safety_incidents WHERE project_id = ?", project_id)
    if row:
        return {"total_incidents": row["total"] or 0, "lti_count": row["lti"] or 0, "recordable_count": 0, "total_lost_days": row["ltd"] or 0, "trir": 0, "ltifr": 0, "safe_man_hours": 0}
    return {"total_incidents": 0, "lti_count": 0, "recordable_count": 0, "total_lost_days": 0, "trir": 0, "ltifr": 0, "safe_man_hours": 0}

@saf.get("/permits/{project_id}")
async def list_permits_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM safety_permits WHERE project_id = ?", project_id)
    return [dict(r) for r in rows]

@saf.get("/observations/{project_id}")
async def list_observations_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM safety_observations WHERE project_id = ?", project_id)
    return [dict(r) for r in rows]


# ===== Training Routes =====
trn = APIRouter(prefix="/api/training", tags=["training"])

@trn.get("/roles")
async def list_roles_dev():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM training_roles")
    return [dict(r) for r in rows]

@trn.get("/courses")
async def list_courses_dev():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM training_courses")
    return [dict(r) for r in rows]

@trn.get("/matrix/{project_id}")
async def training_matrix_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT tr.role_name, tc.course_name, COUNT(p.personnel_id) as total_personnel,
            SUM(CASE WHEN ptr.status='COMPLETED' THEN 1 ELSE 0 END) as certified_count
            FROM personnel p LEFT JOIN personnel_training ptr ON p.personnel_id=ptr.personnel_id
            LEFT JOIN training_courses tc ON ptr.course_id=tc.course_id
            LEFT JOIN training_roles tr ON p.role_id=tr.role_id
            WHERE p.project_id=? GROUP BY tr.role_name, tc.course_name""", project_id)
    return [dict(r) for r in rows]

@trn.get("/expiring-certifications/{project_id}")
async def expiring_certs_dev(project_id: str, days_ahead: int = 30):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT p.full_name, tc.course_name, ptr.expiry_date
            FROM personnel_training ptr JOIN personnel p ON ptr.personnel_id=p.personnel_id
            JOIN training_courses tc ON ptr.course_id=tc.course_id
            WHERE p.project_id=? AND ptr.expiry_date <= date('now','+' || ? || ' days')""", project_id, str(days_ahead))
    return [dict(r) for r in rows]

@trn.get("/personnel/{project_id}")
async def list_personnel_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM personnel WHERE project_id = ?", project_id)
    return [dict(r) for r in rows]


# ===== Planning Routes =====
pln = APIRouter(prefix="/api/planning", tags=["planning"])

@pln.get("/periods/{project_id}")
async def list_periods_dev(project_id: str, period_type: str = None):
    q = "SELECT * FROM planning_periods WHERE project_id = ?"
    params = [project_id]
    if period_type: q += " AND period_type = ?"; params.append(period_type)
    q += " ORDER BY period_start DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@pln.get("/board/{project_id}")
async def planning_board_dev(project_id: str, period_type: str = "WEEKLY"):
    async with pool.acquire() as conn:
        periods = await conn.fetch("SELECT * FROM planning_periods WHERE project_id=? AND period_type=? ORDER BY period_start DESC LIMIT 8", project_id, period_type)
        items = await conn.fetch("SELECT pi.*, a.activity_code, a.activity_name FROM plan_items pi JOIN activities a ON pi.activity_id=a.activity_id JOIN planning_periods pp ON pi.period_id=pp.period_id WHERE pp.project_id=? AND pp.period_type=? ORDER BY pp.period_start DESC", project_id, period_type)
    return {"periods": [dict(r) for r in periods], "items": [dict(r) for r in items], "summary": {"total_items": len(items)}}

@pln.get("/items/{project_id}")
async def list_plan_items_dev(project_id: str, period_id: str = None):
    q = "SELECT pi.* FROM plan_items pi JOIN planning_periods pp ON pi.period_id=pp.period_id WHERE pp.project_id=?"
    params = [project_id]
    if period_id: q += " AND pi.period_id = ?"; params.append(period_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@pln.post("/generate/{project_id}")
async def generate_plans_dev(project_id: str):
    return {"status": "plans generated", "created_periods": {"weekly": 16, "bi_weekly": 8, "monthly": 4, "bi_monthly": 2, "four_month": 1}}


# ===== Completion Routes =====
cmp = APIRouter(prefix="/api/completion", tags=["completion"])

@cmp.get("/sub-systems/{project_id}")
async def list_subsystems_dev(project_id: str, status: str = None):
    q = "SELECT * FROM sub_systems WHERE project_id = ?"
    params = [project_id]
    if status: q += " AND status = ?"; params.append(status)
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@cmp.get("/punch-items/{project_id}")
async def list_punch_dev(project_id: str, status: str = None):
    q = "SELECT * FROM punch_items WHERE project_id = ?"
    params = [project_id]
    if status: q += " AND status = ?"; params.append(status)
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@cmp.get("/punch-summary/{project_id}")
async def punch_summary_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT category, COUNT(*) as total, SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END) as closed FROM punch_items WHERE project_id=? GROUP BY category", project_id)
        total = await conn.fetchval("SELECT COUNT(*) FROM punch_items WHERE project_id=?", project_id)
    return {"by_category": [dict(r) for r in rows], "total": total, "total_closed": sum(r["closed"] for r in rows)}


# ===== Commissioning Routes =====
cms = APIRouter(prefix="/api/commissioning", tags=["commissioning"])

@cms.get("/summary/{project_id}")
async def commissioning_summary_dev(project_id: str):
    async with pool.acquire() as conn:
        by_type = await conn.fetch("SELECT procedure_type, COUNT(*) as total, SUM(CASE WHEN status='PASSED' THEN 1 ELSE 0 END) as passed FROM commissioning_procedures WHERE project_id=? GROUP BY procedure_type", project_id)
    return {"by_procedure_type": [dict(r) for r in by_type]}

@cms.get("/procedures/{project_id}")
async def list_procedures_dev(project_id: str, procedure_type: str = None):
    q = "SELECT * FROM commissioning_procedures WHERE project_id = ?"
    params = [project_id]
    if procedure_type: q += " AND procedure_type = ?"; params.append(procedure_type)
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@cms.get("/checklist/{procedure_id}")
async def checklist_dev(procedure_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM commissioning_checklist WHERE procedure_id = ?", procedure_id)
    return [dict(r) for r in rows]


# ===== Conflicts Routes =====
cfl = APIRouter(prefix="/api/conflicts", tags=["conflicts"])

@cfl.get("/{project_id}")
async def list_conflicts_dev(project_id: str, status: str = None, severity: str = None):
    q = "SELECT * FROM conflicts WHERE project_id = ?"
    params = [project_id]
    if status: q += " AND status = ?"; params.append(status)
    if severity: q += " AND severity = ?"; params.append(severity)
    q += " ORDER BY created_at DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@cfl.get("/summary/{project_id}")
async def conflict_summary_dev(project_id: str):
    async with pool.acquire() as conn:
        by_sev = await conn.fetch("SELECT severity, COUNT(*) as cnt FROM conflicts WHERE project_id=? GROUP BY severity", project_id)
    return {"by_severity": [dict(r) for r in by_sev]}

@cfl.get("/actions/{project_id}")
async def list_actions_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ca.* FROM conflict_actions ca JOIN conflicts c ON ca.conflict_id=c.conflict_id WHERE c.project_id=?", project_id)
    return [dict(r) for r in rows]


# ===== StageGate Routes =====
stg = APIRouter(prefix="/api/stagegate", tags=["stagegate"])

@stg.get("/{project_id}")
async def list_gates_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM stage_gates WHERE project_id=? ORDER BY gate_sequence", project_id)
    return [dict(r) for r in rows]

@stg.get("/{project_id}/{gate_id}")
async def gate_detail_dev(project_id: str, gate_id: str):
    async with pool.acquire() as conn:
        gate = await conn.fetchrow("SELECT * FROM stage_gates WHERE gate_id=? AND project_id=?", gate_id, project_id)
        checklist = await conn.fetch("SELECT * FROM stage_gate_checklist WHERE gate_id=?", gate_id)
    if not gate: return {"error": "not found"}
    return {"gate": dict(gate), "checklist": [dict(r) for r in checklist]}

@stg.post("/assess/{project_id}/{gate_id}")
async def assess_gate_dev(project_id: str, gate_id: str):
    return {"ai_readiness_score": 7.5, "recommendation": "CONDITIONAL — Address open items", "blockers": []}


# ===== Feedback Routes =====
fbk = APIRouter(prefix="/api/feedback", tags=["feedback"])

@fbk.get("/{project_id}")
async def list_feedback_dev(project_id: str, is_actioned: str = None):
    q = "SELECT * FROM feedback_loop WHERE project_id = ?"
    params = [project_id]
    if is_actioned is not None: q += " AND is_actioned = ?"; params.append(is_actioned.lower() == "true")
    async with pool.acquire() as conn:
        rows = await conn.fetch(q, *params)
    return [dict(r) for r in rows]

@fbk.get("/summary/{project_id}")
async def feedback_summary_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT source_stage, target_stage, COUNT(*) as cnt FROM feedback_loop WHERE project_id=? GROUP BY source_stage, target_stage", project_id)
    return {"by_direction": [dict(r) for r in rows]}

@fbk.get("/stale/{project_id}")
async def stale_feedback_dev(project_id: str, days_stale: int = 14):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM feedback_loop WHERE project_id=? AND is_actioned=0 AND created_at <= date('now','-' || ? || ' days')", project_id, str(days_stale))
    return [dict(r) for r in rows]


# ===== Traceability Routes =====
trc = APIRouter(prefix="/api/traceability", tags=["traceability"])

@trc.get("/matrix/{project_id}")
async def trace_matrix_dev(project_id: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""SELECT d.drawing_number, ed.discipline_name, d.status as drawing_status,
            d.issued_for_construction as ifc, COUNT(DISTINCT dm.material_id) as material_count,
            COUNT(DISTINCT de.equipment_id) as equipment_count,
            COUNT(DISTINCT nr.ndt_id) as ndt_count, COUNT(DISTINCT wt.weld_id) as weld_count,
            AVG(COALESCE(nr.percent_complete,0)) as avg_ndt_pct
            FROM drawings d JOIN engineering_disciplines ed ON d.discipline_id=ed.discipline_id
            LEFT JOIN drawing_materials dm ON d.drawing_id=dm.drawing_id
            LEFT JOIN drawing_equipment de ON d.drawing_id=de.drawing_id
            LEFT JOIN ndt_requests nr ON d.drawing_id=nr.drawing_id
            LEFT JOIN weld_tracking wt ON d.drawing_id=wt.drawing_id
            WHERE d.project_id=? GROUP BY d.drawing_id ORDER BY ed.discipline_name, d.drawing_number""", project_id)
    return [dict(r) for r in rows]

@trc.get("/forward/{project_id}/{drawing_id}")
async def forward_trace_dev(project_id: str, drawing_id: str):
    async with pool.acquire() as conn:
        drw = await conn.fetchrow("SELECT d.*, ed.discipline_name FROM drawings d JOIN engineering_disciplines ed ON d.discipline_id=ed.discipline_id WHERE d.drawing_id=? AND d.project_id=?", drawing_id, project_id)
        if not drw: return {"error": "Drawing not found"}
        mto = await conn.fetch("SELECT * FROM material_takeoff WHERE drawing_id=?", drawing_id)
        mats = await conn.fetch("SELECT * FROM drawing_materials WHERE drawing_id=?", drawing_id)
        ndt = await conn.fetch("SELECT * FROM ndt_requests WHERE drawing_id=?", drawing_id)
    return {"drawing": dict(drw), "mto_items": [dict(r) for r in mto], "materials": [dict(r) for r in mats], "ndt_requests": [dict(r) for r in ndt]}

@trc.get("/backward/{project_id}/{system_code}")
async def backward_trace_dev(project_id: str, system_code: str):
    async with pool.acquire() as conn:
        ss = await conn.fetchrow("SELECT * FROM sub_systems WHERE system_code=? AND project_id=?", system_code, project_id)
        if not ss: return {"error": "Sub-system not found"}
    return {"sub_system": dict(ss)}

@trc.get("/impact/{project_id}")
async def impact_dev(project_id: str, entity_type: str, entity_id: str):
    return {"entity_type": entity_type, "entity_id": entity_id, "total_affected_items": 0, "severity": "LOW", "affected": {}}


# ===== Auth Routes (dev mode) =====
# These mirror the production contract (real bcrypt + real JWTs) so the dev
# server exercises the same authentication path as main.py.
auth_dev = APIRouter(prefix="/api/auth", tags=["auth"])


def _sqlite_utc(minutes: int = 0, days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days, minutes=minutes)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _current_user_from_request(request: Request):
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    return decode_token(authorization[7:].strip())


async def _dev_log_auth_event(user_id, event_type: str, request: Request):
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO auth_audit_log
               (log_id, user_id, event_type, ip_address, user_agent)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                user_id,
                event_type,
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
            ),
        )


@auth_dev.post("/login")
async def login_dev(data: dict, request: Request):
    username = (data or {}).get("username")
    password = (data or {}).get("password")
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and password are required.",
        )
    if len(password) > 128:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Password too long.")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", username,
        )
    user = dict(row) if row else None

    # Constant-time-ish: always run bcrypt, even for unknown usernames.
    password_hash = user["hashed_password"] if user else DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, password_hash)
    if not user or not password_ok:
        await _dev_log_auth_event(user["user_id"] if user else None, "FAILED_LOGIN", request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {"sub": user["user_id"], "username": user["username"], "role": user["role"]}
    access_token = create_access_token(token_data)
    raw_refresh, refresh_hash = create_refresh_token(token_data)

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
               VALUES (?, ?, ?, ?)""",
            (str(uuid.uuid4()), user["user_id"], refresh_hash,
             _sqlite_utc(days=REFRESH_TOKEN_EXPIRE_DAYS)),
        )
        await conn.execute(
            "UPDATE users SET last_login = datetime('now') WHERE user_id = ?",
            (user["user_id"],),
        )

    await _dev_log_auth_event(user["user_id"], "LOGIN", request)
    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": 900,
    }


DEV_ROLES = ("admin", "project_manager", "trade_lead", "viewer")


@auth_dev.post("/register")
async def register_dev(data: dict, request: Request):
    """Register a new user. Admin only (mirrors routers/auth_router.py)."""
    caller = _current_user_from_request(request)
    if caller is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated.")
    if caller.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This action requires admin role.")

    data = data or {}
    username = data.get("username") or ""
    email = data.get("email") or ""
    password = data.get("password") or ""
    full_name = data.get("full_name")
    role = data.get("role", "viewer")

    if len(username) < 3 or len(username) > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Username must be 3-100 characters.")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Password must be at least 8 characters.")
    if "@" not in email or len(email) > 255:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Invalid email address.")
    if role not in DEV_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role. Must be one of: admin, project_manager, trade_lead, viewer.",
        )

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT user_id FROM users WHERE username = ?", username,
        )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Username already exists.")

    user_id = str(uuid.uuid4())
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO users
                   (user_id, username, email, hashed_password, full_name, role, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (user_id, username, email, hash_password(password), full_name, role),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Username or email already exists.")

    await _dev_log_auth_event(user_id, "REGISTER", request)
    return {
        "user_id": user_id,
        "username": username,
        "email": email,
        "full_name": full_name,
        "role": role,
        "is_active": True,
    }


@auth_dev.post("/refresh")
async def refresh_dev(data: dict, request: Request):
    raw_token = (data or {}).get("refresh_token")
    if not raw_token or len(raw_token) > 256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid refresh token.")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    result = None
    reuse_user_id = None

    async with pool.acquire() as conn:
        # SQLite's RETURNING cannot be combined with this pool's eager commit,
        # so claim the token with a guarded UPDATE after selecting it.
        claimed = await conn.fetchrow(
            """SELECT user_id FROM refresh_tokens
               WHERE token_hash = ? AND revoked = 0 AND expires_at > datetime('now')""",
            token_hash,
        )
        if claimed:
            await conn.execute(
                """UPDATE refresh_tokens SET revoked = 1
                   WHERE token_hash = ? AND revoked = 0""",
                token_hash,
            )
            user_row = await conn.fetchrow(
                "SELECT user_id, username, role FROM users WHERE user_id = ? AND is_active = 1",
                claimed["user_id"],
            )
            if user_row:
                token_data = {
                    "sub": user_row["user_id"],
                    "username": user_row["username"],
                    "role": user_row["role"],
                }
                access_token = create_access_token(token_data)
                raw_refresh, new_hash = create_refresh_token(token_data)
                await conn.execute(
                    """INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
                       VALUES (?, ?, ?, ?)""",
                    (str(uuid.uuid4()), user_row["user_id"], new_hash,
                     _sqlite_utc(days=REFRESH_TOKEN_EXPIRE_DAYS)),
                )
                result = (user_row["user_id"], access_token, raw_refresh)
        else:
            existing = await conn.fetchrow(
                "SELECT user_id FROM refresh_tokens WHERE token_hash = ?", token_hash,
            )
            if existing:
                reuse_user_id = existing["user_id"]
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (reuse_user_id,),
                )

    if result is None:
        if reuse_user_id:
            await _dev_log_auth_event(reuse_user_id, "REFRESH_REUSE", request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or revoked refresh token.")

    user_id, access_token, raw_refresh = result
    await _dev_log_auth_event(user_id, "REFRESH", request)
    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": 900,
    }


@auth_dev.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_dev(request: Request, data: dict | None = None):
    raw_token = (data or {}).get("refresh_token")
    user_id = None
    if raw_token and len(raw_token) <= 256:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT user_id FROM refresh_tokens WHERE token_hash = ?", token_hash,
            )
            if existing:
                user_id = existing["user_id"]
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?", (token_hash,),
                )
        if user_id:
            await _dev_log_auth_event(user_id, "LOGOUT", request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_dev.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_dev(request: Request):
    user = _current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated.")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user.user_id,),
        )
    await _dev_log_auth_event(user.user_id, "LOGOUT_ALL", request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@auth_dev.get("/me")
async def me_dev(request: Request):
    user = _current_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated.")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = ? AND is_active = 1", user.user_id,
        )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    row = dict(row)
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "email": row["email"],
        "full_name": row.get("full_name"),
        "role": row["role"],
        "is_active": bool(row["is_active"]),
    }


# Register all routers
app.include_router(eng)
app.include_router(proc)
app.include_router(con)
app.include_router(insp)
app.include_router(rpt)
app.include_router(eq)
app.include_router(ai_router)
app.include_router(auth_dev)
app.include_router(qty)
app.include_router(saf)
app.include_router(trn)
app.include_router(pln)
app.include_router(cmp)
app.include_router(cms)
app.include_router(cfl)
app.include_router(stg)
app.include_router(fbk)
app.include_router(trc)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dev_main:app", host="127.0.0.1", port=8080, reload=True)
