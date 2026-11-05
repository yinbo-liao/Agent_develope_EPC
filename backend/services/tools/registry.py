"""
Function Tool Registry — decorator-based tool registration with schema validation.

Each registered tool becomes:
1. A callable async function for direct Python invocation
2. A JSON Schema definition for LLM tool use
3. An auditable entry point with logging and timeout
"""

import time
import json
import logging
from typing import Any, Callable
from functools import wraps
from services.llm_provider import ToolDefinition
from services.tools.schema import ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of database-query tools callable by the LLM."""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        timeout_ms: int = 5000,
    ):
        """Decorator — register an async function as a callable tool.

        Args:
            name: Unique tool name (e.g. 'query_activities')
            description: Human-readable description shown to the LLM
            parameters: JSON Schema for the tool's input parameters
            timeout_ms: Query timeout in milliseconds
        """

        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(**kwargs) -> ToolResult:
                start = time.perf_counter()
                try:
                    result = await func(**kwargs)
                    elapsed = (time.perf_counter() - start) * 1000
                    return ToolResult(
                        success=True,
                        data=result if isinstance(result, list) else result,
                        row_count=len(result) if isinstance(result, list) else 1,
                        query_time_ms=round(elapsed, 2),
                    )
                except Exception as e:
                    elapsed = (time.perf_counter() - start) * 1000
                    logger.error(f"Tool '{name}' failed: {e}", exc_info=True)
                    return ToolResult(
                        success=False,
                        error=str(e),
                        query_time_ms=round(elapsed, 2),
                    )

            self._tools[name] = {
                "func": wrapper,
                "definition": ToolDefinition(
                    name=name,
                    description=description,
                    parameters=parameters,
                ),
                "timeout_ms": timeout_ms,
            }
            return wrapper

        return decorator

    def get_tool(self, name: str):
        """Get a tool's callable and definition by name."""
        entry = self._tools.get(name)
        if entry is None:
            return None
        return entry["func"], entry["definition"]

    def get_definitions(self, names: list[str] | None = None) -> list[ToolDefinition]:
        """Get JSON Schema definitions for all or specific tools."""
        tools = []
        for name, entry in self._tools.items():
            if names is None or name in names:
                tools.append(entry["definition"])
        return tools

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return sorted(self._tools.keys())

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with the given arguments."""
        entry = self._tools.get(name)
        if entry is None:
            return ToolResult(success=False, error=f"Unknown tool: {name}. Available: {self.list_tools()}")

        func = entry["func"]
        timeout = entry["timeout_ms"] / 1000

        try:
            import asyncio
            return await asyncio.wait_for(func(**kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Tool '{name}' timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, error=f"Tool '{name}' error: {str(e)}")


# Singleton
tool_registry = ToolRegistry()
