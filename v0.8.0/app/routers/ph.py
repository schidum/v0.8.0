# app/routers/ph.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles, require_field_access  # ← измени импорт
from app.models import RoleEnum,Person
from app.schemas import OkResponse, PhMeasurementCreate, PhMeasurementOut
from app.services import PhMeasurementService

router = APIRouter(prefix="/measurements/ph", tags=["Измерения pH"])

_any          = Depends(get_current_person)
_chemist      = Depends(require_roles(RoleEnum.chemist))
_field_access = Depends(require_field_access())          # ← НОВОЕ


@router.post("/", response_model=PhMeasurementOut, status_code=201, dependencies=[_chemist])
async def add_ph(
    body: PhMeasurementCreate,
    current: Person = _field_access,        # ← защита по полю
    db: AsyncSession = Depends(get_db),
):
    return await PhMeasurementService(db).add(body)


@router.get("/point/{point_id}", response_model=List[PhMeasurementOut])
async def list_by_point(
    point_id: int, 
    current: Person = _any,                 # здесь пока оставляем _any (можно усилить позже)
    db: AsyncSession = Depends(get_db),
):
    return await PhMeasurementService(db).list_by_point(point_id)


@router.get("/field/{field_id}/bbox", response_model=List[PhMeasurementOut])
async def ph_in_bbox(
    field_id: int,
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    current: Person = _field_access,        # ← применяем защиту
    db: AsyncSession = Depends(get_db),
):
    return await PhMeasurementService(db).list_in_bbox(
        field_id, min_lat, max_lat, min_lon, max_lon
    )


@router.delete("/{measurement_id}", response_model=OkResponse, dependencies=[_chemist])
async def delete_ph(
    measurement_id: int,
    # Для delete по measurement_id сложно быстро получить field_id.
    # Поэтому оставляем только chemist (или можно улучшить позже)
    current: Person = _any,
    db: AsyncSession = Depends(get_db),
):
    ok = await PhMeasurementService(db).delete(measurement_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Измерение не найдено")
    return OkResponse(message="Измерение pH удалено")