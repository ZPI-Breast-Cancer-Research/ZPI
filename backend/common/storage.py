import os
from functools import cache
from pathlib import Path

import boto3

BUCKET_STUDIES = "studies"
BUCKET_MASKS = "masks"
BUCKET_REPORTS = "reports"
BUCKET_MODELS = "models"


@cache
def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )


def upload_file(path: Path, bucket: str, key: str) -> None:
    s3_client().upload_file(str(path), bucket, key)


def download_file(bucket: str, key: str, path: Path) -> Path:
    s3_client().download_file(bucket, key, str(path))
    return path


def put_bytes(data: bytes, bucket: str, key: str, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    s3_client().put_object(Bucket=bucket, Key=key, Body=data, **extra)
