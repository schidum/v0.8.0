# app/tasks/notifications.py
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services import NotificationService
from app.schemas import NotificationCreate
from app.tasks.async_runner import run_async_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, ignore_result=False)
def send_notification_task(self, notification_dict: dict):
    """
    Фоновая задача Celery — отправка уведомления.
    
    Важно:
    - ignore_result=False  → результат сохраняется в backend (rpc://)
    - bind=True            → доступ к self для retry
    - Возвращает dict с notification_id при успехе
    - Использует безопасный async runner для предотвращения конфликтов event loop
    """
    try:
        notification = NotificationCreate(**notification_dict)

        async def _send():
            async with AsyncSessionLocal() as db:
                service = NotificationService(db)
                result = await service.send(notification)
                logger.info(f"Notification sent successfully | ID={result.id}")
                # Возвращаем результат, который будет доступен через AsyncResult
                return {
                    "notification_id": result.id,
                    "person_id": notification.person_id,
                    "level": notification.level.value,
                    "status": "success"
                }

        # Запускаем async-код безопасно
        return run_async_task(_send())

    except Exception as exc:
        logger.error(f"Error sending notification: {exc}", exc_info=True)
        # Автоматический retry (до 3 раз)
        raise self.retry(exc=exc)