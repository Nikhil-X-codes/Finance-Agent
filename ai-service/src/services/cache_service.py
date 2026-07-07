"""SQLite TTL cache with stale-on-failure fallback."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..config.constants import SQLITE_CACHE_TABLE


Fetcher = Callable[[], Any]


@dataclass
class CacheResult:
    value: Any
    stale: bool = False


class CacheService:
    def __init__(self) -> None:
        self._path: str | None = None

    def initialize(self, sqlite_path: str) -> None:
        self._path = sqlite_path
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._path is None:
            raise RuntimeError("CacheService not initialized")
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SQLITE_CACHE_TABLE} (
                  cache_key TEXT PRIMARY KEY,
                  response_json TEXT NOT NULL,
                  cached_at INTEGER NOT NULL,
                  expires_at INTEGER NOT NULL,
                  source TEXT
                )
                """
            )
            conn.commit()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT response_json, expires_at FROM {SQLITE_CACHE_TABLE} WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["response_json"])
        if isinstance(payload, dict):
            payload["_cache_expires_at"] = int(row["expires_at"])
            return payload
        else:
            return {
                "__wrapped_list__": payload,
                "_cache_expires_at": int(row["expires_at"])
            }

    @staticmethod
    def _without_metadata(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key not in {"_cache_expires_at", "_stale"}
        }

    def set(self, cache_key: str, value: Any, ttl_seconds: int, source: str | None = None) -> None:
        now = int(time.time())
        expires_at = now + ttl_seconds
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {SQLITE_CACHE_TABLE} (cache_key, response_json, cached_at, expires_at, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  response_json = excluded.response_json,
                  cached_at = excluded.cached_at,
                  expires_at = excluded.expires_at,
                  source = excluded.source
                """,
                (cache_key, json.dumps(value), now, expires_at, source),
            )
            conn.commit()

    async def get_or_fetch(
        self,
        cache_key: str,
        ttl_seconds: int,
        fetcher: Fetcher,
        source: str | None = None,
    ) -> CacheResult:
        cached = self.get(cache_key)
        if cached is not None:
            expires_at = cached.pop("_cache_expires_at", 0)
            if expires_at > int(time.time()):
                val = cached.get("__wrapped_list__") if "__wrapped_list__" in cached else cached
                return CacheResult(value=val, stale=False)

        try:
            value = fetcher()
            if hasattr(value, "__await__"):
                value = await value  # type: ignore[func-returns-value]
            self.set(cache_key, value, ttl_seconds, source=source)
            return CacheResult(value=value, stale=False)
        except Exception:
            if cached is not None:
                stale_value = self._without_metadata(cached)
                stale_value = stale_value.get("__wrapped_list__") if "__wrapped_list__" in stale_value else stale_value
                if isinstance(stale_value, dict):
                    stale_value["_stale"] = True
                return CacheResult(value=stale_value, stale=True)
            raise


cache_service = CacheService()
