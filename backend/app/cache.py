"""
Redis cache layer.
Provides a simple async get/set/delete/invalidate API.
Falls back gracefully if Redis is unavailable (no-op cache).
"""
import json
import os
import logging
from functools import wraps
from typing import Any, Callable, Optional

log = logging.getLogger("webpanel.cache")

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_TTL = 60  # seconds

_redis: Optional[Any] = None


async def get_redis():
    global _redis
    if not _REDIS_AVAILABLE:
        return None
    if _redis is None:
        try:
            _redis = aioredis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
            await _redis.ping()
        except Exception as exc:
            log.warning("Redis unavailable: %s — running without cache", exc)
            _redis = None
    return _redis


async def cache_get(key: str) -> Any:
    r = await get_redis()
    if r is None:
        return None
    try:
        val = await r.get(key)
        return json.loads(val) if val is not None else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


async def cache_delete(key: str) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.delete(key)
    except Exception:
        pass


async def cache_invalidate_prefix(prefix: str) -> None:
    """Delete all keys matching prefix:*"""
    r = await get_redis()
    if r is None:
        return
    try:
        keys = await r.keys(f"{prefix}:*")
        if keys:
            await r.delete(*keys)
    except Exception:
        pass


def cached(prefix: str, ttl: int = DEFAULT_TTL):
    """
    Decorator for async functions. Caches the return value in Redis.
    Cache key is built from prefix + str(args).

    Usage:
        @cached("server_stats", ttl=5)
        async def get_stats():
            ...
    """
    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            key = f"{prefix}:{args}:{sorted(kwargs.items())}"
            cached_val = await cache_get(key)
            if cached_val is not None:
                return cached_val
            result = await fn(*args, **kwargs)
            await cache_set(key, result, ttl)
            return result
        return wrapper
    return decorator
