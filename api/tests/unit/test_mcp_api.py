from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1 import mcp as mcp_api
from app.core.mcp_client import mcp_tool_manager


@pytest.fixture(autouse=True)
def allow_policy(monkeypatch):
    monkeypatch.setattr(mcp_api, "authorize_mcp", AsyncMock(return_value=(True, "")))


@pytest.mark.anyio
async def test_mcp_tools_and_health(async_client, auth_headers):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        mcp_tool_manager,
        "get_tools",
        AsyncMock(return_value=[{"name": "query"}]),
    )
    monkeypatch.setattr(
        mcp_tool_manager,
        "get_server_health",
        AsyncMock(
            return_value={
                "postgres": SimpleNamespace(
                    status="up",
                    enabled=True,
                    tools=["query"],
                    last_check=datetime.now(timezone.utc),
                    message="",
                )
            }
        ),
    )
    try:
        tools = await async_client.get("/api/v1/mcp/tools", headers=auth_headers)
        assert tools.status_code == 200
        assert tools.json()["tools"] == [{"name": "query"}]

        health = await async_client.get("/api/v1/mcp/health", headers=auth_headers)
        assert health.status_code == 200
        assert "postgres" in health.json()["servers"]
    finally:
        monkeypatch.undo()


@pytest.mark.anyio
async def test_mcp_invoke_success(async_client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        mcp_tool_manager, "call_tool", AsyncMock(return_value={"rows": 1})
    )
    response = await async_client.post(
        "/api/v1/mcp/invoke/postgres/query",
        json={"sql": "select 1"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["result"] == {"rows": 1}


@pytest.mark.anyio
async def test_mcp_invoke_error(async_client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        mcp_tool_manager, "call_tool", AsyncMock(side_effect=RuntimeError("tool failed"))
    )
    response = await async_client.post(
        "/api/v1/mcp/invoke/postgres/query",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.anyio
async def test_mcp_invoke_denied(async_client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        mcp_api, "authorize_mcp", AsyncMock(return_value=(False, "denied by policy"))
    )
    response = await async_client.post(
        "/api/v1/mcp/invoke/postgres/query",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 403