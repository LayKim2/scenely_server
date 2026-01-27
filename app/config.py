"""Application configuration and environment variables"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Database
    DATABASE_URL: str = "sqlite:///./scenely.db"

    # Google Cloud
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GCS_BUCKET_TMP_AUDIO: str = "scenely-tmp-audio"

    # Gemini API
    GEMINI_API_KEY: str = "AIzaSyCNRkAdlIhT6slKaZjYKON98dUA_ob7pY0"

    # Optional limits
    MAX_VIDEO_MINUTES: int = 60
    MAX_FILE_SIZE_MB: int = 500
    YOUTUBE_RATE_LIMIT_PER_DAY: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
