from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.services.model_router import model_router


class LLMClient:
    """Model provider adapter.

    `simulated` is the demo default. `openai` targets any OpenAI-compatible
    `/chat/completions` endpoint; `anthropic` targets the Messages API. Errors are
    raised to the caller (the workflow runner applies retry/circuit policy).
    """

    @staticmethod
    def _context_text(context: list[dict[str, Any]] | None) -> str:
        items = context or []
        lines = "\n".join(f"- {item.get('snippet', '')}" for item in items[:3])
        return lines or "- No additional context retrieved."

    @staticmethod
    def _simulated(
        prompt: str,
        context: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> dict[str, Any]:
        content = (
            "Generated response\n\n"
            f"Request: {prompt}\n\n"
            "Summary:\n"
            f"{LLMClient._context_text(context)}\n\n"
            f"Execution profile: model={model}, max_tokens={max_tokens}, temperature={temperature}."
        )
        tokens = min(max_tokens, max(1, int(len(content.split()) * 1.3)))
        return {
            "content": content,
            "tokens_used": tokens,
            "cost_usd": model_router.estimate_cost(model, tokens),
            "model": model,
            "provider": "simulated",
        }

    @staticmethod
    def _provider_model(requested: str) -> str:
        configured = (settings.LLM_MODEL or "").strip()
        return configured or requested

    @staticmethod
    async def _openai(
        prompt: str,
        context: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> dict[str, Any]:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY is not configured")
        payload = {
            "model": LLMClient._provider_model(model),
            "messages": [
                {
                    "role": "system",
                    "content": "You are an enterprise workflow assistant. Be concise and cite context.",
                },
                {
                    "role": "user",
                    "content": f"{prompt}\n\nContext:\n{LLMClient._context_text(context)}",
                },
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = str(data["choices"][0]["message"]["content"])
        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or max(1, int(len(content.split()) * 1.3)))
        provider_model = str(data.get("model") or payload["model"])
        return {
            "content": content,
            "tokens_used": tokens,
            "cost_usd": model_router.estimate_cost(provider_model, tokens),
            "model": provider_model,
            "provider": "openai",
        }

    @staticmethod
    async def _anthropic(
        prompt: str,
        context: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> dict[str, Any]:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY is not configured")
        payload = {
            "model": LLMClient._provider_model(model),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": f"{prompt}\n\nContext:\n{LLMClient._context_text(context)}",
                }
            ],
        }
        base = settings.LLM_BASE_URL.rstrip("/")
        messages_url = f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                messages_url,
                headers={
                    "x-api-key": settings.LLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        blocks = data.get("content") or []
        content = "".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict))
        usage = data.get("usage") or {}
        tokens = int(
            (usage.get("input_tokens") or 0)
            + (usage.get("output_tokens") or 0)
            or max(1, int(len(content.split()) * 1.3))
        )
        provider_model = str(data.get("model") or payload["model"])
        return {
            "content": content,
            "tokens_used": tokens,
            "cost_usd": model_router.estimate_cost(provider_model, tokens),
            "model": provider_model,
            "provider": "anthropic",
        }

    @staticmethod
    async def generate(
        prompt: str,
        context: list[dict[str, Any]] | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        model: str = "claude-sonnet-4-6",
    ) -> dict[str, Any]:
        provider = settings.LLM_PROVIDER.lower()
        if provider == "simulated":
            return LLMClient._simulated(prompt, context, max_tokens, temperature, model)
        if provider == "openai":
            return await LLMClient._openai(prompt, context, max_tokens, temperature, model)
        if provider == "anthropic":
            return await LLMClient._anthropic(prompt, context, max_tokens, temperature, model)
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")