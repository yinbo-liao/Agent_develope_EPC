from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class BudgetTier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class BudgetConfig:
    tier: BudgetTier
    daily_token_limit: int
    daily_cost_limit_usd: float
    max_concurrent_workflows: int
    allowed_models: list[str]


BUDGET_CONFIGS = {
    BudgetTier.FREE: BudgetConfig(
        tier=BudgetTier.FREE,
        daily_token_limit=10_000,
        daily_cost_limit_usd=1.0,
        max_concurrent_workflows=1,
        allowed_models=["claude-haiku-3-5"],
    ),
    BudgetTier.STARTER: BudgetConfig(
        tier=BudgetTier.STARTER,
        daily_token_limit=100_000,
        daily_cost_limit_usd=10.0,
        max_concurrent_workflows=3,
        allowed_models=["claude-haiku-3-5", "claude-sonnet-4-6"],
    ),
    BudgetTier.PROFESSIONAL: BudgetConfig(
        tier=BudgetTier.PROFESSIONAL,
        daily_token_limit=1_000_000,
        daily_cost_limit_usd=100.0,
        max_concurrent_workflows=10,
        allowed_models=["claude-haiku-3-5", "claude-sonnet-4-6", "claude-opus-4-6"],
    ),
    BudgetTier.ENTERPRISE: BudgetConfig(
        tier=BudgetTier.ENTERPRISE,
        daily_token_limit=10_000_000,
        daily_cost_limit_usd=1000.0,
        max_concurrent_workflows=50,
        allowed_models=["claude-haiku-3-5", "claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o"],
    ),
}


RESERVE_SCRIPT = """
local tokens = tonumber(redis.call('GET', KEYS[1]) or '0')
local cost = tonumber(redis.call('GET', KEYS[2]) or '0')
local est_tokens = tonumber(ARGV[1])
local est_cost = tonumber(ARGV[2])
local max_tokens = tonumber(ARGV[3])
local max_cost = tonumber(ARGV[4])
if tokens + est_tokens > max_tokens then
  return {0, tokens, cost, 'Daily token limit exceeded'}
end
if cost + est_cost > max_cost then
  return {0, tokens, cost, 'Daily cost limit exceeded'}
end
redis.call('INCRBY', KEYS[1], est_tokens)
redis.call('INCRBYFLOAT', KEYS[2], est_cost)
redis.call('EXPIRE', KEYS[1], 172800)
redis.call('EXPIRE', KEYS[2], 172800)
return {1, tokens + est_tokens, cost + est_cost, ''}
"""


class CostGovernor:
    """Cost governance with Redis persistence and in-memory fallback."""

    def __init__(self, redis_url: str = settings.REDIS_URL) -> None:
        self.redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._redis_available: bool = False
        # In-memory fallback
        self._user_tiers: dict[str, BudgetTier] = {}
        self._usage: dict[tuple[str, str], dict[str, object]] = {}
        self._lock = asyncio.Lock()

    async def _ensure_redis(self) -> bool:
        """Lazy-init Redis connection. Returns True if Redis is available."""
        if self._redis is not None:
            return self._redis_available
        try:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self._redis_available = True
            logger.info("Cost governor connected to Redis")
        except Exception:
            self._redis_available = False
            logger.warning("Redis unavailable; cost governor using in-memory fallback")
        return self._redis_available

    def set_tier(self, user_id: str, tier: str) -> None:
        """Hydrate the in-process tier from the authenticated user record."""
        try:
            self._user_tiers[user_id] = BudgetTier(tier)
        except ValueError:
            self._user_tiers[user_id] = BudgetTier.STARTER

    def get_budget_config(self, user_id: str) -> BudgetConfig:
        tier = self._user_tiers.get(user_id, BudgetTier.STARTER)
        return BUDGET_CONFIGS[tier]

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _usage_key(self, user_id: str) -> tuple[str, str]:
        return user_id, self._today()

    def _current_usage(self, user_id: str) -> dict[str, object]:
        key = self._usage_key(user_id)
        if key not in self._usage:
            self._usage[key] = {
                "tokens": 0,
                "cost": 0.0,
                "models": {},
                "alerts": [],
                "updated_at": datetime.now(timezone.utc),
            }
        return self._usage[key]

    async def _redis_usage(self, user_id: str) -> dict[str, object]:
        """Read current usage from Redis, or return empty defaults."""
        today = self._today()
        token_key = f"usage:{user_id}:{today}:tokens"
        cost_key = f"usage:{user_id}:{today}:cost"
        model_key = f"usage:{user_id}:{today}:models"

        tokens = int(await self._redis.get(token_key) or 0)  # type: ignore[union-attr]
        cost = float(await self._redis.get(cost_key) or 0.0)  # type: ignore[union-attr]
        models_raw = await self._redis.hgetall(model_key)  # type: ignore[union-attr]
        models: dict[str, int] = {k: int(v) for k, v in models_raw.items()}

        return {
            "tokens": tokens,
            "cost": cost,
            "models": models,
            "alerts": [],
        }

    async def check_budget(
        self,
        user_id: str,
        estimated_tokens: int = 0,
        estimated_cost: float = 0.0,
    ) -> tuple[bool, dict[str, object]]:
        config = self.get_budget_config(user_id)

        if await self._ensure_redis():
            usage = await self._redis_usage(user_id)
        else:
            usage = self._current_usage(user_id)

        current_tokens = int(usage["tokens"])
        current_cost = float(usage["cost"])

        details = {
            "tier": config.tier.value,
            "daily_token_limit": config.daily_token_limit,
            "daily_cost_limit_usd": config.daily_cost_limit_usd,
            "current_tokens": current_tokens,
            "current_cost_usd": round(current_cost, 6),
            "projected_tokens": current_tokens + estimated_tokens,
            "projected_cost_usd": round(current_cost + estimated_cost, 6),
        }

        if current_tokens + estimated_tokens > config.daily_token_limit:
            details["reason"] = "Daily token limit exceeded"
            return False, details
        if current_cost + estimated_cost > config.daily_cost_limit_usd:
            details["reason"] = "Daily cost limit exceeded"
            return False, details
        return True, details

    async def record_usage(
        self,
        user_id: str,
        task_id: str,
        tokens: int,
        cost_usd: float,
        model: str,
    ) -> None:
        if await self._ensure_redis():
            today = self._today()
            token_key = f"usage:{user_id}:{today}:tokens"
            cost_key = f"usage:{user_id}:{today}:cost"
            model_key = f"usage:{user_id}:{today}:models"

            pipe = self._redis.pipeline()  # type: ignore[union-attr]
            pipe.incrby(token_key, tokens)
            pipe.incrbyfloat(cost_key, cost_usd)
            pipe.hincrby(model_key, model, tokens)
            pipe.expire(token_key, 172800)  # 2 days TTL
            pipe.expire(cost_key, 172800)
            pipe.expire(model_key, 172800)
            await pipe.execute()
            await self._check_alerts(user_id)
        else:
            usage = self._current_usage(user_id)
            usage["tokens"] = int(usage["tokens"]) + tokens
            usage["cost"] = round(float(usage["cost"]) + cost_usd, 6)
            models = usage["models"]
            assert isinstance(models, dict)
            models[model] = int(models.get(model, 0)) + tokens
            usage["updated_at"] = datetime.now(timezone.utc)
            self._record_alerts_in_memory(user_id)

    async def _check_alerts(self, user_id: str) -> None:
        """Check budget thresholds in Redis and emit alerts."""
        config = self.get_budget_config(user_id)
        today = self._today()
        cost_key = f"usage:{user_id}:{today}:cost"
        alert_key = f"alerts:{user_id}:{today}"

        current_cost = float(await self._redis.get(cost_key) or 0.0)  # type: ignore[union-attr]
        usage_percent = current_cost / config.daily_cost_limit_usd if config.daily_cost_limit_usd else 0.0

        for threshold in (0.5, 0.8, 1.0):
            if usage_percent >= threshold:
                sent = await self._redis.sismember(alert_key, str(threshold))  # type: ignore[union-attr]
                if not sent:
                    logger.warning(
                        "Budget alert: user=%s at %d%% (cost=$%.2f/$%.2f)",
                        user_id, int(threshold * 100), current_cost, config.daily_cost_limit_usd,
                    )
                    await self._redis.sadd(alert_key, str(threshold))  # type: ignore[union-attr]
                    await self._redis.expire(alert_key, 86400)  # type: ignore[union-attr]

    def _record_alerts_in_memory(self, user_id: str) -> None:
        config = self.get_budget_config(user_id)
        usage = self._current_usage(user_id)
        alerts = usage["alerts"]
        assert isinstance(alerts, list)
        current_cost = float(usage["cost"])
        usage_percent = 0.0 if config.daily_cost_limit_usd == 0 else current_cost / config.daily_cost_limit_usd
        thresholds = [0.5, 0.8, 1.0]
        sent_thresholds = {float(alert["threshold"]) for alert in alerts}
        for threshold in thresholds:
            if usage_percent >= threshold and threshold not in sent_thresholds:
                alerts.append(
                    {
                        "threshold": threshold * 100,
                        "triggered_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

    async def get_status(self, user_id: str) -> dict[str, object]:
        config = self.get_budget_config(user_id)

        if await self._ensure_redis():
            usage = await self._redis_usage(user_id)
            alerts_raw = await self._redis.smembers(f"alerts:{user_id}:{self._today()}")  # type: ignore[union-attr]
            alerts: list[dict[str, object]] = [
                {"threshold": float(t) * 100} for t in alerts_raw
            ]
        else:
            usage = self._current_usage(user_id)
            alerts = list(usage.get("alerts", []))

        current_cost = float(usage["cost"])
        current_tokens = int(usage["tokens"])
        model_breakdown = usage["models"]
        assert isinstance(model_breakdown, dict)

        return {
            "user_id": user_id,
            "current_cost_usd": round(current_cost, 6),
            "daily_limit_usd": config.daily_cost_limit_usd,
            "usage_percent": round((current_cost / config.daily_cost_limit_usd) * 100, 2)
            if config.daily_cost_limit_usd
            else 0.0,
            "tokens_used": current_tokens,
            "model_breakdown": [
                {"model": model, "tokens": tokens}
                for model, tokens in sorted(model_breakdown.items(), key=lambda item: item[1], reverse=True)
            ],
            "alerts": alerts,
            "budget_tier": config.tier.value,
            "window_start": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        }

    async def reserve_budget(
        self,
        user_id: str,
        estimated_tokens: int,
        estimated_cost: float,
    ) -> tuple[bool, dict[str, object]]:
        """Atomically reserve budget before an LLM call.

        Redis executes the check-and-increment as one Lua script, so concurrent
        attempts cannot both pass a limit check. Without Redis, an asyncio lock
        provides the same guarantee within this process (production fails closed).
        """
        config = self.get_budget_config(user_id)
        if await self._ensure_redis():
            today = self._today()
            token_key = f"usage:{user_id}:{today}:tokens"
            cost_key = f"usage:{user_id}:{today}:cost"
            try:
                outcome = await self._redis.eval(  # type: ignore[union-attr]
                    RESERVE_SCRIPT,
                    2,
                    token_key,
                    cost_key,
                    estimated_tokens,
                    estimated_cost,
                    config.daily_token_limit,
                    config.daily_cost_limit_usd,
                )
                allowed = bool(int(outcome[0]))
                current_tokens = int(float(outcome[1]))
                current_cost = float(outcome[2])
                reason = str(outcome[3] or "")
                details = {
                    "tier": config.tier.value,
                    "daily_token_limit": config.daily_token_limit,
                    "daily_cost_limit_usd": config.daily_cost_limit_usd,
                    "current_tokens": current_tokens,
                    "current_cost_usd": round(current_cost, 6),
                    "reserved_tokens": estimated_tokens,
                    "reserved_cost_usd": round(estimated_cost, 6),
                }
                if not allowed:
                    details["reason"] = reason or "Budget limit exceeded"
                return allowed, details
            except Exception as exc:
                logger.error("Atomic budget reservation failed: %s", exc)
                if settings.is_production:
                    return False, {
                        "tier": config.tier.value,
                        "reason": "Budget ledger error; failing closed",
                    }

        if settings.is_production:
            return False, {
                "tier": config.tier.value,
                "reason": "Budget ledger unavailable; failing closed",
            }

        async with self._lock:
            usage = self._current_usage(user_id)
            current_tokens = int(usage["tokens"])
            current_cost = float(usage["cost"])
            if current_tokens + estimated_tokens > config.daily_token_limit:
                return False, {
                    "tier": config.tier.value,
                    "reason": "Daily token limit exceeded",
                    "current_tokens": current_tokens,
                }
            if current_cost + estimated_cost > config.daily_cost_limit_usd:
                return False, {
                    "tier": config.tier.value,
                    "reason": "Daily cost limit exceeded",
                    "current_cost_usd": round(current_cost, 6),
                }
            usage["tokens"] = current_tokens + estimated_tokens
            usage["cost"] = round(current_cost + estimated_cost, 6)
            usage["updated_at"] = datetime.now(timezone.utc)
            return True, {
                "tier": config.tier.value,
                "current_tokens": usage["tokens"],
                "current_cost_usd": usage["cost"],
                "reserved_tokens": estimated_tokens,
                "reserved_cost_usd": round(estimated_cost, 6),
            }

    async def commit_usage(
        self,
        user_id: str,
        task_id: str,
        *,
        reserved_tokens: int,
        reserved_cost: float,
        actual_tokens: int,
        actual_cost: float,
        model: str,
    ) -> None:
        """Replace a reservation with the actual usage (zero on failure)."""
        delta_tokens = actual_tokens - reserved_tokens
        delta_cost = actual_cost - reserved_cost
        if await self._ensure_redis():
            today = self._today()
            token_key = f"usage:{user_id}:{today}:tokens"
            cost_key = f"usage:{user_id}:{today}:cost"
            model_key = f"usage:{user_id}:{today}:models"
            pipe = self._redis.pipeline()  # type: ignore[union-attr]
            if delta_tokens:
                pipe.incrby(token_key, delta_tokens)
            if delta_cost:
                pipe.incrbyfloat(cost_key, delta_cost)
            if actual_tokens:
                pipe.hincrby(model_key, model, actual_tokens)
            pipe.expire(token_key, 172800)
            pipe.expire(cost_key, 172800)
            pipe.expire(model_key, 172800)
            await pipe.execute()
            await self._check_alerts(user_id)
            return

        async with self._lock:
            usage = self._current_usage(user_id)
            usage["tokens"] = max(0, int(usage["tokens"]) + delta_tokens)
            usage["cost"] = max(0.0, round(float(usage["cost"]) + delta_cost, 6))
            models = usage["models"]
            assert isinstance(models, dict)
            if actual_tokens:
                models[model] = int(models.get(model, 0)) + actual_tokens
            usage["updated_at"] = datetime.now(timezone.utc)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis_available = False


cost_governor = CostGovernor()
