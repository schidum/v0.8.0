# app/routers/commands/equipment.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, get_current_person
from app.models import RoleEnum, Person                    # ← добавлен
from app.schemas import EquipmentPositionUpdate
from app.services import EquipmentService

router = APIRouter(prefix="/equipment", tags=["Commands — Equipment"])


@router.patch("/{eq_id}/position")
async def update_equipment_position(
    eq_id: int,
    body: EquipmentPositionUpdate,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Обновление позиции техники"""
    if current.has_role(RoleEnum.driver):
        # Водитель может обновлять только свою технику
        if not any(eq.id == eq_id for eq in getattr(current, 'assigned_equipment', [])):
            raise HTTPException(status_code=403, detail="Вы можете обновлять только свою технику")

    service = EquipmentService(db)
    eq = await service.update_position(eq_id, body.latitude, body.longitude)

    if not eq:
        raise HTTPException(status_code=404, detail="Техника не найдена")

    return {"ok": True, "message": "Позиция техники обновлена"}