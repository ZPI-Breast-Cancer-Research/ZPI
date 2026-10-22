#!/bin/sh
set -e

mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
if [ ! -f "/models/$LLM_MODEL_FILE" ]; then
    mc cp "local/models/$LLM_MODEL_FILE" "/models/$LLM_MODEL_FILE"
fi
