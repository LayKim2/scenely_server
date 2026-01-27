"""Pydantic schemas for job-related API requests and responses"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class JobRequest(BaseModel):
    """Request schema for creating a new job"""
    sourceType: str = Field(..., description="Source type: 'upload' or 'youtube'")
    uploadId: Optional[str] = Field(None, description="Upload ID if sourceType is 'upload'")
    youtubeUrl: Optional[str] = Field(None, description="YouTube URL if sourceType is 'youtube'")
    targetLang: str = Field(default="en", description="Target language code")


class JobResponse(BaseModel):
    """Response schema for job creation"""
    jobId: str


class JobStatusResponse(BaseModel):
    """Response schema for job status"""
    status: str
    progress: float = Field(..., ge=0.0, le=1.0)
    message: Optional[str] = None


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
    items: List[dict] = Field(..., description="List of terms with meaningKo and exampleEn")


class JobResultResponse(BaseModel):
    """Response schema for job result"""
    dailyLesson: List[DailyLessonItem]
    transcriptWords: Optional[List[TranscriptWord]] = None
