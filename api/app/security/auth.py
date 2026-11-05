from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
STREAM_TOKEN_EXPIRE_SECONDS = 120

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _base_claims(subject: str, token_type: str, expires: datetime) -> dict[str, Any]:
    return {
        "sub": subject,
        "iat": datetime.now(timezone.utc),
        "exp": expires,
        "jti": str(uuid.uuid4()),
        "type": token_type,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT access token for the given subject (user_id)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    claims = _base_claims(subject, "access", expire)
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)


def issue_refresh_token(subject: str) -> tuple[str, str, datetime]:
    """Create a refresh token and return (token, jti, expires_at).

    The jti is persisted by the caller so rotation and reuse detection are possible.
    """
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    claims = _base_claims(subject, "refresh", expire)
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, str(claims["jti"]), expire


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate issuer/audience. Raises JWTError on failure."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )


def create_api_key() -> str:
    """Generate a cryptographically random API key for M2M auth."""
    return f"ak_{uuid.uuid4().hex}{uuid.uuid4().hex}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage (prefix is preserved for identification)."""
    return pwd_context.hash(api_key)


def create_stream_token(subject: str, task_id: str) -> str:
    """Short-lived token authorising one WebSocket/SSE stream for one task."""
    expire = datetime.now(timezone.utc) + timedelta(seconds=STREAM_TOKEN_EXPIRE_SECONDS)
    claims = _base_claims(subject, "stream", expire)
    claims["scope"] = f"stream:{task_id}"
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_stream_token(token: str, task_id: str) -> str:
    """Validate a stream token and return its subject. Raises JWTError."""
    claims = decode_token(token)
    if claims.get("type") != "stream":
        raise JWTError("not a stream token")
    if claims.get("scope") != f"stream:{task_id}":
        raise JWTError("stream token scope mismatch")
    subject = claims.get("sub")
    if not isinstance(subject, str) or subject == "":
        raise JWTError("stream token missing subject")
    return subject