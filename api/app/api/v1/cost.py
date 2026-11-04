from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user
from app.services.cost_governor import cost_governor
from app.services.semantic_cache import get_stats as get_cache_stats

router = APIRouter(prefix="/cost", tags=["Cost"])

CURRENT_USER = dict[str, object]


@router.get("/status", status_code=status.HTTP_200_OK)
async def cost_status(
    current_user: CURRENT_USER = Depends(get_current_user),
) -> dict[str, object]:
    """Return cost status for the authenticated caller only."""
    return await cost_governor.get_status(str(current_user["user_id"]))


@router.get("/optimization-insights", status_code=status.HTTP_200_OK)
async def optimization_insights(
    current_user: CURRENT_USER = Depends(get_current_user),
) -> dict[str, object]:
    """Return cost optimization metrics for the authenticated caller only."""
    effective_user = str(current_user["user_id"])
    cache_stats = get_cache_stats()
    current = await cost_governor.get_status(effective_user)
    cache_hits = cache_stats["hits"]
    estimated_cache_savings = round(cache_hits * 0.005, 4)

    return {
        "user_id": effective_user,
        "semantic_cache": {
            "hits": cache_stats["hits"],
            "misses": cache_stats["misses"],
            "total_queries": cache_stats["total"],
            "hit_rate": round(cache_stats["hits"] / max(1, cache_stats["total"]) * 100, 1),
            "estimated_savings_usd": estimated_cache_savings,
        },
        "cascade_routing": {
            "enabled": True,
            "description": "Tiered execution: cheapest model first, escalate only if needed",
        },
        "prompt_compression": {
            "enabled": True,
            "max_context_items": 3,
            "max_snippet_chars": 200,
        },
        "projected_monthly_savings_usd": round(estimated_cache_savings * 30, 2),
        "current_usage": current,
    }