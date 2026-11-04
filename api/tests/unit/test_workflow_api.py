from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_create_workflow_returns_202(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await async_client.post(
        "/api/v1/workflows",
        json={
            "input_query": "Review the deployment plan for security impact.",
            "token_budget": 5000,
            "cost_budget_usd": 3.0,
        },
        headers=auth_headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["user_id"] == "test-user-id"
    assert data["current_status"] == "pending"
    assert data["id"] != ""


@pytest.mark.anyio
async def test_create_workflow_rejects_empty_query(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "ab", "token_budget": 5000, "cost_budget_usd": 3.0},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_workflow_requires_authentication(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "Some valid query here."},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_create_workflow_rejects_caller_supplied_user_id(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Identity is derived from the token; a body user_id is a schema error."""
    response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "Valid query text.", "user_id": "victim-user"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_list_workflows(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await async_client.get("/api/v1/workflows", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.anyio
async def test_list_workflows_requires_authentication(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/workflows")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_get_workflow_not_found(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await async_client.get(
        "/api/v1/workflows/nonexistent-id", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_workflow_requires_authentication(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create_response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "A workflow only its owner may read."},
        headers=auth_headers,
    )
    workflow_id = create_response.json()["id"]
    response = await async_client.get(f"/api/v1/workflows/{workflow_id}")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_create_and_get_workflow(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create_response = await async_client.post(
        "/api/v1/workflows",
        json={
            "input_query": "Test the workflow lifecycle end-to-end.",
            "token_budget": 10000,
            "cost_budget_usd": 5.0,
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 202
    workflow_id = create_response.json()["id"]

    get_response = await async_client.get(
        f"/api/v1/workflows/{workflow_id}", headers=auth_headers
    )
    assert get_response.status_code == 200
    detail = get_response.json()
    assert detail["id"] == workflow_id
    assert detail["input_query"] == "Test the workflow lifecycle end-to-end."
    assert detail["user_id"] == "test-user-id"


@pytest.mark.anyio
async def test_cannot_access_other_users_workflow(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    viewer_auth_headers: dict[str, str],
) -> None:
    """A workflow created by one user should not be visible to another."""
    create_response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "This is an admin-only workflow."},
        headers=auth_headers,
    )
    assert create_response.status_code == 202
    workflow_id = create_response.json()["id"]

    get_response = await async_client.get(
        f"/api/v1/workflows/{workflow_id}", headers=viewer_auth_headers
    )
    assert get_response.status_code == 404  # Not found (not 403 — don't leak existence)