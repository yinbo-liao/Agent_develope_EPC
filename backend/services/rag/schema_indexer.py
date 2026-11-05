"""
Schema Indexer — scans the PostgreSQL database schema and indexes tables/columns
as searchable text descriptions for the RAG system.

This generates a "schema knowledge base" that the LLM uses to:
1. Understand what tables and columns exist
2. Decide which function tools to call
3. Construct appropriate queries
"""

import logging
from services.rag.embedder import embedder

logger = logging.getLogger(__name__)

# Known EPC project tables with descriptions
EPC_SCHEMA = {
    "projects": {
        "description": "Core project information: project code, name, client, contract value, planned dates, baseline dates, current status",
        "columns": {
            "project_id": "UUID primary key",
            "project_code": "Unique project identifier code (e.g., FPSO-001)",
            "project_name": "Full project name",
            "client_name": "Client organization name",
            "contract_value": "Contract value in currency units",
            "planned_start_date": "Planned project start date",
            "planned_finish_date": "Planned project completion date",
            "baseline_start_date": "Original baseline start date",
            "baseline_finish_date": "Original baseline finish date",
            "current_status": "ACTIVE, ON_HOLD, COMPLETED, CANCELLED",
        },
    },
    "activities": {
        "description": "Schedule activities: codes, durations, float, critical path, progress, status, work scope categories",
        "columns": {
            "activity_id": "UUID primary key",
            "project_id": "FK to projects",
            "activity_code": "Activity identifier code",
            "activity_name": "Human-readable activity name",
            "original_duration": "Planned duration in days",
            "remaining_duration": "Remaining duration in days",
            "total_float": "Total float (slack) in days — negative or zero means critical",
            "is_critical": "Boolean — is on critical path",
            "physical_percent_complete": "Physical progress 0-100%",
            "status": "NOT_STARTED, IN_PROGRESS, COMPLETED, DELAYED",
            "work_scope_category": "CRITICAL, MIDWARE, SHORTER",
        },
    },
    "drawings": {
        "description": "Engineering drawings with IFA/IFC workflow: numbers, titles, statuses, issue dates, revisions per discipline",
        "columns": {
            "drawing_id": "UUID primary key",
            "project_id": "FK to projects",
            "discipline_id": "FK to engineering_disciplines",
            "drawing_number": "Drawing number",
            "drawing_title": "Drawing title/description",
            "status": "WIP, IFA, IFC, APPROVED",
            "issued_for_info": "Yes/No — IFA status",
            "issued_for_construction": "Yes/No — IFC status",
            "planned_issue_date": "Planned issue date",
            "actual_issue_date": "Actual issue date",
            "revision": "Current revision number",
        },
    },
    "procurement_purchase_orders": {
        "description": "Purchase orders: PO numbers, vendors, order/delivery dates, amounts, status",
    },
    "quality_ncr": {
        "description": "Quality Non-Conformance Reports: NCR numbers, severity, status, root causes, corrective actions, closure dates",
    },
    "safety_incidents": {
        "description": "HSE safety incidents: types (LTI/MTI/FAI/NEAR_MISS), severity, investigation status, lost time days",
    },
    "personnel_training": {
        "description": "Personnel training records: courses completed, expiry dates, certification status, role requirements",
    },
    "stage_gates": {
        "description": "Stage gate approvals: phase transitions, AI readiness scores, checklist items, approval status",
    },
    "conflicts": {
        "description": "Cross-phase conflicts: types (schedule/resource/material/design), severity, AI-detected flag, resolution status",
    },
    "sub_systems": {
        "description": "Completion sub-systems: system codes, names, disciplines, completion status",
    },
    "punch_items": {
        "description": "Punch list items: categories, priorities, statuses, responsible parties, due dates",
    },
    "commissioning_procedures": {
        "description": "Commissioning procedures: test types, checklist items, results (PASSED/FAILED), system codes",
    },
    "schedule_alerts": {
        "description": "Schedule alerts: CRITICAL_FLOAT, MATERIAL_SHORTAGE, NDT_OVERDUE with severity and recommendations",
    },
    "resource_shortages": {
        "description": "Resource shortages: resource names, shortfall quantities, status (OPEN/RESOLVED)",
    },
    "ndt_requests": {
        "description": "NDT inspection requests: methods, weld joints, percent complete, request/complete dates",
    },
    "weld_tracking": {
        "description": "Weld tracking: joint IDs, NDT methods, rejection rates, repair status",
    },
}


class SchemaIndexer:
    """Indexes database schema as searchable text for RAG retrieval."""

    def __init__(self):
        self._index: list[dict] | None = None
        self._embeddings: list[list[float]] | None = None

    async def build_index(self) -> list[dict]:
        """Build the schema index from EPC_SCHEMA definitions."""
        documents = []
        for table_name, table_info in EPC_SCHEMA.items():
            # Create a rich text description
            desc = table_info["description"]
            col_descs = []
            for col_name, col_desc in table_info.get("columns", {}).items():
                col_descs.append(f"  - {col_name}: {col_desc}")

            text = f"Table: {table_name}\nDescription: {desc}"
            if col_descs:
                text += "\nColumns:\n" + "\n".join(col_descs)

            documents.append({
                "table_name": table_name,
                "text": text,
                "description": desc,
                "column_count": len(table_info.get("columns", {})),
            })

        logger.info(f"Schema index built with {len(documents)} tables")
        self._index = documents
        return documents

    async def embed_index(self) -> list[list[float]]:
        """Generate embeddings for all schema documents."""
        if not self._index:
            await self.build_index()

        texts = [doc["text"] for doc in self._index]
        self._embeddings = await embedder.embed(texts)
        logger.info(f"Schema embeddings generated for {len(self._embeddings)} documents")
        return self._embeddings

    def get_index(self) -> list[dict]:
        """Get the current schema index."""
        if self._index is None:
            raise RuntimeError("Schema index not built. Call build_index() first.")
        return self._index

    def get_embeddings(self) -> list[list[float]]:
        """Get the current schema embeddings."""
        if self._embeddings is None:
            raise RuntimeError("Schema embeddings not generated. Call embed_index() first.")
        return self._embeddings


# Singleton
schema_indexer = SchemaIndexer()
