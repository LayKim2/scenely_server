"""STT API for testing Deepgram transcription from Swagger."""

import logging
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.services.deepgram_stt_service import DeepgramSTTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stt", tags=["stt"])


@router.post(
    "/transcribe",
    response_model=dict,
    summary="Transcribe audio (Deepgram nova-2)",
    description="Upload an audio file (e.g. FLAC, WAV, MP3) and get words + transcript. For testing in Swagger.",
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file (FLAC, WAV, MP3, etc.)"),
    language: str = Query("en-US", description="Language code (e.g. en-US, ko)"),
) -> dict:
    """
    Run Deepgram STT on the uploaded file. Returns words with timestamps and full transcript.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = os.path.splitext(file.filename)[1] or ".bin"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        logger.error("Failed to save upload: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    try:
        stt_service = DeepgramSTTService()
        result: dict = stt_service.transcribe_segment(
            local_path=tmp_path,
            language_code=language,
        )
        return result
    except RuntimeError as e:
        if "DEEPGRAM_API_KEY" in str(e):
            raise HTTPException(
                status_code=503,
                detail="STT not configured (DEEPGRAM_API_KEY missing)",
            )
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("STT failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception as e:
            logger.warning("Cleanup temp file failed: %s", e)
