"""Token-bucket rate limiting implemented atomically in Redis via a Lua script.

The script is the standard token-bucket refill algorithm: each key stores
(tokens, last_refill_ts). On each call we refill based on elapsed time, then
try to take 1 token. Doing the whole thing in one EVAL keeps it race-free
under concurrent requests from the same user/IP without needing a separate
lock.
"""

from app.core.redis_client import get_redis

_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])  -- tokens per second
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)

return allowed
"""


async def check_rate_limit(key: str, capacity: int, per_minute: int) -> bool:
    """Returns True if the request is allowed."""
    import time

    redis = get_redis()
    refill_rate = per_minute / 60.0
    result = await redis.eval(_TOKEN_BUCKET_LUA, 1, key, capacity, refill_rate, time.time(), 120)
    return bool(int(result))
