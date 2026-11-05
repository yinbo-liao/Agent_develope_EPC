"""
DeepSeek Provider — OpenAI-compatible API client for DeepSeek models.

DeepSeek API is compatible with the OpenAI SDK format.
We use httpx directly to avoid requiring the openai package.
"""

import json
import logging
import httpx
from typing import Any
from config import settings
from services.llm_provider import ChatMessage, ChatResponse, ToolCall

logger = logging.getLogger(__name__)


class DeepSeekProvider:
    """Client for DeepSeek API (OpenAI-compatible endpoint)."""

    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com/v1"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a chat completion request to DeepSeek."""
        # Convert to OpenAI message format
        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for msg in messages:
            m = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_calls:
                m["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            api_messages.append(m)

        body: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
            body["tool_choice"] = "auto"

        try:
            response = await self.client.post(f"{self.base_url}/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API HTTP error: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise

        choice = data["choices"][0]
        msg = choice.get("message", {})

        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc["function"]["name"],
                    arguments=args,
                ))

        return ChatResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            model=data.get("model", self.model),
            usage=data.get("usage", {}),
        )

    async def embed(self, texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
        """Generate embeddings. Falls back to deepseek-chat based embedding."""
        # DeepSeek doesn't have a native embeddings API yet.
        # We generate embeddings using the chat model by asking for structured representations.
        # In production, use a proper embedding model (OpenAI, Cohere, etc.).
        embeddings = []
        for text in texts:
            try:
                response = await self.client.post(f"{self.base_url}/chat/completions", json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are an embedding generator. Output exactly 128 floating-point numbers separated by commas that represent the semantic meaning of the input text. Output ONLY the numbers, no other text."},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 1024,
                })
                response.raise_for_status()
                data = response.json()
                raw = data["choices"][0]["message"]["content"]
                # Parse floating point numbers
                import re
                nums = [float(x) for x in re.findall(r'-?\d+\.?\d*', raw)]
                if len(nums) < 16:
                    # Pad if too few numbers returned
                    nums = (nums * 8)[:128]
                embeddings.append(nums[:128])
            except Exception as e:
                logger.error(f"Embedding generation failed for text: {e}")
                # Return zero vector as fallback
                embeddings.append([0.0] * 128)
        return embeddings

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
