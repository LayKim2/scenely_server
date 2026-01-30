"""Service for audio extraction using FFmpeg"""

import subprocess
import logging
import os
from pathlib import Path
from typing import Optional
import yt_dlp

from app.config import settings

logger = logging.getLogger(__name__)


def extract_audio_from_youtube(youtube_url: str, output_path: str) -> str:
    """
    Extract audio from YouTube URL using yt-dlp and convert to FLAC.
    
    Args:
        youtube_url: YouTube video URL
        output_path: Output file path (should end with .flac)
        
    Returns:
        Path to the extracted audio file
    """
    try:
        # Use yt-dlp to download audio
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(output_path).replace('.flac', '.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'flac',
                'preferredquality': '192',
            }],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        
        # Find the generated file
        base_path = Path(output_path).with_suffix('')
        flac_path = base_path.with_suffix('.flac')
        
        if not flac_path.exists():
            # Try to find any flac file in the directory
            parent = flac_path.parent
            flac_files = list(parent.glob('*.flac'))
            if flac_files:
                flac_path = flac_files[0]
            else:
                raise FileNotFoundError(f"FLAC file not found at {flac_path}")
        
        # Convert to required format if needed
        final_path = Path(output_path)
        if flac_path != final_path:
            convert_audio_to_flac(str(flac_path), str(final_path))
            cleanup_file(flac_path)
        else:
            # Ensure correct format
            convert_audio_to_flac(str(flac_path), str(final_path))
        
        return str(final_path)
        
    except Exception as e:
        logger.error(f"Error extracting audio from YouTube: {e}")
        raise


def extract_audio_from_file(input_path: str, output_path: str) -> str:
    """
    Extract audio from video file and convert to FLAC.
    
    Args:
        input_path: Path to input video file
        output_path: Path to output FLAC file
        
    Returns:
        Path to the extracted audio file
    """
    try:
        convert_audio_to_flac(input_path, output_path)
        return output_path
    except Exception as e:
        logger.error(f"Error extracting audio from file: {e}")
        raise


def convert_audio_to_flac(input_path: str, output_path: str) -> None:
    """
    Convert audio to FLAC format with required settings.
    
    Args:
        input_path: Path to input audio/video file
        output_path: Path to output FLAC file
    """
    # FFmpeg command: -vn (no video), -ac 1 (mono), -ar 16000 (16kHz), -c:a flac
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-vn',  # No video
        '-ac', '1',  # Mono
        '-ar', '16000',  # 16kHz sample rate
        '-c:a', 'flac',  # FLAC codec
        '-y',  # Overwrite output file
        output_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Audio converted successfully: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr}")


def cut_audio_segment(
    input_path: str, 
    output_path: str, 
    start_sec: float, 
    end_sec: float,
    format: str = "flac"
) -> str:
    """
    Cut a segment from audio file.
    
    Args:
        input_path: Path to input audio file
        output_path: Path to output file
        start_sec: Start time in seconds
        end_sec: End time in seconds
        format: Output format (flac or mp3)
        
    Returns:
        Path to the output file
    """
    duration = end_sec - start_sec
    
    cmd = [
        'ffmpeg',
        '-ss', str(start_sec),
        '-t', str(duration),
        '-i', input_path,
        '-y'
    ]
    
    if format == "flac":
        cmd.extend([
            '-ac', '1',
            '-ar', '16000',
            '-c:a', 'flac',
        ])
    elif format == "mp3":
        cmd.extend([
            '-c:a', 'libmp3lame',
            '-q:a', '2',  # High quality
        ])
    
    cmd.append(output_path)
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Segment cut successfully: {output_path} ({start_sec}s - {end_sec}s)")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error cutting segment: {e.stderr}")
        raise RuntimeError(f"FFmpeg segment cut failed: {e.stderr}")


def cleanup_file(file_path: str) -> None:
    """Clean up a file if it exists"""
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
    except Exception as e:
        logger.warning(f"Error cleaning up file {file_path}: {e}")
