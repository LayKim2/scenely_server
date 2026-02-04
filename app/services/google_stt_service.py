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

        size_bytes = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        bucket = self.storage_client.bucket(self.gcs_bucket)
        blob_name = f"stt-audio/{uuid.uuid4()}_{os.path.basename(local_path)}"
        blob = bucket.blob(blob_name)

        logger.info(
            "STT: uploading to GCS bucket=%s key=%s size_bytes=%s",
            self.gcs_bucket, blob_name, size_bytes,
        )
        blob.upload_from_filename(local_path)
        logger.info("STT: GCS upload done, uri=gs://%s/%s", self.gcs_bucket, blob_name)

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

            logger.info("STT: calling long_running_recognize uri=%s language=%s", gcs_uri, language_code)
            operation = self.client.long_running_recognize(config=config, audio=audio)
            op_name = getattr(operation, "name", None) or "?"
            logger.info(
                "STT: request submitted, operation.name=%s — waiting up to 1800s for result...",
                op_name,
            )
            response = operation.result(timeout=1800)  # 30 minutes for long files
            logger.info("STT: operation.result() returned successfully")

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
