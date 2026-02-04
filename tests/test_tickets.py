from __future__ import annotations

import uuid

import pytest
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.core.settings import settings
from app.models.enums import UserRole
from app.models.user import User
from app.db.session import SessionLocal


async def _create_user(email: str, role: UserRole) -> User:
    async with SessionLocal() as session:
        user = User(
            email=email,
            hashed_password=hash_password("Password123"),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, role=str(user.role))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
async def redis() -> Redis:
    r = Redis.from_url(settings.redis_url, decode_responses=False)
    await r.flushdb()
    try:
        yield r
    finally:
        await r.aclose()


@pytest.mark.asyncio
async def test_user_create_and_idempotency(async_client, redis):
    user = await _create_user("u1@example.com", UserRole.USER)

    payload = {
        "title": "Test",
        "description": "Desc",
        "priority": "MEDIUM",
        "tags": ["it"],
    }
    key = str(uuid.uuid4())
    r1 = await async_client.post(
        "/v1/tickets",
        json=payload,
        headers={**_auth_header(user), "Idempotency-Key": key},
    )
    assert r1.status_code == 201, r1.text
    t1 = r1.json()

    r2 = await async_client.post(
        "/v1/tickets",
        json=payload,
        headers={**_auth_header(user), "Idempotency-Key": key},
    )
    assert r2.status_code == 201, r2.text
    t2 = r2.json()
    assert t2["id"] == t1["id"]


@pytest.mark.asyncio
async def test_permissions_user_cannot_view_others(async_client):
    u1 = await _create_user("u1@example.com", UserRole.USER)
    u2 = await _create_user("u2@example.com", UserRole.USER)

    r = await async_client.post(
        "/v1/tickets",
        json={"title": "A", "description": "B", "priority": "LOW"},
        headers=_auth_header(u1),
    )
    tid = r.json()["id"]

    r = await async_client.get(f"/v1/tickets/{tid}", headers=_auth_header(u2))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_agent_can_list_all_user_only_own(async_client):
    u1 = await _create_user("u1@example.com", UserRole.USER)
    u2 = await _create_user("u2@example.com", UserRole.USER)
    agent = await _create_user("a1@example.com", UserRole.AGENT)

    await async_client.post(
        "/v1/tickets",
        json={"title": "T1", "description": "", "priority": "LOW"},
        headers=_auth_header(u1),
    )
    await async_client.post(
        "/v1/tickets",
        json={"title": "T2", "description": "", "priority": "LOW"},
        headers=_auth_header(u2),
    )

    r = await async_client.get("/v1/tickets", headers=_auth_header(agent))
    assert r.status_code == 200
    assert r.json()["total"] == 2

    r = await async_client.get("/v1/tickets", headers=_auth_header(u1))
    assert r.status_code == 200
    assert r.json()["total"] == 1


@pytest.mark.asyncio
async def test_workflow_transitions(async_client):
    user = await _create_user("u1@example.com", UserRole.USER)
    agent = await _create_user("a1@example.com", UserRole.AGENT)

    r = await async_client.post(
        "/v1/tickets",
        json={"title": "T", "description": "", "priority": "LOW"},
        headers=_auth_header(user),
    )
    tid = r.json()["id"]

    r = await async_client.post(
        f"/v1/tickets/{tid}/transition",
        json={"status": "IN_PROGRESS"},
        headers=_auth_header(agent),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"

    r = await async_client.post(
        f"/v1/tickets/{tid}/transition",
        json={"status": "DONE"},
        headers=_auth_header(agent),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "DONE"
    assert r.json()["closed_at"] is not None

    # DONE is terminal
    r = await async_client.post(
        f"/v1/tickets/{tid}/transition",
        json={"status": "IN_PROGRESS"},
        headers=_auth_header(agent),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_soft_delete_and_admin_include_deleted(async_client):
    user = await _create_user("u1@example.com", UserRole.USER)
    admin = await _create_user("admin@example.com", UserRole.ADMIN)

    r = await async_client.post(
        "/v1/tickets",
        json={"title": "T", "description": "", "priority": "LOW"},
        headers=_auth_header(user),
    )
    tid = r.json()["id"]

    r = await async_client.delete(f"/v1/tickets/{tid}", headers=_auth_header(user))
    assert r.status_code == 200

    r = await async_client.get("/v1/tickets", headers=_auth_header(user))
    assert r.json()["total"] == 0

    r = await async_client.get("/v1/tickets?include_deleted=true", headers=_auth_header(admin))
    assert r.status_code == 200
    assert r.json()["total"] == 1
