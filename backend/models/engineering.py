from sqlalchemy import Column, String, Integer, Numeric, Date, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid


class EngineeringDiscipline(Base):
    __tablename__ = "engineering_disciplines"
    discipline_id = Column(Integer, primary_key=True, autoincrement=True)
    discipline_name = Column(String(50), unique=True, nullable=False)

    drawings = relationship("Drawing", back_populates="discipline")
    mto_items = relationship("MaterialTakeoff", back_populates="discipline")


class Drawing(Base):
    __tablename__ = "drawings"
    drawing_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    discipline_id = Column(Integer, ForeignKey("engineering_disciplines.discipline_id"))
    drawing_number = Column(String(50), nullable=False)
    drawing_title = Column(String(200))
    drawing_type = Column(String(30))
    status = Column(String(30), default="WIP")
    planned_issue_date = Column(Date)
    actual_issue_date = Column(Date)
    revision = Column(String(10))
    weight_kg = Column(Numeric(12, 2))

    discipline = relationship("EngineeringDiscipline", back_populates="drawings")
    mto_items = relationship("MaterialTakeoff", back_populates="drawing")
    materials = relationship("DrawingMaterial", back_populates="drawing")
    equipment = relationship("DrawingEquipment", back_populates="drawing")
    ndt_requests = relationship("NDTRequest", back_populates="drawing")


class MaterialTakeoff(Base):
    __tablename__ = "material_takeoff"
    mto_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    discipline_id = Column(Integer, ForeignKey("engineering_disciplines.discipline_id"))
    drawing_id = Column(UUID(as_uuid=True), ForeignKey("drawings.drawing_id"))
    material_type = Column(String(100))
    material_spec = Column(String(100))
    quantity = Column(Numeric(12, 2))
    unit = Column(String(20))
    unit_weight_kg = Column(Numeric(12, 2))
    # total_weight_kg is GENERATED ALWAYS AS (quantity * unit_weight_kg) STORED in DB

    discipline = relationship("EngineeringDiscipline", back_populates="mto_items")
    drawing = relationship("Drawing", back_populates="mto_items")
