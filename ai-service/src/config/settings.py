"""Runtime settings for the AI service.

Documented environment variables:
- GROQ_API_KEY: Groq API key for LLM access.
- INTERNAL_API_KEY: Shared secret used by Next.js when proxying requests.
- NEWSAPI_KEY: Optional NewsAPI key for primary news fetches.
- SQLITE_PATH: Path to the AI service SQLite database.
- FAISS_INDEX_PATH: Path to the FAISS index file.
- FAISS_METADATA_PATH: Optional JSON metadata file for FAISS chunks.
- EMBEDDING_MODEL_NAME: Sentence transformer model name.
- EMBEDDING_CACHE_FOLDER: Cache directory for the embedding model.
- GROQ_MODEL: Groq chat model used by the LLM service.
- MAX_MEMORY_MB: Memory ceiling used for startup health checks.
- REPORT_RATE_LIMIT_PER_MINUTE: Report generation limit per user.
- QA_RATE_LIMIT_PER_MINUTE: Q&A limit per user.
- STOCK_QUOTE_CACHE_TTL_SECONDS: Cache TTL for live stock quotes.
- STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS: Cache TTL for fundamentals.
- STOCK_NEWS_CACHE_TTL_SECONDS: Cache TTL for stock news.
- MF_NAV_CACHE_TTL_SECONDS: Cache TTL for mutual fund NAV data.
- MF_METADATA_CACHE_TTL_SECONDS: Cache TTL for mutual fund metadata.
- MF_HOLDINGS_CACHE_TTL_SECONDS: Cache TTL for mutual fund holdings.
- MACRO_CACHE_TTL_SECONDS: Cache TTL for macro data.
- GROQ_FAILURE_THRESHOLD: Failures before circuit breaker opens.
- GROQ_CIRCUIT_RESET_SECONDS: Circuit breaker reset window.
- TEMP_FILE_TTL_SECONDS: Cleanup timeout for uploaded PDFs.
- MAX_PDF_SIZE_BYTES: Maximum accepted PDF size.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

# Load local .env file
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)

from .constants import (
    DEFAULT_CACHE_TTL_SECONDS,
    GROQ_CIRCUIT_RESET_SECONDS,
    GROQ_FAILURE_THRESHOLD,
    MACRO_CACHE_TTL_SECONDS,
    MAX_MEMORY_MB,
    MAX_PDF_SIZE_BYTES,
    MF_METADATA_CACHE_TTL_SECONDS,
    MF_HOLDINGS_CACHE_TTL_SECONDS,
    MF_NAV_CACHE_TTL_SECONDS,
    QA_RATE_LIMIT_PER_MINUTE,
    REPORT_RATE_LIMIT_PER_MINUTE,
    STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS,
    STOCK_NEWS_CACHE_TTL_SECONDS,
    STOCK_QUOTE_CACHE_TTL_SECONDS,
    TEMP_FILE_TTL_SECONDS,
)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or value == "" else int(value)


@dataclass(frozen=True, slots=True)
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    internal_api_key: str = os.getenv("INTERNAL_API_KEY", "")
    newsapi_key: str = os.getenv("NEWSAPI_KEY", "")
    sqlite_path: str = os.getenv("SQLITE_PATH", "./data/cache/portfolio.db")
    faiss_index_path: str = os.getenv("FAISS_INDEX_PATH", "./data/vector_store/faiss.index")
    faiss_metadata_path: str = os.getenv("FAISS_METADATA_PATH", "./data/vector_store/meta.json")
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en")
    embedding_cache_folder: str = os.getenv("EMBEDDING_CACHE_FOLDER", "./data/model_cache")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    max_memory_mb: int = _int_env("MAX_MEMORY_MB", MAX_MEMORY_MB)
    report_rate_limit_per_minute: int = _int_env(
        "REPORT_RATE_LIMIT_PER_MINUTE", REPORT_RATE_LIMIT_PER_MINUTE
    )
    qa_rate_limit_per_minute: int = _int_env("QA_RATE_LIMIT_PER_MINUTE", QA_RATE_LIMIT_PER_MINUTE)
    default_cache_ttl_seconds: int = _int_env("DEFAULT_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS)
    stock_quote_cache_ttl_seconds: int = _int_env(
        "STOCK_QUOTE_CACHE_TTL_SECONDS", STOCK_QUOTE_CACHE_TTL_SECONDS
    )
    stock_fundamentals_cache_ttl_seconds: int = _int_env(
        "STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS", STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS
    )
    stock_news_cache_ttl_seconds: int = _int_env("STOCK_NEWS_CACHE_TTL_SECONDS", STOCK_NEWS_CACHE_TTL_SECONDS)
    mf_nav_cache_ttl_seconds: int = _int_env("MF_NAV_CACHE_TTL_SECONDS", MF_NAV_CACHE_TTL_SECONDS)
    mf_metadata_cache_ttl_seconds: int = _int_env(
        "MF_METADATA_CACHE_TTL_SECONDS", MF_METADATA_CACHE_TTL_SECONDS
    )
    mf_holdings_cache_ttl_seconds: int = _int_env(
        "MF_HOLDINGS_CACHE_TTL_SECONDS", MF_HOLDINGS_CACHE_TTL_SECONDS
    )
    macro_cache_ttl_seconds: int = _int_env("MACRO_CACHE_TTL_SECONDS", MACRO_CACHE_TTL_SECONDS)
    finapi_base_url: str = os.getenv("FINAPI_BASE_URL", "https://api.mfapi.in")
    groq_failure_threshold: int = _int_env("GROQ_FAILURE_THRESHOLD", GROQ_FAILURE_THRESHOLD)
    groq_circuit_reset_seconds: int = _int_env("GROQ_CIRCUIT_RESET_SECONDS", GROQ_CIRCUIT_RESET_SECONDS)
    temp_file_ttl_seconds: int = _int_env("TEMP_FILE_TTL_SECONDS", TEMP_FILE_TTL_SECONDS)
    max_pdf_size_bytes: int = _int_env("MAX_PDF_SIZE_BYTES", MAX_PDF_SIZE_BYTES)
    langsmith_tracing: str = os.getenv("LANGSMITH_TRACING", "false")
    langsmith_api_key: str = os.getenv("LANGSMITH_API_KEY", "")
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "Agent")
    langsmith_endpoint: str = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")


settings = Settings()
