# app/celery_app.py
from celery import Celery
from app.config import settings
import logging

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agro_tasks",
    broker=settings.RABBITMQ_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,

    # Настройки специально для RabbitMQ 3.6.6 + Windows 7 32-bit
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_pool_limit=5,
    worker_prefetch_multiplier=1,
)

logger.info("✅ Celery initialized with RabbitMQ 3.6.6 (Windows 7 32-bit)")
logger.info(f"   Broker : {settings.RABBITMQ_URL}")
logger.info(f"   Backend: {settings.CELERY_RESULT_BACKEND}")