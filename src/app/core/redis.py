from __future__ import annotations

from redis.asyncio import Redis

from app.core.settings import settings


redis_client: Redis = Redis.from_url(
    settings.redis_url,
    decode_responses=False,
)
