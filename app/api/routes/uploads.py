"""API routes for file uploads"""

import logging
import uuid
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.gcs_service import GCSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])


class PresignResponse(BaseModel):
    """Response schema for presigned URL generation"""
    uploadId: str
    uploadUrl: str


@router.post("/presign", response_model=PresignResponse)
def create_presigned_upload():
    """
    Generate a presigned URL for uploading a video file.
    
    Returns an uploadId and a presigned URL that can be used to upload
    the file directly to GCS.
    """
    try:
        upload_id = str(uuid.uuid4())
        gcs_service = GCSService()
        upload_url = gcs_service.generate_presigned_url(upload_id)
        
        logger.info(f"Generated presigned URL for upload: {upload_id}")
        
        return PresignResponse(
            uploadId=upload_id,
            uploadUrl=upload_url
        )
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate presigned URL"
        )
