"""
Authentication & Authorization Service

OAuth2+JWT with RS256 (fallback HS256 for dev), bcrypt password hashing,
refresh token rotation, and RBAC.

Token flow:
- POST /api/auth/login       → access_token (15min) + refresh_token (7d)
- POST /api/auth/refresh     → new access_token + rotated refresh_token
- POST /api/auth/register    → create user (admin only)
- GET  /api/auth/me          → current user info
"""

import logging
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"  # Use RS256 in production with proper key management

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# A valid bcrypt hash of a password nobody knows. Login verifies against this
# when the username does not exist (or is inactive) so that successful and
# failed logins take the same amount of time (closes the user-enumeration
# timing oracle).
DUMMY_PASSWORD_HASH = "$2b$12$lA.qgEvxEcPGyKj0RQAFDufBCIBHEGI0yL4Al3l3sZt3M4nXH7fNi"

# Shared rate limiter. Defined here (not in main.py) so that the auth router can
# use it without a circular import; main.py imports this same instance for
# SlowAPIMiddleware. Memory storage is used outside production so that a
# developer/test environment without Redis never fails requests.
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    _rate_limit_storage = (
        settings.redis_url
        if settings.environment == "production" and settings.redis_url
        else "memory://"
    )
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["120/minute"],
        storage_uri=_rate_limit_storage,
        swallow_errors=True,
    )
except ImportError:  # pragma: no cover - slowapi is an optional dependency
    limiter = None

WRITE_ROLES = ("trade_lead", "project_manager", "admin")

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60

class TokenData(BaseModel):
    user_id: str
    username: str
    role: str

class UserInfo(BaseModel):
    user_id: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "viewer"  # Default to least privilege

class RefreshRequest(BaseModel):
    refresh_token: str

# ---------------------------------------------------------------------------
# Password Utilities
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ---------------------------------------------------------------------------
# JWT Token Utilities
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    """Create a long-lived opaque refresh token (stored hashed in DB)."""
    raw_token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash

def decode_token(token: str) -> Optional[TokenData]:
    """Validate and decode a JWT access token. Returns None if invalid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return TokenData(
            user_id=payload.get("sub", ""),
            username=payload.get("username", ""),
            role=payload.get("role", "viewer"),
        )
    except JWTError:
        return None

# ---------------------------------------------------------------------------
# Role-Based Access Control
# ---------------------------------------------------------------------------

# Permission hierarchy: admin > project_manager > trade_lead > viewer
ROLE_HIERARCHY = {
    "admin": 4,
    "project_manager": 3,
    "trade_lead": 2,
    "viewer": 1,
}

def has_role(user_role: str, required_role: str) -> bool:
    """Check if user_role meets or exceeds required_role.
    Returns False for unknown roles."""
    user_level = ROLE_HIERARCHY.get(user_role)
    required_level = ROLE_HIERARCHY.get(required_role)
    if user_level is None or required_level is None:
        return False
    return user_level >= required_level

def require_role(*roles: str):
    """FastAPI dependency factory — requires at least one of the given roles.

    Usage:
        @router.post("/", dependencies=[Depends(require_role("admin", "project_manager"))])
        async def create_thing(...): ...
    """
    async def role_checker(token_data: TokenData = Depends(get_current_user)):
        if not any(has_role(token_data.role, r) for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {', '.join(roles)}",
            )
        return token_data
    return role_checker

# ---------------------------------------------------------------------------
# Authentication Dependencies
# ---------------------------------------------------------------------------

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> TokenData:
    """FastAPI dependency — validates JWT and returns current user info.

    Raises 401 if token is missing or invalid.

    ``FPSO_AUTH_ENFORCEMENT=false`` is an emergency kill switch only: it makes
    a missing/invalid token resolve to a synthetic admin identity. It is never
    enabled by default and must not be used in production.

    Used as:  user: TokenData = Depends(get_current_user)
    """
    token_data = decode_token(token) if token else None
    if token_data is None and not settings.auth_enforcement:
        logger.warning(
            "AUTH ENFORCEMENT DISABLED: granting synthetic admin access to %s "
            "(FPSO_AUTH_ENFORCEMENT=false)",
            "an unauthenticated request" if not token else "an invalid token",
        )
        return TokenData(
            user_id="00000000-0000-0000-0000-000000000000",
            username="auth-disabled-bypass",
            role="admin",
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a Bearer token in the Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data

# Reusable write-access dependency: every role that may mutate data.
require_write_access = require_role(*WRITE_ROLES)


async def get_optional_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[TokenData]:
    """FastAPI dependency — validates JWT if present, but does not require it.
    Returns None if no token is provided.
    """
    if not token:
        return None
    return decode_token(token)

# ---------------------------------------------------------------------------
# Database Operations (raw SQL via pool)
# ---------------------------------------------------------------------------

async def db_create_user(pool, username: str, email: str, password_hash: str,
                         full_name: Optional[str], role: str) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO users (user_id, username, email, hashed_password, full_name, role)
               VALUES (gen_random_uuid(), $1, $2, $3, $4, $5)
               RETURNING user_id, username, email, full_name, role, is_active, created_at""",
            username, email, password_hash, full_name, role,
        )
        return dict(row)

async def db_get_user_by_username(pool, username: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE username = $1 AND is_active = TRUE",
            username,
        )
        return dict(row) if row else None

async def db_get_user_by_id(pool, user_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1 AND is_active = TRUE",
            user_id,
        )
        return dict(row) if row else None

async def db_store_refresh_token(pool, user_id: str, token_hash: str, expires_at: datetime):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO refresh_tokens (token_id, user_id, token_hash, expires_at)
               VALUES (gen_random_uuid(), $1, $2, $3)""",
            user_id, token_hash, expires_at,
        )

async def db_revoke_refresh_token(pool, token_hash: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1",
            token_hash,
        )

async def db_revoke_all_user_tokens(pool, user_id: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1",
            user_id,
        )

async def db_log_auth_event(pool, user_id: Optional[str], event_type: str,
                            ip_address: Optional[str] = None, user_agent: Optional[str] = None):
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO auth_audit_log (log_id, user_id, event_type, ip_address, user_agent)
               VALUES (gen_random_uuid(), $1, $2, $3, $4)""",
            user_id, event_type, ip_address, user_agent,
        )


async def db_get_refresh_token(pool, token_hash: str) -> Optional[dict]:
    """Look up a refresh token by its SHA-256 hash (any state)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id, expires_at, revoked FROM refresh_tokens WHERE token_hash = $1",
            token_hash,
        )
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Project Membership (row-level authorization)
# ---------------------------------------------------------------------------

async def db_project_has_members(pool, project_id: str) -> bool:
    async with pool.acquire() as conn:
        # ::text keeps this working when project identifiers are UUIDs in the
        # database but opaque strings (e.g. "demo-project") in the API.
        return bool(await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM project_members WHERE project_id::text = $1)",
            project_id,
        ))


async def db_user_is_project_member(pool, project_id: str, user_id: str) -> bool:
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(
            """SELECT EXISTS (
                   SELECT 1 FROM project_members
                   WHERE project_id::text = $1 AND user_id::text = $2
               )""",
            project_id, user_id,
        ))


async def user_has_project_access(pool, project_id: str, user: TokenData) -> bool:
    """Return True when ``user`` may access ``project_id``.

    Rules:
    - ``admin`` and ``project_manager`` bypass membership checks.
    - Otherwise the user must be listed in ``project_members``.
    - Backward compatibility: if a project has no membership rows at all, any
      authenticated user is allowed. This keeps existing deployments working
      before memberships are populated. Once a project has at least one
      membership row it becomes closed and only members (plus admins/PMs) pass.
    """
    if user.role in ("admin", "project_manager"):
        return True
    try:
        if not await db_project_has_members(pool, project_id):
            return True
        return await db_user_is_project_member(pool, project_id, user.user_id)
    except Exception as exc:  # pragma: no cover - depends on deployed schema
        # Missing migration -> treat as "no memberships" for compatibility.
        if getattr(exc, "sqlstate", None) == "42P01":
            logger.warning(
                "project_members table is missing; allowing authenticated access "
                "to project %s (apply database/migrations/004_auth_hardening.sql)",
                project_id,
            )
            return True
        raise


async def _get_db_pool():
    """Indirection so auth.py does not import the pool module at import time."""
    from db import get_pool
    return await get_pool()


async def require_project_access(
    project_id: str,
    user: TokenData = Depends(get_current_user),
    pool=Depends(_get_db_pool),
) -> TokenData:
    """FastAPI dependency — requires project membership (see rules above)."""
    if not await user_has_project_access(pool, project_id, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project.",
        )
    return user


# ---------------------------------------------------------------------------
# Admin bootstrap
# ---------------------------------------------------------------------------

async def bootstrap_admin(pool) -> Optional[dict]:
    """Create the initial admin account when the users table is empty.

    The password comes from ``FPSO_BOOTSTRAP_ADMIN_PASSWORD``. In production a
    missing password is a hard startup failure (otherwise the system would have
    no way to authenticate). In development/test it is a warning.
    """
    try:
        async with pool.acquire() as conn:
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
    except Exception as exc:
        logger.warning("Skipping admin bootstrap (users table unavailable): %s", exc)
        return None

    if user_count:
        return None

    password = settings.bootstrap_admin_password
    if not password:
        if settings.environment == "production":
            raise RuntimeError(
                "No users exist and FPSO_BOOTSTRAP_ADMIN_PASSWORD is not set. "
                "Set it before starting in production."
            )
        logger.warning(
            "No users exist and FPSO_BOOTSTRAP_ADMIN_PASSWORD is not set; "
            "skipping admin bootstrap (use dev_main.py or configure a password)."
        )
        return None

    username = settings.bootstrap_admin_username
    user = await db_create_user(
        pool,
        username=username,
        email=f"{username}@fpso-epc.local",
        password_hash=hash_password(password),
        full_name="System Administrator",
        role="admin",
    )
    await db_log_auth_event(pool, user["user_id"], "BOOTSTRAP_ADMIN")
    logger.info("Bootstrapped initial admin user '%s'", username)
    return user
