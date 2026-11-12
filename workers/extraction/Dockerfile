FROM python:3.12-slim

# PADDLE_PDX_CACHE_HOME: PaddleOCR models (~200 MB, downloaded on first OCR) go to a directory
# that compose mounts as a volume, so they survive container re-creation.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend \
    PADDLE_PDX_CACHE_HOME=/models/paddlex

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/
COPY workers/extraction/requirements*.txt workers/extraction/
RUN pip install --no-cache-dir -r backend/requirements.txt \
    -r workers/extraction/requirements-paddle.txt

# Unprivileged user; the model directory is created here so a new named volume inherits its owner.
RUN useradd --create-home --uid 1000 worker \
    && mkdir -p "$PADDLE_PDX_CACHE_HOME" && chown worker "$PADDLE_PDX_CACHE_HOME"

COPY backend backend
COPY workers/__init__.py workers/
COPY workers/extraction workers/extraction

USER worker

# One process: each process loads its own copy of the OCR models, and the single LLM server is
# the bottleneck anyway.
CMD ["celery", "-A", "config", "worker", "-Q", "extraction", "-I", "workers.extraction.tasks", \
     "--concurrency=1", "--loglevel=info"]
