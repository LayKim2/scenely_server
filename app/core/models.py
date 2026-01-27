"""Database models"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Text, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.core.db import Base


class JobStatus(str, enum.Enum):
    """Job status enumeration"""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    EXTRACTING_AUDIO = "extracting_audio"
    UPLOADING_GCS = "uploading_gcs"
    ASR_RUNNING = "asr_running"
    GEMINI_RUNNING = "gemini_running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, enum.Enum):
    """Source type enumeration"""
    UPLOAD = "upload"
    YOUTUBE = "youtube"


class Job(Base):
    """Job model for tracking processing tasks"""
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=True)
    source_type = Column(SQLEnum(SourceType), nullable=False)
    youtube_url = Column(String, nullable=True)
    upload_id = Column(String, nullable=True)
    target_lang = Column(String, default="en")
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    progress = Column(Float, default=0.0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    result = relationship("Result", back_populates="job", uselist=False)


class Result(Base):
    """Result model for storing job results"""
    __tablename__ = "results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), unique=True, nullable=False)
    daily_lesson_json = Column(Text, nullable=False)
    transcript_words_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    job = relationship("Job", back_populates="result")
