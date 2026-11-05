from sqlalchemy import Column, String, Integer, Numeric, Date, Boolean, Text, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid


class DailyManpower(Base):
    __tablename__ = "daily_manpower"
    __table_args__ = (UniqueConstraint("project_id", "report_date", "discipline"),)
    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    report_date = Column(Date, nullable=False)
    discipline = Column(String(50))
    planned_headcount = Column(Integer)
    actual_headcount = Column(Integer)
    overtime_hours = Column(Numeric(5, 2))


class WeeklyPlanningTask(Base):
    __tablename__ = "weekly_planning_tasks"
    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    week_start = Column(Date, nullable=False)
    activity_id = Column(UUID(as_uuid=True), ForeignKey("activities.activity_id"))
    planned_status = Column(String(100))
    planned_completion_percent = Column(Integer)
    actual_completion_percent = Column(Integer)
    is_completed = Column(Boolean, default=False)
    delay_reason = Column(Text)
    accountability_party = Column(String(100))


class ResourceShortage(Base):
    __tablename__ = "resource_shortages"
    shortage_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    shortage_type = Column(String(30))
    resource_name = Column(String(200))
    required_quantity = Column(Numeric(12, 2))
    available_quantity = Column(Numeric(12, 2))
    shortfall = Column(Numeric(12, 2))
    expected_resolution_date = Column(Date)
    impact_description = Column(Text)
    status = Column(String(30), default="OPEN")
