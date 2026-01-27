"""Utilities for parsing and normalizing timestamps"""

from typing import Union


def parse_timestamp_to_seconds(timestamp: Union[str, dict, float]) -> float:
    """
    Parse various timestamp formats to float seconds.
    
    Supports:
    - String: "12.300s" or "12.3"
    - Dict: {"seconds": 12, "nanos": 300000000}
    - Float: 12.3
    """
    if isinstance(timestamp, float):
        return timestamp
    
    if isinstance(timestamp, int):
        return float(timestamp)
    
    if isinstance(timestamp, dict):
        seconds = timestamp.get("seconds", 0)
        nanos = timestamp.get("nanos", 0)
        return float(seconds) + (float(nanos) / 1_000_000_000)
    
    if isinstance(timestamp, str):
        # Remove 's' suffix if present
        timestamp = timestamp.rstrip("s")
        try:
            return float(timestamp)
        except ValueError:
            raise ValueError(f"Unable to parse timestamp: {timestamp}")
    
    raise ValueError(f"Unsupported timestamp type: {type(timestamp)}")
