"""Postgres TTL cache with stale-on-provider-failure fallback."""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, PoolClosed, PoolTimeout

logger = logging.getLogger(__name__)


@dataclass
class CacheResult:
    value: Any
    stale: bool = False


class CacheService:
    def __init__(self) -> None:
        self._pool: AsyncConnectionPool | None = None

    def initialize(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    def shutdown(self) -> None:
        self._pool = None

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        if self._pool is None:
            return None
        try:
            async with self._pool.connection(timeout=2) as conn:
                row = await (await conn.execute(
                    "SELECT response_json, expires_at FROM finance_agent.api_cache WHERE cache_key = %s",
                    (cache_key,),
                )).fetchone()
        except (psycopg.Error, PoolClosed, PoolTimeout):
            logger.warning("Could not read the Postgres market-data cache")
            return None
        if row is None:
            return None
        payload = row["response_json"]
        if not isinstance(payload, dict):
            payload = {"__wrapped_list__": payload}
        return {**payload, "_cache_expires_at": row["expires_at"]}

    async def set(self, cache_key: str, value: Any, ttl_seconds: int, source: str | None = None) -> None:
        if self._pool is None:
            return
        now = int(time.time())
        try:
            async with self._pool.connection(timeout=2) as conn:
                await conn.execute(
                    """
                    INSERT INTO finance_agent.api_cache (cache_key, response_json, cached_at, expires_at, source)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (cache_key) DO UPDATE SET response_json = EXCLUDED.response_json,
                      cached_at = EXCLUDED.cached_at, expires_at = EXCLUDED.expires_at, source = EXCLUDED.source
                    """,
                    (cache_key, Jsonb(value), now, now + ttl_seconds, source),
                )
        except (psycopg.Error, PoolClosed, PoolTimeout):
            logger.warning("Could not write the Postgres market-data cache")

    async def get_or_fetch(
        self, cache_key: str, ttl_seconds: int, fetcher: Callable[[], Any], source: str | None = None,
    ) -> CacheResult:
        cached = await self.get(cache_key)
        cached_value = None
        if cached is not None:
            expires_at = cached.pop("_cache_expires_at")
            cached.pop("_stale", None)
            cached_value = cached.get("__wrapped_list__", cached)
            if expires_at > int(time.time()):
                return CacheResult(value=cached_value)
        try:
            value = fetcher()
            if inspect.isawaitable(value):
                value = await value
        except Exception:
            if cached is None:
                raise
            if isinstance(cached_value, dict):
                cached_value["_stale"] = True
            return CacheResult(value=cached_value, stale=True)

        await self.set(cache_key, value, ttl_seconds, source=source)
        return CacheResult(value=value)


cache_service = CacheService()
