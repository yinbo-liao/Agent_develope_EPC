from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _create_run(async_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await async_client.post(
        "/api/v1/workflows",
        json={"input_query": "A workflow used to test the event stream."},
        headers=headers,
    )
    assert response.status_code == 202
    return response.json()["id"]


@pytest.mark.anyio
async def test_ticket_requires_authentication(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    task_id = await _create_run(async_client, auth_headers)
    response = await async_client.post(f"/api/v1/events/ticket/{task_id}")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_state_requires_authentication(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    task_id = await _create_run(async_client, auth_headers)
    response = await async_client.get(f"/api/v1/events/state/{task_id}")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_owner_can_read_state_and_get_ticket(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    task_id = await _create_run(async_client, auth_headers)

    state = await async_client.get(
        f"/api/v1/events/state/{task_id}", headers=auth_headers
    )
    assert state.status_code == 200
    assert state.json()["taskId"] == task_id

    ticket = await async_client.post(
        f"/api/v1/events/ticket/{task_id}", headers=auth_headers
    )
    assert ticket.status_code == 200
    assert ticket.json()["ticket"]


@pytest.mark.anyio
async def test_other_user_cannot_get_ticket_or_state(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    other_user_auth_headers: dict[str, str],
) -> None:
    task_id = await _create_run(async_client, auth_headers)

    ticket = await async_client.post(
        f"/api/v1/events/ticket/{task_id}", headers=other_user_auth_headers
    )
    assert ticket.status_code == 404

    state = await async_client.get(
        f"/api/v1/events/state/{task_id}", headers=other_user_auth_headers
    )
    assert state.status_code == 404


@pytest.mark.anyio
async def test_sse_requires_a_ticket(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/events/sse/some-task-id")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_ticket_is_scoped_to_one_task(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    first = await _create_run(async_client, auth_headers)
    second = await _create_run(async_client, auth_headers)
    ticket = (
        await async_client.post(
            f"/api/v1/events/ticket/{first}", headers=auth_headers
        )
    ).json()["ticket"]

    response = await async_client.get(
        f"/api/v1/events/sse/{second}", params={"ticket": ticket}
    )
    assert response.status_code == 401