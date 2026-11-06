"""Traceability router — full lifecycle trace from drawing to commissioning and back."""
from fastapi import APIRouter, HTTPException, Depends
from services.traceability_service import TraceabilityService
from db import get_pool


router = APIRouter(prefix="/api/traceability", tags=["traceability"])


@router.get("/forward/{project_id}/{drawing_id}")
async def forward_trace(project_id: str, drawing_id: str, pool = Depends(get_pool)):
    """Trace forward from a drawing through MTO→PO→Materials→NDT→Welds→Activities."""
    result = await TraceabilityService.forward_trace(drawing_id, project_id, pool)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/backward/{project_id}/{system_code}")
async def backward_trace(project_id: str, system_code: str, pool = Depends(get_pool)):
    """Trace backward from a sub-system through commissioning→punch→drawings→POs."""
    result = await TraceabilityService.backward_trace(system_code, project_id, pool)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/impact/{project_id}")
async def impact_analysis(project_id: str, entity_type: str, entity_id: str, pool = Depends(get_pool)):
    """Analyze downstream impact if an entity (drawing/activity/PO) is delayed."""
    valid_types = {"drawing", "activity", "purchase_order", "equipment"}
    if entity_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of: {', '.join(valid_types)}")
    result = await TraceabilityService.impact_analysis(entity_type, entity_id, project_id, pool)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/matrix/{project_id}")
async def traceability_matrix(project_id: str, page: int = 1, page_size: int = 500,
                              pool = Depends(get_pool)):
    """Full project traceability matrix — all drawings with downstream item counts (paginated)."""
    return await TraceabilityService.full_traceability_matrix(project_id, pool, page, page_size)
