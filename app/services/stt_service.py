"""Service for Google Cloud Speech-to-Text operations"""

import logging
import time
from typing import List, Dict, Any
from google.cloud import speech_v1
from google.cloud.speech_v1 import types

from app.config import settings
from app.utils.timeparse import parse_timestamp_to_seconds

logger = logging.getLogger(__name__)


class STTService:
    """Service for Google Cloud Speech-to-Text"""
    
    def __init__(self):
        self.client = speech_v1.SpeechClient()
    
    def start_long_running_recognize(
        self,
        gcs_uri: str,
        language_code: str = "en-US",
        sample_rate_hertz: int = 16000
    ) -> str:
        """
        Start a long-running recognition operation.
        
        Args:
            gcs_uri: GCS URI of the audio file
            language_code: Language code (e.g., "en-US")
            sample_rate_hertz: Audio sample rate
            
        Returns:
            Operation name
        """
        try:
            config = types.RecognitionConfig(
                encoding=types.RecognitionConfig.AudioEncoding.FLAC,
                sample_rate_hertz=sample_rate_hertz,
                language_code=language_code,
                enable_word_time_offsets=True,
                enable_automatic_punctuation=True,
            )
            
            audio = types.RecognitionAudio(uri=gcs_uri)
            
            operation = self.client.long_running_recognize(
                config=config,
                audio=audio
            )
            
            logger.info(f"Started STT operation: {operation.operation.name}")
            return operation.operation.name
            
        except Exception as e:
            logger.error(f"Error starting STT operation: {e}")
            raise
    
    def wait_for_completion(self, operation_name: str, timeout_seconds: int = 3600) -> Dict[str, Any]:
        """
        Wait for STT operation to complete and return results.
        
        Args:
            operation_name: Operation name from start_long_running_recognize
            timeout_seconds: Maximum time to wait
            
        Returns:
            Dictionary with words and transcript
        """
        try:
            operation = self.client.get_operation(operation_name)
            start_time = time.time()
            
            while not operation.done:
                if time.time() - start_time > timeout_seconds:
                    raise TimeoutError(f"STT operation timed out after {timeout_seconds} seconds")
                
                time.sleep(5)  # Poll every 5 seconds
                operation = self.client.get_operation(operation_name)
            
            if operation.error:
                raise RuntimeError(f"STT operation failed: {operation.error}")
            
            # Get results
            response = operation.response
            if not response or not response.results:
                raise RuntimeError("No results from STT operation")
            
            # Extract words with timestamps
            words = []
            full_transcript = []
            
            for result in response.results:
                if result.alternatives:
                    alternative = result.alternatives[0]
                    full_transcript.append(alternative.transcript)
                    
                    for word_info in alternative.words:
                        word_data = {
                            "word": word_info.word,
                            "startSeconds": parse_timestamp_to_seconds(word_info.start_time),
                            "endSeconds": parse_timestamp_to_seconds(word_info.end_time),
                        }
                        words.append(word_data)
            
            logger.info(f"STT completed: {len(words)} words, {len(full_transcript)} segments")
            
            return {
                "words": words,
                "transcript": " ".join(full_transcript)
            }
            
        except Exception as e:
            logger.error(f"Error waiting for STT completion: {e}")
            raise
