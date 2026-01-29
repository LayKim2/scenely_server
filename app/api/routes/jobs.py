"""API routes for job management."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import (
    DailyLesson,
    DailyLessonItemModel,
    Job,
    JobResult,
    JobStatus,
    JobType,
    MediaSource,
    Transcript,
    TranscriptWordModel,
    User,
)
from app.api.schemas.jobs import (
    JobRequest,
    JobResponse,
    JobStatusResponse,
    JobSummary,
)
from app.api.schemas.results import (
    DailyLessonItem,
    TranscriptWord,
    TranscriptSegment,
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
    """Build dailyLesson + transcriptWords response from normalized tables."""
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job.status.value}",
        )

    transcript = db.query(Transcript).filter(Transcript.job_id == job.id).first()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found for job",
        )

    words_models: List[TranscriptWordModel] = (
        db.query(TranscriptWordModel)
        .filter(TranscriptWordModel.transcript_id == transcript.id)
        .order_by(TranscriptWordModel.idx.asc())
        .all()
    )
    transcript_words = [
        TranscriptWord(
            word=w.word,
            startSeconds=w.start_sec,
            endSeconds=w.end_sec,
        )
        for w in words_models
    ]

    lessons: List[DailyLesson] = (
        db.query(DailyLesson)
        .filter(DailyLesson.job_id == job.id)
        .order_by(DailyLesson.idx.asc())
        .all()
    )
    if not lessons:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily lesson not found for job",
        )

    daily_lesson_items = []
    for lesson in lessons:
        items: List[DailyLessonItemModel] = (
            db.query(DailyLessonItemModel)
            .filter(DailyLessonItemModel.daily_lesson_id == lesson.id)
            .order_by(DailyLessonItemModel.idx.asc())
            .all()
        )
        daily_lesson_items.append(
            DailyLessonItem(
                startSec=lesson.start_sec,
                endSec=lesson.end_sec,
                sentence=lesson.sentence,
                items=[
                    {
                        "term": i.term,
                        "meaningKo": i.meaning_ko,
                        "exampleEn": i.example_en,
                    }
                    for i in items
                ],
            )
        )

    # Reuse JobResultResponse schema via results module to avoid circular import.
    from app.api.schemas.jobs import JobResultResponse  # local import to break cycle

    return JobResultResponse(
        dailyLesson=daily_lesson_items,
        transcriptWords=transcript_words,
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
