"""Service for Google Cloud Storage operations"""

import logging
from pathlib import Path
from typing import Optional
from google.cloud import storage
from google.cloud.storage import Blob
from datetime import timedelta

from app.config import settings

logger = logging.getLogger(__name__)


class GCSService:
    """Service for GCS operations"""
    
    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = settings.GCS_BUCKET_TMP_AUDIO
    
    def upload_audio_file(self, local_path: str, job_id: str) -> str:
        """
        Upload audio file to GCS temporary storage.
        
        Args:
            local_path: Local path to the audio file
            job_id: Job ID for naming the file
            
        Returns:
            GCS URI (gs://bucket/path)
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob_path = f"tmp-audio/{job_id}.flac"
            blob = bucket.blob(blob_path)
            
            blob.upload_from_filename(local_path)
            logger.info(f"Uploaded audio to GCS: {blob_path}")
            
            return f"gs://{self.bucket_name}/{blob_path}"
        except Exception as e:
            logger.error(f"Error uploading to GCS: {e}")
            raise
    
    def delete_audio_file(self, job_id: str) -> None:
        """
        Delete audio file from GCS.
        
        Args:
            job_id: Job ID to delete the file for
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob_path = f"tmp-audio/{job_id}.flac"
            blob = bucket.blob(blob_path)
            
            if blob.exists():
                blob.delete()
                logger.info(f"Deleted audio from GCS: {blob_path}")
        except Exception as e:
            logger.warning(f"Error deleting from GCS: {e}")
    
    def generate_presigned_url(self, upload_id: str, expiration_minutes: int = 60) -> str:
        """
        Generate presigned URL for file upload.
        
        Args:
            upload_id: Unique upload ID
            expiration_minutes: URL expiration time in minutes
            
        Returns:
            Presigned URL for upload
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob_path = f"uploads/{upload_id}"
            blob = bucket.blob(blob_path)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="PUT",
                content_type="video/*"
            )
            
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise
    
    def download_file(self, gcs_uri: str, local_path: str) -> None:
        """
        Download file from GCS to local path.
        
        Args:
            gcs_uri: GCS URI (gs://bucket/path)
            local_path: Local path to save the file
        """
        try:
            # Parse GCS URI
            if not gcs_uri.startswith("gs://"):
                raise ValueError(f"Invalid GCS URI: {gcs_uri}")
            
            parts = gcs_uri[5:].split("/", 1)
            bucket_name = parts[0]
            blob_path = parts[1] if len(parts) > 1 else ""
            
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            
            blob.download_to_filename(local_path)
            logger.info(f"Downloaded file from GCS: {gcs_uri} -> {local_path}")
        except Exception as e:
            logger.error(f"Error downloading from GCS: {e}")
            raise
