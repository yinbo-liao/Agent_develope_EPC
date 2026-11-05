from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_same_key_returns_same_workflow(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"input_query": "Idempotent workflow creation test."}
    headers = {**auth_headers, "Idempotency-Key": "key-001"}

    first = await async_client.post("/api/v1/workflows", json=payload, headers=headers)
    second = await async_client.post("/api/v1/workflows", json=payload, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]

    listed = await async_client.get("/api/v1/workflows", headers=auth_headers)
    matching = [
        item
        for item in listed.json()["items"]
        if item["id"] == first.json()["id"]
    ]
    assert len(matching) == 1


@pytest.mark.anyio
async def test_different_keys_create_different_workflows(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"input_query": "Another idempotency test."}
    first = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers={**auth_headers, "Idempotency-Key": "key-a"},
    )
    second = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers={**auth_headers, "Idempotency-Key": "key-b"},
    )
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.anyio
async def test_same_key_is_scoped_per_user(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    viewer_auth_headers: dict[str, str],
) -> None:
    payload = {"input_query": "Scoped idempotency test."}
    first = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers={**auth_headers, "Idempotency-Key": "shared-key"},
    )
    second = await async_client.post(
        "/api/v1/workflows",
        json=payload,
        headers={**viewer_auth_headers, "Idempotency-Key": "shared-key"},
    )
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.anyio
async def test_missing_key_always_creates(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {"input_query": "No idempotency key supplied."}
    first = await async_client.post("/api/v1/workflows", json=payload, headers=auth_headers)
    second = await async_client.post("/api/v1/workflows", json=payload, headers=auth_headers)
    assert first.json()["id"] != second.json()["id"]
