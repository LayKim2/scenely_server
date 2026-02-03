"""Media routes: presigned upload for YouTube audio (client uploads extracted audio to S3)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import MediaSource, MediaSourceKind, User
from app.services.s3_service import S3Service
from app.config import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


class PresignRequest(BaseModel):
    """Request: youtubeUrl only (YouTube case only)."""

    youtubeUrl: str = Field(..., description="YouTube URL. Client will upload extracted audio to uploadUrl.")


class PresignResponse(BaseModel):
    """Response: mediaSourceId + presigned uploadUrl for S3."""

    mediaSourceId: str
    uploadUrl: str


@router.post("/presign", response_model=PresignResponse)
def create_presigned_upload(
    body: PresignRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a MediaSource for a YouTube URL and return a presigned URL.
    Client must upload the extracted audio file to uploadUrl (PUT), then create a job with mediaSourceId.
    """
    try:
        url = (body.youtubeUrl or "").strip()
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="youtubeUrl is required",
            )

        upload_id = str(uuid.uuid4())
        s3_service = S3Service()
        upload_url = s3_service.generate_presigned_url(upload_id)
        storage_path = f"s3://{settings.S3_BUCKET}/uploads/{upload_id}"

        media_source = MediaSource(
            user_id=current_user.id,
            source_type=MediaSourceKind.YOUTUBE,
            youtube_url=url,
            storage_path=storage_path,
        )
        db.add(media_source)
        db.commit()
        db.refresh(media_source)
        logger.info("Created YouTube media_source %s with presign", media_source.id)
        return PresignResponse(mediaSourceId=media_source.id, uploadUrl=upload_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating media source: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create media source",
        )
