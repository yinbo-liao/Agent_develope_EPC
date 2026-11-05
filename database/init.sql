-- FPSO EPC Project Control System - Database Initialization
-- Version 4.0

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Projects
CREATE TABLE projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code VARCHAR(20) UNIQUE NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    client_name VARCHAR(200),
    contract_value DECIMAL(18,2),
    planned_start_date DATE NOT NULL,
    planned_finish_date DATE NOT NULL,
    baseline_start_date DATE,
    baseline_finish_date DATE,
    current_status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Schedule Activities
CREATE TABLE activities (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    activity_code VARCHAR(50) NOT NULL,
    activity_name VARCHAR(200) NOT NULL,
    original_duration INT NOT NULL,
    remaining_duration INT,
    early_start TIMESTAMP,
    early_finish TIMESTAMP,
    total_float INT,
    is_critical BOOLEAN DEFAULT FALSE,
    physical_percent_complete DECIMAL(5,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'NOT_STARTED',
    work_scope_category VARCHAR(20),
    data_date DATE,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE activity_relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predecessor_id UUID REFERENCES activities(activity_id),
    successor_id UUID REFERENCES activities(activity_id),
    relationship_type VARCHAR(2) DEFAULT 'FS',
    lag INT DEFAULT 0
);

-- Engineering Disciplines
CREATE TABLE engineering_disciplines (
    discipline_id SERIAL PRIMARY KEY,
    discipline_name VARCHAR(50) UNIQUE NOT NULL
);

INSERT INTO engineering_disciplines (discipline_name) VALUES
    ('STRUCTURAL'), ('PIPING'), ('MECHANICAL'), ('ELECTRICAL'), ('HVAC')
ON CONFLICT (discipline_name) DO NOTHING;

-- Drawings
CREATE TABLE drawings (
    drawing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    drawing_number VARCHAR(50) NOT NULL,
    drawing_title VARCHAR(200),
    drawing_type VARCHAR(30),
    status VARCHAR(30) DEFAULT 'WIP',
    planned_issue_date DATE,
    actual_issue_date DATE,
    revision VARCHAR(10),
    weight_kg DECIMAL(12,2)
);

-- Material Take-Off
CREATE TABLE material_takeoff (
    mto_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    discipline_id INT REFERENCES engineering_disciplines(discipline_id),
    drawing_id UUID REFERENCES drawings(drawing_id),
    material_type VARCHAR(100),
    material_spec VARCHAR(100),
    quantity DECIMAL(12,2),
    unit VARCHAR(20),
    unit_weight_kg DECIMAL(12,2),
    total_weight_kg DECIMAL(12,2) GENERATED ALWAYS AS (quantity * unit_weight_kg) STORED
);

-- Procurement
CREATE TABLE procurement_purchase_orders (
    po_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    po_number VARCHAR(50) UNIQUE NOT NULL,
    vendor_name VARCHAR(200),
    order_date DATE,
    expected_delivery_date DATE,
    actual_delivery_date DATE,
    total_amount DECIMAL(18,2),
    status VARCHAR(30) DEFAULT 'ORDERED'
);

CREATE TABLE purchase_items (
    purchase_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_id UUID REFERENCES procurement_purchase_orders(po_id),
    material_type VARCHAR(100),
    material_spec VARCHAR(100),
    quantity_ordered DECIMAL(12,2),
    unit VARCHAR(20),
    unit_price DECIMAL(12,2),
    quantity_received DECIMAL(12,2),
    received_date DATE
);

-- Equipment List
CREATE TABLE equipment_categories (
    cat_id SERIAL PRIMARY KEY,
    category_name VARCHAR(50) UNIQUE
);

INSERT INTO equipment_categories (category_name) VALUES
    ('MECHANICAL'), ('ELECTRICAL'), ('HVAC')
ON CONFLICT (category_name) DO NOTHING;

CREATE TABLE equipment_list (
    equipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    category_id INT REFERENCES equipment_categories(cat_id),
    tag_number VARCHAR(50) NOT NULL,
    equipment_name VARCHAR(200),
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    specification_doc VARCHAR(200),
    spec_status VARCHAR(30) DEFAULT 'SUBMITTED',
    order_date DATE,
    delivery_date DATE,
    installation_date DATE
);

-- Construction
CREATE TABLE daily_manpower (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    report_date DATE NOT NULL,
    discipline VARCHAR(50),
    planned_headcount INT,
    actual_headcount INT,
    overtime_hours DECIMAL(5,2),
    UNIQUE(project_id, report_date, discipline)
);

CREATE TABLE weekly_planning_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    week_start DATE NOT NULL,
    activity_id UUID REFERENCES activities(activity_id),
    planned_status VARCHAR(100),
    planned_completion_percent INT,
    actual_completion_percent INT,
    is_completed BOOLEAN DEFAULT FALSE,
    delay_reason TEXT,
    accountability_party VARCHAR(100)
);

CREATE TABLE resource_shortages (
    shortage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    shortage_type VARCHAR(30),
    resource_name VARCHAR(200),
    required_quantity DECIMAL(12,2),
    available_quantity DECIMAL(12,2),
    shortfall DECIMAL(12,2),
    expected_resolution_date DATE,
    impact_description TEXT,
    status VARCHAR(30) DEFAULT 'OPEN'
);

-- Inspection & NDT
CREATE TABLE inspection_requests (
    rfi_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    activity_id UUID REFERENCES activities(activity_id),
    rfi_number VARCHAR(50) UNIQUE,
    inspection_type VARCHAR(50),
    requested_date DATE,
    scheduled_date DATE,
    actual_date DATE,
    status VARCHAR(30) DEFAULT 'SUBMITTED',
    inspector_name VARCHAR(100),
    result VARCHAR(20)
);

CREATE TABLE ndt_requests (
    ndt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    activity_id UUID REFERENCES activities(activity_id),
    drawing_id UUID REFERENCES drawings(drawing_id),
    discipline_name VARCHAR(50),
    material_class VARCHAR(30),
    ndt_method VARCHAR(20),
    weld_joint_id VARCHAR(100),
    joint_type VARCHAR(10),
    joint_length_mm DECIMAL(10,1) DEFAULT 0,
    weld_length_mm DECIMAL(10,1) DEFAULT 0,
    requested_date DATE,
    completed_date DATE,
    status VARCHAR(30) DEFAULT 'REQUESTED',
    result VARCHAR(20),
    percent_complete DECIMAL(5,2) DEFAULT 0,
    acceptance_criteria VARCHAR(100),
    technician_name VARCHAR(100)
);

CREATE TABLE daily_inspection_focus (
    focus_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    focus_date DATE NOT NULL,
    discipline VARCHAR(50),
    focus_point TEXT,
    priority VARCHAR(10) DEFAULT 'HIGH',
    is_achieved BOOLEAN DEFAULT FALSE,
    achievement_notes TEXT
);

-- Alerts
CREATE TABLE schedule_alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id),
    alert_type VARCHAR(30) NOT NULL,
    activity_id UUID REFERENCES activities(activity_id),
    alert_title VARCHAR(200),
    severity VARCHAR(20) NOT NULL,
    recommended_action TEXT,
    is_resolved BOOLEAN DEFAULT FALSE
);

-- Indexes
CREATE INDEX idx_activities_project ON activities(project_id);
CREATE INDEX idx_activities_critical ON activities(project_id, is_critical);
CREATE INDEX idx_ndt_status ON ndt_requests(project_id, status);
CREATE INDEX idx_drawings_project ON drawings(project_id);
CREATE INDEX idx_drawings_discipline ON drawings(project_id, discipline_id);
CREATE INDEX idx_manpower_project_date ON daily_manpower(project_id, report_date);
CREATE INDEX idx_weekly_planning ON weekly_planning_tasks(project_id, week_start);
CREATE INDEX idx_shortages_open ON resource_shortages(project_id, status);
CREATE INDEX idx_alerts_project ON schedule_alerts(project_id, is_resolved);
CREATE INDEX idx_purchase_orders_project ON procurement_purchase_orders(project_id);
