from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.model_router import ModelRouter, score_confidence


class TestScoreConfidence:
    def test_empty_content_returns_zero(self) -> None:
        assert score_confidence("") == 0.0

    def test_short_content_returns_zero(self) -> None:
        assert score_confidence("Hi") == 0.0
        assert score_confidence("Short reply here") == 0.0  # 3 words, < 20 chars

    def test_uncertainty_penalty(self) -> None:
        content = "I don't know the answer to this question. I'm not sure what you mean."
        score = score_confidence(content)
        assert score < 0.7  # multiple uncertainty markers penalized

    def test_high_quality_content(self) -> None:
        content = (
            "Here is a detailed analysis of the deployment plan. "
            "In summary, the changes are safe to deploy. "
            "I recommend proceeding with the following steps: "
            "first, verify the database migration, second, update the service, "
            "third, run the smoke tests. This is a comprehensive response "
            "that covers all aspects of the request in sufficient detail "
            "to be actionable and useful for the operations team. "
            "We have verified the security impact and confirm there are "
            "no elevated risks with this deployment."
        )
        score = score_confidence(content)
        assert score >= 0.7

    def test_score_capped_at_one(self) -> None:
        """Score must never exceed 1.0 even with very long, well-structured content."""
        content = (
            "In summary, this is an excellent response. " * 20
            + "Here are the key conclusions and recommendations. " * 5
        )
        score = score_confidence(content)
        assert 0.0 <= score <= 1.0

    def test_score_capped_at_zero(self) -> None:
        """Score must never go below 0.0."""
        content = "I don't know. I'm not sure. Unable to help. I apologize. No information. Could not find."  # lots of uncertainty
        score = score_confidence(content)
        assert score >= 0.0

    def test_structure_bonus(self) -> None:
        """Content with 'summary' should get a small bonus."""
        without_summary = score_confidence(
            "Here is a basic response with moderate length and some useful information "
            "for the user to consider before making a decision about deployment."
        )
        with_summary = score_confidence(
            "Here is a basic response with moderate length and some useful information "
            "for the user to consider. In summary, the deployment should proceed safely."
        )
        # With summary should score higher than without, all else equal
        assert with_summary > without_summary


class TestSelectCascade:
    @pytest.mark.anyio
    async def test_cascade_mode_enabled_for_multi_model_tier(self) -> None:
        router = ModelRouter()
        from app.services.cost_governor import BudgetTier, cost_governor

        cost_governor._user_tiers["test-user"] = BudgetTier.STARTER
        with patch.object(cost_governor, "_ensure_redis", return_value=False):
            result = await router.select_cascade(
                user_id="test-user", task_complexity="fast", estimated_tokens=1000
            )
        assert result["cascade_mode"] is True
        assert len(result["models"]) >= 2
        assert result["models"][0] == "claude-haiku-3-5"

    @pytest.mark.anyio
    async def test_cascade_mode_disabled_for_single_model_tier(self) -> None:
        router = ModelRouter()
        from app.services.cost_governor import BudgetTier, cost_governor

        cost_governor._user_tiers["free-user"] = BudgetTier.FREE
        with patch.object(cost_governor, "_ensure_redis", return_value=False):
            result = await router.select_cascade(
                user_id="free-user", task_complexity="complex", estimated_tokens=5000
            )
        assert result["cascade_mode"] is False
        assert len(result["models"]) == 1

    @pytest.mark.anyio
    async def test_cascade_models_ordered_by_cost(self) -> None:
        router = ModelRouter()
        from app.services.cost_governor import BudgetTier, cost_governor

        cost_governor._user_tiers["pro-user"] = BudgetTier.PROFESSIONAL
        with patch.object(cost_governor, "_ensure_redis", return_value=False):
            result = await router.select_cascade(
                user_id="pro-user", task_complexity="medium", estimated_tokens=2000
            )
        models = result["models"]
        costs = [router.estimate_cost(m, 2000) for m in models]
        assert costs == sorted(costs)

    @pytest.mark.anyio
    async def test_cascade_for_enterprise_tier(self) -> None:
        router = ModelRouter()
        from app.services.cost_governor import BudgetTier, cost_governor

        cost_governor._user_tiers["ent-user"] = BudgetTier.ENTERPRISE
        with patch.object(cost_governor, "_ensure_redis", return_value=False):
            result = await router.select_cascade(
                user_id="ent-user", task_complexity="complex", estimated_tokens=10000
            )
        assert result["cascade_mode"] is True
        assert len(result["models"]) == 4
