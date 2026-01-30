"""Pydantic schemas for result-related data structures"""

from pydantic import BaseModel, Field
from typing import List, Optional


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
