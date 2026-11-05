from __future__ import annotations

import pytest

from app.security import mcp_policy
from app.security.opa_client import opa_client


@pytest.mark.anyio
async def test_policy_allows_when_opa_allows(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow(role: str, server: str, tool: str) -> dict[str, object]:
        return {"allowed": True, "violations": [], "input": {}}

    monkeypatch.setattr(opa_client, "evaluate_mcp", allow)
    allowed, reason = await mcp_policy.authorize_mcp("admin", "postgres", "query")
    assert allowed is True
    assert reason == ""


@pytest.mark.anyio
async def test_policy_denies_when_opa_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    async def deny(role: str, server: str, tool: str) -> dict[str, object]:
        return {
            "allowed": False,
            "violations": [{"msg": "role cannot invoke this tool"}],
            "input": {},
        }

    monkeypatch.setattr(opa_client, "evaluate_mcp", deny)
    allowed, reason = await mcp_policy.authorize_mcp("viewer", "postgres", "execute_sql")
    assert allowed is False
    assert "cannot invoke" in reason