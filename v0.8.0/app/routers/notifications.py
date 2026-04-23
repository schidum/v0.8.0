# app/routers/notifications.py

from typing import List          # ← добавить эту строку
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, get_current_person
from app.models import RoleEnum, Person
from app.schemas import NotificationCreate, NotificationOut
from app.tasks.notifications import send_notification_task

router = APIRouter(prefix="/notifications", tags=["Уведомления"])

_mgr = Depends(require_roles(RoleEnum.manager))


@router.post("/", status_code=202)   # 202 Accepted — важно для фоновых задач
async def send_notification(
    body: NotificationCreate,
    current: Person = Depends(get_current_person)
):
    """Отправить уведомление через Celery (асинхронно)"""
    try:
        # Отправляем задачу в Celery
        task = send_notification_task.delay(body.dict())

        return {
            "status": "accepted",
            "message": "Уведомление поставлено в очередь",
            "task_id": task.id,
            "person_id": body.person_id,
            "level": body.level.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка постановки задачи: {str(e)}")


@router.get("/my", response_model=List[NotificationOut])
async def my_notifications(
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Получить свои непрочитанные уведомления"""
    from app.services import NotificationService
    return await NotificationService(db).get_unread(current.id)