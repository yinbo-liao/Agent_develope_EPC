from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.circuit_breaker import breaker_registry
from app.core.hashing import review_state_hash
from app.core.metrics import track_llm_cost
from app.models.workflow import WorkflowRun
from app.services.cost_governor import cost_governor
from app.services.llm_client import LLMClient
from app.services.model_router import model_router, score_confidence
from app.services.semantic_cache import check_cache, record_hit, record_miss, store_cache
from app.services.vector_store import retrieve_context
from app.workflows.state import RiskLevel, WorkflowStatus

# Risk pattern bias factors — adjusted by feedback from human reviewers
# Higher bias = more sensitive (false positives), lower = less sensitive (false negatives)
_pattern_biases: dict[str, float] = {}


async def validate_input(run: WorkflowRun) -> dict[str, Any]:
    query = run.input_query.strip()
    if not query:
        return {
            "current_step": "validate_input",
            "current_status": WorkflowStatus.FAILED.value,
            "risk_level": RiskLevel.CRITICAL.value,
            "error_info": "Query cannot be empty.",
        }
    return {
        "current_step": "validate_input",
        "current_status": WorkflowStatus.RETRIEVING.value,
        "updated_at": datetime.now(timezone.utc),
    }


async def retrieve_context_node(run: WorkflowRun) -> dict[str, Any]:
    results = await retrieve_context(run.input_query, top_k=5)
    return {
        "current_step": "retrieve_context",
        "current_status": WorkflowStatus.ASSESSING.value,
        "retrieval_results": results,
        "updated_at": datetime.now(timezone.utc),
    }


async def assess_risk(run: WorkflowRun) -> dict[str, Any]:
    query = run.input_query.lower()
    score = 0
    factors: list[str] = []

    critical_patterns = {
        r"\b(payment|credit.?card|ssn|social.security)\b": "Sensitive financial or personal data",
        r"\b(drop|truncate|destroy)\b": "Destructive operation requested",
        r"\b(sudo|root|superuser)\b": "Privilege escalation language",
    }
    high_patterns = {
        r"\b(delete|remove)\b": "Deletion request",
        r"\b(update|modify|alter)\b": "Modification request",
        r"\b(secret|token|password|key)\b": "Credential-related access",
    }

    for pattern, reason in critical_patterns.items():
        if re.search(pattern, query):
            bias = _pattern_biases.get(pattern, 1.0)
            score += int(50 * bias)
            factors.append(f"CRITICAL: {reason}")

    for pattern, reason in high_patterns.items():
        if re.search(pattern, query):
            bias = _pattern_biases.get(pattern, 1.0)
            score += int(20 * bias)
            factors.append(f"HIGH: {reason}")

    if run.retrieval_results:
        score += min(10, len(run.retrieval_results) * 2)

    if score >= 50:
        level = RiskLevel.CRITICAL
    elif score >= 30:
        level = RiskLevel.HIGH
    elif score >= 10:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW

    return {
        "current_step": "assess_risk",
        "current_status": WorkflowStatus.EXECUTING.value
        if level is RiskLevel.LOW
        else WorkflowStatus.REVIEWING.value
        if level is RiskLevel.CRITICAL
        else WorkflowStatus.EXECUTING.value,
        "risk_level": level.value,
        "risk_factors": factors,
        "updated_at": datetime.now(timezone.utc),
    }


def adjust_risk_bias(pattern: str, outcome: str) -> None:
    """Adjust risk pattern bias based on human review outcome.

    - If CRITICAL workflow was APPROVED: reduce bias (it was a false positive)
    - If LOW/ MEDIUM workflow FAILED: increase bias (it was a false negative)
    """
    current = _pattern_biases.get(pattern, 1.0)
    if outcome == "approved":
        _pattern_biases[pattern] = max(0.3, current - 0.1)
    elif outcome == "rejected":
        _pattern_biases[pattern] = min(2.0, current + 0.1)


async def meta_review_node(run: WorkflowRun) -> dict[str, Any]:
    """Self-review the final response using a different model for adversarial critique.

    Returns a dict with 'review_passed' (bool) and 'review_feedback' (str).
    If review fails, triggers re-generation via the 'needs_regeneration' flag.
    """
    content = run.final_response or ""
    if not content:
        return {
            "current_step": "meta_review",
            "review_passed": False,
            "review_feedback": "Empty response — regeneration required.",
            "needs_regeneration": True,
            "updated_at": datetime.now(timezone.utc),
        }

    # Use a different model/prompt for the review (adversarial check)
    reviewer_model = "claude-haiku-3-5"  # cheap model for review
    review_prompt = (
        f"Review the following response for correctness, completeness, and safety.\n\n"
        f"Original query: {run.input_query}\n\n"
        f"Response to review:\n{content[:1000]}\n\n"
        f"Check for:\n"
        f"1. Hallucinations or factual errors\n"
        f"2. Missing critical information\n"
        f"3. Unsafe or harmful recommendations\n"
        f"4. Contradictions or logical gaps\n\n"
        f"Is this response acceptable? Answer YES or NO and explain briefly."
    )

    breaker = breaker_registry.get_llm_breaker(reviewer_model)
    try:
        async with breaker:
            review_response = await LLMClient.generate(
                prompt=review_prompt,
                context=run.retrieval_results or [],
                max_tokens=256,
                temperature=0.0,
                model=reviewer_model,
            )
    except RuntimeError:
        # Circuit breaker open — skip review
        return {
            "current_step": "meta_review",
            "review_passed": True,
            "review_feedback": "Meta-review skipped (circuit breaker open).",
            "needs_regeneration": False,
            "updated_at": datetime.now(timezone.utc),
        }

    review_text = review_response.get("content", "").lower()
    passed = "yes" in review_text[:10]  # first word should indicate judgment

    return {
        "current_step": "meta_review",
        "review_passed": passed,
        "review_feedback": review_response.get("content", ""),
        "needs_regeneration": not passed,
        "updated_at": datetime.now(timezone.utc),
    }


def get_risk_biases() -> dict[str, float]:
    """Return current risk bias factors for observability."""
    return dict(_pattern_biases)


async def evaluate_output_quality(run: WorkflowRun) -> dict[str, Any]:
    """Evaluate the quality of the current response and decide if refinement is needed.

    Uses heuristic scoring to determine if the response is adequate.
    Returns a dict with 'quality_score' (0.0-1.0) and 'needs_refinement' (bool).
    """
    content = run.final_response or ""

    if not content or len(content.strip()) < 20:
        return {
            "current_step": "evaluate_quality",
            "quality_score": 0.0,
            "needs_refinement": True,
            "updated_at": datetime.now(timezone.utc),
        }

    score = 1.0

    # Completeness: does response length match query complexity?
    query_words = len(run.input_query.split())
    response_words = len(content.split())
    if response_words < query_words * 0.5:
        score -= 0.3

    # Coherence: check for contradiction markers
    lowered = content.lower()
    contradiction_markers = ["however", "on the other hand", "but actually", "contrary"]
    if sum(1 for m in contradiction_markers if m in lowered) > 2:
        score -= 0.15

    # Grounding: does response reference the context?
    if run.retrieval_results:
        has_reference = any(
            str(item.get("snippet", ""))[:30].lower() in lowered
            for item in run.retrieval_results
        )
        if not has_reference:
            score -= 0.2

    # Actionability: does response contain concrete steps?
    actionable_markers = ["step", "recommend", "should", "you can", "try to"]
    if not any(m in lowered for m in actionable_markers):
        score -= 0.1

    needs_refinement = score < 0.5
    return {
        "current_step": "evaluate_quality",
        "quality_score": max(0.0, min(1.0, score)),
        "needs_refinement": needs_refinement,
        "updated_at": datetime.now(timezone.utc),
    }


async def auto_generate_response(run: WorkflowRun) -> dict[str, Any]:
    max_tokens = max(256, run.token_budget - run.total_tokens_used)
    model_choice = await model_router.select_model(
        user_id=run.user_id,
        task_complexity="fast",
        estimated_tokens=max_tokens,
    )
    estimated_cost = float(model_choice["estimated_cost"])
    allowed, budget_status = await cost_governor.reserve_budget(
        run.user_id, estimated_tokens=max_tokens, estimated_cost=estimated_cost
    )
    if not allowed:
        return {
            "current_step": "budget_guard",
            "current_status": WorkflowStatus.FAILED.value,
            "error_info": str(budget_status.get("reason", "Budget check failed")),
            "updated_at": datetime.now(timezone.utc),
        }

    model_name = str(model_choice["model"])

    # Check semantic cache before generating
    cached_response = await check_cache(run.input_query, model_name, run.user_id, run.risk_level)
    if cached_response is not None:
        record_hit()
        cached_tokens = int(cached_response.get("tokens_used", 0))
        await cost_governor.commit_usage(
            user_id=run.user_id,
            task_id=run.id,
            reserved_tokens=max_tokens,
            reserved_cost=estimated_cost,
            actual_tokens=cached_tokens,
            actual_cost=0.0,
            model=model_name,
        )
        return {
            "current_step": "auto_generate_response",
            "current_status": WorkflowStatus.COMPLETED.value,
            "final_response": cached_response.get("content", ""),
            "agent_finding": f"Cached response served (model={model_name}).",
            "total_tokens_used": run.total_tokens_used + cached_tokens,
            "cost_usd": round(run.cost_usd, 6),
            "completed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    record_miss()

    breaker = breaker_registry.get_llm_breaker(model_name)
    try:
        async with breaker:
            response = await LLMClient.generate(
                prompt=run.input_query,
                context=run.retrieval_results or [],
                max_tokens=max_tokens,
                temperature=0.2,
                model=model_name,
            )
    except Exception:
        # Release the reservation: nothing was consumed.
        await cost_governor.commit_usage(
            user_id=run.user_id,
            task_id=run.id,
            reserved_tokens=max_tokens,
            reserved_cost=estimated_cost,
            actual_tokens=0,
            actual_cost=0.0,
            model=model_name,
        )
        raise

    await cost_governor.commit_usage(
        user_id=run.user_id,
        task_id=run.id,
        reserved_tokens=max_tokens,
        reserved_cost=estimated_cost,
        actual_tokens=int(response["tokens_used"]),
        actual_cost=float(response["cost_usd"]),
        model=str(response["model"]),
    )
    track_llm_cost(str(response["model"]), float(response["cost_usd"]))

    # Store in semantic cache for future reuse
    await store_cache(
        run.input_query,
        model_name,
        response,
        scope=run.user_id,
        risk_level=run.risk_level,
    )

    return {
        "current_step": "auto_generate_response",
        "current_status": WorkflowStatus.COMPLETED.value,
        "final_response": response["content"],
        "agent_finding": f"Direct response generated in low-risk path with {response['model']}.",
        "total_tokens_used": run.total_tokens_used + response["tokens_used"],
        "cost_usd": round(run.cost_usd + response["cost_usd"], 6),
        "completed_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


async def complex_analysis(run: WorkflowRun) -> dict[str, Any]:
    max_tokens = max(512, run.token_budget - run.total_tokens_used)
    complexity = "complex" if run.risk_level == RiskLevel.HIGH.value else "medium"
    cascade = await model_router.select_cascade(
        user_id=run.user_id,
        task_complexity=complexity,
        estimated_tokens=max_tokens,
    )

    cascade_models = cascade.get("models", [cascade["model"]])
    last_response: dict[str, Any] | None = None

    for attempt, model_name in enumerate(cascade_models[:3]):  # max 3 tiers
        estimated_cost = model_router.estimate_cost(model_name, max_tokens)
        allowed, budget_status = await cost_governor.reserve_budget(
            run.user_id, estimated_tokens=max_tokens, estimated_cost=estimated_cost
        )
        if not allowed:
            if last_response is not None:
                break  # Use last successful response
            return {
                "current_step": "budget_guard",
                "current_status": WorkflowStatus.FAILED.value,
                "error_info": str(budget_status.get("reason", "Budget check failed")),
                "updated_at": datetime.now(timezone.utc),
            }

        breaker = breaker_registry.get_llm_breaker(model_name)
        try:
            async with breaker:
                response = await LLMClient.generate(
                    prompt=f"Provide a more careful operational analysis for: {run.input_query}",
                    context=run.retrieval_results or [],
                    max_tokens=max_tokens,
                    temperature=0.1,
                    model=model_name,
                )
        except RuntimeError:  # circuit breaker open
            await cost_governor.commit_usage(
                user_id=run.user_id,
                task_id=run.id,
                reserved_tokens=max_tokens,
                reserved_cost=estimated_cost,
                actual_tokens=0,
                actual_cost=0.0,
                model=model_name,
            )
            continue
        except Exception:
            await cost_governor.commit_usage(
                user_id=run.user_id,
                task_id=run.id,
                reserved_tokens=max_tokens,
                reserved_cost=estimated_cost,
                actual_tokens=0,
                actual_cost=0.0,
                model=model_name,
            )
            raise

        confidence = score_confidence(response["content"])

        await cost_governor.commit_usage(
            user_id=run.user_id,
            task_id=run.id,
            reserved_tokens=max_tokens,
            reserved_cost=estimated_cost,
            actual_tokens=int(response["tokens_used"]),
            actual_cost=float(response["cost_usd"]),
            model=str(response["model"]),
        )
        track_llm_cost(str(response["model"]), float(response["cost_usd"]))
        last_response = response

        # If confidence is high enough, stop escalating
        if confidence >= 0.7 or attempt == len(cascade_models) - 1:
            return {
                "current_step": "complex_analysis",
                "current_status": WorkflowStatus.COMPLETED.value,
                "final_response": response["content"],
                "agent_finding": (
                    f"Cascade analysis tier {attempt + 1} "
                    f"(model={response['model']}, confidence={confidence:.2f})."
                ),
                "total_tokens_used": run.total_tokens_used + response["tokens_used"],
                "cost_usd": round(run.cost_usd + response["cost_usd"], 6),
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

    # All cascade tiers exhausted
    if last_response is not None:
        return {
            "current_step": "complex_analysis",
            "current_status": WorkflowStatus.COMPLETED.value,
            "final_response": last_response["content"],
            "agent_finding": "Cascade analysis completed with fallback model.",
            "total_tokens_used": run.total_tokens_used + last_response["tokens_used"],
            "cost_usd": round(run.cost_usd + last_response["cost_usd"], 6),
            "completed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    return {
        "current_step": "complex_analysis",
        "current_status": WorkflowStatus.FAILED.value,
        "error_info": "All cascade tiers unavailable.",
        "updated_at": datetime.now(timezone.utc),
    }


async def human_review_node(run: WorkflowRun) -> dict[str, Any]:
    if run.human_decision == "approved":
        return {
            "current_step": "human_review_approved",
            "current_status": WorkflowStatus.COMPLETED.value,
            "is_human_review_needed": False,
            "final_response": (
                "Human review approved the task. Execution can continue in later waves "
                "with tool orchestration and live transport."
            ),
            "agent_finding": "Human reviewer approved the workflow.",
            "completed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    if run.human_decision == "rejected":
        return {
            "current_step": "human_review_rejected",
            "current_status": WorkflowStatus.CANCELLED.value,
            "is_human_review_needed": False,
            "error_info": "Human review rejected the request.",
            "completed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    return {
        "current_step": "human_review_pending",
        "current_status": WorkflowStatus.REVIEWING.value,
        "is_human_review_needed": True,
        "review_deadline": datetime.now(timezone.utc) + timedelta(minutes=30),
        "review_state_hash": review_state_hash(run),
        "updated_at": datetime.now(timezone.utc),
    }
