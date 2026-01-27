"""Celery application configuration"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "scenely_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600 * 2,  # 2 hours
    task_soft_time_limit=3600 * 1.5,  # 1.5 hours
)
