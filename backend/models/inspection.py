from sqlalchemy import Column, String, Integer, Numeric, Date, Boolean, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid


class InspectionRequest(Base):
    __tablename__ = "inspection_requests"
    rfi_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    activity_id = Column(UUID(as_uuid=True), ForeignKey("activities.activity_id"))
    rfi_number = Column(String(50), unique=True)
    inspection_type = Column(String(50))
    requested_date = Column(Date)
    scheduled_date = Column(Date)
    actual_date = Column(Date)
    status = Column(String(30), default="SUBMITTED")
    inspector_name = Column(String(100))
    result = Column(String(20))


class NDTRequest(Base):
    __tablename__ = "ndt_requests"
    ndt_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    activity_id = Column(UUID(as_uuid=True), ForeignKey("activities.activity_id"))
    ndt_method = Column(String(20))
    weld_joint_id = Column(String(100))
    requested_date = Column(Date)
    completed_date = Column(Date)
    status = Column(String(30), default="REQUESTED")
    result = Column(String(20))
    percent_complete = Column(Numeric(5, 2), default=0)
    acceptance_criteria = Column(String(100))
    technician_name = Column(String(100))


class DailyInspectionFocus(Base):
    __tablename__ = "daily_inspection_focus"
    focus_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    focus_date = Column(Date, nullable=False)
    discipline = Column(String(50))
    focus_point = Column(Text)
    priority = Column(String(10), default="HIGH")
    is_achieved = Column(Boolean, default=False)
    achievement_notes = Column(Text)
