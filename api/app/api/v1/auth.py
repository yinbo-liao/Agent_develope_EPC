from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.deps import get_current_user, require_role
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.security.auth import (
    create_access_token,
    decode_token,
    hash_password,
    issue_refresh_token,
    verify_password,
)
from app.services.audit import append_audit
from app.services.cost_governor import cost_governor

router = APIRouter(prefix="/auth", tags=["Authentication"])

Role = Literal["viewer", "reviewer", "admin"]
Tier = Literal["free", "starter", "professional", "enterprise"]


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: str
    role: str
    tier: str


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=255, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Role = "viewer"
    tier: Tier = "starter"


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    tier: str
    is_active: bool

    model_config = {"from_attributes": True}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _token_pair(user: User) -> tuple[TokenResponse, RefreshToken]:
    access_token = create_access_token(
        subject=user.id, extra_claims={"role": user.role, "tier": user.tier}
    )
    refresh_token, jti, expires_at = issue_refresh_token(user.id)
    record = RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at)
    return (
        TokenResponse(access_token=access_token, refresh_token=refresh_token),
        record,
    )


@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: TokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate and return an access/refresh token pair."""
    result = await session.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        await append_audit(
            session,
            actor=payload.username,
            action="auth.login_failed",
            payload={"reason": "invalid_credentials"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    tokens, refresh_record = _token_pair(user)
    session.add(refresh_record)
    await append_audit(
        session,
        actor=user.id,
        action="auth.login",
        resource=user.id,
        payload={"role": user.role, "tier": user.tier},
    )
    await session.commit()
    cost_governor.set_tier(user.id, user.tier)
    return tokens


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Rotate a refresh token. Reuse of a revoked token revokes the whole family."""
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type.")
        user_id = claims.get("sub")
        jti = claims.get("jti")
        if not isinstance(user_id, str) or not isinstance(jti, str):
            raise HTTPException(status_code=401, detail="Missing token claims.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.") from exc

    record = await session.get(RefreshToken, jti)
    if record is None:
        raise HTTPException(status_code=401, detail="Refresh token is not recognised.")
    if record.revoked:
        # Reuse detection: an old token was replayed. Revoke every session for the user.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .values(revoked=True)
        )
        await append_audit(
            session,
            actor=user_id,
            action="auth.refresh_reuse_detected",
            resource=user_id,
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected.")
    if _aware(record.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token expired.")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Account not found or deactivated.")

    tokens, new_record = _token_pair(user)
    record.revoked = True
    record.replaced_by = new_record.jti
    session.add(new_record)
    await append_audit(
        session,
        actor=user.id,
        action="auth.refresh",
        resource=user.id,
    )
    await session.commit()
    cost_governor.set_tier(user.id, user.tier)
    return tokens


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Revoke the supplied refresh token (access tokens remain short-lived)."""
    try:
        claims = decode_token(payload.refresh_token)
        jti = claims.get("jti")
        user_id = claims.get("sub")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token.") from exc
    if not isinstance(jti, str) or not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    record = await session.get(RefreshToken, jti)
    if record is not None and not record.revoked:
        record.revoked = True
        await append_audit(
            session,
            actor=user_id,
            action="auth.logout",
            resource=user_id,
        )
        await session.commit()
    return {"status": "revoked"}


@router.get("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def current_user_info(
    current_user: dict[str, object] = Depends(get_current_user),
) -> MeResponse:
    """Return the authenticated identity encoded in the access token."""
    return MeResponse(
        user_id=str(current_user["user_id"]),
        role=str(current_user.get("role", "viewer")),
        tier=str(current_user.get("tier", "starter")),
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: dict[str, object] = Depends(require_role("admin")),
) -> UserResponse:
    """Provision a local user. Admin-only; there is no self-registration."""
    existing = await session.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already exists.")

    user = User(
        id=str(uuid.uuid4()),
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        tier=payload.tier,
    )
    session.add(user)
    await session.flush()
    await append_audit(
        session,
        actor=str(current_user["user_id"]),
        action="auth.user_created",
        resource=user.id,
        payload={"username": user.username, "role": user.role, "tier": user.tier},
    )
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/users", response_model=list[UserResponse], status_code=status.HTTP_200_OK)
async def list_users(
    session: AsyncSession = Depends(get_db_session),
    current_user: dict[str, object] = Depends(require_role("admin")),
) -> list[UserResponse]:
    result = await session.execute(select(User).order_by(User.username.asc()))
    return [UserResponse.model_validate(user) for user in result.scalars().all()]