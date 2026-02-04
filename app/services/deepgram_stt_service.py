"""Deepgram STT service (nova-2). Same interface as Google STT for drop-in replacement."""

import logging
from typing import Any, Dict, List

import httpx
from deepgram import DeepgramClient, PrerecordedOptions

from app.config import settings

logger = logging.getLogger(__name__)


class DeepgramSTTService:
    """Speech-to-Text via Deepgram Nova-2. Returns words + transcript like Google STT."""

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        if not self.api_key:
            logger.warning("DEEPGRAM_API_KEY is not set; Deepgram STT will fail.")
        self._client: DeepgramClient | None = None

    @property
    def client(self) -> DeepgramClient:
        if self._client is None:
            self._client = DeepgramClient(self.api_key)
        return self._client

    def transcribe_segment(self, local_path: str, language_code: str = "en-US") -> Dict[str, Any]:
        """
        Transcribe audio file with Nova-2. Returns same shape as Google STT:
        { "words": [{ word, startSeconds, endSeconds }], "transcript": "..." }
        """
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured in settings.")

        logger.info(
            "STT (Deepgram nova-2): transcribe path=%s language=%s",
            local_path,
            language_code,
        )

        with open(local_path, "rb") as audio:
            source = {"buffer": audio}
            options = PrerecordedOptions(
                model="nova-2",
                language=language_code.replace("-", "_") if language_code else "en",
                smart_format=True,
                punctuate=True,
            )
            response = self.client.listen.rest.v("1").transcribe_file(
                source,
                options,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )

        words: List[Dict[str, Any]] = []
        transcript_parts: List[str] = []

        # SDK may return dict or object
        if hasattr(response, "to_dict"):
            data = response.to_dict()
        elif isinstance(response, dict):
            data = response
        else:
            data = getattr(response, "__dict__", {}) or {}

        try:
            results = data.get("results") or {}
            channels = results.get("channels") or []
            if not channels:
                logger.warning("Deepgram returned no channels")
                return {"words": [], "transcript": ""}
            channel = channels[0]
            alts = channel.get("alternatives") or []
            if not alts:
                logger.warning("Deepgram returned no alternatives")
                return {"words": [], "transcript": ""}
            alt = alts[0]
            transcript_parts.append(alt.get("transcript") or "")
            for w in alt.get("words") or []:
                words.append({
                    "word": w.get("word", ""),
                    "startSeconds": float(w.get("start", 0.0)),
                    "endSeconds": float(w.get("end", 0.0)),
                })
        except (KeyError, IndexError, TypeError) as e:
            logger.error("Deepgram response parse error: %s", e)
            raise

        transcript = " ".join(transcript_parts).strip()
        logger.info("Deepgram STT completed: %d words", len(words))

        return {
            "words": words,
            "transcript": transcript,
        }
