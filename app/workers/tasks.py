"""Celery tasks for job processing"""

import logging
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.models import (
    AnalysisSegment,
    AnalysisSegmentVoca,
    Job,
    JobResult,
    JobStatus,
    MediaSource,
    MediaSourceKind,
    SourceType,
)
from app.services.ffmpeg_service import (
    extract_audio_from_youtube,
    extract_audio_from_file,
    cleanup_file as cleanup_ffmpeg_file
)
from app.services.s3_service import S3Service
from app.services.gemini_service import GeminiService
from app.utils.file_cleanup import cleanup_temp_files
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_job")
def process_job(self, job_id: str):
    """
    Job pipeline: acquire audio -> Gemini segment analysis -> persist segments only.
    No STT, no mp3 cut/upload.
    """
    db: Session = SessionLocal()
    job = None
    temp_audio_path = None

    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        media_source: MediaSource = None
        if job.media_source_id:
            media_source = db.query(MediaSource).filter(MediaSource.id == job.media_source_id).first()

        s3_service = S3Service()
        gemini_service = GeminiService()

        # Step 1: Validate
        logger.info("Processing job %s: Validation", job_id)
        job.status = JobStatus.DOWNLOADING
        job.progress = 0.1
        db.commit()

        # Step 2: Acquire input (full audio)
        logger.info("Processing job %s: Acquiring input", job_id)
        temp_audio_path = f"/tmp/{job_id}.flac"

        if media_source:
            if media_source.source_type == MediaSourceKind.YOUTUBE:
                extract_audio_from_youtube(media_source.youtube_url, temp_audio_path)
                if os.path.exists(temp_audio_path):
                    media_source.size_bytes = os.path.getsize(temp_audio_path)
                    db.commit()
            elif media_source.source_type == MediaSourceKind.FILE:
                upload_path = f"/tmp/upload_{job_id}"
                s3_service.download_file(media_source.storage_path, upload_path)
                if os.path.exists(upload_path):
                    media_source.size_bytes = os.path.getsize(upload_path)
                    db.commit()
                extract_audio_from_file(upload_path, temp_audio_path)
                cleanup_ffmpeg_file(upload_path)
        else:
            if job.source_type == SourceType.YOUTUBE:
                extract_audio_from_youtube(job.youtube_url, temp_audio_path)
            elif job.source_type == SourceType.UPLOAD:
                upload_path = f"/tmp/upload_{job_id}"
                upload_uri = f"s3://{settings.S3_BUCKET}/uploads/{job.upload_id}"
                s3_service.download_file(upload_uri, upload_path)
                extract_audio_from_file(upload_path, temp_audio_path)
                cleanup_ffmpeg_file(upload_path)

        job.status = JobStatus.EXTRACTING_AUDIO
        job.progress = 0.25
        db.commit()

        # Step 3: Gemini segment analysis (full audio -> segments)
        logger.info("Processing job %s: Gemini analysis & selection", job_id)
        job.status = JobStatus.GEMINI_RUNNING
        job.progress = 0.40
        db.commit()

        gemini_result = gemini_service.analyze_media_and_select_segments(temp_audio_path)
        logger.info("Gemini response for job %s: %s", job_id, json.dumps(gemini_result, ensure_ascii=False, indent=2))

        analysis_data = gemini_result.get("analysis", {}) or {}
        selected_segments = gemini_result.get("segments", [])
        summary = analysis_data.get("summary") if isinstance(analysis_data, dict) else None
        difficulty = analysis_data.get("difficulty") if isinstance(analysis_data, dict) else None
        situation = analysis_data.get("situation") if isinstance(analysis_data, dict) else None

        if not selected_segments:
            logger.warning("Gemini did not select any segments for job %s", job_id)

        # Step 4: Persist Gemini segments only (no STT, no mp3)
        logger.info("Processing job %s: Persisting segments", job_id)
        job.status = JobStatus.ASR_RUNNING
        job.progress = 0.70
        db.commit()

        full_text = " ".join(seg.get("sentence", "") for seg in selected_segments)

        for idx, seg in enumerate(selected_segments):
            start_sec = float(seg.get("startSec", 0))
            end_sec = float(seg.get("endSec", 0))
            segment_sentence = seg.get("sentence") or ""

            segment = AnalysisSegment(
                job_id=job_id,
                idx=idx,
                start_sec=start_sec,
                end_sec=end_sec,
                sentence=segment_sentence,
                reason=seg.get("reason"),
                suggested_activity=seg.get("suggestedActivity"),
            )
            db.add(segment)
            db.flush()

            vocab_items = seg.get("items") or []
            for v_idx, vocab in enumerate(vocab_items):
                db.add(AnalysisSegmentVoca(
                    analysis_segment_id=segment.id,
                    idx=v_idx,
                    term=vocab.get("term", ""),
                    meaning_ko=vocab.get("meaningKo", ""),
                    example_en=vocab.get("exampleEn", ""),
                ))

        # Step 5: Persist result (meta + full_text)
        logger.info("Processing job %s: Finalizing", job_id)
        meta = JobResult(
            job_id=job_id,
            result_type="DAILY_LESSON_V2",
            language=job.target_lang or "en-US",
            full_text=full_text,
            summary=summary,
            difficulty=difficulty,
            situation=situation,
        )
        db.add(meta)

        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        db.commit()
        logger.info("Job %s completed successfully", job_id)

    except Exception as e:
        logger.error("Error processing job %s: %s", job_id, e, exc_info=True)
        if job:
            job.status = JobStatus.FAILED
            job.error = str(e)
            db.commit()
        raise

    finally:
        try:
            if temp_audio_path and os.path.exists(temp_audio_path):
                cleanup_ffmpeg_file(temp_audio_path)
            cleanup_temp_files(job_id)
        except Exception as e:
            logger.warning("Error during cleanup for job %s: %s", job_id, e)
        db.close()
