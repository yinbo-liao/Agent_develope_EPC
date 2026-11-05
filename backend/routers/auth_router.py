"""
Auth Router — OAuth2+JWT login, register, refresh, user info.
"""

import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from auth import (
    LoginRequest, RegisterRequest, RefreshRequest,
    TokenResponse, UserInfo,
    verify_password, hash_password, create_access_token, create_refresh_token,
    get_current_user, require_role, TokenData,
    db_get_user_by_username, db_get_user_by_id, db_create_user,
    db_store_refresh_token, db_revoke_all_user_tokens, db_log_auth_event,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
import hashlib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def get_auth_pool():
    """Get the unified database pool."""
    from db import get_pool as _get_pool
    return await _get_pool()


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """Authenticate user and return access + refresh tokens."""
    if not req.username or not req.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and password are required.",
        )
    if len(req.password) > 128:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Password too long.")

    pool = await get_auth_pool()
    user = await db_get_user_by_username(pool, req.username)

    if not user or not verify_password(req.password, user["hashed_password"]):
        await db_log_auth_event(
            pool, user.get("user_id") if user else None,
            "FAILED_LOGIN", request.client.host if request.client else None,
            request.headers.get("user-agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    token_data = {"sub": user["user_id"], "username": user["username"], "role": user["role"]}
    access_token = create_access_token(token_data)
    raw_refresh, refresh_hash = create_refresh_token(token_data)

    # Store refresh token hash
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    await db_store_refresh_token(pool, user["user_id"], refresh_hash, expires_at)

    # Update last_login
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE user_id = $1",
            user["user_id"],
        )

    await db_log_auth_event(
        pool, user["user_id"], "LOGIN",
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
    )


@router.post("/register", response_model=UserInfo)
async def register(req: RegisterRequest, _user: TokenData = Depends(require_role("admin"))):
    """Register a new user. Admin only."""
    if len(req.username) < 3 or len(req.username) > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username must be 3-100 characters.",
        )
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters.",
        )
    if "@" not in req.email or len(req.email) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address.",
        )
    if req.role not in ("admin", "project_manager", "trade_lead", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role. Must be one of: admin, project_manager, trade_lead, viewer.",
        )

    pool = await get_auth_pool()
    existing = await db_get_user_by_username(pool, req.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        )

    try:
        user = await db_create_user(
            pool, req.username, req.email,
            hash_password(req.password), req.full_name, req.role,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists.",
        )

    return UserInfo(
        user_id=user["user_id"],
        username=user["username"],
        email=user["email"],
        full_name=user.get("full_name"),
        role=user["role"],
        is_active=user["is_active"],
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, request: Request):
    """Exchange a refresh token for new access + refresh tokens (token rotation)."""
    if not req.refresh_token or len(req.refresh_token) > 256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    token_hash = hashlib.sha256(req.refresh_token.encode()).hexdigest()
    pool = await get_auth_pool()

    # Look up the refresh token
    async with pool.acquire() as conn:
        rt_row = await conn.fetchrow(
            """SELECT rt.user_id, rt.expires_at, u.role, u.username
               FROM refresh_tokens rt
               JOIN users u ON rt.user_id = u.user_id
               WHERE rt.token_hash = $1 AND rt.revoked = FALSE AND u.is_active = TRUE""",
            token_hash,
        )
        if not rt_row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token.",
            )

        if rt_row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired. Please log in again.",
            )

        user_id = str(rt_row["user_id"])

        # Revoke the old refresh token (rotation)
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
            token_hash,
        )

        # Create new tokens
        token_data = {"sub": user_id, "username": rt_row["username"], "role": rt_row["role"]}
        access_token = create_access_token(token_data)
        raw_refresh, new_hash = create_refresh_token(token_data)

        # Store new refresh token
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        await conn.execute(
            """INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
               VALUES (gen_random_uuid(), $1, $2, $3)""",
            user_id, new_hash, expires_at,
        )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(user: TokenData = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    pool = await get_auth_pool()
    user_row = await db_get_user_by_id(pool, user.user_id)
    if not user_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return UserInfo(
        user_id=user_row["user_id"],
        username=user_row["username"],
        email=user_row["email"],
        full_name=user_row.get("full_name"),
        role=user_row["role"],
        is_active=user_row["is_active"],
    )
