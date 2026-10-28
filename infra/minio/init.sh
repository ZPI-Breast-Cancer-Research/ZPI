#!/bin/sh
set -e

# Przekazujemy dane logowania z MinIO do zmiennych akceptowanych przez AWS CLI
export AWS_ACCESS_KEY_ID="$MINIO_ROOT_USER"
export AWS_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD"
export AWS_DEFAULT_REGION="us-east-1"

# Czekamy chwilę na pełne wstanie serwera MinIO
echo "Oczekiwanie na uruchomienie serwera MinIO..."
sleep 3

# Adres URL do Twojego kontenera z MinIO
MINIO_URL="http://minio:9000"

# Lista bucketów do utworzenia
for bucket in studies masks reports models mlflow; do
    echo "Tworzenie bucketu: $bucket..."
    
    # Tworzymy bucket. Jeśli już istnieje, AWS CLI zwróci błąd, 
    # dlatego przekierowujemy błędy i sprawdzamy status, zastępując flagę --ignore-existing
    aws --endpoint-url "$MINIO_URL" s3api create-bucket --bucket "$bucket" 2>/dev/null || \
    echo "Bucket '$bucket' już istnieje lub został pominięty."
done

echo "Inicjalizacja MinIO zakończona pomyślnie!"
