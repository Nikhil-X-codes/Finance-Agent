FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv

COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

RUN mkdir -p /data/model_cache /data/vector_store /data/cache && \
    python - <<'PY'
from sentence_transformers import SentenceTransformer
SentenceTransformer("BAAI/bge-small-en", device="cpu", cache_folder="/data/model_cache")
PY

COPY src ./src
COPY data ./data
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
