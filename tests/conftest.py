from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.app import app
from app.db.session import SessionLocal


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
async def async_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
async def clean_db() -> None:
    async with SessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE refresh_tokens, ticket_events, ticket_comments, tickets, users RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
