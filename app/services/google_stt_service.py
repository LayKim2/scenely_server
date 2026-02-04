import logging
import os
import uuid
from typing import Any, Dict, List

from google.cloud import speech_v1p1beta1 as speech
from google.cloud import storage

from app.config import settings

logger = logging.getLogger(__name__)


class GoogleSTTService:
    """Service for Google Cloud Speech-to-Text V1p1beta1 (for word-level timestamps)."""

    def __init__(self):
        # Configure credentials for both Speech and Storage clients
        if settings.GOOGLE_APPLICATION_CREDENTIALS:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS

        self.client = speech.SpeechClient()
        self.storage_client = storage.Client()
        self.gcs_bucket = settings.GCS_BUCKET

        if not self.gcs_bucket:
            logger.warning("GCS_BUCKET is not set; Google STT with GCS URI will fail.")

    def _upload_to_gcs(self, local_path: str) -> str:
        """
        Upload local audio file to GCS and return gs:// URI.
        """
        if not self.gcs_bucket:
            raise RuntimeError("GCS_BUCKET is not configured in settings.")

        bucket = self.storage_client.bucket(self.gcs_bucket)
        # Use a stable prefix for STT audio; include random suffix to avoid collisions
        blob_name = f"stt-audio/{uuid.uuid4()}_{os.path.basename(local_path)}"
        blob = bucket.blob(blob_name)

        logger.info("Uploading audio to GCS bucket=%s key=%s", self.gcs_bucket, blob_name)
        blob.upload_from_filename(local_path)

        return f"gs://{self.gcs_bucket}/{blob_name}"

    def transcribe_segment(self, local_path: str, language_code: str = "en-US") -> Dict[str, Any]:
        """
        Transcribe audio using LongRunningRecognize (async), referencing audio via GCS URI.
        Returns: { "words": [{ word, startSeconds, endSeconds }], "transcript": "..." }
        """
        gcs_uri = None
        try:
            gcs_uri = self._upload_to_gcs(local_path)

            audio = speech.RecognitionAudio(uri=gcs_uri)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
                sample_rate_hertz=16000,
                language_code=language_code,
                enable_word_time_offsets=True,
                enable_automatic_punctuation=True,
            )

            logger.info("Requesting Google STT (long_running_recognize) for %s", gcs_uri)
            operation = self.client.long_running_recognize(config=config, audio=audio)
            logger.info("Waiting for Speech-to-Text result (may take several minutes for long audio)...")
            response = operation.result(timeout=1800)  # 30 minutes for long files

            words: List[Dict[str, Any]] = []
            full_transcript: List[str] = []

            for result in response.results:
                alternative = result.alternatives[0]
                full_transcript.append(alternative.transcript)

                for word_info in alternative.words:
                    words.append(
                        {
                            "word": word_info.word,
                            "startSeconds": word_info.start_time.total_seconds(),
                            "endSeconds": word_info.end_time.total_seconds(),
                        }
                    )

            transcript = " ".join(full_transcript)
            logger.info("Google STT completed: %d words found", len(words))

            return {
                "words": words,
                "transcript": transcript,
            }
        except Exception as e:
            logger.error("Error in Google STT: %s", e)
            raise
        finally:
            # Best-effort cleanup of temporary GCS object
            if gcs_uri:
                try:
                    # gcs_uri format: gs://bucket/key
                    _, _, bucket_and_key = gcs_uri.partition("gs://")
                    bucket_name, _, key = bucket_and_key.partition("/")
                    if bucket_name and key:
                        bucket = self.storage_client.bucket(bucket_name)
                        blob = bucket.blob(key)
                        blob.delete()
                        logger.info("Deleted temporary GCS object: %s", gcs_uri)
                except Exception as cleanup_err:
                    logger.warning("Failed to delete GCS object %s: %s", gcs_uri, cleanup_err)
