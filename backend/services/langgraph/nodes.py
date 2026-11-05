"""
LangGraph Nodes — individual processing steps in the EPC Agent state machine.

Node functions:
  classify_intent    — determine what the user wants (query/analysis/report/action/chat)
  route_to_tools     — select which tools to call based on intent and query
  execute_tools      — run selected tools against the database
  validate_results   — check tool results for completeness and quality
  compose_response   — send context + results to LLM for final response
  handle_error       — graceful degradation with rule-based fallback
"""

import json
import logging
from datetime import date
from services.llm_provider import ChatMessage, llm_provider
from services.langgraph.state import EPCAgentState

logger = logging.getLogger(__name__)

# ── Intent Classification Keywords ────────────────────────────────────────

INTENT_PATTERNS = {
    "query": ["show", "list", "find", "get", "what", "how many", "count", "display", "search"],
    "analysis": ["analyze", "assess", "evaluate", "risk", "trend", "compare", "predict", "bottleneck"],
    "report": ["report", "summarize", "summary", "generate report", "weekly", "monthly"],
    "action": ["create", "update", "delete", "approve", "reject", "resolve", "assign"],
}

TOOL_SELECTION_MAP = {
    "activity": ["query_activities"],
    "schedule": ["query_activities"],
    "drawing": ["query_drawings"],
    "engineering": ["query_drawings"],
    "procurement": ["query_procurement"],
    "purchase": ["query_procurement"],
    "material": ["query_procurement"],
    "quality": ["query_quality_ncr"],
    "ncr": ["query_quality_ncr"],
    "safety": ["query_safety_incidents"],
    "incident": ["query_safety_incidents"],
    "hse": ["query_safety_incidents"],
    "training": ["query_training_records"],
    "certification": ["query_training_records"],
    "personnel": ["query_training_records"],
    "gate": ["query_stage_gates"],
    "stage": ["query_stage_gates"],
    "phase": ["query_stage_gates"],
    "conflict": ["query_conflicts"],
    "clash": ["query_conflicts"],
    "traceability": ["query_traceability"],
    "trace": ["query_traceability"],
    "impact": ["query_traceability"],
    "chain": ["query_traceability"],
    "kpi": ["calculate_kpi"],
    "progress": ["calculate_kpi"],
    "metric": ["calculate_kpi"],
    "performance": ["calculate_kpi"],
    "report": ["generate_report", "calculate_kpi"],
}


# ── Node Functions ────────────────────────────────────────────────────────

async def classify_intent(state: EPCAgentState) -> EPCAgentState:
    """Classify the user's intent from their query text."""
    query = state.get("user_query", "").lower()

    scores = {}
    for intent, keywords in INTENT_PATTERNS.items():
        scores[intent] = sum(1 for kw in keywords if kw in query)

    if scores:
        best = max(scores, key=scores.get)
        if scores[best] > 0:
            state["intent"] = best
            state["confidence"] = min(scores[best] / 5, 1.0)
        else:
            state["intent"] = "chat"
            state["confidence"] = 0.5
    else:
        state["intent"] = "chat"
        state["confidence"] = 0.3

    state["iteration"] = state.get("iteration", 0) + 1
    return state


async def route_to_tools(state: EPCAgentState) -> EPCAgentState:
    """Select tools based on intent and query content."""
    query = state.get("user_query", "").lower()
    selected = set()

    # Always include KPI for context if doing analysis or report
    if state.get("intent") in ("analysis", "report"):
        selected.add("calculate_kpi")

    # Match keywords to tools
    for keyword, tools in TOOL_SELECTION_MAP.items():
        if keyword in query:
            selected.update(tools)

    # If nothing matched, use these defaults based on intent
    if not selected:
        if state.get("intent") == "query":
            selected = {"query_activities", "calculate_kpi"}
        elif state.get("intent") == "analysis":
            selected = {"query_activities", "query_conflicts", "calculate_kpi"}
        elif state.get("intent") == "report":
            selected = {"generate_report", "calculate_kpi"}
        else:
            selected = {"calculate_kpi"}

    state["selected_tools"] = list(selected)
    return state


async def execute_tools(state: EPCAgentState, pool) -> EPCAgentState:
    """Execute selected tools against the database."""
    from services.tools.registry import tool_registry

    tool_results = []
    tool_calls = []

    for tool_name in state.get("selected_tools", []):
        kwargs = {"pool": pool, "project_id": state.get("project_id", "")}
        result = await tool_registry.execute(tool_name, **kwargs)
        tool_results.append({
            "tool": tool_name,
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "row_count": result.row_count,
            "query_time_ms": result.query_time_ms,
        })
        tool_calls.append({
            "name": tool_name,
            "args": {"project_id": state.get("project_id")},
            "result_summary": f"{result.row_count} rows in {result.query_time_ms:.0f}ms" if result.success else f"Error: {result.error}",
        })

    state["tool_results"] = tool_results
    state["tool_calls"] = tool_calls
    state["sources"] = [
        {"tool": r["tool"], "row_count": r["row_count"], "success": r["success"]}
        for r in tool_results
    ]
    return state


async def validate_results(state: EPCAgentState) -> EPCAgentState:
    """Validate tool results. Route: valid→compose, incomplete→retry, error→handle_error."""
    results = state.get("tool_results", [])

    if not results:
        state["error"] = "No tools were executed"
        state["fallback_used"] = True
        return state

    # Check if all tools failed
    all_failed = all(not r["success"] for r in results)
    if all_failed:
        errors = [r["error"] for r in results if r["error"]]
        state["error"] = f"All tools failed: {'; '.join(errors)}"
        state["fallback_used"] = True
        return state

    # Check if we got useful data
    total_rows = sum(r.get("row_count", 0) for r in results if r["success"])
    if total_rows == 0 and state.get("intent") in ("query", "analysis"):
        state["needs_clarification"] = True
        state["clarification_question"] = "No data was found for your query. The project may not have records in the requested areas. Would you like to try a different query or check another project?"

    return state


async def compose_response(state: EPCAgentState) -> EPCAgentState:
    """Assemble context from tool results and generate a natural language response."""
    # Build context from tool results
    context_parts = []
    for r in state.get("tool_results", []):
        if r["success"] and r["data"] is not None:
            data = r["data"]
            if isinstance(data, list):
                context_parts.append(f"[{r['tool']} returned {r['row_count']} rows]: {json.dumps(data[:5], default=str)}")
            else:
                context_parts.append(f"[{r['tool']}]: {json.dumps(data, default=str)}")
        elif r.get("error"):
            context_parts.append(f"[{r['tool']} error]: {r['error']}")

    context = "\n\n".join(context_parts)
    state["context"] = context

    # Try LLM for response composition
    if llm_provider.enabled:
        try:
            system_prompt = (
                "You are an EPC project management AI assistant. Analyze the database query "
                "results and provide a clear, concise, professional response. "
                "Focus on actionable insights. If data seems incomplete, note that. "
                "Format numbers clearly. Use bullet points for lists. "
                "Always mention which data sources (tools) your answer is based on."
            )
            messages = [
                ChatMessage(role="user", content=(
                    f"User query: {state.get('user_query', 'N/A')}\n\n"
                    f"Database query results:\n{context}\n\n"
                    f"Provide a comprehensive answer to the user's query based on these results."
                ))
            ]
            response = await llm_provider.chat(messages, system=system_prompt)
            if response.content and not response.error:
                state["response"] = response.content
                return state
        except Exception as e:
            logger.warning(f"LLM response composition failed: {e}")

    # Rule-based fallback response
    state["fallback_used"] = True
    parts = [f"Here's what I found for: **{state.get('user_query', 'your query')}**\n"]

    for r in state.get("tool_results", []):
        if r["success"]:
            parts.append(f"\n**{r['tool'].replace('_', ' ').title()}** ({r['row_count']} results, {r['query_time_ms']:.0f}ms):")
            data = r["data"]
            if isinstance(data, list) and data:
                for item in data[:5]:
                    if isinstance(item, dict):
                        parts.append(f"  • {json.dumps(item, default=str)[:200]}")
            elif isinstance(data, dict):
                parts.append(f"  {json.dumps(data, default=str)[:500]}")
        else:
            parts.append(f"\n**{r['tool']}**: Error — {r.get('error', 'Unknown error')}")

    state["response"] = "\n".join(parts)
    return state


async def handle_error(state: EPCAgentState) -> EPCAgentState:
    """Handle errors gracefully with a user-friendly message."""
    error = state.get("error", "An unknown error occurred")
    state["fallback_used"] = True
    state["response"] = (
        f"I encountered an issue processing your request: **{error}**\n\n"
        f"Please try rephrasing your query or checking that the project has data in the requested areas. "
        f"You can ask me about: project KPIs, schedule activities, drawings, procurement, "
        f"quality/NCRs, safety incidents, training, stage gates, conflicts, or traceability."
    )
    return state
