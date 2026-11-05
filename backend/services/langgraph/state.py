"""
LangGraph State — TypedDict defining the EPC Agent state machine.

The agent cycles through: classify → route → execute → validate → compose
with human-in-the-loop checkpoints at validate step.
"""

from typing import TypedDict, Annotated
from services.llm_provider import ChatMessage, ToolCall


class EPCAgentState(TypedDict, total=False):
    """State for the EPC AI agent's LangGraph state machine."""

    # Conversation
    messages: list[dict]              # Full conversation history (serialized ChatMessages)
    user_query: str                    # Original user question
    project_id: str                    # Current project context
    user_id: str                       # Authenticated user ID

    # Workflow control
    intent: str                        # query, analysis, report, action, chat
    confidence: float                  # 0-1 confidence score for the intent classification
    iteration: int                     # Current iteration (prevents infinite loops)

    # Tool execution
    selected_tools: list[str]          # Tool names selected for execution
    tool_calls: list[dict]             # Pending tool calls
    tool_results: list[dict]           # Executed tool results

    # Response
    context: str                       # Assembled context from tool results for the LLM
    response: str                      # Final natural language response
    sources: list[dict]                # Data sources used (tool name + row count)

    # Error handling
    error: str | None                  # Error message if something went wrong
    needs_clarification: bool          # True if the agent needs to ask the user for clarification
    clarification_question: str        # Question to ask the user
    fallback_used: bool                # True if fallback (rule-based) was used
