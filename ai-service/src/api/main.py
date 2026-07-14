"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import os

import psutil
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from ..config.settings import settings
from ..core.rate_limit import limiter
from ..services.cache_service import cache_service
from .routes import router
from ..middleware.internal_api_key import InternalApiKeyMiddleware


def _memory_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.memory_mb = _memory_mb

    print("=" * 60)
    print("STARTUP: Loading all models eagerly...")
    print("=" * 60)

    # 1. Initialize Cache
    try:
        cache_service.initialize(settings.sqlite_path)
        print("Cache initialized")
    except Exception as e:
        print(f"Cache init failed: {e}")

    # 2. Eager load LLMService
    print("\n[1/2] Loading Groq LLM...")
    try:
        from ..services.llm_service import LLMService
        llm = LLMService.get_instance()
        print(f"LLMService initialized with model: {llm.model}")
    except Exception as e:
        print(f"LLMService failed: {e}")
        print("Server starting without initialized LLMService.")

    # 3. Eager load EmbeddingService (SentenceTransformer)
    print("\n[2/2] Loading SentenceTransformer Embeddings...")
    try:
        from ..services.embedding_service import get_embedding_service
        get_embedding_service(
            model_name=settings.embedding_model_name,
            cache_folder=settings.embedding_cache_folder
        )
        print("SentenceTransformer Embeddings loaded successfully!")
    except Exception as e:
        print(f"EmbeddingService failed to load: {e}")
        print("Server starting without pre-loaded EmbeddingService.")



    print("\n" + "=" * 60)
    print("ALL MODELS LOADED — Server ready for requests")
    print("=" * 60)

    yield


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Finance Agent AI Service", lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(InternalApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "memory_mb": round(_memory_mb(), 2)}


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):  # pragma: no cover - framework callback
    return JSONResponse({"error": "RATE_LIMITED", "code": "RATE_LIMITED"}, status_code=429)


