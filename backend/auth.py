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
    Used as:  user: TokenData = Depends(get_current_user)
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a Bearer token in the Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = decode_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data

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
