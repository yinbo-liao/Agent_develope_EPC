"""
Pydantic schemas for tool input/output validation.

Each tool has:
- Input schema (validated before execution)
- Output schema (validated after execution)
- Error schema (returned on failure)
"""

from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import date


class ToolResult(BaseModel):
    """Standard wrapper for all tool execution results."""
    success: bool = True
    data: Any = None
    error: str | None = None
    row_count: int = 0
    query_time_ms: float = 0.0


class QueryActivitiesInput(BaseModel):
    project_id: str
    status: str | None = None
    is_critical: bool | None = None
    work_scope_category: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QueryDrawingsInput(BaseModel):
    project_id: str
    discipline_name: str | None = None
    status: str | None = None
    drawing_type: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QueryProcurementInput(BaseModel):
    project_id: str
    vendor_name: str | None = None
    status: str | None = None
    material_type: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QueryQualityNCRInput(BaseModel):
    project_id: str
    severity: str | None = None
    status: str | None = None
    discipline_name: str | None = None
    from_date: date | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QuerySafetyIncidentsInput(BaseModel):
    project_id: str
    incident_type: str | None = None
    severity: str | None = None
    from_date: date | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QueryTrainingRecordsInput(BaseModel):
    project_id: str
    personnel_name: str | None = None
    course_name: str | None = None
    certification_expired: bool | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QueryStageGatesInput(BaseModel):
    project_id: str
    status: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class QueryConflictsInput(BaseModel):
    project_id: str
    conflict_type: str | None = None
    severity: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class QueryTraceabilityInput(BaseModel):
    project_id: str
    entity_type: str  # drawing, activity, purchase_order, equipment, system
    entity_id: str


class CalculateKPIInput(BaseModel):
    project_id: str


class GenerateReportInput(BaseModel):
    project_id: str
    report_type: str = "weekly"  # weekly, monthly, executive
    week_end: date | None = None
