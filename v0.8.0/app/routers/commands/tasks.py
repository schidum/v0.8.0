# app/routers/commands/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, get_current_person
from app.models import RoleEnum, Person, Task
from app.schemas import TaskCreateCommand, TaskMarkCompletedCommand
from app.services import TaskService

router = APIRouter(prefix="/tasks", tags=["Commands — Tasks"])

_mgr = Depends(require_roles(RoleEnum.manager))


@router.post("/create", dependencies=[_mgr])
async def create_task(
    cmd: TaskCreateCommand,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    task = Task(
        title=cmd.title,
        description=cmd.description,
        assigned_by_id=current.id,
        assigned_to_id=cmd.assigned_to_id,
        equipment_id=cmd.equipment_id,
        field_id=cmd.field_id,
        due_date=cmd.due_date,
    )

    service = TaskService(db)
    created_task = await service.create(task)

    return {"ok": True, "task_id": created_task.id}


@router.patch("/{task_id}/complete")
async def mark_task_completed(
    task_id: int,
    cmd: TaskMarkCompletedCommand,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    service = TaskService(db)
    task = await service.mark_completed(task_id, cmd.result_comment)
    if not task:
        raise HTTPException(404, "Задание не найдено")

    return {"ok": True, "task_id": task.id, "status": task.status.value}