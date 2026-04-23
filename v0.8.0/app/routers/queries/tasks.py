# app/routers/tasks.py — мониторинг статуса Celery-задач
from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult
from app.celery_app import celery_app
from app.schemas import TaskStatusResponse

router = APIRouter(prefix="/tasks", tags=["Задачи (Celery)"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Получить полный статус любой Celery-задачи по её ID.
    
    Возвращает:
    - task_id
    - status (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED)
    - result (если задача завершена успешно)
    - error (если задача упала)
    - traceback (при ошибке)
    
    Пример ответа при успехе:
    {
        "task_id": "abc123-...",
        "status": "SUCCESS",
        "result": {
            "notification_id": 42,
            "person_id": 5,
            "level": "normal",
            "status": "success"
        },
        "error": null,
        "traceback": null
    }
    """
    # Получаем объект результата из Celery (использует rpc backend)
    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.status,           # PENDING / STARTED / SUCCESS / FAILURE ...
        "result": None,
        "error": None,
        "traceback": None,
    }

    if task_result.status == "SUCCESS":
        response["result"] = task_result.result

    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.result)
        response["traceback"] = task_result.traceback

    elif task_result.status == "RETRY":
        response["error"] = "Задача в процессе повторной попытки"

    return response