from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.workflows import graph as graph_module


def make_run(risk: str = "low") -> SimpleNamespace:
    return SimpleNamespace(
        id="task-1",
        user_id="user-1",
        input_query="review the deployment plan",
        risk_level=risk,
        risk_factors=[],
        retrieval_results=[],
        final_response=None,
        current_status="pending",
        current_step="validate_input",
    )


@pytest.fixture
def patched_nodes(monkeypatch):
    async def validate(run):
        return {"current_step": "validate_input", "current_status": "retrieving"}

    async def retrieve(run):
        return {
            "current_step": "retrieve_context",
            "current_status": "assessing",
            "retrieval_results": [],
        }

    async def assess(run):
        return {
            "current_step": "assess_risk",
            "current_status": "executing",
            "risk_level": run.risk_level,
            "risk_factors": [],
        }

    async def auto(run):
        return {
            "current_step": "auto",
            "current_status": "completed",
            "final_response": "auto response",
        }

    async def complex_(run):
        return {
            "current_step": "complex",
            "current_status": "completed",
            "final_response": "complex response",
        }

    async def quality(run):
        return {"current_step": "quality", "quality_score": 0.9, "needs_refinement": False}

    async def meta(run):
        return {"current_step": "meta", "review_passed": True, "needs_regeneration": False}

    async def human(run):
        return {
            "current_step": "human_review_pending",
            "current_status": "reviewing",
            "is_human_review_needed": True,
        }

    monkeypatch.setattr(graph_module, "validate_input", validate)
    monkeypatch.setattr(graph_module, "retrieve_context_node", retrieve)
    monkeypatch.setattr(graph_module, "assess_risk", assess)
    monkeypatch.setattr(graph_module, "auto_generate_response", auto)
    monkeypatch.setattr(graph_module, "complex_analysis", complex_)
    monkeypatch.setattr(graph_module, "evaluate_output_quality", quality)
    monkeypatch.setattr(graph_module, "meta_review_node", meta)
    monkeypatch.setattr(graph_module, "human_review_node", human)


@pytest.mark.anyio
async def test_low_risk_path(patched_nodes):
    steps = await graph_module.workflow_graph.execute(make_run("low"))
    assert steps[-1]["current_status"] == "completed"
    assert steps[-1]["final_response"] == "auto response"


@pytest.mark.anyio
async def test_high_risk_react_meta_path(patched_nodes):
    steps = await graph_module.workflow_graph.execute(make_run("high"))
    names = [step["current_step"] for step in steps]
    assert "complex" in names
    assert "meta" in names
    assert steps[-1]["review_passed"] is True


@pytest.mark.anyio
async def test_critical_risk_pauses(patched_nodes):
    steps = await graph_module.workflow_graph.execute(make_run("critical"))
    assert steps[-1]["current_status"] == "reviewing"


@pytest.mark.anyio
async def test_validate_failure_short_circuits(patched_nodes, monkeypatch):
    async def failed(run):
        return {"current_step": "validate_input", "current_status": "failed"}

    monkeypatch.setattr(graph_module, "validate_input", failed)
    steps = await graph_module.workflow_graph.execute(make_run())
    assert len(steps) == 1


@pytest.mark.anyio
async def test_refinement_and_regeneration(patched_nodes, monkeypatch):
    quality_calls = {"n": 0}

    async def quality(run):
        quality_calls["n"] += 1
        return {
            "current_step": "quality",
            "quality_score": 0.2,
            "needs_refinement": quality_calls["n"] == 1,
        }

    async def meta(run):
        return {"current_step": "meta", "review_passed": False, "needs_regeneration": True}

    monkeypatch.setattr(graph_module, "evaluate_output_quality", quality)
    monkeypatch.setattr(graph_module, "meta_review_node", meta)
    steps = await graph_module.workflow_graph.execute(make_run("medium"))
    names = [step["current_step"] for step in steps]
    assert names.count("complex") >= 2
    assert names.count("meta") == 1
