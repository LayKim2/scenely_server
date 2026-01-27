"""Service for converting transcript words to segments"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def words_to_segments(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert word list to sentence segments.
    
    Simple rule-based segmentation: split on punctuation (. ! ?)
    
    Args:
        words: List of word dicts with word, startSeconds, endSeconds
        
    Returns:
        List of segment dicts with start, end, text
    """
    if not words:
        return []
    
    segments = []
    current_segment = []
    current_start = None
    
    for word_data in words:
        word = word_data.get("word", "").strip()
        start = word_data.get("startSeconds", 0.0)
        end = word_data.get("endSeconds", 0.0)
        
        if current_start is None:
            current_start = start
        
        current_segment.append(word)
        
        # Check if word ends with sentence-ending punctuation
        if word and word[-1] in ".!?":
            segment_text = " ".join(current_segment)
            segments.append({
                "start": current_start,
                "end": end,
                "text": segment_text
            })
            current_segment = []
            current_start = None
    
    # Add remaining words as final segment
    if current_segment:
        last_word = words[-1]
        segment_text = " ".join(current_segment)
        segments.append({
            "start": current_start or last_word.get("startSeconds", 0.0),
            "end": last_word.get("endSeconds", 0.0),
            "text": segment_text
        })
    
    logger.info(f"Converted {len(words)} words to {len(segments)} segments")
    return segments
