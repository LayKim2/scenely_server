"""Celery tasks for job processing"""

import logging
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.models import (
    DailyLesson,
    DailyLessonItemModel,
    Job,
    JobResult,
    JobStatus,
    MediaSource,
    MediaSourceKind,
    Result,
    SourceType,
    Transcript,
    TranscriptSegment,
    TranscriptWordModel,
)
from app.services.ffmpeg_service import (
    extract_audio_from_youtube,
    extract_audio_from_file,
    cut_audio_segment,
    cleanup_file as cleanup_ffmpeg_file
)
from app.services.s3_service import S3Service
from app.services.google_stt_service import GoogleSTTService
from app.services.gemini_service import GeminiService
from app.utils.file_cleanup import cleanup_temp_files
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_job")
def process_job(self, job_id: str):
    """
    Main orchestrator task for processing a job.
    
    New Pipeline:
    1. Validate input
    2. Acquire input (download/YouTube) -> extract FULL audio
    3. Gemini Analysis (Full Audio) -> select segments + overall analysis
    4. For each selected segment:
       - FFmpeg cut -> segment audio (flac for STT, mp3 for front)
       - Google STT -> word-level timestamps
       - Upload mp3 to S3
    5. Persist results (normalized DailyLesson + TranscriptWords)
    6. Cleanup
    """
    db: Session = SessionLocal()
    job = None
    temp_audio_path = None
    segment_files = []

    try:
        # Get job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        media_source: MediaSource = None
        if job.media_source_id:
            media_source = db.query(MediaSource).filter(MediaSource.id == job.media_source_id).first()

        # Initialize services
        s3_service = S3Service()
        stt_service = GoogleSTTService()
        gemini_service = GeminiService()
        
        # Step 1: Validate
        logger.info(f"Processing job {job_id}: Validation")
        job.status = JobStatus.DOWNLOADING
        job.progress = 0.1
        db.commit()
        
        # Step 2: Acquire Input
        logger.info(f"Processing job {job_id}: Acquiring input")
        temp_audio_path = f"/tmp/{job_id}.flac"

        if media_source:
            if media_source.source_kind == MediaSourceKind.YOUTUBE:
                extract_audio_from_youtube(media_source.youtube_url, temp_audio_path)
            elif media_source.source_kind == MediaSourceKind.FILE:
                upload_path = f"/tmp/upload_{job_id}"
                s3_service.download_file(media_source.storage_path, upload_path)
                extract_audio_from_file(upload_path, temp_audio_path)
                cleanup_ffmpeg_file(upload_path)
        else:
            # Legacy fields
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
        
        # Step 3: Gemini Analysis (Selection)
        logger.info(f"Processing job {job_id}: Gemini analysis & selection")
        job.status = JobStatus.GEMINI_RUNNING
        job.progress = 0.40
        db.commit()

        # Call Gemini with the full audio file to get segments
        gemini_result = gemini_service.analyze_media_and_select_segments(temp_audio_path)
        analysis_data = gemini_result.get("analysis", {})
        selected_segments = gemini_result.get("segments", [])

        # Construct analysis text for the DB (JSON string or formatted summary)
        analysis_text = json.dumps(analysis_data, ensure_ascii=False) if isinstance(analysis_data, dict) else str(analysis_data)

        if not selected_segments:
            logger.warning(f"Gemini did not select any segments for job {job_id}")

        # Step 4: Process each segment (STT + FFmpeg cut)
        logger.info(f"Processing job {job_id}: Segment processing (STT + Cutting)")
        job.status = JobStatus.ASR_RUNNING
        job.progress = 0.60
        db.commit()

        processed_lessons = []
        all_words = []
        total_segments = len(selected_segments)

        # We'll create one Transcript for the job
        transcript = Transcript(
            job_id=job_id,
            language=job.target_lang or "en-US",
            full_text="", # Will be combined from segments
        )
        db.add(transcript)
        db.flush()

        for idx, seg in enumerate(selected_segments):
            start_sec = float(seg["startSec"])
            end_sec = float(seg["endSec"])
            
            # Update progress
            job.progress = 0.60 + (0.30 * (idx / total_segments if total_segments > 0 else 1))
            db.commit()

            # A. Cut segment audio (flac for STT)
            seg_flac = f"/tmp/{job_id}_seg_{idx}.flac"
            cut_audio_segment(temp_audio_path, seg_flac, start_sec, end_sec, format="flac")
            segment_files.append(seg_flac)

            # B. Google STT on segment
            stt_res = stt_service.transcribe_segment(seg_flac, language_code=job.target_lang or "en-US")
            
            # Convert segment-relative word timings to absolute video timings
            seg_words = []
            for w in stt_res["words"]:
                abs_w = {
                    "word": w["word"],
                    "startSeconds": w["startSeconds"] + start_sec,
                    "endSeconds": w["endSeconds"] + start_sec
                }
                seg_words.append(abs_w)
                all_words.append(abs_w)

            # C. Cut segment audio (mp3 for front)
            seg_mp3 = f"/tmp/{job_id}_seg_{idx}.mp3"
            cut_audio_segment(temp_audio_path, seg_mp3, start_sec, end_sec, format="mp3")
            segment_files.append(seg_mp3)

            # D. Upload mp3 to S3
            mp3_s3_key = f"lessons/{job_id}/segment_{idx}.mp3"
            s3_service.client.upload_file(seg_mp3, settings.S3_BUCKET, mp3_s3_key)
            clip_url = f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{mp3_s3_key}"
            if settings.CLOUDFRONT_DOMAIN:
                clip_url = f"https://{settings.CLOUDFRONT_DOMAIN}/{mp3_s3_key}"

            # Prepare DailyLesson data
            # Use Gemini's provided sentence if available, else fall back to STT transcript
            lesson_sentence = seg.get("sentence") or stt_res["transcript"]
            
            lesson = DailyLesson(
                job_id=job_id,
                idx=idx,
                start_sec=start_sec,
                end_sec=end_sec,
                sentence=lesson_sentence,
                reason=seg.get("reason"),
                suggested_activity=seg.get("suggestedActivity"),
                clip_audio_url=clip_url
            )
            db.add(lesson)
            db.flush()

            # Get vocabulary items from Gemini if it provided them in the selection, 
            # or we might want another Gemini pass for vocabulary based on STT text.
            # For now, let's assume Gemini provided them or we'll add them if present.
            # Note: Gemini 1.5 might be good at this too.
            vocab_items = seg.get("items", []) # If Gemini provided them in selection
            for v_idx, vocab in enumerate(vocab_items):
                db.add(DailyLessonItemModel(
                    daily_lesson_id=lesson.id,
                    idx=v_idx,
                    term=vocab.get("term", ""),
                    meaning_ko=vocab.get("meaningKo", ""),
                    example_en=vocab.get("exampleEn", "")
                ))

            # Store segment in TranscriptSegment (optional but good for consistency)
            db.add(TranscriptSegment(
                transcript_id=transcript.id,
                idx=idx,
                start_sec=start_sec,
                end_sec=end_sec,
                text=stt_res["transcript"]
            ))

        # Update full transcript text
        transcript.full_text = " ".join([seg.get("text", "") for seg in (
            db.query(TranscriptSegment).filter(TranscriptSegment.transcript_id == transcript.id)
            .order_by(TranscriptSegment.idx.asc()).all()
        )])

        # Persist all words
        for w_idx, w in enumerate(all_words):
            db.add(TranscriptWordModel(
                transcript_id=transcript.id,
                idx=w_idx,
                start_sec=w["startSeconds"],
                end_sec=w["endSeconds"],
                word=w["word"]
            ))

        # Step 5: Persist Meta
        logger.info(f"Processing job {job_id}: Finalizing")
        meta = JobResult(
            job_id=job_id,
            result_type="DAILY_LESSON_V2",
            analysis=analysis_text,
            raw_daily_json=json.dumps(selected_segments, ensure_ascii=False),
            raw_transcript_json=json.dumps(all_words, ensure_ascii=False),
        )
        db.add(meta)

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
        # Step 6: Cleanup
        try:
            if temp_audio_path and os.path.exists(temp_audio_path):
                cleanup_ffmpeg_file(temp_audio_path)
            for f in segment_files:
                if os.path.exists(f):
                    cleanup_ffmpeg_file(f)
            cleanup_temp_files(job_id)
        except Exception as e:
            logger.warning(f"Error during cleanup for job {job_id}: {e}")
        
        db.close()
