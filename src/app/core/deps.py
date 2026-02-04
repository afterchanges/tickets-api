from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User


bearer_scheme = HTTPBearer(auto_error=False)


def _err(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _err("auth_required", "Authentication required", status.HTTP_401_UNAUTHORIZED)

    try:
        decoded = decode_token(credentials.credentials)
    except ValueError:
        raise _err("invalid_token", "Invalid token", status.HTTP_401_UNAUTHORIZED)

    if decoded.token_type != "access":
        raise _err("invalid_token_type", "Access token required", status.HTTP_401_UNAUTHORIZED)

    user = await db.scalar(select(User).where(User.id == decoded.sub))
    if user is None:
        raise _err("user_not_found", "User not found", status.HTTP_401_UNAUTHORIZED)
    if not user.is_active:
        raise _err("user_inactive", "User is inactive", status.HTTP_403_FORBIDDEN)
    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise _err("forbidden", "Insufficient role", status.HTTP_403_FORBIDDEN)
        return user

    return _dep
