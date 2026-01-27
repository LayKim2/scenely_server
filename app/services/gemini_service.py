"""Service for Google Gemini API operations"""

import logging
import json
from typing import List, Dict, Any
import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for Google Gemini API"""
    
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')
    
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
            response = self.model.generate_content(prompt)
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
            
            logger.info(f"Generated {len(daily_lesson)} daily lesson items")
            return daily_lesson
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Gemini JSON response: {e}")
            logger.error(f"Response text: {response_text[:500]}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            raise
