from __future__ import annotations

import time

from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.redis import redis_client


logger = get_logger(__name__)


async def hit(*, key: str, limit: int, window_sec: int) -> tuple[bool, int]:
    now = int(time.time())
    window_start = now - (now % window_sec)
    retry_after = window_sec - (now % window_sec)

    redis_key = f"{key}:{window_start}".encode("utf-8")

    try:
        count = await redis_client.incr(redis_key)
        if int(count) == 1:
            await redis_client.expire(redis_key, window_sec + 1)
        allowed = int(count) <= int(limit)
        return allowed, retry_after
    except RedisError:
        logger.warning("rate_limit_redis_unavailable", key=key)
        return True, 0
