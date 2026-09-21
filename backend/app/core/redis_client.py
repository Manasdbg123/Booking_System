from redis import asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """RESP2 is pinned explicitly: redis-py >=5 negotiates RESP3 with a HELLO
    command on connect, which the Redis 5.x Windows port used for local dev
    doesn't implement. RESP2 is understood by every server version we target
    (the 5.x local port and the Redis 7 image in docker-compose), and nothing
    here needs RESP3-only features."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True, protocol=2)
    return _redis
