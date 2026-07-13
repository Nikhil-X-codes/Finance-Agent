"""Middleware that validates the internal API key on every request."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config.constants import INTERNAL_API_HEADER
from ..config.settings import settings


class InternalApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
            
        path = request.url.path
        
        # Exact match bypasses
        bypass_exact = {
            "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico", "/",
            "/parse-statement", "/v1/enrich", "/validate-trade",
            "/generate-report", "/qa",
            "/mf/categories", "/v1/stocks/popular", "/v1/stocks/search",
        }
        
        # Prefix match bypasses (any path starting with these)
        bypass_prefixes = (
            "/mf/comparison/",
            "/tools/",
            "/v1/stocks/",  # <-- This covers /v1/stocks/RELIANCE, /v1/stocks/HDFCBANK, etc.
        )
        
        # Check exact match
        if path in bypass_exact:
            return await call_next(request)
        
        # Check prefix match
        if any(path.startswith(prefix) for prefix in bypass_prefixes):
            return await call_next(request)
        
        # Require auth for everything else
        provided_key = request.headers.get(INTERNAL_API_HEADER)
        if not settings.internal_api_key:
            return JSONResponse(
                {"error": "AI_UNAVAILABLE", "code": "AI_UNAVAILABLE"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if provided_key != settings.internal_api_key:
            return JSONResponse(
                {"error": "FORBIDDEN", "code": "FORBIDDEN"},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        return await call_next(request)