"""
LangGraph Graph Builder — builds and runs the EPC Agent state machine.

The graph flow:
  classify_intent → route_to_tools → execute_tools → validate_results
    → [valid] compose_response → END
    → [incomplete] route_to_tools (retry with different tools)
    → [error] handle_error → END

Maximum 3 iterations to prevent infinite loops.
"""

import logging
from typing import Any
from config import settings
from services.langgraph.state import EPCAgentState
from services.langgraph.nodes import (
    classify_intent, route_to_tools, execute_tools,
    validate_results, compose_response, handle_error,
)

logger = logging.getLogger(__name__)


async def run_epc_agent(
    user_query: str,
    project_id: str,
    pool,
    user_id: str = "anonymous",
    max_iterations: int | None = None,
) -> dict:
    """
    Run the EPC Agent state machine. Does NOT require LangGraph to be installed —
    uses a pure Python state machine when LangGraph is unavailable.

    Args:
        user_query: Natural language question from the user
        project_id: Project UUID for data context
        pool: Asyncpg connection pool
        user_id: Authenticated user ID
        max_iterations: Max tool execution iterations (default from config)

    Returns:
        Dict with: response, intent, tool_calls, sources, confidence, fallback_used, iterations
    """
    max_iter = max_iterations or settings.langgraph_max_steps

    # Initialize state
    state: EPCAgentState = {
        "messages": [],
        "user_query": user_query,
        "project_id": project_id,
        "user_id": user_id,
        "intent": "",
        "confidence": 0.0,
        "iteration": 0,
        "selected_tools": [],
        "tool_calls": [],
        "tool_results": [],
        "context": "",
        "response": "",
        "sources": [],
        "error": None,
        "needs_clarification": False,
        "clarification_question": "",
        "fallback_used": False,
    }

    # Try LangGraph StateGraph if installed
    try:
        import langgraph
        return await _run_with_langgraph(state, pool, max_iter)
    except ImportError:
        logger.info("LangGraph not installed — using pure Python state machine")
        return await _run_pure_python(state, pool, max_iter)


async def _run_pure_python(state: EPCAgentState, pool, max_iter: int) -> dict:
    """Pure Python state machine (no LangGraph dependency)."""
    for i in range(max_iter):
        state["iteration"] = i + 1

        # Step 1: Classify intent
        state = await classify_intent(state)

        # Step 2: Route to tools
        state = await route_to_tools(state)

        # Step 3: Execute tools
        state = await execute_tools(state, pool)

        # Step 4: Validate results
        state = await validate_results(state)

        # Check validation outcome
        if state.get("error"):
            state = await handle_error(state)
            break

        if state.get("needs_clarification"):
            logger.info("Agent needs clarification — returning partial result")
            break

        # Step 5: Compose response
        state = await compose_response(state)

        if state.get("response"):
            break

        # If no response yet, loop back with broader tool selection
        if i < max_iter - 1:
            state["selected_tools"] = ["calculate_kpi", "query_activities"]
    else:
        state["fallback_used"] = True
        state["response"] = (
            "I searched the project database but couldn't find a complete answer. "
            "Please try a more specific question about project activities, drawings, "
            "procurement, quality, safety, training, or ask for the KPI summary."
        )

    return _format_result(state)


async def _run_with_langgraph(state: EPCAgentState, pool, max_iter: int) -> dict:
    """Run using LangGraph StateGraph (installed)."""
    try:
        from langgraph.graph import StateGraph, END

        workflow = StateGraph(EPCAgentState)

        # Add nodes
        workflow.add_node("classify", classify_intent)
        workflow.add_node("route", route_to_tools)
        workflow.add_node("execute", lambda s: execute_tools(s, pool))
        workflow.add_node("validate", validate_results)
        workflow.add_node("compose", compose_response)
        workflow.add_node("error_handler", handle_error)

        # Set entry
        workflow.set_entry_point("classify")

        # Define edges
        workflow.add_edge("classify", "route")
        workflow.add_edge("route", "execute")
        workflow.add_edge("execute", "validate")

        # Conditional edges from validate
        def after_validate(s: EPCAgentState) -> str:
            if s.get("error"):
                return "error_handler"
            if s.get("response"):
                return END
            if s.get("iteration", 0) >= max_iter:
                return END
            return "compose"

        workflow.add_conditional_edges("validate", after_validate, {
            "compose": "compose",
            "error_handler": "error_handler",
            END: END,
        })
        workflow.add_edge("compose", END)
        workflow.add_edge("error_handler", END)

        # Compile
        graph = workflow.compile()

        # Run
        result_state = await graph.ainvoke(state)
        return _format_result(result_state)

    except Exception as e:
        logger.error(f"LangGraph execution failed: {e}", exc_info=True)
        return await _run_pure_python(state, pool, max_iter)


def _format_result(state: EPCAgentState) -> dict:
    """Format the final state into an API response dict."""
    return {
        "response": state.get("response", "No response generated."),
        "intent": state.get("intent", "unknown"),
        "confidence": state.get("confidence", 0.0),
        "tool_calls": state.get("tool_calls", []),
        "sources": state.get("sources", []),
        "needs_clarification": state.get("needs_clarification", False),
        "clarification_question": state.get("clarification_question", ""),
        "fallback_used": state.get("fallback_used", False),
        "iterations": state.get("iteration", 0),
    }


def build_epc_graph():
    """Build and return a LangGraph StateGraph for the EPC agent (for testing)."""
    return run_epc_agent  # Return the main entry point for now
