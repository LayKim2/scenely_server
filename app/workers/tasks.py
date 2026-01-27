"""Celery tasks for job processing"""

import logging
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.models import Job, Result, JobStatus, SourceType
from app.services.ffmpeg_service import (
    extract_audio_from_youtube,
    extract_audio_from_file,
    cleanup_file as cleanup_ffmpeg_file
)
from app.services.gcs_service import GCSService
from app.services.stt_service import STTService
from app.services.transcript_service import words_to_segments
from app.services.gemini_service import GeminiService
from app.utils.file_cleanup import cleanup_temp_files
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_job")
def process_job(self, job_id: str):
    """
    Main orchestrator task for processing a job.
    
    Pipeline:
    1. Validate input
    2. Acquire input (download/YouTube)
    3. FFmpeg → temp audio
    4. Upload to GCS temp
    5. Google STT LongRunningRecognize
    6. Build transcript segments
    7. Gemini Analysis
    8. Persist result
    9. Cleanup
    """
    db: Session = SessionLocal()
    job = None
    temp_audio_path = None
    gcs_uri = None
    
    try:
        # Get job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Initialize services
        gcs_service = GCSService()
        stt_service = STTService()
        gemini_service = GeminiService()
        
        # Step 1: Validate
        logger.info(f"Processing job {job_id}: Validation")
        job.status = JobStatus.DOWNLOADING
        job.progress = 0.1
        db.commit()
        
        # Step 2: Acquire Input
        logger.info(f"Processing job {job_id}: Acquiring input")
        temp_audio_path = f"/tmp/{job_id}.flac"
        
        if job.source_type == SourceType.YOUTUBE:
            if not job.youtube_url:
                raise ValueError("YouTube URL is required for youtube source type")
            extract_audio_from_youtube(job.youtube_url, temp_audio_path)
        elif job.source_type == SourceType.UPLOAD:
            if not job.upload_id:
                raise ValueError("Upload ID is required for upload source type")
            # Download from GCS if needed
            upload_path = f"/tmp/upload_{job_id}"
            gcs_upload_uri = f"gs://{settings.GCS_BUCKET_TMP_AUDIO}/uploads/{job.upload_id}"
            gcs_service.download_file(gcs_upload_uri, upload_path)
            extract_audio_from_file(upload_path, temp_audio_path)
            cleanup_ffmpeg_file(upload_path)
        else:
            raise ValueError(f"Unknown source type: {job.source_type}")
        
        # Step 3: FFmpeg → temp audio (already done above)
        logger.info(f"Processing job {job_id}: Audio extracted")
        job.status = JobStatus.EXTRACTING_AUDIO
        job.progress = 0.25
        db.commit()
        
        # Step 4: Upload to GCS temp
        logger.info(f"Processing job {job_id}: Uploading to GCS")
        job.status = JobStatus.UPLOADING_GCS
        job.progress = 0.40
        db.commit()
        
        gcs_uri = gcs_service.upload_audio_file(temp_audio_path, job_id)
        
        # Step 5: Google STT LongRunningRecognize
        logger.info(f"Processing job {job_id}: Starting STT")
        job.status = JobStatus.ASR_RUNNING
        job.progress = 0.60
        db.commit()
        
        operation_name = stt_service.start_long_running_recognize(
            gcs_uri,
            language_code=job.target_lang or "en-US"
        )
        
        stt_result = stt_service.wait_for_completion(operation_name)
        words = stt_result["words"]
        
        # Step 6: Build transcript segments
        logger.info(f"Processing job {job_id}: Building segments")
        segments = words_to_segments(words)
        
        # Step 7: Gemini Analysis
        logger.info(f"Processing job {job_id}: Running Gemini analysis")
        job.status = JobStatus.GEMINI_RUNNING
        job.progress = 0.85
        db.commit()
        
        daily_lesson = gemini_service.analyze_transcript(segments)
        
        # Step 8: Persist result
        logger.info(f"Processing job {job_id}: Persisting result")
        result = Result(
            job_id=job_id,
            daily_lesson_json=json.dumps(daily_lesson, ensure_ascii=False),
            transcript_words_json=json.dumps(words, ensure_ascii=False)
        )
        db.add(result)
        
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        db.commit()
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
        if job:
            job.status = JobStatus.FAILED
            job.error = str(e)
            db.commit()
        raise
    
    finally:
        # Step 9: Cleanup
        try:
            if temp_audio_path and os.path.exists(temp_audio_path):
                cleanup_ffmpeg_file(temp_audio_path)
            
            if gcs_uri:
                gcs_service = GCSService()
                gcs_service.delete_audio_file(job_id)
            
            cleanup_temp_files(job_id)
        except Exception as e:
            logger.warning(f"Error during cleanup for job {job_id}: {e}")
        
        db.close()
