"""Media routes for presigned uploads and YouTube sources."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import MediaSource, MediaSourceKind, User
from app.services.s3_service import S3Service
from app.config import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


class PresignRequest(BaseModel):
    """Optional metadata for presign."""

    fileName: Optional[str] = None
    fileSize: Optional[int] = None
    mimeType: Optional[str] = None


class PresignResponse(BaseModel):
    """Response schema for presigned URL generation."""

    mediaSourceId: str
    uploadUrl: str


class YoutubeCreateRequest(BaseModel):
    """Create a media source from YouTube URL."""

    youtubeUrl: str


class YoutubeCreateResponse(BaseModel):
    """Response for YouTube media source creation."""

    mediaSourceId: str


@router.post("/presign", response_model=PresignResponse)
def create_presigned_upload(
    payload: PresignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a presigned URL for uploading a video file and create a MediaSource.
    """
    try:
        upload_id = str(uuid.uuid4())
        s3_service = S3Service()
        upload_url = s3_service.generate_presigned_url(upload_id)

        storage_path = f"s3://{settings.S3_BUCKET}/uploads/{upload_id}"

        media_source = MediaSource(
            user_id=current_user.id,
            source_kind=MediaSourceKind.FILE,
            storage_path=storage_path,
            original_name=payload.fileName,
            size_bytes=payload.fileSize,
            mime_type=payload.mimeType,
        )
        db.add(media_source)
        db.commit()
        db.refresh(media_source)

        logger.info("Generated presigned URL for media_source %s", media_source.id)

        return PresignResponse(
            mediaSourceId=media_source.id,
            uploadUrl=upload_url,
        )
    except Exception as e:
        logger.error("Error generating media presigned URL: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate presigned URL",
        )


@router.post("/youtube", response_model=YoutubeCreateResponse)
def create_youtube_source(
    payload: YoutubeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a MediaSource that points to a YouTube URL.
    """
    if not payload.youtubeUrl:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="youtubeUrl is required",
        )

    media_source = MediaSource(
        user_id=current_user.id,
        source_kind=MediaSourceKind.YOUTUBE,
        youtube_url=payload.youtubeUrl,
    )
    db.add(media_source)
    db.commit()
    db.refresh(media_source)

    logger.info("Created YouTube media_source %s", media_source.id)

    return YoutubeCreateResponse(mediaSourceId=media_source.id)

