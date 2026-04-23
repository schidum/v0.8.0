# =============================================================================
# ФАЙЛ: app/routers/commands/maintenance.py – команды для обслуживания
# =============================================================================
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_person, require_roles
from app.models import RoleEnum, Person
from app.schemas import MaintenanceCreate, MaintenanceOut
from app.services import MaintenanceService

router = APIRouter(prefix="/commands/maintenance", tags=["Commands - Maintenance"])

@router.post("/", response_model=MaintenanceOut, status_code=201)
async def create_maintenance(
    dto: MaintenanceCreate,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Создать запись о ТО/ремонте (только manager)"""
    if not current.has_role(RoleEnum.manager):
        raise HTTPException(403, "Only manager can create maintenance records")

    service = MaintenanceService(db)
    # performed_by_id – текущий пользователь, owner_id – тоже текущий (для ownership)
    maintenance = await service.create(dto, performed_by_id=current.id, owner_id=current.id)
    return maintenance

@router.delete("/{maintenance_id}")
async def delete_maintenance(
    maintenance_id: int,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    if not current.has_role(RoleEnum.manager):
        raise HTTPException(403, "Only manager can delete maintenance")
    service = MaintenanceService(db)
    ok = await service.delete(maintenance_id)
    if not ok:
        raise HTTPException(404, "Maintenance record not found")
    return {"ok": True}