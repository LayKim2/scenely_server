"""Lesson/result routes built on normalized tables."""

import logging
from typing import List, Any, Optional

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
    User,
)
from app.api.schemas.results import DailyLessonItem
from app.api.schemas.jobs import JobResultResponse


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lessons", tags=["lessons"])


def _ensure_job_owner(job: Job, current_user: User) -> None:
    if not job or job.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )


@router.get("/{job_id}", response_model=JobResultResponse)
def get_lesson_for_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return dailyLesson + transcriptWords for a completed job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    _ensure_job_owner(job, current_user)

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed. Current status: {job.status.value}",
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

    # Build analysis from JobResult columns
    job_result = db.query(JobResult).filter(JobResult.job_id == job.id).first()
    analysis = None
    if job_result and (job_result.summary or job_result.difficulty or job_result.situation):
        analysis = {
            "summary": job_result.summary,
            "difficulty": job_result.difficulty,
            "situation": job_result.situation,
        }

    return JobResultResponse(
        analysis=analysis,
        dailyLesson=daily_lesson_items,
        transcriptWords=[],
    )

