"""Runtime settings for the AI service."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

from .constants import (
    DEFAULT_CACHE_TTL_SECONDS,
    GROQ_CIRCUIT_RESET_SECONDS,
    GROQ_FAILURE_THRESHOLD,
    MAX_PDF_SIZE_BYTES,
    MF_METADATA_CACHE_TTL_SECONDS,
    QA_RATE_LIMIT_PER_MINUTE,
    REPORT_RATE_LIMIT_PER_MINUTE,
    STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS,
    STOCK_NEWS_CACHE_TTL_SECONDS,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or value == "" else int(value)


@dataclass(frozen=True, slots=True)
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    internal_api_key: str = os.getenv("INTERNAL_API_KEY", "")
    newsapi_key: str = os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY", "")
    supabase_db_url: str = os.getenv("SUPABASE_DB_URL", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    report_rate_limit_per_minute: int = _int_env(
        "REPORT_RATE_LIMIT_PER_MINUTE", REPORT_RATE_LIMIT_PER_MINUTE
    )
    qa_rate_limit_per_minute: int = _int_env("QA_RATE_LIMIT_PER_MINUTE", QA_RATE_LIMIT_PER_MINUTE)
    default_cache_ttl_seconds: int = _int_env("DEFAULT_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS)
    stock_fundamentals_cache_ttl_seconds: int = _int_env(
        "STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS", STOCK_FUNDAMENTALS_CACHE_TTL_SECONDS
    )
    stock_news_cache_ttl_seconds: int = _int_env("STOCK_NEWS_CACHE_TTL_SECONDS", STOCK_NEWS_CACHE_TTL_SECONDS)
    mf_metadata_cache_ttl_seconds: int = _int_env(
        "MF_METADATA_CACHE_TTL_SECONDS", MF_METADATA_CACHE_TTL_SECONDS
    )
    mfapi_base_url: str = os.getenv("MFAPI_BASE_URL", "https://api.mfapi.in")
    groq_failure_threshold: int = _int_env("GROQ_FAILURE_THRESHOLD", GROQ_FAILURE_THRESHOLD)
    groq_circuit_reset_seconds: int = _int_env("GROQ_CIRCUIT_RESET_SECONDS", GROQ_CIRCUIT_RESET_SECONDS)
    max_pdf_size_bytes: int = _int_env("MAX_PDF_SIZE_BYTES", MAX_PDF_SIZE_BYTES)
    nse_market_data: bool = os.getenv("NSE_MARKET_DATA", "").lower() == "true"
    nse_quote_max_age_seconds: int = _int_env("NSE_QUOTE_MAX_AGE_SECONDS", 360)
    nse_mcp_timeout_seconds: int = _int_env("NSE_MCP_TIMEOUT_SECONDS", 15)
    cors_allowed_origins: str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001")
    cors_allowed_origin_regex: str = os.getenv("CORS_ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app|https://.*\.onrender\.com")


settings = Settings()
