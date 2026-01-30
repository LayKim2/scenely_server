"""Service for AWS S3 operations (replaces GCS)."""

import logging
from datetime import timedelta
from typing import Optional

import boto3
from botocore.config import Config

from app.config import settings

logger = logging.getLogger(__name__)


class S3Service:
    """Service for S3 operations (upload presign, upload/download/delete)."""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
        self.bucket_name = settings.S3_BUCKET

    def upload_audio_file(self, local_path: str, job_id: str) -> str:
        """
        Upload audio file to S3 (tmp-audio prefix for worker/Transcribe).
        Returns S3 URI (s3://bucket/key).
        """
        try:
            key = f"tmp-audio/{job_id}.flac"
            self.client.upload_file(local_path, self.bucket_name, key)
            logger.info("Uploaded audio to S3: %s", key)
            return f"s3://{self.bucket_name}/{key}"
        except Exception as e:
            logger.error("Error uploading to S3: %s", e)
            raise

    def delete_audio_file(self, job_id: str) -> None:
        """Delete tmp-audio object for a job from S3."""
        try:
            key = f"tmp-audio/{job_id}.flac"
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info("Deleted audio from S3: %s", key)
        except Exception as e:
            logger.warning("Error deleting from S3: %s", e)

    def generate_presigned_url(
        self, upload_id: str, expiration_minutes: int = 60, content_type: str = "video/*"
    ) -> str:
        """Generate presigned URL for PUT upload (client uploads file directly to S3)."""
        try:
            key = f"uploads/{upload_id}"
            url = self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expiration_minutes * 60,
            )
            return url
        except Exception as e:
            logger.error("Error generating presigned URL: %s", e)
            raise

    def download_file(self, s3_uri: str, local_path: str) -> None:
        """
        Download file from S3 to local path.
        s3_uri: s3://bucket/key
        """
        try:
            if not s3_uri.startswith("s3://"):
                raise ValueError(f"Invalid S3 URI: {s3_uri}")
            parts = s3_uri[5:].split("/", 1)  # strip "s3://"
            bucket_name = parts[0]
            key = parts[1] if len(parts) > 1 else ""
            self.client.download_file(bucket_name, key, local_path)
            logger.info("Downloaded file from S3: %s -> %s", s3_uri, local_path)
        except Exception as e:
            logger.error("Error downloading from S3: %s", e)
            raise

    def get_public_url(self, key: str) -> Optional[str]:
        """Return CloudFront URL for key if CLOUDFRONT_DOMAIN is set, else None."""
        if not settings.CLOUDFRONT_DOMAIN:
            return None
        domain = settings.CLOUDFRONT_DOMAIN.rstrip("/")
        return f"https://{domain}/{key}"
