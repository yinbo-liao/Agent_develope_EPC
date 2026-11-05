from sqlalchemy import Column, String, Integer, Date, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid


class EquipmentCategory(Base):
    __tablename__ = "equipment_categories"
    cat_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(50), unique=True)


class Equipment(Base):
    __tablename__ = "equipment_list"
    equipment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    category_id = Column(Integer, ForeignKey("equipment_categories.cat_id"))
    tag_number = Column(String(50), nullable=False)
    equipment_name = Column(String(200))
    manufacturer = Column(String(100))
    model = Column(String(100))
    specification_doc = Column(String(200))
    spec_status = Column(String(30), default="SUBMITTED")
    order_date = Column(Date)
    delivery_date = Column(Date)
    installation_date = Column(Date)
