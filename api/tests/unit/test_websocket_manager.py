from __future__ import annotations


import pytest
from starlette.websockets import WebSocketState

from app.core import websocket_manager as ws_module
from app.core.websocket_manager import RedisWebSocketManager


class FakeWebSocket:
    def __init__(self, state: WebSocketState = WebSocketState.CONNECTED) -> None:
        self.client_state = state
        self.accepted = False
        self.sent: list[dict] = []
        self.closed: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = code


@pytest.mark.anyio
async def test_add_remove_connection() -> None:
    manager = RedisWebSocketManager("redis://localhost:1/0")
    websocket = FakeWebSocket()

    await manager.add_connection("task-1", websocket)  # type: ignore[arg-type]
    assert websocket.accepted is True
    assert websocket in manager.local_connections["task-1"]
    assert websocket.sent[0]["type"] == "connection"

    manager.remove_connection("task-1", websocket)  # type: ignore[arg-type]
    assert "task-1" not in manager.local_connections
    manager.remove_connection("missing", websocket)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_broadcast_and_stale_cleanup() -> None:
    manager = RedisWebSocketManager("redis://localhost:1/0")
    live = FakeWebSocket()
    stale = FakeWebSocket(WebSocketState.DISCONNECTED)
    manager.local_connections["task-1"].update({live, stale})  # type: ignore[arg-type]

    await manager.broadcast("task-1", {"type": "step", "status": "running"})
    assert live.sent[-1]["taskId"] == "task-1"
    assert stale not in manager.local_connections["task-1"]


@pytest.mark.anyio
async def test_broadcast_falls_back_when_redis_publish_fails() -> None:
    class FailingRedis:
        async def publish(self, *args, **kwargs):
            raise RuntimeError("redis down")

    manager = RedisWebSocketManager("redis://localhost:1/0")
    manager.redis_client = FailingRedis()  # type: ignore[assignment]
    websocket = FakeWebSocket()
    manager.local_connections["task-1"].add(websocket)  # type: ignore[arg-type]

    await manager.broadcast("task-1", {"type": "step"})
    assert websocket.sent[-1]["type"] == "step"


@pytest.mark.anyio
async def test_event_stream_bridges_queue() -> None:
    manager = RedisWebSocketManager("redis://localhost:1/0")
    stream = manager.event_stream("task-1")
    first = await anext(stream)
    assert first["transport"] == "sse"

    await manager.broadcast("task-1", {"type": "step", "currentStep": "work"})
    second = await anext(stream)
    assert second["type"] == "step"

    await stream.aclose()
    assert "task-1" not in manager.local_connections


@pytest.mark.anyio
async def test_connect_without_redis_and_disconnect(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("no redis")

    monkeypatch.setattr(ws_module.redis, "from_url", fail)
    manager = RedisWebSocketManager("redis://localhost:1/0")
    await manager.connect()
    assert manager.redis_client is None
    assert manager._initialized is True
    await manager.disconnect()
    assert manager._initialized is False