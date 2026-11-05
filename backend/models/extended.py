"""Extended schema ORM models — completion, commissioning, quality, safety, training, planning, conflicts, stage-gate, feedback, traceability."""

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, ForeignKey, Date, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from database import Base


# ═══════════════════════════════════════════════════════════════════════
# Completion Models
# ═══════════════════════════════════════════════════════════════════════

class SubSystem(Base):
    __tablename__ = "sub_systems"
    sub_system_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    system_code = Column(String(50), nullable=False, unique=True)
    system_name = Column(String(200))
    discipline_id = Column(Integer)
    status = Column(String(30), default="NOT_STARTED")
    planned_completion_date = Column(Date)
    actual_completion_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PunchItem(Base):
    __tablename__ = "punch_items"
    punch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    sub_system_id = Column(UUID(as_uuid=True), ForeignKey("sub_systems.sub_system_id"))
    punch_number = Column(String(50), unique=True)
    description = Column(Text)
    severity = Column(String(20), default="B")
    status = Column(String(30), default="OPEN")
    assigned_to = Column(String(200))
    due_date = Column(Date)
    closed_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════
# Commissioning Models
# ═══════════════════════════════════════════════════════════════════════

class CommissioningProcedure(Base):
    __tablename__ = "commissioning_procedures"
    procedure_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    sub_system_id = Column(UUID(as_uuid=True), ForeignKey("sub_systems.sub_system_id"))
    procedure_number = Column(String(50), unique=True)
    procedure_name = Column(String(200))
    procedure_type = Column(String(50))
    status = Column(String(30), default="PENDING")
    planned_date = Column(Date)
    actual_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CommissioningChecklist(Base):
    __tablename__ = "commissioning_checklist"
    checklist_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    procedure_id = Column(UUID(as_uuid=True), ForeignKey("commissioning_procedures.procedure_id"))
    item_number = Column(Integer)
    description = Column(Text)
    is_complete = Column(Boolean, default=False)
    result = Column(String(50))
    comment = Column(Text)


# ═══════════════════════════════════════════════════════════════════════
# Quality / NCR Models
# ═══════════════════════════════════════════════════════════════════════

class QualityNCR(Base):
    __tablename__ = "quality_ncr"
    ncr_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    ncr_number = Column(String(50), unique=True)
    description = Column(Text)
    severity = Column(String(20), default="MINOR")
    discipline = Column(String(50))
    status = Column(String(30), default="OPEN")
    reported_by = Column(String(200))
    reported_date = Column(Date)
    closed_date = Column(Date)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WeldTracking(Base):
    __tablename__ = "weld_tracking"
    weld_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    drawing_id = Column(UUID(as_uuid=True))
    weld_number = Column(String(100))
    ndt_method = Column(String(20))
    joint_type = Column(String(10))
    status = Column(String(30), default="PENDING")
    result = Column(String(20))
    rejection_reason = Column(Text)
    inspected_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════
# Safety / HSE Models
# ═══════════════════════════════════════════════════════════════════════

class SafetyIncident(Base):
    __tablename__ = "safety_incidents"
    incident_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    incident_number = Column(String(50), unique=True)
    incident_type = Column(String(20))  # LTI, MTI, FA, NEAR_MISS
    description = Column(Text)
    incident_date = Column(Date)
    incident_time = Column(String(10))
    location = Column(String(200))
    severity = Column(String(20))
    investigation_status = Column(String(30), default="OPEN")
    root_cause = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SafetyPermit(Base):
    __tablename__ = "safety_permits"
    permit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    permit_number = Column(String(50), unique=True)
    permit_type = Column(String(30))
    work_description = Column(Text)
    issued_date = Column(Date)
    expiry_date = Column(Date)
    status = Column(String(20), default="ACTIVE")
    issued_by = Column(String(200))

class SafetyObservation(Base):
    __tablename__ = "safety_observations"
    observation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    observation_type = Column(String(30))
    description = Column(Text)
    location = Column(String(200))
    observed_date = Column(Date)
    reported_by = Column(String(200))
    status = Column(String(20), default="OPEN")


# ═══════════════════════════════════════════════════════════════════════
# Training Models
# ═══════════════════════════════════════════════════════════════════════

class TrainingRole(Base):
    __tablename__ = "training_roles"
    role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    role_name = Column(String(100), nullable=False)
    description = Column(Text)

class TrainingCourse(Base):
    __tablename__ = "training_courses"
    course_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    course_name = Column(String(200), nullable=False)
    course_code = Column(String(50))
    validity_months = Column(Integer)
    provider = Column(String(200))

class TrainingRoleRequirement(Base):
    __tablename__ = "training_role_requirements"
    requirement_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id = Column(UUID(as_uuid=True), ForeignKey("training_roles.role_id"))
    course_id = Column(UUID(as_uuid=True), ForeignKey("training_courses.course_id"))
    is_mandatory = Column(Boolean, default=True)

class Personnel(Base):
    __tablename__ = "personnel"
    person_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    badge_number = Column(String(50), unique=True)
    full_name = Column(String(200), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("training_roles.role_id"))
    trade = Column(String(50))
    date_joined = Column(Date)

class PersonnelTraining(Base):
    __tablename__ = "personnel_training"
    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("personnel.person_id"))
    course_id = Column(UUID(as_uuid=True), ForeignKey("training_courses.course_id"))
    completion_date = Column(Date)
    expiry_date = Column(Date)
    certificate_number = Column(String(100))
    status = Column(String(20), default="VALID")


# ═══════════════════════════════════════════════════════════════════════
# Planning Models
# ═══════════════════════════════════════════════════════════════════════

class PlanningPeriod(Base):
    __tablename__ = "planning_periods"
    period_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    period_name = Column(String(200))
    period_type = Column(String(20))  # WEEKLY, BI_WEEKLY, MONTHLY, BI_MONTHLY, FOUR_MONTH
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    item_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PlanItem(Base):
    __tablename__ = "plan_items"
    item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_id = Column(UUID(as_uuid=True), ForeignKey("planning_periods.period_id"))
    project_id = Column(UUID(as_uuid=True), nullable=False)
    description = Column(Text)
    planned_pct = Column(Float, default=0)
    actual_pct = Column(Float, default=0)
    status = Column(String(30), default="PENDING")
    responsible = Column(String(200))


# ═══════════════════════════════════════════════════════════════════════
# Conflict Resolution Models
# ═══════════════════════════════════════════════════════════════════════

class Conflict(Base):
    __tablename__ = "conflicts"
    conflict_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    conflict_type = Column(String(30))
    title = Column(String(200))
    description = Column(Text)
    severity = Column(String(20))
    source_entity = Column(String(200))
    target_entity = Column(String(200))
    status = Column(String(30), default="OPEN")
    detected_by_ai = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ConflictAction(Base):
    __tablename__ = "conflict_actions"
    action_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conflict_id = Column(UUID(as_uuid=True), ForeignKey("conflicts.conflict_id"))
    action_description = Column(Text)
    assigned_to = Column(String(200))
    due_date = Column(Date)
    status = Column(String(30), default="PENDING")
    completed_date = Column(Date)


# ═══════════════════════════════════════════════════════════════════════
# Stage-Gate Models
# ═══════════════════════════════════════════════════════════════════════

class StageGate(Base):
    __tablename__ = "stage_gates"
    gate_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    gate_name = Column(String(100), nullable=False)
    from_phase = Column(String(50))
    to_phase = Column(String(50))
    status = Column(String(30), default="PENDING")
    ai_readiness_score = Column(Float)
    planned_date = Column(Date)
    actual_date = Column(Date)
    assessment_summary = Column(Text)

class StageGateChecklist(Base):
    __tablename__ = "stage_gate_checklist"
    checklist_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gate_id = Column(UUID(as_uuid=True), ForeignKey("stage_gates.gate_id"))
    item_number = Column(Integer)
    description = Column(Text)
    is_complete = Column(Boolean, default=False)
    evidence_link = Column(String(500))


# ═══════════════════════════════════════════════════════════════════════
# Feedback Loop Models
# ═══════════════════════════════════════════════════════════════════════

class FeedbackLoop(Base):
    __tablename__ = "feedback_loop"
    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    source_entity = Column(String(200))
    feedback_type = Column(String(50))
    description = Column(Text)
    severity = Column(String(20))
    status = Column(String(30), default="OPEN")
    submitted_by = Column(String(200))
    submitted_date = Column(Date)
    resolved_date = Column(Date)
    resolution_notes = Column(Text)


# ═══════════════════════════════════════════════════════════════════════
# Traceability / Change Log Models
# ═══════════════════════════════════════════════════════════════════════

class ChangeLog(Base):
    __tablename__ = "change_log"
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    entity_type = Column(String(20), nullable=False)  # drawing, material
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(20), nullable=False)  # create, delete
    entity_number = Column(String(50))
    discipline_name = Column(String(50))
    logged_at = Column(DateTime(timezone=True), server_default=func.now())

class DrawingMaterial(Base):
    __tablename__ = "drawing_materials"
    material_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.drawing_id"))
    project_id = Column(UUID(as_uuid=True), nullable=False)
    piece_mark = Column(String(50), default="-")
    material_grade = Column(String(100))
    material_thickness = Column(String(50))
    material_weight = Column(Float)
    material_type = Column(String(100))
    size = Column(String(50))
    diameter = Column(String(50))
    material_length = Column(Float)
    material_category = Column(String(50))
    total_weight = Column(Float)
    material_class = Column(String(50))
    po_status = Column(String(50))
    mvr_status = Column(String(30), default="Info-AFI")
    mvr_confirmed_by = Column(String(200))
    mvr_confirmed_at = Column(DateTime(timezone=True))

class DrawingEquipment(Base):
    __tablename__ = "drawing_equipment"
    equipment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.drawing_id"))
    project_id = Column(UUID(as_uuid=True), nullable=False)
    equipment_tag = Column(String(100))
    equipment_name = Column(String(200))
    equipment_detail = Column(Text)
    install_location = Column(String(200))
    weight = Column(Float)
    equipment_type = Column(String(100))
    certification = Column(String(200))
    fat_status = Column(String(30), default="PENDING")
    test_status = Column(String(50))
    system_code = Column(String(50))
    system_name = Column(String(200))
    schedule_delivery_date = Column(Date)
    schedule_install_date = Column(Date)
    remark = Column(Text)


# ═══════════════════════════════════════════════════════════════════════
# NDT Daily Log
# ═══════════════════════════════════════════════════════════════════════

class NDTDailyLog(Base):
    __tablename__ = "ndt_daily_log"
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    log_date = Column(Date, nullable=False)
    discipline_name = Column(String(50), nullable=False)
    ndt_method = Column(String(20), nullable=False)
    rfi_total_length_mm = Column(Float, default=0)
    ndt_complete_length_mm = Column(Float, default=0)
    daily_length_done_mm = Column(Float, default=0)
    team_deployed = Column(Integer, default=0)
    previous_status = Column(Text)
    remarks = Column(Text)
    updated_by = Column(String(200))
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


# Composite Indexes
Index("idx_conflicts_project_status", Conflict.project_id, Conflict.status)
Index("idx_ncr_project_severity", QualityNCR.project_id, QualityNCR.severity)
Index("idx_incidents_project_date", SafetyIncident.project_id, SafetyIncident.incident_date)
Index("idx_drawing_materials_drawing", DrawingMaterial.drawing_id)
Index("idx_drawing_equipment_drawing", DrawingEquipment.drawing_id)
Index("idx_change_log_project_type", ChangeLog.project_id, ChangeLog.entity_type)
