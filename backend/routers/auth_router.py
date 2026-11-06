"""
Auth Router — OAuth2+JWT login, register, refresh, logout, user info.

Refresh tokens are rotated atomically and hashed at rest. Every authentication
event is written to ``auth_audit_log``.
"""

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from auth import (
    LoginRequest, RegisterRequest, RefreshRequest,
    TokenResponse, UserInfo,
    verify_password, hash_password, create_access_token, create_refresh_token,
    get_current_user, require_role, TokenData,
    db_get_user_by_username, db_get_user_by_id, db_create_user,
    db_revoke_refresh_token, db_revoke_all_user_tokens,
    db_get_refresh_token, db_log_auth_event,
    REFRESH_TOKEN_EXPIRE_DAYS, DUMMY_PASSWORD_HASH, limiter,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


def _rate_limit(limit_value: str):
    """Apply a slowapi limit when the limiter is available (no-op otherwise)."""
    if limiter is None:  # pragma: no cover - slowapi is an optional dependency
        def _noop(func):
            return func
        return _noop
    return limiter.limit(limit_value)


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def get_auth_pool():
    """Get the unified database pool."""
    from db import get_pool as _get_pool
    return await _get_pool()


@router.post("/login", response_model=TokenResponse)
@_rate_limit("5/minute")
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

    # Always run bcrypt, even for unknown users, to avoid a timing oracle that
    # would reveal whether a username exists.
    password_hash = user["hashed_password"] if user else DUMMY_PASSWORD_HASH
    password_ok = verify_password(req.password, password_hash)

    if not user or not password_ok:
        await db_log_auth_event(
            pool, user["user_id"] if user else None,
            "FAILED_LOGIN", _client_ip(request),
            request.headers.get("user-agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens (asyncpg returns UUID objects; JWTs must carry JSON strings)
    user_id = str(user["user_id"])
    token_data = {"sub": user_id, "username": user["username"], "role": user["role"]}
    access_token = create_access_token(token_data)
    raw_refresh, refresh_hash = create_refresh_token(token_data)

    # Store refresh token hash. Expiry is computed by the database so it can
    # never drift from the `expires_at > NOW()` rotation check.
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
               VALUES (gen_random_uuid(), $1, $2,
                       NOW() + ($3::int * INTERVAL '1 day'))""",
            user_id, refresh_hash, REFRESH_TOKEN_EXPIRE_DAYS,
        )
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE user_id = $1",
            user["user_id"],
        )

    await db_log_auth_event(
        pool, user_id, "LOGIN",
        _client_ip(request), request.headers.get("user-agent"),
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
        user_id=str(user["user_id"]),
        username=user["username"],
        email=user["email"],
        full_name=user.get("full_name"),
        role=user["role"],
        is_active=user["is_active"],
    )


@router.post("/refresh", response_model=TokenResponse)
@_rate_limit("5/minute")
async def refresh(req: RefreshRequest, request: Request):
    """Exchange a refresh token for new access + refresh tokens (token rotation).

    Rotation is atomic: a single ``UPDATE ... WHERE revoked = FALSE
    AND expires_at > NOW() RETURNING user_id`` claims the token, so two
    concurrent requests can never both succeed.
    """
    if not req.refresh_token or len(req.refresh_token) > 256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    token_hash = hashlib.sha256(req.refresh_token.encode()).hexdigest()
    pool = await get_auth_pool()
    client_ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")

    rotated: Optional[tuple[dict, str, str]] = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            claimed = await conn.fetchrow(
                """UPDATE refresh_tokens
                   SET revoked = TRUE
                   WHERE token_hash = $1 AND revoked = FALSE AND expires_at > NOW()
                   RETURNING user_id""",
                token_hash,
            )
            if claimed:
                user_row = await conn.fetchrow(
                    """SELECT user_id, username, role
                       FROM users WHERE user_id = $1 AND is_active = TRUE""",
                    claimed["user_id"],
                )
                if user_row:
                    user_id = str(user_row["user_id"])
                    token_data = {
                        "sub": user_id,
                        "username": user_row["username"],
                        "role": user_row["role"],
                    }
                    access_token = create_access_token(token_data)
                    raw_refresh, new_hash = create_refresh_token(token_data)
                    await conn.execute(
                        """INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
                           VALUES (gen_random_uuid(), $1, $2,
                                   NOW() + ($3::int * INTERVAL '1 day'))""",
                        user_id, new_hash, REFRESH_TOKEN_EXPIRE_DAYS,
                    )
                    rotated = (dict(user_row), raw_refresh, access_token)

    if rotated is None:
        # The token was not claimable. If it exists at all it was already
        # revoked/expired — treat presentation of a used token as reuse and
        # revoke the whole family for that user.
        existing = await db_get_refresh_token(pool, token_hash)
        if existing and existing.get("user_id"):
            await db_revoke_all_user_tokens(pool, existing["user_id"])
            await db_log_auth_event(
                pool, existing["user_id"], "REFRESH_REUSE", client_ip, user_agent,
            )
            logger.warning("Refresh token reuse detected; revoked all tokens for user %s",
                           existing["user_id"])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked refresh token.",
        )

    user_row, raw_refresh, access_token = rotated
    await db_log_auth_event(
        pool, user_row["user_id"], "REFRESH", client_ip, user_agent,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    req: Optional[LogoutRequest] = Body(default=None),
):
    """Revoke the supplied refresh token (or do nothing when omitted)."""
    raw_token = req.refresh_token if req else None
    if raw_token and len(raw_token) <= 256:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        pool = await get_auth_pool()
        existing = await db_get_refresh_token(pool, token_hash)
        await db_revoke_refresh_token(pool, token_hash)
        if existing and existing.get("user_id"):
            await db_log_auth_event(
                pool, existing["user_id"], "LOGOUT",
                _client_ip(request), request.headers.get("user-agent"),
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    user: TokenData = Depends(get_current_user),
):
    """Revoke every refresh token belonging to the current user."""
    pool = await get_auth_pool()
    await db_revoke_all_user_tokens(pool, user.user_id)
    await db_log_auth_event(
        pool, user.user_id, "LOGOUT_ALL",
        _client_ip(request), request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        user_id=str(user_row["user_id"]),
        username=user_row["username"],
        email=user_row["email"],
        full_name=user_row.get("full_name"),
        role=user_row["role"],
        is_active=user_row["is_active"],
    )
