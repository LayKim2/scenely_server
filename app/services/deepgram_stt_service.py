"""Deepgram STT: pre-recorded file transcription (문장별 + 전체 스크립트).

Flux(https://developers.deepgram.com/docs/flux/quickstart)는 실시간 스트리밍용(/v2/listen WebSocket)이라
업로드 파일 배치 처리에는 사용하지 않음. 파일 STT는 Pre-Recorded API(v1, nova-2) + utterances 사용.
"""

import logging
from typing import Any, Dict, List

import httpx
from deepgram import DeepgramClient, PrerecordedOptions

from app.config import settings

logger = logging.getLogger(__name__)


class DeepgramSTTService:
    """Pre-recorded file STT (Nova-2). Returns full transcript + sentence list only."""

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
        Transcribe audio file (Pre-Recorded API). Returns:
        {
          "transcript": "...",   # 전체 스크립트
          "sentences": [{ startSeconds, endSeconds, text }, ...]  # 문장별
        }
        """
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured in settings.")

        logger.info(
            "STT (Deepgram pre-recorded nova-2): path=%s language=%s",
            local_path,
            language_code,
        )

        with open(local_path, "rb") as audio:
            source = {"buffer": audio}
            lang = (language_code or "en").strip() or "en"
            options = PrerecordedOptions(
                model="nova-2",
                language=lang,
                smart_format=True,
                punctuate=True,
                utterances=True,
            )
            response = self.client.listen.rest.v("1").transcribe_file(
                source,
                options,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )

        transcript_parts: List[str] = []
        sentences: List[Dict[str, Any]] = []

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
                return {"transcript": "", "sentences": []}
            channel = channels[0]
            alts = channel.get("alternatives") or []
            if not alts:
                logger.warning("Deepgram returned no alternatives")
                return {"transcript": "", "sentences": []}
            alt = alts[0]
            transcript_parts.append(alt.get("transcript") or "")

            for ut in results.get("utterances") or []:
                sentences.append({
                    "startSeconds": float(ut.get("start", 0.0)),
                    "endSeconds": float(ut.get("end", 0.0)),
                    "text": (ut.get("transcript") or "").strip(),
                })
        except (KeyError, IndexError, TypeError) as e:
            logger.error("Deepgram response parse error: %s", e)
            raise

        transcript = " ".join(transcript_parts).strip()
        logger.info("Deepgram STT completed: %d sentences", len(sentences))

        return {
            "transcript": transcript,
            "sentences": sentences,
        }
