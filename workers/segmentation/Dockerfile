FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend

WORKDIR /app

COPY backend/requirements.txt backend/
COPY workers/segmentation/requirements*.txt workers/segmentation/
RUN pip install --no-cache-dir -r backend/requirements.txt \
    -r workers/segmentation/requirements.txt

COPY backend backend
COPY workers/__init__.py workers/
COPY workers/segmentation workers/segmentation

CMD ["celery", "-A", "config", "worker", "-Q", "segmentation", "-I", "workers.segmentation.tasks", "--loglevel=info"]
