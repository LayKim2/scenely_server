"""Lesson/result routes built on normalized tables."""

import logging
import json
from typing import List, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import (
    DailyLesson,
    DailyLessonItemModel,
    Job,
    JobStatus,
    Transcript,
    TranscriptWordModel,
    User,
)
from app.api.schemas.results import DailyLessonItem, TranscriptWord
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

    transcript = db.query(Transcript).filter(Transcript.job_id == job.id).first()
    # Transcript might be empty if we only processed segments or had an error, 
    # but for completed job we expect at least the segments.
    
    transcript_words = []
    if transcript:
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
                reason=lesson.reason,
                suggestedActivity=lesson.suggested_activity,
                clipAudioUrl=lesson.clip_audio_url,
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

    # Get analysis from JobResult
    job_result = db.query(JobResult).filter(JobResult.job_id == job.id).first()
    analysis = None
    if job_result and job_result.analysis:
        try:
            analysis = json.loads(job_result.analysis)
        except:
            analysis = job_result.analysis

    return JobResultResponse(
        analysis=analysis,
        dailyLesson=daily_lesson_items,
        transcriptWords=transcript_words,
    )

