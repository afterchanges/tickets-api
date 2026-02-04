from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
)
from app.services.auth import (
    authenticate_user,
    issue_tokens,
    refresh_tokens,
    register_user,
    revoke_refresh_token,
)


router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _err(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


@router.post("/register", response_model=MeResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, email=str(payload.email), password=payload.password)
    except ValueError as exc:
        if str(exc) == "email_taken":
            raise _err("email_taken", "Email already registered", status.HTTP_409_CONFLICT)
        raise

    return MeResponse(
        id=str(user.id),
        email=user.email,
        role=str(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, email=str(payload.email), password=payload.password)
    if user is None:
        raise _err("invalid_credentials", "Invalid email or password", status.HTTP_401_UNAUTHORIZED)

    access, refresh = await issue_tokens(db, user=user)
    return TokenPairResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        access, refresh_token = await refresh_tokens(db, refresh_token=payload.refresh_token)
    except ValueError as exc:
        code = str(exc)
        raise _err(code, "Refresh token is invalid", status.HTTP_401_UNAUTHORIZED)

    return TokenPairResponse(access_token=access, refresh_token=refresh_token)


@router.post("/logout")
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)):
    try:
        await revoke_refresh_token(db, refresh_token=payload.refresh_token)
    except ValueError:
        pass
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(user=Depends(get_current_user)):
    return MeResponse(
        id=str(user.id),
        email=user.email,
        role=str(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
    )
