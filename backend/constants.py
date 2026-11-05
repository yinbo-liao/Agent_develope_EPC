"""Canonical status definitions for EPC project management.

All status strings used across routers and services should reference
these constants rather than ad-hoc string literals.
"""
from enum import Enum


class DrawingStatus(str, Enum):
    """Engineering drawing release status."""
    WIP = "WIP"              # Work In Progress
    IFA = "IFA"              # Issued For Approval
    IFC = "IFC"              # Issued For Construction
    AFC = "AFC"              # Approved For Construction (alias for IFC)
    REVISED = "REVISED"      # Revised after issue
    CANCELLED = "CANCELLED"


class IFAStatus(str, Enum):
    """Drawing IFA state (used in drawing_materials view)."""
    YES = "Yes"
    NO = "No"


class IFCStatus(str, Enum):
    """Drawing IFC state (used in drawing_materials view)."""
    YES = "Yes"
    NO = "No"


class MVRStatus(str, Enum):
    """Material Verification Request status workflow."""
    INFO_AFI = "Info-AFI"                # Initial state — information only
    STRUCTURE_REQUESTED = "Structure-requested"  # MVR requested for structural
    PIPING_REQUESTED = "piping-requested"        # MVR requested for piping
    MVR_CONFIRM = "MVR-confirm"           # MVR confirmed (requires AFC drawing)
    CANCELLED = "CANCELLED"


class POStatus(str, Enum):
    """Purchase Order status."""
    ORDERED = "ORDERED"
    PR_RAISED = "PR-RAISED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class MaterialPOStatus(str, Enum):
    """PO status as displayed on material items."""
    INFO_AFI = "Info-AFI"
    STRUCTURE_REQUESTED = "Structure-requested"
    PR_RAISED = "PR-Raised"
    NONE = "None"


class CompletionStatus(str, Enum):
    """Sub-system completion status."""
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_MC = "READY_FOR_MC"
    MC_COMPLETE = "MC_COMPLETE"
    HANDED_OVER = "HANDED_OVER"


class PunchCategory(str, Enum):
    """Punch item category (A=critical, B=standard, C=cosmetic)."""
    A = "A"  # Critical — must resolve before handover
    B = "B"  # Standard — resolve before system completion
    C = "C"  # Cosmetic — resolve when convenient


class PunchStatus(str, Enum):
    """Punch item status."""
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class CommissioningProcedureType(str, Enum):
    """Commissioning procedure types in execution order."""
    MC_CHECK = "MC_CHECK"
    PRE_COMM = "PRE_COMM"
    COMM_PROCEDURE = "COMM_PROCEDURE"
    PERFORMANCE_TEST = "PERFORMANCE_TEST"


class CommissioningStatus(str, Enum):
    """Commissioning procedure execution status."""
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    REVALIDATED = "REVALIDATED"


class NCRSeverity(str, Enum):
    """Non-Conformance Report severity."""
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    OBSERVATION = "OBSERVATION"


class NCRStatus(str, Enum):
    """NCR lifecycle status."""
    OPEN = "OPEN"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    CORRECTIVE_ACTION = "CORRECTIVE_ACTION"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    CLOSED = "CLOSED"


class IncidentType(str, Enum):
    """Safety incident classification."""
    LTI = "LTI"                  # Lost Time Injury
    MTI = "MTI"                  # Medical Treatment Injury
    RWC = "RWC"                  # Restricted Work Case
    FA = "FA"                    # Fatal Accident
    NEAR_MISS = "NEAR_MISS"
    OBSERVATION = "OBSERVATION"
    FIRST_AID = "FIRST_AID"


class IncidentSeverity(str, Enum):
    """Safety incident severity."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PermitType(str, Enum):
    """Safety permit types."""
    HOT_WORK = "HOT_WORK"
    COLD_WORK = "COLD_WORK"
    CONFINED_SPACE = "CONFINED_SPACE"
    ELECTRICAL_ISOLATION = "ELECTRICAL_ISOLATION"
    EXCAVATION = "EXCAVATION"
    LIFTING = "LIFTING"
    RADIOGRAPHY = "RADIOGRAPHY"
    DIVING = "DIVING"


class PermitStatus(str, Enum):
    """Safety permit status workflow."""
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    ISSUED = "ISSUED"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ConflictType(str, Enum):
    """Conflict detection categories."""
    SCHEDULE_CLASH = "SCHEDULE_CLASH"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    DESIGN_CLASH = "DESIGN_CLASH"
    INTERFACE_GAP = "INTERFACE_GAP"
    SCOPE_CHANGE = "SCOPE_CHANGE"
    MATERIAL_DELAY = "MATERIAL_DELAY"
    MANPOWER_SHORTAGE = "MANPOWER_SHORTAGE"
    VENDOR_ISSUE = "VENDOR_ISSUE"
    SAFETY_RISK = "SAFETY_RISK"


class ConflictSeverity(str, Enum):
    """Conflict severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConflictStatus(str, Enum):
    """Conflict resolution workflow."""
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_RESOLUTION = "IN_RESOLUTION"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class FeedbackType(str, Enum):
    """Cross-phase feedback categories."""
    DESIGN_CHANGE = "DESIGN_CHANGE"
    MATERIAL_SUBSTITUTION = "MATERIAL_SUBSTITUTION"
    SCHEDULE_ADJUSTMENT = "SCHEDULE_ADJUSTMENT"
    SCOPE_VARIATION = "SCOPE_VARIATION"
    QUALITY_ISSUE = "QUALITY_ISSUE"
    SAFETY_CONCERN = "SAFETY_CONCERN"
    TECHNICAL_QUERY = "TECHNICAL_QUERY"


class StageGateStatus(str, Enum):
    """Stage gate approval status."""
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONDITIONAL = "CONDITIONAL"


class PlanningPeriodType(str, Enum):
    """Multi-level planning period types."""
    WEEKLY = "WEEKLY"
    BI_WEEKLY = "BI_WEEKLY"
    MONTHLY = "MONTHLY"
    BI_MONTHLY = "BI_MONTHLY"
    FOUR_MONTH = "FOUR_MONTH"


class PlanItemStatus(str, Enum):
    """Plan item execution status."""
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    DELAYED = "DELAYED"
    COMPLETED = "COMPLETED"


class ProjectStatus(str, Enum):
    """Overall project status."""
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    CANCELLED = "CANCELLED"


class WeldStatus(str, Enum):
    """Weld tracking status."""
    WELDED = "WELDED"
    PENDING_NDT = "PENDING_NDT"
    NDT_PASSED = "NDT_PASSED"
    NDT_FAILED = "NDT_FAILED"
    REPAIRED = "REPAIRED"
    ACCEPTED = "ACCEPTED"


class NDTMethod(str, Enum):
    """Non-Destructive Testing methods."""
    UT = "UT"       # Ultrasonic Testing
    RT = "RT"       # Radiographic Testing
    MT = "MT"       # Magnetic Particle Testing
    PT = "PT"       # Penetrant Testing
    VT = "VT"       # Visual Testing
    PAUT = "PAUT"   # Phased Array UT
    TOFD = "TOFD"   # Time of Flight Diffraction


class AlertSeverity(str, Enum):
    """Schedule alert severity."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertType(str, Enum):
    """Schedule alert categories."""
    CRITICAL_FLOAT = "CRITICAL_FLOAT"
    MATERIAL_SHORTAGE = "MATERIAL_SHORTAGE"
    NDT_OVERDUE = "NDT_OVERDUE"
    SAFETY_INCIDENT = "SAFETY_INCIDENT"
    TRAINING_EXPIRY = "TRAINING_EXPIRY"
    GATE_OVERDUE = "GATE_OVERDUE"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"


# ── Discipline Enum ────────────────────────────────────────────────

class Discipline(str, Enum):
    """Engineering disciplines."""
    STRUCTURAL = "STRUCTURAL"
    PIPING = "PIPING"
    MECHANICAL = "MECHANICAL"
    ELECTRICAL = "ELECTRICAL"
    HVAC = "HVAC"
    ARCHITECTURE_DECORATION = "ARCHITECTURE_DECORATION"


# ── Mapping: MVR Status Workflow ──────────────────────────────────

MVR_STATUS_TRANSITIONS = {
    MVRStatus.INFO_AFI: [MVRStatus.STRUCTURE_REQUESTED, MVRStatus.PIPING_REQUESTED, MVRStatus.CANCELLED],
    MVRStatus.STRUCTURE_REQUESTED: [MVRStatus.MVR_CONFIRM, MVRStatus.CANCELLED],
    MVRStatus.PIPING_REQUESTED: [MVRStatus.MVR_CONFIRM, MVRStatus.CANCELLED],
    MVRStatus.MVR_CONFIRM: [MVRStatus.CANCELLED],
    MVRStatus.CANCELLED: [],
}
