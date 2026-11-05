"""Runtime MCP authorization.

The local agent policy (agent/scope) governs Claude Code tools; this policy governs
runtime MCP invocation by platform users. It is evaluated by OPA and fails closed.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.security.opa_client import opa_client

logger = logging.getLogger(__name__)


async def authorize_mcp(role: str, server: str, tool: str) -> tuple[bool, str]:
    if not settings.MCP_POLICY_ENFORCE:
        return True, "MCP policy enforcement disabled"
    decision = await opa_client.evaluate_mcp(role=role, server=server, tool=tool)
    if decision["allowed"]:
        return True, ""
    reason = "MCP policy denied"
    violations = decision.get("violations") or []
    if violations and isinstance(violations[0], dict):
        reason = str(violations[0].get("msg", reason))
    logger.warning("MCP policy denied role=%s server=%s tool=%s", role, server, tool)
    return False, reason