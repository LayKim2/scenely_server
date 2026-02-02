"""Database models"""

import uuid
from datetime import datetime
import enum

from sqlalchemy import (
    Column,
    String,
    Float,
    Text,
    ForeignKey,
    DateTime,
    Integer,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

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
    """Source type enumeration (legacy, kept for backward compatibility)"""

    UPLOAD = "upload"
    YOUTUBE = "youtube"


class JobType(str, enum.Enum):
    """Job type for future expansion."""

    DAILY_LESSON = "daily_lesson"


class MediaSourceKind(str, enum.Enum):
    """Kind of input media for a job."""

    YOUTUBE = "YOUTUBE"
    FILE = "FILE"


class User(Base):
    """Service-level user."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=True)
    nickname = Column(String, nullable=True)
    profile_image = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    identities = relationship("UserIdentity", back_populates="user", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="user")


class UserIdentity(Base):
    """Mapping to external identity providers (kakao/naver/google/local)."""

    __tablename__ = "user_identities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)
    provider_user_id = Column(String, nullable=False)
    provider_email = Column(String, nullable=True)
    profile_nickname = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="identities")


class MediaSource(Base):
    """Input media source. type=FILE → storage_path (S3), type=YOUTUBE → youtube_url."""

    __tablename__ = "media_sources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    source_type = Column("type", SQLEnum(MediaSourceKind), nullable=False)
    youtube_url = Column(String, nullable=True)  # when source_type=YOUTUBE
    storage_path = Column(String, nullable=True)  # when source_type=FILE
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    jobs = relationship("Job", back_populates="media_source")


class Job(Base):
    """Job model for tracking processing tasks."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    # New fields
    media_source_id = Column(String, ForeignKey("media_sources.id"), nullable=True)
    job_type = Column(SQLEnum(JobType), nullable=False, default=JobType.DAILY_LESSON)

    # Legacy fields (kept for backward compatibility with existing data)
    source_type = Column(SQLEnum(SourceType), nullable=True)
    youtube_url = Column(String, nullable=True)
    upload_id = Column(String, nullable=True)

    target_lang = Column(String, default="en")
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    progress = Column(Float, default=0.0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="jobs")
    media_source = relationship("MediaSource", back_populates="jobs")
    job_result_meta = relationship("JobResult", back_populates="job", uselist=False)


class JobResult(Base):
    """Job result metadata + raw JSON, for new pipeline."""

    __tablename__ = "job_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), unique=True, nullable=False)
    result_type = Column(String, nullable=False, default="DAILY_LESSON_V1")
    analysis = Column(Text, nullable=True)  # Overall analysis/guide from Gemini
    raw_daily_json = Column(Text, nullable=True)
    raw_transcript_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="job_result_meta")


class Transcript(Base):
    """Full transcript per job."""

    __tablename__ = "transcripts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    language = Column(String, nullable=True)
    full_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job")


class DailyLesson(Base):
    """Daily lesson unit per job."""

    __tablename__ = "daily_lessons"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    idx = Column(Integer, nullable=False)
    start_sec = Column(Float, nullable=False)
    end_sec = Column(Float, nullable=False)
    sentence = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)  # Gemini's reason for selection
    suggested_activity = Column(String, nullable=True)  # e.g. "Shadowing"
    clip_audio_url = Column(String, nullable=True)  # S3 URL for this segment's mp3
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job")
    items = relationship("DailyLessonItemModel", back_populates="lesson", cascade="all, delete-orphan")


class DailyLessonItemModel(Base):
    """Vocabulary/phrase items for a daily lesson."""

    __tablename__ = "daily_lesson_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    daily_lesson_id = Column(String, ForeignKey("daily_lessons.id"), nullable=False)
    idx = Column(Integer, nullable=False)
    term = Column(String, nullable=False)
    meaning_ko = Column(Text, nullable=False)
    example_en = Column(Text, nullable=False)

    lesson = relationship("DailyLesson", back_populates="items")
