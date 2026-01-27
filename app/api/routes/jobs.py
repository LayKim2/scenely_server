"""API routes for job management"""

import logging
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Job, Result, JobStatus, SourceType
from app.api.schemas.jobs import (
    JobRequest,
    JobResponse,
    JobStatusResponse,
    JobResultResponse,
    DailyLessonItem,
    TranscriptWord
)
from app.workers.tasks import process_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new job for processing video/audio.
    
    Validates input and queues the job for processing.
    """
    # Validate source type and required fields
    if request.sourceType not in ["upload", "youtube"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sourceType must be 'upload' or 'youtube'"
        )
    
    if request.sourceType == "upload" and not request.uploadId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uploadId is required when sourceType is 'upload'"
        )
    
    if request.sourceType == "youtube" and not request.youtubeUrl:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="youtubeUrl is required when sourceType is 'youtube'"
        )
    
    # Create job
    job = Job(
        source_type=SourceType(request.sourceType),
        upload_id=request.uploadId,
        youtube_url=request.youtubeUrl,
        target_lang=request.targetLang,
        status=JobStatus.QUEUED,
        progress=0.0
    )
    
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue Celery task
    try:
        process_job.delay(job.id)
        logger.info(f"Queued job {job.id} for processing")
    except Exception as e:
        logger.error(f"Error queueing job {job.id}: {e}")
        job.status = JobStatus.FAILED
        job.error = f"Failed to queue job: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue job for processing"
        )
    
    return JobResponse(jobId=job.id)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the current status of a job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )
    
    return JobStatusResponse(
        status=job.status.value,
        progress=job.progress,
        message=job.error
    )


@router.get("/{job_id}/result", response_model=JobResultResponse)
def get_job_result(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the result of a completed job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}"
        )
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job.status.value}"
        )
    
    result = db.query(Result).filter(Result.job_id == job_id).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result not found for job: {job_id}"
        )
    
    # Parse JSON
    daily_lesson_data = json.loads(result.daily_lesson_json)
    daily_lesson = [DailyLessonItem(**item) for item in daily_lesson_data]
    
    transcript_words = None
    if result.transcript_words_json:
        transcript_words_data = json.loads(result.transcript_words_json)
        transcript_words = [TranscriptWord(**word) for word in transcript_words_data]
    
    return JobResultResponse(
        dailyLesson=daily_lesson,
        transcriptWords=transcript_words
    )
