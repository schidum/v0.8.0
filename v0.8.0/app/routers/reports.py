# app/routers/reports.py
from fastapi import APIRouter, Depends
from app.dependencies import require_roles
from app.models import RoleEnum
from app.schemas import ReportGenerateRequest, ReportTaskResponse
from app.tasks.reports import generate_completed_tasks_report

router = APIRouter(prefix="/reports", tags=["Отчёты (Celery)"])


@router.post("/generate", response_model=ReportTaskResponse)
async def generate_report(
    body: ReportGenerateRequest = None,
    current = Depends(require_roles(RoleEnum.manager))
):
    if body is None:
        body = ReportGenerateRequest()

    task = generate_completed_tasks_report.delay(body.model_dump() if body else {})
    return ReportTaskResponse(task_id=task.id, status="PENDING")