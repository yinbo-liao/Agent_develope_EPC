from sqlalchemy import Column, String, Numeric, Date, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base
import uuid


class PurchaseOrder(Base):
    __tablename__ = "procurement_purchase_orders"
    po_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.project_id"))
    po_number = Column(String(50), unique=True, nullable=False)
    vendor_name = Column(String(200))
    order_date = Column(Date)
    expected_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)
    total_amount = Column(Numeric(18, 2))
    status = Column(String(30), default="ORDERED")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    purchase_item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    po_id = Column(UUID(as_uuid=True), ForeignKey("procurement_purchase_orders.po_id"))
    material_type = Column(String(100))
    material_spec = Column(String(100))
    quantity_ordered = Column(Numeric(12, 2))
    unit = Column(String(20))
    unit_price = Column(Numeric(12, 2))
    quantity_received = Column(Numeric(12, 2))
    received_date = Column(Date)
