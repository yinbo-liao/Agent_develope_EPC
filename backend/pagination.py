"""
Reusable pagination for list endpoints.

Usage:
    from pagination import PaginationParams, paginate, PaginatedResponse

    @router.get("/items/{project_id}")
    async def list_items(project_id: str, pagination: PaginationParams = Depends()):
        base_query = "SELECT * FROM items WHERE project_id = $1"
        base_count = "SELECT COUNT(*) FROM items WHERE project_id = $1"
        result = await paginate(conn, base_query, base_count, [project_id], pagination)
        return result
"""

from dataclasses import dataclass
from typing import Any, Optional
from fastapi import Query, Depends


@dataclass
class PaginationParams:
    page: int = Query(1, ge=1, description="Page number (1-based)")
    page_size: int = Query(50, ge=1, le=500, description="Items per page (max 500)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse:
    """Wrapper for paginated API responses."""

    def __init__(self, items: list[dict], total: int, page: int, page_size: int):
        self.items = items
        self.total = total
        self.page = page
        self.page_size = page_size
        self.total_pages = max(1, (total + page_size - 1) // page_size)
        self.has_next = page < self.total_pages
        self.has_prev = page > 1

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "pagination": {
                "total": self.total,
                "page": self.page,
                "page_size": self.page_size,
                "total_pages": self.total_pages,
                "has_next": self.has_next,
                "has_prev": self.has_prev,
            },
        }

    @staticmethod
    def empty(page_size: int = 50) -> dict:
        return {
            "items": [],
            "pagination": {
                "total": 0,
                "page": 1,
                "page_size": page_size,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False,
            },
        }


async def paginate(
    conn,
    base_query: str,
    count_query: str,
    params: list,
    pagination: PaginationParams,
    order_by: str = "",
) -> dict:
    """Execute a paginated query and return structured response.

    Args:
        conn: Database connection (asyncpg or SQLAlchemy)
        base_query: SELECT query WITHOUT LIMIT/OFFSET/ORDER BY
        count_query: SELECT COUNT(*) query
        params: Query parameters (list for $1, $2, ...)
        pagination: PaginationParams from dependency
        order_by: Optional ORDER BY clause to append

    Returns:
        dict with 'items' and 'pagination' keys
    """
    # Get total count
    total_row = await conn.fetchval(count_query, *params) if hasattr(conn, 'fetchval') else (
        await conn.execute(count_query, *params)
    )
    # Handle both asyncpg (returns int) and SQLAlchemy (returns Result)
    if hasattr(total_row, 'scalar'):
        total = total_row.scalar()
    else:
        total = total_row or 0

    if total == 0:
        return PaginatedResponse.empty(pagination.page_size)

    # Build paginated query
    query = base_query
    if order_by:
        query += f" {order_by}"
    query += f" LIMIT {pagination.limit} OFFSET {pagination.offset}"

    # Fetch page
    if hasattr(conn, 'fetch'):
        rows = await conn.fetch(query, *params)
        items = [dict(r) for r in rows]
    else:
        result = await conn.execute(query, *params)
        items = [dict(r._mapping) for r in result]

    return PaginatedResponse(items, total, pagination.page, pagination.page_size).to_dict()
