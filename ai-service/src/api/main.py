"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path

import psutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ..config.settings import settings
from ..core.graph import create_report_graph
from ..core.qa_graph import create_qa_graph
from ..core.rate_limit import limiter
from ..services.cache_service import cache_service
from .routes import router
from ..middleware.internal_api_key import InternalApiKeyMiddleware


def _memory_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.supabase_db_url:
        raise RuntimeError("Configure SUPABASE_DB_URL before starting the AI service")

    connection_options = conninfo_to_dict(settings.supabase_db_url)
    root_cert = connection_options.get("sslrootcert", os.getenv("PGSSLROOTCERT"))
    ssl_mode = connection_options.get("sslmode", os.getenv("PGSSLMODE"))
    if (
        ssl_mode in {"verify-ca", "verify-full"}
        and root_cert and root_cert != "system" and not Path(root_cert).is_file()
    ):
        raise RuntimeError(
            "The Postgres sslrootcert file was not found. Set SUPABASE_DB_URL or "
            "PGSSLROOTCERT to point to the Supabase CA file on this host. "
            "On Render, upload the CA as a Secret File and use /etc/secrets/<filename>."
        )

    if os.name == "nt" and not isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
        raise RuntimeError("On Windows, start Uvicorn with --loop asyncio:SelectorEventLoop")

    async def configure(conn):
        await conn.execute("SET search_path TO finance_agent")

    async with AsyncConnectionPool(
        settings.supabase_db_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        configure=configure,
        min_size=1,
        max_size=5,
        timeout=8,
        open=False,
    ) as pool:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1 FROM finance_agent.api_cache LIMIT 0")

        cache_service.initialize(pool)
        app.state.report_graph = create_report_graph()
        app.state.qa_graph = create_qa_graph()
        try:
            yield
        finally:
            cache_service.shutdown()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Finance Agent AI Service", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(InternalApiKeyMiddleware)
# Dynamic CORS Configuration
allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
allowed_origin_regex = settings.cors_allowed_origin_regex or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def api_home() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Finance Agent API</title>
  <style>
    body { color-scheme: dark; background: #020617; color: #f8fafc; font: 1rem/1.6 system-ui; margin: 0; }
    main { max-width: 38rem; margin: 12vh auto; padding: 0 1.5rem; }
    a { color: #7dd3fc; }
  </style>
</head>
<body>
  <main>
    <h1>Finance Agent API</h1>
    <p>This port runs the backend. If you are running the app locally, use the frontend on port 3000.</p>
    <p><a href="http://localhost:3000">Open the Finance Agent website</a></p>
    <p><a href="/health">Check backend health</a></p>
  </main>
</body>
</html>"""
    )


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def api_favicon() -> Response:
    return Response(status_code=204)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> dict:
    return {"status": "ok", "memory_mb": round(_memory_mb(), 2)}


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):  # pragma: no cover - framework callback
    return JSONResponse({"error": "RATE_LIMITED", "code": "RATE_LIMITED"}, status_code=429)


