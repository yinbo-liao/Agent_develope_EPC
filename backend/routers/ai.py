"""AI Insights router — expose AI engine capabilities via REST API.

Endpoints:
  GET  /api/ai/status              — AI engine status + available features
  POST /api/ai/analyze/{pid}       — Run traditional analysis (schedule, conflict, gate, report)
  GET  /api/ai/insights/{pid}      — Get stored AI insights for a project
  POST /api/ai/chat/{pid}          — RAG-powered conversational AI chat
  GET  /api/ai/sessions/{pid}      — List AI chat sessions for a project
  GET  /api/ai/sessions/{pid}/{sid}— Get session messages
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional
from database import get_db
from services.ai_engine import ai_engine, broadcast_ai_insight
from errors import bad_request, not_found

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AIAnalysisRequest(BaseModel):
    analysis_type: str  # schedule_risk, conflict_detection, gate_assessment, weekly_report
    gate_id: Optional[str] = None
    week_end: Optional[date] = None


class AIChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None  # Resume existing session or create new


@router.get("/status")
async def ai_status():
    """Check if AI engine is enabled and configured."""
    from services.llm_provider import llm_provider
    import services.tools.query_tools  # noqa: F401 — triggers tool registrations
    from services.tools.registry import tool_registry

    return {
        "enabled": ai_engine.enabled or llm_provider.enabled,
        "primary_provider": "deepseek" if llm_provider.deepseek else None,
        "fallback_provider": "anthropic" if llm_provider.anthropic else None,
        "model": (
            "deepseek+claude" if (llm_provider.deepseek and llm_provider.anthropic)
            else "deepseek" if llm_provider.deepseek
            else "claude" if llm_provider.anthropic
            else "rule_based"
        ),
        "features": [
            "schedule_risk_analysis",
            "conflict_detection",
            "stage_gate_assessment",
            "weekly_report_composer",
            "rag_chat",
            "kpi_calculation",
            "natural_language_query",
        ],
        "available_tools": tool_registry.list_tools(),
    }


@router.post("/analyze/{project_id}")
async def run_analysis(project_id: str, request: AIAnalysisRequest, db: AsyncSession = Depends(get_db)):
    """Run an AI analysis on the project and return insights."""
    # Access the unified asyncpg pool for the AI engine
    from db import get_pool
    pool = await get_pool()

    if request.analysis_type == "schedule_risk":
        result = await ai_engine.analyze_schedule_risk(project_id, pool)
        await broadcast_ai_insight(project_id, "schedule_risk", result)
        return result

    elif request.analysis_type == "conflict_detection":
        conflicts = await ai_engine.detect_conflicts(project_id, pool)
        # Save detected conflicts to database
        for c in conflicts:
            await db.execute(
                text("""INSERT INTO conflicts (conflict_id, project_id, conflict_type, title, description,
                         severity, detected_by_agent, ai_confidence, ai_recommendation)
                        VALUES (gen_random_uuid(), :pid, :ctype, :title, :desc, :sev, TRUE, :conf, :rec)"""),
                {"pid": project_id, "ctype": c.get("conflict_type", "OTHER"),
                 "title": c.get("title", ""), "desc": c.get("description", ""),
                 "sev": c.get("severity", "MEDIUM"), "conf": c.get("confidence", 0.5),
                 "rec": c.get("recommended_action", "")}
            )
        await db.commit()
        await broadcast_ai_insight(project_id, "conflicts_detected", {"count": len(conflicts)})
        return {"conflicts_found": len(conflicts), "conflicts": conflicts}

    elif request.analysis_type == "gate_assessment":
        if not request.gate_id:
            raise bad_request("gate_id required for gate_assessment")
        result = await ai_engine.assess_stage_gate(project_id, request.gate_id, pool)
        # Update the gate's AI score
        if "ai_readiness_score" in result:
            await db.execute(
                text("UPDATE stage_gates SET ai_readiness_score = :score WHERE gate_id = :gid"),
                {"score": result["ai_readiness_score"], "gid": request.gate_id}
            )
            await db.commit()
        await broadcast_ai_insight(project_id, "gate_assessment", result)
        return result

    elif request.analysis_type == "weekly_report":
        if not request.week_end:
            request.week_end = date.today()
        report = await ai_engine.compose_weekly_report(project_id, request.week_end, pool)
        return {"report": report, "week_end": request.week_end.isoformat()}

    else:
        raise bad_request(f"Unknown analysis_type: {request.analysis_type}")


@router.get("/insights/{project_id}")
async def get_insights(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get all AI-detected insights (conflicts, recommendations) for a project."""
    conflicts = await db.execute(
        text("SELECT * FROM conflicts WHERE project_id = :pid AND detected_by_agent = TRUE ORDER BY created_at DESC LIMIT 50"),
        {"pid": project_id}
    )
    feedback = await db.execute(
        text("SELECT * FROM feedback_loop WHERE project_id = :pid AND ai_generated_assessment = TRUE ORDER BY created_at DESC LIMIT 50"),
        {"pid": project_id}
    )
    gate_scores = await db.execute(
        text("SELECT gate_name, from_phase, to_phase, ai_readiness_score, status FROM stage_gates WHERE project_id = :pid AND ai_readiness_score IS NOT NULL ORDER BY gate_sequence"),
        {"pid": project_id}
    )
    return {
        "ai_detected_conflicts": [dict(r._mapping) for r in conflicts],
        "ai_assessed_feedback": [dict(r._mapping) for r in feedback],
        "gate_readiness_scores": [dict(r._mapping) for r in gate_scores],
    }


# ── RAG Chat Endpoint ────────────────────────────────────────────────────

@router.post("/chat/{project_id}")
async def ai_chat(project_id: str, request: AIChatRequest, db: AsyncSession = Depends(get_db)):
    """
    RAG-powered conversational AI chat.

    Uses the LangGraph agent with function tools to answer natural language
    queries about the project. The agent:
    1. Classifies the query intent
    2. Selects relevant database-query tools
    3. Executes tools against project data
    4. Composes a natural language response

    All data sources are limited to the project database.
    """
    from db import get_pool
    from services.langgraph.graph import run_epc_agent
    import services.tools.query_tools  # noqa: F401 — triggers tool registrations

    pool = await get_pool()

    # Run the EPC agent
    result = await run_epc_agent(
        user_query=request.query,
        project_id=project_id,
        pool=pool,
        user_id="anonymous",  # TODO: use actual auth user
    )

    # Save session and message if session_id provided
    session_id = request.session_id
    if not session_id:
        # Create new session
        session_result = await db.execute(
            text("""INSERT INTO ai_sessions (session_id, project_id, title, model_used)
                    VALUES (gen_random_uuid(), :pid, :title, :model)
                    RETURNING session_id"""),
            {"pid": project_id, "title": request.query[:200],
             "model": result.get("intent", "rule_based")}
        )
        row = session_result.fetchone()
        if row:
            session_id = str(row._mapping["session_id"])
        await db.commit()

    if session_id:
        # Save user message
        await db.execute(
            text("""INSERT INTO ai_messages (message_id, session_id, role, content)
                    VALUES (gen_random_uuid(), :sid, 'user', :content)"""),
            {"sid": session_id, "content": request.query}
        )
        # Save assistant response
        await db.execute(
            text("""INSERT INTO ai_messages (message_id, session_id, role, content, tool_calls)
                    VALUES (gen_random_uuid(), :sid, 'assistant', :content, :tool_calls::jsonb)"""),
            {"sid": session_id, "content": result.get("response", ""),
             "tool_calls": str(result.get("tool_calls", []))}
        )
        await db.commit()

    return {
        "session_id": session_id,
        "query": request.query,
        "response": result.get("response", ""),
        "intent": result.get("intent", "unknown"),
        "confidence": result.get("confidence", 0.0),
        "tool_calls": result.get("tool_calls", []),
        "sources": result.get("sources", []),
        "fallback_used": result.get("fallback_used", False),
        "iterations": result.get("iterations", 0),
    }


# ── Session Management ───────────────────────────────────────────────────

@router.get("/sessions/{project_id}")
async def list_sessions(project_id: str, db: AsyncSession = Depends(get_db)):
    """List AI chat sessions for a project."""
    result = await db.execute(
        text("""SELECT session_id, title, model_used, created_at, updated_at
                FROM ai_sessions WHERE project_id = :pid
                ORDER BY updated_at DESC LIMIT 50"""),
        {"pid": project_id}
    )
    return [dict(r._mapping) for r in result]


@router.get("/sessions/{project_id}/{session_id}")
async def get_session(project_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    """Get all messages for an AI chat session."""
    # Verify session belongs to project
    session = await db.execute(
        text("SELECT * FROM ai_sessions WHERE session_id = :sid AND project_id = :pid"),
        {"sid": session_id, "pid": project_id}
    )
    if not session.fetchone():
        raise not_found("AI session", session_id)

    messages = await db.execute(
        text("""SELECT role, content, tool_calls, created_at
                FROM ai_messages WHERE session_id = :sid
                ORDER BY created_at"""),
        {"sid": session_id}
    )
    return [dict(r._mapping) for r in messages]


@router.delete("/sessions/{project_id}/{session_id}")
async def delete_session(project_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an AI chat session."""
    result = await db.execute(
        text("DELETE FROM ai_sessions WHERE session_id = :sid AND project_id = :pid"),
        {"sid": session_id, "pid": project_id}
    )
    await db.commit()
    return {"status": "deleted"}
