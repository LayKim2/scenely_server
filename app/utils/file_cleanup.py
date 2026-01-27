"""Utilities for file cleanup operations"""

import os
import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def cleanup_file(file_path: Union[str, Path]) -> bool:
    """
    Safely delete a file if it exists.
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        True if file was deleted or didn't exist, False on error
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return True
        return True
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        return False


def cleanup_temp_files(job_id: str, base_dir: str = "/tmp") -> None:
    """
    Clean up temporary files for a job.
    
    Args:
        job_id: Job ID to clean up files for
        base_dir: Base directory for temp files (default: /tmp)
    """
    temp_dir = Path(base_dir)
    pattern = f"*{job_id}*"
    
    for file_path in temp_dir.glob(pattern):
        cleanup_file(file_path)
