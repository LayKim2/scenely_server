"""Media routes for presigned uploads and media source creation."""

import logging
import uuid
from typing import Literal, Optional

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

SOURCE_TYPE_FILE = "FILE"
SOURCE_TYPE_YOUTUBE = "YOUTUBE"


class CreateMediaSourceRequest(BaseModel):
    """Request body: sourceType + youtubeUrl (required when sourceType=YOUTUBE)."""

    sourceType: Literal["FILE", "YOUTUBE"] = Field(
        default=SOURCE_TYPE_FILE,
        description="FILE: presign upload. YOUTUBE: provide youtubeUrl.",
    )
    youtubeUrl: Optional[str] = Field(default=None, description="Required when sourceType=YOUTUBE.")


class PresignResponse(BaseModel):
    """Response: mediaSourceId always; uploadUrl only when sourceType=FILE."""

    mediaSourceId: str
    uploadUrl: Optional[str] = None


@router.post("/presign", response_model=PresignResponse)
def create_presigned_upload(
    body: CreateMediaSourceRequest = CreateMediaSourceRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a MediaSource. FILE: generate presigned URL and storage_path. YOUTUBE: store youtubeUrl (no uploadUrl).
    """
    try:
        if body.sourceType == SOURCE_TYPE_YOUTUBE:
            if not body.youtubeUrl or not body.youtubeUrl.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"youtubeUrl is required when sourceType is {SOURCE_TYPE_YOUTUBE}",
                )
            media_source = MediaSource(
                user_id=current_user.id,
                source_type=MediaSourceKind.YOUTUBE,
                youtube_url=body.youtubeUrl.strip(),
            )
            db.add(media_source)
            db.commit()
            db.refresh(media_source)
            logger.info("Created YouTube media_source %s", media_source.id)
            return PresignResponse(mediaSourceId=media_source.id, uploadUrl=None)

        # FILE: presign + storage_path
        upload_id = str(uuid.uuid4())
        s3_service = S3Service()
        upload_url = s3_service.generate_presigned_url(upload_id)
        storage_path = f"s3://{settings.S3_BUCKET}/uploads/{upload_id}"
        media_source = MediaSource(
            user_id=current_user.id,
            source_type=MediaSourceKind.FILE,
            storage_path=storage_path,
        )
        db.add(media_source)
        db.commit()
        db.refresh(media_source)
        logger.info("Generated presigned URL for media_source %s", media_source.id)
        return PresignResponse(mediaSourceId=media_source.id, uploadUrl=upload_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating media source: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create media source",
        )
