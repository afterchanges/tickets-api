from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.settings import settings


ALGORITHM = "HS256"

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


@dataclass(frozen=True)
class DecodedToken:
    sub: uuid.UUID
    role: str
    token_type: str
    jti: uuid.UUID
    exp: datetime
    iat: datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_access_token(*, user_id: uuid.UUID, role: str) -> str:
    now = _utcnow()
    exp = now + timedelta(minutes=int(settings.jwt_access_ttl_min))
    jti = uuid.uuid4()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: uuid.UUID, role: str, jti: uuid.UUID, expires_at: datetime) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> DecodedToken:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc

    try:
        sub = uuid.UUID(str(payload.get("sub")))
        role = str(payload.get("role"))
        token_type = str(payload.get("type"))
        jti = uuid.UUID(str(payload.get("jti")))
        exp_ts = int(payload.get("exp"))
        iat_ts = int(payload.get("iat"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid_claims") from exc

    return DecodedToken(
        sub=sub,
        role=role,
        token_type=token_type,
        jti=jti,
        exp=datetime.fromtimestamp(exp_ts, tz=UTC),
        iat=datetime.fromtimestamp(iat_ts, tz=UTC),
    )
