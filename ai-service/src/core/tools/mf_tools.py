"""MFapi.in scheme metadata and latest NAV."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from ...config.constants import MF_METADATA_CACHE_TTL_SECONDS
from ...config.settings import settings
from ...services.cache_service import cache_service

MFAPI_SOURCE = "MFapi.in"


def _mfapi_url() -> str:
    return f"{settings.mfapi_base_url.rstrip('/')}/mf"


async def get_mfapi_catalog(client: httpx.AsyncClient) -> list[dict]:
    async def fetch():
        response = await client.get(_mfapi_url())
        response.raise_for_status()
        catalog = response.json()
        if not isinstance(catalog, list) or not catalog:
            raise ValueError("MFapi.in returned an invalid scheme catalog.")
        return catalog

    cached = await cache_service.get_or_fetch("MFAPI_CATALOG", 86400, fetch, source=MFAPI_SOURCE)
    return cached.value


async def fetch_mfapi_scheme(client: httpx.AsyncClient, scheme_code: str) -> dict:
    if not scheme_code.isascii() or not scheme_code.isdecimal():
        raise ValueError("MFapi.in scheme codes must be numeric.")
    response = await client.get(f"{_mfapi_url()}/{scheme_code}/latest")
    response.raise_for_status()
    payload = response.json()
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("meta"), dict)
        or not isinstance(payload.get("data"), list)
        or str(payload["meta"].get("scheme_code")) != scheme_code
    ):
        raise ValueError("MFapi.in returned invalid scheme details.")
    return payload


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

    async def get_metadata(self, isin: str) -> MFResult:
        resolved_isin = isin.strip().upper()
        scheme_code = resolved_isin
        cache_key = self._cache_key("MFAPI_META", resolved_isin)
        cached = await cache_service.get(cache_key)
        if cached is not None and self._is_fresh(cached):
            return MFResult(data=self._decorate(self._public_payload(cached), cached=True, fresh=True), stale=False)

        stale_payload = self._public_payload(cached) if cached is not None else None

        try:
            client = await self._get_client()
            if not scheme_code.isdecimal():
                catalog = await get_mfapi_catalog(client)
                scheme_code = next((
                    str(scheme["schemeCode"]) for scheme in catalog
                    if isinstance(scheme, dict) and scheme.get("schemeCode")
                    and resolved_isin in (scheme.get("isinGrowth"), scheme.get("isinDivReinvestment"))
                ), "")
                if not scheme_code:
                    raise ValueError("MFapi.in has no scheme for this ISIN.")
            payload = await fetch_mfapi_scheme(client, scheme_code)
            scheme = payload["meta"]
            value = {
                "isin": resolved_isin,
                "scheme_code": scheme_code,
                "expense_ratio": None,
                "aum": None,
                "category": scheme.get("scheme_category"),
                "benchmark": None,
                "source": MFAPI_SOURCE,
            }
            await cache_service.set(cache_key, value, MF_METADATA_CACHE_TTL_SECONDS, source=MFAPI_SOURCE)
            return MFResult(data=self._decorate(value, cached=False, fresh=True, source=MFAPI_SOURCE), stale=False)
        except Exception as provider_error:
            if stale_payload is not None:
                return MFResult(
                    data=self._decorate(
                        stale_payload,
                        cached=True,
                        fresh=False,
                        source=stale_payload.get("source", MFAPI_SOURCE),
                        stale_warning="MFapi.in unavailable; serving stale metadata",
                    ),
                    stale=True,
                    error=str(provider_error),
                )
            return MFResult(
                data={"isin": resolved_isin, "scheme_code": scheme_code, "error": "MF_METADATA_UNAVAILABLE"},
                stale=False,
                error=str(provider_error),
            )

mf_tools = MFTools()


async def get_metadata(isin: str) -> MFResult:
    return await mf_tools.get_metadata(isin)
