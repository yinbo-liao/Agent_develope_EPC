from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached
from app.core.database import get_db_session
from app.core.deps import get_current_user
from app.core.mcp_client import mcp_tool_manager
from app.core.mcp_interceptors import AuditLogInterceptor, RateLimitInterceptor
from app.core.metrics import track_mcp_call
from app.security.mcp_policy import authorize_mcp
from app.services.audit import append_audit

router = APIRouter(prefix="/mcp", tags=["MCP"])

audit_interceptor = AuditLogInterceptor()
rate_limit_interceptor = RateLimitInterceptor(max_calls_per_minute=60)


@router.get("/health", status_code=status.HTTP_200_OK)
@cached("mcp_health", ttl=30)
async def mcp_health(
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    health = await mcp_tool_manager.get_server_health()
    return {
        "servers": {
            name: {
                "status": server.status,
                "enabled": server.enabled,
                "tools": server.tools,
                "last_check": server.last_check.isoformat(),
                "message": server.message,
            }
            for name, server in health.items()
        }
    }


@router.get("/tools", status_code=status.HTTP_200_OK)
async def list_mcp_tools(
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    return {"tools": await mcp_tool_manager.get_tools()}


@router.post("/invoke/{server_name}/{tool_name}", status_code=status.HTTP_200_OK)
async def invoke_mcp_tool(
    server_name: str,
    tool_name: str,
    args: dict[str, object],
    session: AsyncSession = Depends(get_db_session),
    current_user: dict[str, object] = Depends(get_current_user),
) -> dict[str, object]:
    correlation_id = str(uuid.uuid4())
    role = str(current_user.get("role", "viewer"))
    allowed, reason = await authorize_mcp(role, server_name, tool_name)
    if not allowed:
        await append_audit(
            session,
            actor=str(current_user["user_id"]),
            action="mcp.invoke_denied",
            resource=f"{server_name}.{tool_name}",
            payload={"role": role, "reason": reason},
        )
        await session.commit()
        raise HTTPException(status_code=403, detail="MCP policy denied this invocation")
    try:
        rate_limit_interceptor.check(f"{server_name}.{tool_name}")
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    await audit_interceptor.on_request(
        session=session,
        correlation_id=correlation_id,
        server_name=server_name,
        tool_name=tool_name,
        args=args,
    )
    try:
        result = await mcp_tool_manager.call_tool(server_name, tool_name, args)
    except Exception as exc:
        track_mcp_call(server_name, tool_name, "error")
        await audit_interceptor.on_response(
            session=session,
            correlation_id=correlation_id,
            result={"error": str(exc)},
            status="error",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit_interceptor.on_response(
        session=session,
        correlation_id=correlation_id,
        result=result,
        status="success",
    )
    await append_audit(
        session,
        actor=str(current_user["user_id"]),
        action="mcp.invoke",
        resource=f"{server_name}.{tool_name}",
        payload={"role": role, "correlation_id": correlation_id},
    )
    await session.commit()
    track_mcp_call(server_name, tool_name, "success")
    return {"correlation_id": correlation_id, "result": result}
