from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_register_login_me_refresh(async_client):
    # Register
    r = await async_client.post(
        "/v1/auth/register",
        json={"email": "user1@example.com", "password": "Password123"},
    )
    assert r.status_code == 200, r.text
    user = r.json()
    assert user["email"] == "user1@example.com"
    assert user["role"] == "USER"
    assert user["is_active"] is True

    # Login
    r = await async_client.post(
        "/v1/auth/login",
        json={"email": "user1@example.com", "password": "Password123"},
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens

    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    # Me
    r = await async_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["email"] == "user1@example.com"

    # Refresh (rotates refresh token)
    r = await async_client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    new_tokens = r.json()
    assert new_tokens["access_token"] != access
    assert new_tokens["refresh_token"] != refresh

    # Old refresh should be rejected now
    r = await async_client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh(async_client):
    await async_client.post(
        "/v1/auth/register",
        json={"email": "user2@example.com", "password": "Password123"},
    )
    r = await async_client.post(
        "/v1/auth/login",
        json={"email": "user2@example.com", "password": "Password123"},
    )
    tokens = r.json()
    refresh = tokens["refresh_token"]

    r = await async_client.post("/v1/auth/logout", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    r = await async_client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401
