FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/
COPY workers/extraction/requirements*.txt workers/extraction/
RUN pip install --no-cache-dir -r backend/requirements.txt \
    -r workers/extraction/requirements-paddle.txt

COPY backend backend
COPY workers/__init__.py workers/
COPY workers/extraction workers/extraction

CMD ["celery", "-A", "config", "worker", "-Q", "extraction", "-I", "workers.extraction.tasks", "--loglevel=info"]
