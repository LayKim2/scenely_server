"""Service for Google Gemini API operations (google-genai SDK)."""

import logging
import json
from typing import List, Dict, Any

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

# gemini-3.0-flash is available in v1alpha (experimental). v1beta = beta, v1 = stable.
GEMINI_MODEL = "gemini-3-flash"

class GeminiService:
    """Service for Google Gemini API (google-genai SDK)."""

    def __init__(self):
        # Use v1alpha so gemini-3.0-flash (and other preview models) are available.
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(api_version="v1alpha"),
        )
        try:
            logger.info("--- 사용 가능한 모델 목록 ---")
            for model in self.client.models.list():
                methods = getattr(model, "supported_generation_methods", None) or []
                logger.info("Name: %s, Supported Methods: %s", model.name, methods)
        except Exception as e:
            logger.warning("리스트 확인 중 에러 발생: %s", e)

    def analyze_media_and_select_segments(self, local_audio_path: str) -> Dict[str, Any]:
        """
        Upload audio to Gemini and get learning guide + selected segments.

        Returns:
            {
                "analysis": "...",
                "segments": [
                    { "startSec": float, "endSec": float, "reason": "...", "suggestedActivity": "..." }
                ]
            }
        """
        try:
            logger.info("Uploading audio to Gemini File API: %s", local_audio_path)
            audio_file = self.client.files.upload(
                file=local_audio_path,
                config=types.UploadFileConfig(mime_type="audio/flac"),
            )

            prompt = """# Role
                    너는 전 세계 언어 학습자를 위한 최고의 외국어 교육 전문가이자 영상 분석가야.
                    너의 임무는 제공된 영상을 분석하여 학습자가 '반복 청취 및 쉐도잉'하기에 가장 적합한 핵심 구간들을 선정하고, 그 이유와 대사를 정확히 추출하는 것이다.

                    # Task
                    영상을 시청하고 다음 단계를 수행하라:
                    1. 영상의 전체적인 주제, 난이도(CEFR 레벨 기준), 그리고 어떤 학습 상황(비즈니스, 일상, 여행 등)인지 요약하라.
                    2. 학습자가 실제로 '소리 내어 따라 읽기(Shadowing)' 좋고, 실생활 활용도가 높은 '베스트 학습 구간'을 3~5개 선정하라.
                    3. 각 선정된 구간에 대해 시작/종료 타임스탬프, 추천 이유, 그리고 정확한 대사를 제공하라.

                    # Selection Criteria (구간 선정 기준)
                    - 화자의 발음이 명확하고 배경 소음이 적은 구간.
                    - 실생활에서 자주 쓰이는 구어체 표현이나 핵심 숙어가 포함된 구간.
                    - 너무 짧거나 너무 길지 않은(대략 10초~30초) 호흡의 문장 단위 구간.

                    # Output Format (MUST BE JSON)
                    반드시 아래 구조의 JSON 형식으로만 응답하라. 다른 설명 문구는 포함하지 마라.

                    {
                    "analysis": {
                        "summary": "영상 전체 주제 요약 (한국어)",
                        "difficulty": "CEFR 레벨 (예: A2, B1, C1 등)",
                        "situation": "학습 상황 (예: 비즈니스, 일상, 여행 등)"
                    },
                    "segments": [
                        {
                        "startSec": 시작 시간 (float, 초 단위),
                        "endSec": 종료 시간 (float, 초 단위),
                        "reason": "선정 이유 (한국어)",
                        "sentence": "해당 구간의 정확한 영어 대사",
                        "items": [
                            {
                            "term": "주요 단어/숙어",
                            "meaningKo": "한국어 뜻",
                            "exampleEn": "해당 표현이 들어간 새로운 예문"
                            }
                        ]
                        }
                    ]
                    }
                    """
            logger.info("Calling Gemini for media analysis")
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt, audio_file],
            )

            response_text = response.text.strip()

            # Remove markdown code blocks
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            result = json.loads(response_text)

            # Basic validation
            if "analysis" not in result or "segments" not in result:
                raise ValueError("Incomplete Gemini response")

            return result

        except Exception as e:
            logger.error("Error in Gemini media analysis: %s", e)
            raise

    def analyze_transcript(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze transcript segments and generate daily lesson content.

        Args:
            segments: List of transcript segments with start, end, text

        Returns:
            List of daily lesson items
        """
        try:
            # Prepare input JSON
            input_data = {"segments": segments}
            input_json = json.dumps(input_data, indent=2)

            # Create prompt
            prompt = f"""Analyze the following transcript segments and create a daily lesson JSON structure.

Input transcript segments:
{input_json}

Requirements:
1. Create a JSON array called "dailyLesson"
2. Each item must have:
   - startSec: float (start time in seconds)
   - endSec: float (end time in seconds)
   - sentence: string (the sentence from the transcript)
   - items: array of objects, each with:
     - term: string (key word or phrase)
     - meaningKo: string (Korean meaning)
     - exampleEn: string (example sentence in English)

3. Extract important vocabulary and phrases from each segment
4. Ensure startSec and endSec match the segment timings
5. Return ONLY valid JSON, no markdown or code blocks

Output format:
{{
  "dailyLesson": [
    {{
      "startSec": 0.0,
      "endSec": 5.2,
      "sentence": "Hello, how are you?",
      "items": [
        {{
          "term": "how are you",
          "meaningKo": "어떻게 지내세요?",
          "exampleEn": "How are you doing today?"
        }}
      ]
    }}
  ]
}}"""

            # Call Gemini API
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # Parse JSON response
            result = json.loads(response_text)
            daily_lesson = result.get("dailyLesson", [])

            # Validate structure
            for item in daily_lesson:
                if "startSec" not in item or "endSec" not in item:
                    raise ValueError("Missing startSec or endSec in daily lesson item")
                if "sentence" not in item:
                    raise ValueError("Missing sentence in daily lesson item")
                if "items" not in item:
                    item["items"] = []

            logger.info("Generated %d daily lesson items", len(daily_lesson))
            return daily_lesson

        except json.JSONDecodeError as e:
            logger.error("Error parsing Gemini JSON response: %s", e)
            logger.error("Response text: %s", response_text[:500])
            raise ValueError(f"Invalid JSON response from Gemini: {e}") from e
        except Exception as e:
            logger.error("Error calling Gemini API: %s", e)
            raise
