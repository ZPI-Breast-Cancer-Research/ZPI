FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend

WORKDIR /app

COPY backend/requirements.txt backend/
COPY workers/training/requirements*.txt workers/training/
COPY workers/segmentation/requirements.txt workers/segmentation/
RUN pip install --no-cache-dir -r backend/requirements.txt \
    -r workers/training/requirements.txt

COPY backend backend
COPY workers/__init__.py workers/
COPY workers/training workers/training

CMD ["celery", "-A", "config", "worker", "-Q", "training", "-I", "workers.training.tasks", "--concurrency=1", "--loglevel=info"]
