from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.services.kpi import compute_kpi

router = APIRouter(prefix="/kpi", tags=["KPI"])

CURRENT_USER = dict[str, object]


@router.get("/summary", status_code=200)
async def kpi_summary(
    session: AsyncSession = Depends(get_db_session),
    current_user: CURRENT_USER = Depends(get_current_user),
) -> dict[str, object]:
    return await compute_kpi(session)


@router.get("/gate-g", status_code=200)
async def gate_g(
    session: AsyncSession = Depends(get_db_session),
    current_user: CURRENT_USER = Depends(require_role("admin")),
) -> dict[str, object]:
    """GATE_G is expansion-only: it never blocks a release, only autonomy expansion."""
    return await compute_kpi(session)