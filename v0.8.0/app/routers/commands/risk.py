# =============================================================================
# ФАЙЛ: app/routers/commands/risk.py – запуск фоновой задачи прогнозирования
# =============================================================================
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.dependencies import require_roles
from app.models import RoleEnum
from app.tasks.risk_prediction import generate_risk_predictions
from app.schemas import ReportTaskResponse

router = APIRouter(prefix="/commands/risk", tags=["Commands - Risk Prediction"])

class RunRiskPredictionRequest(BaseModel):
    field_ids: Optional[List[int]] = None

@router.post("/predict", response_model=ReportTaskResponse)
async def run_risk_prediction(
    req: RunRiskPredictionRequest,
    current = Depends(require_roles(RoleEnum.manager, RoleEnum.agronomist))
):
    """Запуск фонового прогнозирования рисков для полей (Celery). Возвращает task_id."""
    task = generate_risk_predictions.delay(req.field_ids)
    return ReportTaskResponse(task_id=task.id, status="PENDING")