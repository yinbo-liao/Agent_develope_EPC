"""
Anthropic Provider — Claude API client refactored from ai_engine.py.

Uses the official anthropic SDK for chat completions.
"""

import json
import logging
from typing import Any
from services.llm_provider import ChatMessage, ChatResponse, ToolCall

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """Client for Anthropic Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None and self.api_key:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
            except ImportError:
                logger.error("anthropic package not installed. Install with: pip install anthropic")
                raise
        return self._client

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self._client is not None

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """Send a chat completion request to Claude."""
        if not self.available:
            raise RuntimeError("Anthropic client not available (missing API key or SDK)")

        # Convert to Anthropic message format
        anthropic_messages = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_calls:
                # Anthropic uses tool_use content blocks, not top-level tool_calls
                tool_use_blocks = []
                for tc in msg.tool_calls:
                    tool_use_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                m["content"] = tool_use_blocks
            if msg.tool_call_id:
                m["content"] = [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content or "",
                }]
            anthropic_messages.append(m)

        # Convert tool definitions to Anthropic format
        anthropic_tools = None
        if tools:
            anthropic_tools = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]

        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": anthropic_messages,
            }
            if system:
                kwargs["system"] = system
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            response = await self.client.messages.create(**kwargs)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

        # Parse response content
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else json.loads(str(block.input)),
                ))

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens if hasattr(response, 'usage') else 0,
                "output_tokens": response.usage.output_tokens if hasattr(response, 'usage') else 0,
            },
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Anthropic doesn't have a native embeddings API. Return zero vectors as fallback."""
        logger.warning("Anthropic embedding not supported — returning zero vectors. Use DeepSeek/OpenAI for embeddings.")
        return [[0.0] * 128 for _ in texts]

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
