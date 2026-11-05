from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, Boolean, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from database import Base


class Project(Base):
    __tablename__ = "projects"
    project_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_code = Column(String(20), unique=True, nullable=False)
    project_name = Column(String(200), nullable=False)
    client_name = Column(String(200))
    contract_value = Column(Numeric(18, 2))
    planned_start_date = Column(Date, nullable=False)
    planned_finish_date = Column(Date, nullable=False)
    baseline_start_date = Column(Date)
    baseline_finish_date = Column(Date)
    current_status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, server_default=func.now())


class Activity(Base):
    __tablename__ = "activities"
    activity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    activity_code = Column(String(50), nullable=False)
    activity_name = Column(String(200), nullable=False)
    original_duration = Column(Integer, nullable=False)
    remaining_duration = Column(Integer)
    early_start = Column(DateTime)
    early_finish = Column(DateTime)
    total_float = Column(Integer)
    is_critical = Column(Boolean, default=False)
    physical_percent_complete = Column(Numeric(5, 2), default=0)
    status = Column(String(20), default="NOT_STARTED")
    work_scope_category = Column(String(20))
    data_date = Column(Date)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ActivityRelationship(Base):
    __tablename__ = "activity_relationships"
    relationship_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    predecessor_id = Column(UUID(as_uuid=True), ForeignKey("activities.activity_id"))
    successor_id = Column(UUID(as_uuid=True), ForeignKey("activities.activity_id"))
    relationship_type = Column(String(2), default="FS")
    lag = Column(Integer, default=0)
