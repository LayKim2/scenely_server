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

    # Auth / JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Kakao OAuth
    KAKAO_REST_API_KEY: Optional[str] = None
    KAKAO_CLIENT_SECRET: Optional[str] = None
    KAKAO_REDIRECT_URI: Optional[str] = None

    # Naver OAuth (reserved for future use)
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None
    NAVER_REDIRECT_URI: Optional[str] = None

    # Google OAuth (reserved for future use)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # Optional limits
    MAX_VIDEO_MINUTES: int = 60
    MAX_FILE_SIZE_MB: int = 500
    YOUTUBE_RATE_LIMIT_PER_DAY: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
