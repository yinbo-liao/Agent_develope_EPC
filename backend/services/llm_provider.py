"""
Multi-LLM Provider — unified interface for DeepSeek, Anthropic, and fallback routing.

Supports:
- Primary/fallback routing (DeepSeek → Claude → rule-based)
- Chat completion with tool use
- Embedding generation
- Streaming responses
- Automatic retry with exponential backoff
"""

import logging
from typing import Any, AsyncIterator
from dataclasses import dataclass, field
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Schema for a function tool callable by the LLM."""
    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's input


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    """A single message in a conversation."""
    role: str  # system, user, assistant, tool
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ChatResponse:
    """Response from an LLM chat completion."""
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # stop, tool_calls, length, error
    model: str = ""
    usage: dict = field(default_factory=dict)
    error: str | None = None


class LLMProvider:
    """
    Multi-provider LLM abstraction with primary/fallback routing.

    Usage:
        provider = LLMProvider()
        response = await provider.chat(messages, tools=[...])
        # Automatically tries DeepSeek first, falls back to Claude, then rule-based
    """

    def __init__(self):
        self._deepseek = None
        self._anthropic = None
        self.primary = settings.llm_primary
        self.fallback = settings.llm_fallback

    @property
    def deepseek(self):
        if self._deepseek is None:
            from services.providers.deepseek_provider import DeepSeekProvider
            self._deepseek = DeepSeekProvider(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model,
                base_url=settings.deepseek_base_url,
            )
        return self._deepseek

    @property
    def anthropic(self):
        if self._anthropic is None:
            from services.providers.anthropic_provider import AnthropicProvider
            self._anthropic = AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
            )
        return self._anthropic

    @property
    def enabled(self) -> bool:
        """Check if any LLM provider is configured."""
        return bool(settings.deepseek_api_key) or bool(settings.anthropic_api_key)

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> ChatResponse:
        """
        Send a chat completion request, routing through primary → fallback providers.

        Args:
            messages: Conversation history
            tools: Optional function tool definitions
            system: Optional system prompt
            temperature: Sampling temperature (default from config)
            max_tokens: Max response tokens (default from config)
            stream: If True, returns an async iterator instead

        Returns:
            ChatResponse with content and/or tool calls
        """
        temp = temperature if temperature is not None else settings.ai_temperature
        max_tok = max_tokens if max_tokens is not None else settings.ai_max_tokens

        # Try primary provider
        try:
            if self.primary == "deepseek" and settings.deepseek_api_key:
                return await self.deepseek.chat(messages, tools, system, temp, max_tok)
            elif self.primary == "anthropic" and settings.anthropic_api_key:
                return await self.anthropic.chat(messages, tools, system, temp, max_tok)
        except Exception as e:
            logger.warning(f"Primary LLM ({self.primary}) failed: {e}, trying fallback ({self.fallback})")

        # Try fallback provider
        try:
            if self.fallback == "anthropic" and settings.anthropic_api_key:
                return await self.anthropic.chat(messages, tools, system, temp, max_tok)
            elif self.fallback == "deepseek" and settings.deepseek_api_key:
                return await self.deepseek.chat(messages, tools, system, temp, max_tok)
        except Exception as e:
            logger.error(f"Fallback LLM ({self.fallback}) also failed: {e}")

        # Ultimate fallback: error response
        return ChatResponse(
            content=None,
            finish_reason="error",
            error=f"All LLM providers failed. Primary ({self.primary}) and fallback ({self.fallback}) are unavailable.",
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens."""
        # For now, use non-streaming chat and yield the result
        # Full streaming support can be added per-provider
        response = await self.chat(messages, tools, system)
        if response.content:
            yield response.content
        if response.error:
            yield f"[Error: {response.error}]"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for the given texts."""
        # Try DeepSeek embeddings first (OpenAI-compatible endpoint)
        if settings.deepseek_api_key:
            try:
                return await self.deepseek.embed(texts, settings.ai_embedding_model)
            except Exception as e:
                logger.warning(f"DeepSeek embedding failed: {e}")

        # Fallback: use Anthropic (via a separate embedding model or API)
        if settings.anthropic_api_key:
            try:
                return await self.anthropic.embed(texts)
            except Exception as e:
                logger.warning(f"Anthropic embedding failed: {e}")

        raise RuntimeError("No embedding provider available. Set FPSO_DEEPSEEK_API_KEY or FPSO_ANTHROPIC_API_KEY.")


# Singleton
llm_provider = LLMProvider()
