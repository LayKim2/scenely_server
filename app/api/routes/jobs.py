"""API routes for job management."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import (
    AnalysisSegment,
    AnalysisSegmentVoca,
    Job,
    JobResult,
    JobStatus,
    JobType,
    MediaSource,
    User,
)
from app.api.schemas.jobs import (
    DailyLessonItem,
    JobRequest,
    JobResponse,
    JobResultResponse,
    JobStatusResponse,
    JobSummary,
)
from app.workers.tasks import process_job


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _ensure_job_owner(job: Job, current_user: User) -> None:
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )


def _build_job_result_response(job: Job, db: Session):
    """Build dailyLesson + transcriptWords response from job_result and analysis_segments."""
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job.status.value}",
        )

    job_result = db.query(JobResult).filter(JobResult.job_id == job.id).first()
    if not job_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job result not found for job",
        )

    segments: List[AnalysisSegment] = (
        db.query(AnalysisSegment)
        .filter(AnalysisSegment.job_id == job.id)
        .order_by(AnalysisSegment.idx.asc())
        .all()
    )
    if not segments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis segments not found for job",
        )

    daily_lesson_items = []
    for segment in segments:
        voca_list: List[AnalysisSegmentVoca] = (
            db.query(AnalysisSegmentVoca)
            .filter(AnalysisSegmentVoca.analysis_segment_id == segment.id)
            .order_by(AnalysisSegmentVoca.idx.asc())
            .all()
        )
        daily_lesson_items.append(
            DailyLessonItem(
                startSec=segment.start_sec,
                endSec=segment.end_sec,
                sentence=segment.sentence,
                reason=segment.reason,
                suggestedActivity=segment.suggested_activity,
                clipAudioUrl=segment.clip_audio_url,
                items=[
                    {
                        "term": v.term,
                        "meaningKo": v.meaning_ko,
                        "exampleEn": v.example_en,
                    }
                    for v in voca_list
                ],
            )
        )

    return JobResultResponse(
        dailyLesson=daily_lesson_items,
        transcriptWords=[],
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    request: JobRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new job for processing video/audio.
    """
    media_source = (
        db.query(MediaSource)
        .filter(
            MediaSource.id == request.mediaSourceId,
            MediaSource.user_id == current_user.id,
        )
        .first()
    )
    if not media_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media source not found",
        )

    try:
        job_type = JobType(request.jobType.lower())
    except ValueError:
        job_type = JobType.DAILY_LESSON

    job = Job(
        user_id=current_user.id,
        media_source_id=media_source.id,
        job_type=job_type,
        target_lang=request.targetLang,
        status=JobStatus.QUEUED,
        progress=0.0,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        process_job.delay(job.id)
        logger.info("Queued job %s for processing", job.id)
    except Exception as e:
        logger.error("Error queueing job %s: %s", job.id, e)
        job.status = JobStatus.FAILED
        job.error = f"Failed to queue job: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue job for processing",
        )

    return JobResponse(jobId=job.id)


@router.get("/me", response_model=List[JobSummary])
def list_my_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List jobs for the current user."""
    jobs = (
        db.query(Job)
        .filter(Job.user_id == current_user.id)
        .order_by(Job.created_at.desc())
        .all()
    )

    return [
        JobSummary(
            id=j.id,
            jobType=j.job_type.value if j.job_type else "",
            status=j.status.value if j.status else "",
            progress=j.progress,
            createdAt=j.created_at,
        )
        for j in jobs
    ]


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the current status of a job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    _ensure_job_owner(job, current_user)

    return JobStatusResponse(
        status=job.status.value,
        progress=job.progress,
        message=job.error,
    )


@router.get("/{job_id}/result")
def get_job_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the result of a completed job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    _ensure_job_owner(job, current_user)
    return _build_job_result_response(job, db)
