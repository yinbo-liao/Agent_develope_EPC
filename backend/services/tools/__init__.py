"""Function Tool Registry — database-query tools callable by the LLM.

Each tool is a typed async function that queries the project database.
The registry maps tool names to their implementations and JSON schemas.

Import query_tools to trigger @tool_registry.register() decorators.
"""
from services.tools.registry import tool_registry
import services.tools.query_tools  # noqa: F401 — triggers tool registrations

__all__ = ["tool_registry"]
