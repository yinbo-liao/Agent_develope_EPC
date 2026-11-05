from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.workflow import WorkflowRun
from app.services.feedback_analyzer import analyze_workflow_patterns
from app.services.llm_client import LLMClient
from app.services.prompt_compressor import (
    compress_context,
    compress_prompt,
    estimate_prompt_tokens,
)
from app.services.vector_store import retrieve_context


def test_compress_context_limits_and_truncates() -> None:
    results = [
        {"snippet": "a" * 300, "source": "s"},
        {"snippet": "short", "source": "s"},
        {"snippet": "third", "source": "s"},
        {"snippet": "fourth", "source": "s"},
    ]
    compressed = compress_context(results, max_items=2, max_chars=20)
    assert len(compressed) == 2
    assert compressed[0]["snippet"].endswith("...")
    assert len(compressed[0]["snippet"]) == 20
    assert compress_context(None) == []


def test_compress_prompt_and_token_estimate() -> None:
    assert compress_prompt("short") == "short"
    long = compress_prompt("x" * 100, max_query_chars=10)
    assert long.endswith("...") and len(long) == 10
    assert estimate_prompt_tokens("one two three", [{"snippet": "four five"}]) >= 1


@pytest.mark.anyio
async def test_llm_client_simulated_generation() -> None:
    response = await LLMClient.generate(
        "hello",
        context=[{"snippet": "context"}],
        max_tokens=100,
        model="claude-haiku-3-5",
    )
    assert response["model"] == "claude-haiku-3-5"
    assert response["tokens_used"] <= 100
    assert "context" in response["content"]

    empty = await LLMClient.generate("hello", context=None)
    assert "No additional context" in empty["content"]


@pytest.mark.anyio
async def test_vector_store_keywords() -> None:
    results = await retrieve_context("security deployment database", top_k=2)
    assert len(results) == 2
    assert results[0]["source"] == "keyword-index"
    assert await retrieve_context("nothing relevant") == []


@pytest.mark.anyio
async def test_feedback_analyzer(async_client):
    from app.core.database import SessionLocal

    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        session.add_all(
            [
                WorkflowRun(
                    id="failed-1",
                    user_id="u",
                    input_query="q",
                    current_status="failed",
                    error_info="timeout while calling model",
                    created_at=now,
                ),
                WorkflowRun(
                    id="critical-1",
                    user_id="u",
                    input_query="q",
                    current_status="completed",
                    risk_level="critical",
                    human_decision="approved",
                    created_at=now,
                ),
            ]
        )
        await session.commit()

    async with SessionLocal() as session:
        report = await analyze_workflow_patterns(session, hours=24)
    assert report["workflows"]["total"] >= 2
    assert report["workflows"]["failed"] >= 1
    assert report["risk_accuracy"]["false_positives"] >= 1
    assert report["common_errors"].get("timeout") == 1
    assert report["insights"]