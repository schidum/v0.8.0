# app/tasks/notifications.py
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services import NotificationService
from app.schemas import NotificationCreate
import asyncio


@shared_task(bind=True, max_retries=3, default_retry_delay=60, ignore_result=False)
def send_notification_task(self, notification_dict: dict):
    """
    Фоновая задача Celery — отправка уведомления.
    
    Важно:
    - ignore_result=False  → результат сохраняется в backend (rpc://)
    - bind=True            → доступ к self для retry
    - Возвращает dict с notification_id при успехе
    """
    try:
        notification = NotificationCreate(**notification_dict)

        async def _send():
            async with AsyncSessionLocal() as db:
                service = NotificationService(db)
                result = await service.send(notification)
                print(f"Celery (RabbitMQ): Уведомление отправлено | ID={result.id}")
                # Возвращаем результат, который будет доступен через AsyncResult
                return {
                    "notification_id": result.id,
                    "person_id": notification.person_id,
                    "level": notification.level.value,
                    "status": "success"
                }

        # Запускаем async-код и возвращаем результат
        return asyncio.run(_send())

    except Exception as exc:
        print(f"❌ Celery (RabbitMQ): Ошибка отправки уведомления: {exc}")
        # Автоматический retry (до 3 раз)
        raise self.retry(exc=exc)