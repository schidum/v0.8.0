# app/routers/queries/equipment.py — CQRS Query side для техники

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person
from app.models import Person                     # ← ИСПРАВЛЕНИЕ: добавлен импорт
from app.schemas import EquipmentOut

router = APIRouter(prefix="/equipment", tags=["Queries — Equipment"])


@router.get("/")
async def list_equipment(
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Список всей техники (водитель видит только свою)"""
    from app.services import EquipmentService      # импорт внутри функции — защита от циклических импортов

    equipment_list = await EquipmentService(db).list_all()

    # Ограничение видимости для роли driver
    if current.has_role("driver"):                 # можно использовать .has_role(RoleEnum.driver)
        equipment_list = [eq for eq in equipment_list if eq.assigned_driver_id == current.id]

    return equipment_list