"""Authenticate server-to-server calls and suppress private request tracing."""

from hmac import compare_digest

from fastapi import Request, status
from fastapi.responses import JSONResponse
from langsmith import tracing_context
from starlette.middleware.base import BaseHTTPMiddleware

from ..config.constants import INTERNAL_API_HEADER
from ..config.settings import settings


class InternalApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD"} and request.url.path in {"/", "/health", "/favicon.ico"}:
            return await call_next(request)

        if not settings.internal_api_key:
            return JSONResponse(
                {"error": "AI_UNAVAILABLE", "code": "AI_UNAVAILABLE"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided_key = request.headers.get(INTERNAL_API_HEADER, "")
        if not compare_digest(provided_key.encode(), settings.internal_api_key.encode()):
            return JSONResponse(
                {"error": "FORBIDDEN", "code": "FORBIDDEN"},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # The downstream request task (including SSE generation) inherits this context.
        with tracing_context(enabled=False):
            return await call_next(request)
