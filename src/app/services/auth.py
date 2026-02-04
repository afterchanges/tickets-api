from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.core.settings import settings
from app.models.enums import UserRole
from app.models.refresh_token import RefreshToken
from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def register_user(db: AsyncSession, *, email: str, password: str) -> User:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ValueError("email_taken")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> User | None:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def issue_tokens(db: AsyncSession, *, user: User, rotate_refresh: bool = True) -> tuple[str, str]:
    access = create_access_token(user_id=user.id, role=str(user.role))

    refresh_jti = uuid.uuid4()
    expires_at = _utcnow() + timedelta(days=int(settings.jwt_refresh_ttl_days))
    refresh = create_refresh_token(
        user_id=user.id,
        role=str(user.role),
        jti=refresh_jti,
        expires_at=expires_at,
    )

    token_row = RefreshToken(
        user_id=user.id,
        jti=refresh_jti,
        expires_at=expires_at,
    )
    db.add(token_row)
    await db.commit()

    return access, refresh


async def refresh_tokens(db: AsyncSession, *, refresh_token: str) -> tuple[str, str]:
    from app.core.security import decode_token

    decoded = decode_token(refresh_token)
    if decoded.token_type != "refresh":
        raise ValueError("invalid_token_type")

    token_row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == decoded.jti))
    if token_row is None:
        raise ValueError("refresh_not_found")
    if token_row.revoked_at is not None:
        raise ValueError("refresh_revoked")
    if token_row.expires_at <= _utcnow():
        raise ValueError("refresh_expired")

    user = await db.scalar(select(User).where(User.id == token_row.user_id))
    if user is None or not user.is_active:
        raise ValueError("user_invalid")

    token_row.revoked_at = _utcnow()
    await db.commit()

    return await issue_tokens(db, user=user, rotate_refresh=True)


async def revoke_refresh_token(db: AsyncSession, *, refresh_token: str) -> None:
    from app.core.security import decode_token

    decoded = decode_token(refresh_token)
    if decoded.token_type != "refresh":
        raise ValueError("invalid_token_type")

    token_row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == decoded.jti))
    if token_row is None:
        return
    if token_row.revoked_at is None:
        token_row.revoked_at = _utcnow()
        await db.commit()
