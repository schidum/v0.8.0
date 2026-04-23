# app/routers/queries/tasks.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person
from app.schemas import TaskOut

router = APIRouter(prefix="/tasks", tags=["Queries — Tasks"])


@router.get("/")
async def list_tasks(
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Список всех заданий"""
    from app.services import TaskService
    tasks = await TaskService(db).list_all()
    return tasks