#!/bin/sh
set -e

# Configuration for Minio
aws configure set aws_access_key_id "$MINIO_ROOT_USER"
aws configure set aws_secret_access_key "$MINIO_ROOT_PASSWORD"
aws configure set default.region us-east-1

# Checking if model exists if not then dowloading
if [ ! -f "/models/$LLM_MODEL_FILE" ]; then
    echo "Downloading model $LLM_MODEL_FILE from MinIO..."
    aws --endpoint-url=http://minio:9000 s3 cp "s3://models/$LLM_MODEL_FILE" "/models/$LLM_MODEL_FILE"
    echo "Model downloaded successfully."
else
    echo "Model already exists, skipping download."
fi