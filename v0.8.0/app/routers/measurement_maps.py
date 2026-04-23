# app/routers/measurement_maps.py — карты измерений (дата + тип)

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles
from app.models import RoleEnum,Person
from app.schemas import MeasurementMapCreate, MeasurementMapOut, OkResponse
from app.services import MeasurementMapService

from app.dependencies import get_current_person, require_roles, require_field_access

_field_access = Depends(require_field_access())

router = APIRouter(prefix="/measurement-maps", tags=["Карты измерений"])

_any     = Depends(get_current_person)
_chemist = Depends(require_roles(RoleEnum.chemist))


@router.get("/field/{field_id}", response_model=List[MeasurementMapOut], dependencies=[_any])
async def list_by_field(field_id: int,current: Person = _field_access, db: AsyncSession = Depends(get_db)):
    """Все карты измерений поля (по убыванию даты)."""
    return await MeasurementMapService(db).list_by_field(field_id)


@router.post("/", response_model=MeasurementMapOut, status_code=201, dependencies=[_chemist])
async def create_map(body: MeasurementMapCreate,current: Person = _field_access, db: AsyncSession = Depends(get_db)):
    """Создать новую карту измерений (химик начинает серию замеров)."""
    return await MeasurementMapService(db).create(body)


@router.get("/{map_id}", response_model=MeasurementMapOut, dependencies=[_any])
async def get_map(map_id: int, db: AsyncSession = Depends(get_db)):
    mmap = await MeasurementMapService(db).get(map_id)
    if not mmap:
        raise HTTPException(status_code=404, detail="Карта измерений не найдена")
    return mmap


@router.delete("/{map_id}", response_model=OkResponse, dependencies=[_chemist])
async def delete_map(map_id: int, db: AsyncSession = Depends(get_db)):
    ok = await MeasurementMapService(db).delete(map_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Карта измерений не найдена")
    return OkResponse(message="Карта измерений удалена")
