from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.security.auth import decode_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Validate JWT token and return the current user claims.

    Raises 401 if no token is provided or the token is invalid.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — please provide a valid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type — expected an access token.",
            )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject claim.",
            )
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc

    return {"user_id": user_id, "role": payload.get("role", "viewer")}



def require_role(*allowed_roles: str):
    """Return a dependency that checks the current user has one of the allowed roles."""

    async def _check(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.get('role')}' not in {allowed_roles}",
            )
        return current_user

    return _check
