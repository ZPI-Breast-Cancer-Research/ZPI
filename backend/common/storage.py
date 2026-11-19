import os
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import boto3
from boto3.exceptions import Boto3Error
from botocore.exceptions import BotoCoreError, ClientError

from .errors import ObjectNotFound, StorageError

BUCKET_STUDIES = "studies"
BUCKET_MASKS = "masks"
BUCKET_REPORTS = "reports"
BUCKET_MODELS = "models"

SETTINGS = ("S3_ENDPOINT_URL", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
# error codes S3 uses for a key (or a bucket) that does not exist
MISSING = {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


@cache
def s3_client():
    missing = [name for name in SETTINGS if not os.environ.get(name)]
    if missing:
        raise StorageError(f"storage is not configured: {', '.join(missing)} not set")
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )


@contextmanager
def _storage_errors(action: str):
    """Whatever boto raises becomes a StorageError that says what was being done."""
    try:
        yield
    except ClientError as exc:  # the server answered with an error
        if exc.response.get("Error", {}).get("Code") in MISSING:
            raise ObjectNotFound(f"{action}: no such object") from exc
        raise StorageError(f"{action} failed: {exc}") from exc
    except (BotoCoreError, Boto3Error) as exc:  # no connection, timeout, failed transfer
        raise StorageError(f"{action} failed: {exc}") from exc


def upload_file(path: Path, bucket: str, key: str) -> None:
    with _storage_errors(f"upload of {path} to {bucket}/{key}"):
        s3_client().upload_file(str(path), bucket, key)


def download_file(bucket: str, key: str, path: Path) -> Path:
    with _storage_errors(f"download of {bucket}/{key}"):
        s3_client().download_file(bucket, key, str(path))
    return path


def get_bytes(bucket: str, key: str) -> bytes:
    with _storage_errors(f"read of {bucket}/{key}"):
        return s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()


def put_bytes(data: bytes, bucket: str, key: str, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    with _storage_errors(f"write of {bucket}/{key}"):
        s3_client().put_object(Bucket=bucket, Key=key, Body=data, **extra)


def delete_object(bucket: str, key: str) -> None:
    """Delete one object; S3 does not complain about a key that is already gone."""
    with _storage_errors(f"delete of {bucket}/{key}"):
        s3_client().delete_object(Bucket=bucket, Key=key)


def delete_prefix(bucket: str, prefix: str) -> int:
    """Delete every object whose key starts with the prefix; returns how many there were."""
    deleted = 0
    with _storage_errors(f"delete of {bucket}/{prefix}*"):
        pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for page in pages:
            keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if keys:
                s3_client().delete_objects(Bucket=bucket, Delete={"Objects": keys})
                deleted += len(keys)
    return deleted


def is_avaible() -> bool:
    try:
        with _storage_errors("listing the buckets"):
            s3_client().list_buckets()
        return True
    except StorageError:
        return False
