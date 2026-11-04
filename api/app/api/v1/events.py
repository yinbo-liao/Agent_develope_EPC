from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from jose import JWTError
from sqlalchemy import select

from app.core.database import SessionLocal, get_db_session
from app.core.deps import get_current_user
from app.core.sse_manager import sse_manager
from app.core.websocket_manager import ws_manager
from app.models.workflow import WorkflowRun
from app.security.auth import STREAM_TOKEN_EXPIRE_SECONDS, create_stream_token, decode_stream_token

router = APIRouter(prefix="/events", tags=["Events"])

CURRENT_USER = dict[str, object]


async def _owned_run(session, task_id: str, user_id: str) -> WorkflowRun | None:
    result = await session.execute(
        select(WorkflowRun).where(WorkflowRun.id == task_id, WorkflowRun.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def build_state_payload(task_id: str, user_id: str) -> dict[str, object]:
    async with SessionLocal() as session:
        run = await _owned_run(session, task_id, user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "type": "state",
        "taskId": run.id,
        "status": run.current_status,
        "currentStep": run.current_step,
        "riskLevel": run.risk_level,
        "isHumanReviewNeeded": run.is_human_review_needed,
        "finalResponse": run.final_response,
        "error": run.error_info,
        "totalTokens": run.total_tokens_used,
        "totalCost": run.cost_usd,
        "reviewData": {
            "decision": run.human_decision,
            "comment": run.human_comment,
            "deadline": run.review_deadline.isoformat() if run.review_deadline else None,
            "factors": run.risk_factors,
        },
    }


@router.post("/ticket/{task_id}", status_code=200)
async def issue_stream_ticket(
    task_id: str,
    session=Depends(get_db_session),
    current_user: CURRENT_USER = Depends(get_current_user),
) -> dict[str, object]:
    """Issue a short-lived, task-scoped ticket for WebSocket/SSE connections.

    Browsers cannot attach Authorization headers to EventSource and should not put
    a long-lived access token in a query string. The ticket is valid for two
    minutes and only for this task.
    """
    user_id = str(current_user["user_id"])
    if await _owned_run(session, task_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "ticket": create_stream_token(user_id, task_id),
        "expiresIn": STREAM_TOKEN_EXPIRE_SECONDS,
    }


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    task_id: str,
    ticket: str | None = None,
) -> None:
    try:
        user_id = decode_stream_token(ticket or "", task_id)
    except JWTError:
        await websocket.close(code=4401)
        return

    async with SessionLocal() as session:
        run = await _owned_run(session, task_id, user_id)
    if run is None:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    await ws_manager.add_connection(task_id, websocket)
    try:
        await websocket.send_json(await build_state_payload(task_id, user_id))
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
            except (asyncio.TimeoutError, TimeoutError):
                # Idle clients get a keepalive instead of an unhandled exception.
                await websocket.send_json({"type": "ping", "taskId": task_id})
                continue
            message_type = data.get("type")
            if message_type == "ping":
                await websocket.send_json({"type": "pong", "taskId": task_id})
            elif message_type == "status":
                await websocket.send_json(await build_state_payload(task_id, user_id))
            # Human decisions are REST-only (`POST /human-review/decide`): a socket
            # message is never an approval.
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.remove_connection(task_id, websocket)


@router.get("/sse/{task_id}")
async def sse_endpoint(task_id: str, ticket: str | None = None) -> StreamingResponse:
    try:
        user_id = decode_stream_token(ticket or "", task_id)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="A valid stream ticket is required") from exc

    async with SessionLocal() as session:
        if await _owned_run(session, task_id, user_id) is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

    return StreamingResponse(
        sse_manager.subscribe(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/state/{task_id}")
async def state_endpoint(
    task_id: str,
    current_user: CURRENT_USER = Depends(get_current_user),
) -> dict[str, object]:
    return await build_state_payload(task_id, str(current_user["user_id"]))