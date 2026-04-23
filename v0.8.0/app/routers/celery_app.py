# app/celery_app.py
from celery import Celery
from app.config import settings

# Redis как брокер и бэкенд
celery_app = Celery(
    "agro_tasks",
    broker="redis://127.0.0.1:6379/0",
    backend="redis://127.0.0.1:6379/1",
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,        # 5 минут максимум
    task_soft_time_limit=240,
)

print("✅ Celery initialized with Redis")