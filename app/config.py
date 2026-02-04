"""Application configuration and environment variables"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Database (PostgreSQL)
    DATABASE_URL: str = "postgresql://scenely:scenely@localhost:5432/scenely"

    # AWS (S3 + Transcribe)
    AWS_REGION: str = "ap-northeast-2"  # Seoul
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET: Optional[str] = None
    CLOUDFRONT_DOMAIN: Optional[str] = None  # optional, for public read URLs

    # Gemini API
    GEMINI_API_KEY: Optional[str] = None

    # STT: Deepgram (primary)
    DEEPGRAM_API_KEY: Optional[str] = None

    # Google Cloud STT (legacy, optional)
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None  # Path to service account JSON
    GCS_BUCKET: Optional[str] = None  # Bucket for STT audio (gs://GCS_BUCKET/...)

    # Auth / JWT
    JWT_SECRET_KEY: Optional[str] = None 
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Kakao OAuth (SDK 방식: redirect_uri는 kakao{NATIVE_APP_KEY}://oauth 고정)
    KAKAO_REST_API_KEY: Optional[str] = None
    KAKAO_NATIVE_APP_KEY: Optional[str] = None  # SDK용 네이티브 앱 키 (redirect_uri 생성에 사용)
    KAKAO_CLIENT_SECRET: Optional[str] = None

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
