from __future__ import annotations

import pytest

from app.services import llm_client


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    last_url: str | None = None
    last_headers: dict | None = None
    last_json: dict | None = None

    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        FakeClient.last_url = url
        FakeClient.last_headers = headers
        FakeClient.last_json = json
        return self.response


@pytest.fixture
def configure(monkeypatch):
    def _configure(provider: str, payload: dict) -> None:
        monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", provider)
        monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", "test-key")
        monkeypatch.setattr(llm_client.settings, "LLM_BASE_URL", "https://llm.example/v1")
        monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "provider-model")
        monkeypatch.setattr(
            llm_client.httpx,
            "AsyncClient",
            lambda **kwargs: FakeClient(FakeResponse(payload)),
        )

    return _configure


@pytest.mark.anyio
async def test_openai_adapter(configure):
    configure(
        "openai",
        {
            "model": "gpt-test",
            "choices": [{"message": {"content": "provider answer"}}],
            "usage": {"total_tokens": 120},
        },
    )
    result = await llm_client.LLMClient.generate("hello", context=[{"snippet": "ctx"}])
    assert result["content"] == "provider answer"
    assert result["tokens_used"] == 120
    assert result["provider"] == "openai"
    assert FakeClient.last_url == "https://llm.example/v1/chat/completions"
    assert FakeClient.last_json["model"] == "provider-model"
    assert FakeClient.last_headers["Authorization"] == "Bearer test-key"


@pytest.mark.anyio
async def test_anthropic_adapter(configure):
    configure(
        "anthropic",
        {
            "model": "claude-test",
            "content": [{"text": "anthropic answer"}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    )
    result = await llm_client.LLMClient.generate("hello")
    assert result["content"] == "anthropic answer"
    assert result["tokens_used"] == 30
    assert result["provider"] == "anthropic"
    assert FakeClient.last_url == "https://llm.example/v1/messages"


@pytest.mark.anyio
async def test_provider_requires_key(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_client.settings, "LLM_API_KEY", None)
    with pytest.raises(RuntimeError):
        await llm_client.LLMClient.generate("hello")


@pytest.mark.anyio
async def test_unknown_provider(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        await llm_client.LLMClient.generate("hello")