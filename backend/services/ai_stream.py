"""
AI Streaming Service — WebSocket event streaming for real-time AI progress.

Yields events as the LangGraph agent processes a query:
  thinking → tool_call → tool_result → response → done
"""

import logging
from typing import AsyncIterator
from datetime import datetime

logger = logging.getLogger(__name__)


async def stream_ai_response(
    user_query: str,
    project_id: str,
    pool,
    user_id: str = "anonymous",
) -> AsyncIterator[dict]:
    """
    Stream AI processing events via async generator.

    Yields dicts with:
      {type: "thinking"|"tool_call"|"tool_result"|"response"|"error"|"done",
       message/data/tool/count: ...,
       timestamp: isoformat}

    Usage (in FastAPI WebSocket):
        async for event in stream_ai_response(query, project_id, pool):
            await ws.send_json(event)
    """
    from services.langgraph.graph import run_epc_agent

    yield {
        "type": "thinking",
        "message": "Analyzing your query...",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Run the agent (non-streaming for now; events emitted around execution)
        result = await run_epc_agent(
            user_query=user_query,
            project_id=project_id,
            pool=pool,
            user_id=user_id,
        )

        # Emit tool calls
        for tc in result.get("tool_calls", []):
            yield {
                "type": "tool_call",
                "tool": tc.get("name", "unknown"),
                "args": tc.get("args", {}),
                "timestamp": datetime.now().isoformat(),
            }
            yield {
                "type": "tool_result",
                "tool": tc.get("name", "unknown"),
                "summary": tc.get("result_summary", "Complete"),
                "timestamp": datetime.now().isoformat(),
            }

        # Emit response
        yield {
            "type": "response",
            "content": result.get("response", ""),
            "intent": result.get("intent", "unknown"),
            "confidence": result.get("confidence", 0.0),
            "sources": result.get("sources", []),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"AI streaming error: {e}", exc_info=True)
        yield {
            "type": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }

    yield {
        "type": "done",
        "timestamp": datetime.now().isoformat(),
    }
