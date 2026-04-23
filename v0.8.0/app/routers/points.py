# app/routers/points.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles, require_field_access   # ← измени импорт
from app.models import RoleEnum,Person
from app.schemas import GpsPointCreate, GpsPointOut, OkResponse
from app.services import GpsPointService
from typing import List

router = APIRouter(prefix="/fields/{field_id}/points", tags=["GPS-точки"])

_any          = Depends(get_current_person)
_chemist      = Depends(require_roles(RoleEnum.chemist))
_field_access = Depends(require_field_access())          # ← НОВОЕ


@router.get("/", response_model=List[GpsPointOut])
async def list_points(
    field_id: int,
    current: Person = _field_access,        # ← применяем защиту
    db: AsyncSession = Depends(get_db),
):
    """Все GPS-точки поля."""
    return await GpsPointService(db).list_by_field(field_id)


@router.get("/bbox", response_model=List[GpsPointOut])
async def points_in_bbox(
    field_id: int,
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    current: Person = _field_access,        # ← применяем защиту
    db: AsyncSession = Depends(get_db),
):
    """Точки в пределах bounding box."""
    return await GpsPointService(db).list_in_bbox(field_id, min_lat, max_lat, min_lon, max_lon)


@router.post("/find-or-create", response_model=GpsPointOut, dependencies=[_chemist])
async def find_or_create_point(
    field_id: int,
    body: GpsPointCreate,
    current: Person = _field_access,        # ← применяем защиту
    db: AsyncSession = Depends(get_db),
):
    """Найти или создать точку."""
    try:
        point, _ = await GpsPointService(db).create_or_get(
            field_id, body.latitude, body.longitude
        )
        return point
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{point_id}", response_model=OkResponse, dependencies=[_chemist])
async def delete_point(
    field_id: int,
    point_id: int,
    current: Person = _field_access,        # ← применяем защиту
    db: AsyncSession = Depends(get_db),
):
    ok = await GpsPointService(db).delete(point_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Точка не найдена")
    return OkResponse(message="Точка удалена")