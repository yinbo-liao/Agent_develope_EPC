from sqlalchemy import Column, String, Boolean, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid


class ScheduleAlert(Base):
    __tablename__ = "schedule_alerts"
    alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    alert_type = Column(String(30), nullable=False)
    activity_id = Column(UUID(as_uuid=True), ForeignKey("activities.activity_id"))
    alert_title = Column(String(200))
    severity = Column(String(20), nullable=False)
    recommended_action = Column(Text)
    is_resolved = Column(Boolean, default=False)
