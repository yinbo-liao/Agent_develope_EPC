from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.security.auth import decode_token, hash_password

PASSWORD = "strong-demo-pass-1234"


async def _create_user(username: str, role: str = "viewer", tier: str = "starter") -> str:
    from app.core.database import SessionLocal

    user_id = str(uuid.uuid4())
    async with SessionLocal() as session:
        session.add(
            User(
                id=user_id,
                username=username,
                hashed_password=hash_password(PASSWORD),
                role=role,
                tier=tier,
            )
        )
        await session.commit()
    return user_id


async def _login(async_client: AsyncClient, username: str) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/token",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
async def test_login_tokens_carry_issuer_and_audience(async_client: AsyncClient) -> None:
    await _create_user("issuer-user")
    tokens = await _login(async_client, "issuer-user")
    claims = decode_token(tokens["access_token"])
    assert claims["iss"] == "aiwf"
    assert claims["aud"] == "aiwf-api"
    assert claims["type"] == "access"


@pytest.mark.anyio
async def test_refresh_rotation_and_reuse_detection(async_client: AsyncClient) -> None:
    await _create_user("rotate-user")
    tokens = await _login(async_client, "rotate-user")

    first = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert first.status_code == 200
    rotated = first.json()

    replay = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    # Reuse revoked the family, so even the newest token is now invalid.
    after_reuse = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert after_reuse.status_code == 401


@pytest.mark.anyio
async def test_logout_revokes_refresh_token(async_client: AsyncClient) -> None:
    await _create_user("logout-user")
    tokens = await _login(async_client, "logout-user")

    logout = await async_client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout.status_code == 200

    refresh = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == 401


@pytest.mark.anyio
async def test_admin_can_provision_user(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await async_client.post(
        "/api/v1/auth/users",
        json={
            "username": "provisioned-reviewer",
            "password": PASSWORD,
            "role": "reviewer",
            "tier": "professional",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "reviewer"
    assert "hashed_password" not in body

    login = await async_client.post(
        "/api/v1/auth/token",
        json={"username": "provisioned-reviewer", "password": PASSWORD},
    )
    assert login.status_code == 200


@pytest.mark.anyio
async def test_non_admin_cannot_provision(
    async_client: AsyncClient, viewer_auth_headers: dict[str, str]
) -> None:
    response = await async_client.post(
        "/api/v1/auth/users",
        json={"username": "nope", "password": PASSWORD},
        headers=viewer_auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_provisioning_rejects_duplicate_and_weak_password(
    async_client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    duplicate = await async_client.post(
        "/api/v1/auth/users",
        json={"username": "dupe-user", "password": PASSWORD},
        headers=auth_headers,
    )
    assert duplicate.status_code == 201
    again = await async_client.post(
        "/api/v1/auth/users",
        json={"username": "dupe-user", "password": PASSWORD},
        headers=auth_headers,
    )
    assert again.status_code == 409

    weak = await async_client.post(
        "/api/v1/auth/users",
        json={"username": "weak-user", "password": "short"},
        headers=auth_headers,
    )
    assert weak.status_code == 422