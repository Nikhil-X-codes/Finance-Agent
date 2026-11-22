"""Phase 1 mutual fund tools with FinAPI primary and stale fallback."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from ...config.constants import MF_METADATA_CACHE_TTL_SECONDS
from ...config.settings import settings
from ...services.cache_service import cache_service


@dataclass(slots=True)
class MFResult:
    data: dict[str, Any]
    stale: bool = False
    error: str | None = None


class MFTools:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
        return self._client

    @staticmethod
    def _cache_key(prefix: str, isin: str) -> str:
        return f"{prefix}:{isin.upper()}"

    @staticmethod
    def _is_fresh(payload: dict[str, Any]) -> bool:
        expires_at = int(payload.get("_cache_expires_at", 0) or 0)
        return expires_at > int(time.time())

    @staticmethod
    def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key not in {"_cache_expires_at", "_stale"}}

    @staticmethod
    def _decorate(
        payload: dict[str, Any],
        *,
        cached: bool,
        fresh: bool,
        source: str | None = None,
        stale_warning: str | None = None,
    ) -> dict[str, Any]:
        data = dict(payload)
        data["cached"] = cached
        data["fresh"] = fresh
        if source is not None:
            data["source"] = source
        if stale_warning:
            data["stale_warning"] = stale_warning
        return data

    def _metadata_lookup(self) -> dict[str, Any]:
        return {}

    def _reverse_lookup(self) -> dict[str, str]:
        return {}

    def _resolve_isin(self, isin_or_scheme_code: str) -> tuple[str, dict[str, Any]]:
        key = isin_or_scheme_code.strip().upper()
        lookup = self._metadata_lookup()
        if key in lookup:
            return key, lookup[key]
        reverse = self._reverse_lookup()
        isin = reverse.get(key)
        if isin and isin in lookup:
            return isin, lookup[isin]
        return key, {}

    async def _fetch_finapi(self, scheme_code: str, fields: str | None = None) -> dict[str, Any]:
        client = await self._get_client()
        url = f"{settings.finapi_base_url.rstrip('/')}/mf/{scheme_code}"
        response = await client.get(url, params={"fields": fields} if fields else None)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload if isinstance(payload, dict) else {"data": payload}

    async def get_metadata(self, isin: str) -> MFResult:
        resolved_isin, metadata = self._resolve_isin(isin)
        scheme_code = str(metadata.get("schemeCode") or resolved_isin).strip()
        cache_key = self._cache_key("FINAPI_META", resolved_isin)
        cached = await cache_service.get(cache_key)
        if cached is not None and self._is_fresh(cached):
            return MFResult(data=self._decorate(self._public_payload(cached), cached=True, fresh=True), stale=False)

        stale_payload = self._public_payload(cached) if cached is not None else None

        try:
            payload = await self._fetch_finapi(scheme_code, fields="expenseRatio,aum,schemeCategory,benchmark")
            value = {
                "isin": resolved_isin,
                "scheme_code": scheme_code,
                "expense_ratio": payload.get("expenseRatio") or metadata.get("expenseRatio"),
                "aum": payload.get("aum") or metadata.get("aum"),
                "category": payload.get("schemeCategory") or metadata.get("category"),
                "benchmark": payload.get("benchmark") or metadata.get("benchmark"),
                "source": "FINAPI",
            }
            await cache_service.set(cache_key, value, MF_METADATA_CACHE_TTL_SECONDS, source="FINAPI")
            return MFResult(data=self._decorate(value, cached=False, fresh=True, source="FINAPI"), stale=False)
        except Exception as finapi_error:
            if stale_payload is not None:
                return MFResult(
                    data=self._decorate(
                        stale_payload,
                        cached=True,
                        fresh=False,
                        source=stale_payload.get("source", "FINAPI"),
                        stale_warning="FinAPI unavailable; serving stale metadata",
                    ),
                    stale=True,
                    error=str(finapi_error),
                )
            return MFResult(
                data={"isin": resolved_isin, "scheme_code": scheme_code, "error": "MF_METADATA_UNAVAILABLE"},
                stale=False,
                error=str(finapi_error),
            )

mf_tools = MFTools()


async def get_metadata(isin: str) -> MFResult:
    return await mf_tools.get_metadata(isin)
