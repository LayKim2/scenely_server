"""Pydantic schemas for job-related API requests and responses"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class JobRequest(BaseModel):
    """Request schema for creating a new job."""

    mediaSourceId: str = Field(..., description="ID of media source to process")
    jobType: str = Field(default="DAILY_LESSON", description="Job type (e.g. DAILY_LESSON)")
    targetLang: str = Field(default="en-US", description="Target language code for STT")


class JobResponse(BaseModel):
    """Response schema for job creation."""

    jobId: str


class JobStatusResponse(BaseModel):
    """Response schema for job status."""

    status: str
    progress: float = Field(..., ge=0.0, le=1.0)
    message: Optional[str] = None


class JobSummary(BaseModel):
    """Summary of a job for listing."""

    id: str
    jobType: str
    status: str
    progress: float
    createdAt: datetime


class TranscriptWord(BaseModel):
    """Schema for a single transcript word with timing"""
    word: str
    startSeconds: float
    endSeconds: float


class TranscriptSegment(BaseModel):
    """Schema for a transcript segment (sentence)"""
    start: float
    end: float
    text: str


class DailyLessonItem(BaseModel):
    """Schema for a daily lesson item"""
    startSec: float
    endSec: float
    sentence: str
    reason: Optional[str] = None
    suggestedActivity: Optional[str] = None
    clipAudioUrl: Optional[str] = None
    items: List[dict] = Field(..., description="List of terms with meaningKo and exampleEn")


class JobResultResponse(BaseModel):
    """Response schema for job result"""
    analysis: Optional[Any] = None
    dailyLesson: List[DailyLessonItem]
    fullTranscript: Optional[str] = None
    transcriptSentences: Optional[List[TranscriptSegment]] = None
