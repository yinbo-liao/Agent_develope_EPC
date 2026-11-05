from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class OPAPolicyClient:
    """Thin OPA client with fail-closed behavior."""

    def __init__(self, opa_url: str = settings.OPA_URL) -> None:
        self.opa_url = opa_url.rstrip("/")

    async def evaluate(
        self,
        agent: str,
        action: str,
        path: str,
        command: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent": agent, "action": action, "path": path}
        if command:
            payload["command"] = command

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                allow_response = await client.post(
                    f"{self.opa_url}/v1/data/agent/scope/allow",
                    json={"input": payload},
                )
                allow_response.raise_for_status()

                violation_response = await client.post(
                    f"{self.opa_url}/v1/data/agent/scope/violation",
                    json={"input": payload},
                )
                violation_response.raise_for_status()

            return {
                "allowed": bool(allow_response.json().get("result", False)),
                "violations": violation_response.json().get("result", []),
                "input": payload,
            }
        except httpx.HTTPError as exc:
            logger.error("OPA evaluation failed: %s", exc)
            return {
                "allowed": False,
                "violations": [{"msg": "Policy engine unavailable - access denied"}],
                "input": payload,
            }

    async def evaluate_mcp(self, role: str, server: str, tool: str) -> dict[str, Any]:
        """Evaluate the runtime MCP policy for a user role. Fail closed."""
        payload = {"role": role, "server": server, "tool": tool}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.opa_url}/v1/data/aiwf/mcp/allow",
                    json={"input": payload},
                )
                response.raise_for_status()
            allowed = bool(response.json().get("result", False))
            return {
                "allowed": allowed,
                "violations": [] if allowed else [{"msg": "MCP policy denied"}],
                "input": payload,
            }
        except httpx.HTTPError as exc:
            logger.error("OPA MCP evaluation failed: %s", exc)
            return {
                "allowed": False,
                "violations": [{"msg": "Policy engine unavailable - access denied"}],
                "input": payload,
            }

    async def check_scope(
        self,
        agent: str,
        action: str,
        path: str,
        command: str | None = None,
    ) -> bool:
        decision = await self.evaluate(agent=agent, action=action, path=path, command=command)
        return bool(decision["allowed"])


opa_client = OPAPolicyClient()
