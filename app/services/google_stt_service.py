import logging
import os
from typing import Any, Dict, List

from google.cloud import speech_v1p1beta1 as speech
from app.config import settings

logger = logging.getLogger(__name__)


class GoogleSTTService:
    """Service for Google Cloud Speech-to-Text V1p1beta1 (for word-level timestamps)."""

    def __init__(self):
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
        self.client = speech.SpeechClient()

    def transcribe_segment(self, local_path: str, language_code: str = "en-US") -> Dict[str, Any]:
        """
        Transcribe audio using LongRunningRecognize (async).
        Returns: { "words": [{ word, startSeconds, endSeconds }], "transcript": "..." }
        """
        try:
            with open(local_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
                sample_rate_hertz=16000,
                language_code=language_code,
                enable_word_time_offsets=True,
                enable_automatic_punctuation=True,
            )

            logger.info(f"Requesting Google STT (long_running_recognize) for {local_path}")
            operation = self.client.long_running_recognize(config=config, audio=audio)
            response = operation.result(timeout=600)  # 10 minutes timeout

            words: List[Dict[str, Any]] = []
            full_transcript: List[str] = []

            for result in response.results:
                alternative = result.alternatives[0]
                full_transcript.append(alternative.transcript)
                
                for word_info in alternative.words:
                    words.append({
                        "word": word_info.word,
                        "startSeconds": word_info.start_time.total_seconds(),
                        "endSeconds": word_info.end_time.total_seconds(),
                    })

            transcript = " ".join(full_transcript)
            logger.info(f"Google STT completed: {len(words)} words found")
            
            return {
                "words": words,
                "transcript": transcript
            }
        except Exception as e:
            logger.error(f"Error in Google STT: {e}")
            raise
