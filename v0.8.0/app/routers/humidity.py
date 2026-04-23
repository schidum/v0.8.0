# app/routers/humidity.py — измерения влажности (с защитой доступа к полям)

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_person, 
    require_roles, 
    require_field_access   # ← Новая зависимость для защиты полей
)
from app.models import RoleEnum,Person
from app.schemas import HumidityMeasurementCreate, HumidityMeasurementOut, OkResponse
from app.services import HumidityMeasurementService

router = APIRouter(
    prefix="/measurements/humidity", 
    tags=["Измерения влажности"]
)

# Зависимости
_any          = Depends(get_current_person)
_chemist      = Depends(require_roles(RoleEnum.chemist))
_field_access = Depends(require_field_access())          # ← Защита доступа к полю


@router.post("/", 
             response_model=HumidityMeasurementOut, 
             status_code=201, 
             dependencies=[_chemist])
async def add_humidity(
    body: HumidityMeasurementCreate,
    current: Person = _field_access,          # ← Проверка доступа к полю
    db: AsyncSession = Depends(get_db),
):
    """
    Внести измерение влажности для GPS-точки.
    Только химик может добавлять измерения.
    Пользователь должен иметь доступ к полю (manager или chemist + health карта).
    """
    return await HumidityMeasurementService(db).add(body)


@router.get("/point/{point_id}", 
            response_model=List[HumidityMeasurementOut], 
            dependencies=[_any])
async def list_by_point(
    point_id: int, 
    current: Person = _any,                   # Здесь можно оставить _any (история точки)
    db: AsyncSession = Depends(get_db),
):
    """История измерений влажности для одной точки."""
    return await HumidityMeasurementService(db).list_by_point(point_id)


@router.get("/field/{field_id}/bbox", 
            response_model=List[HumidityMeasurementOut])
async def humidity_in_bbox(
    field_id: int,
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    current: Person = _field_access,          # ← Защита: только разрешённые пользователи
    db: AsyncSession = Depends(get_db),
):
    """
    Влажность в области просмотра (bounding box).
    getMeasurementsInBBox из диаграммы менеджера (тип humidity).
    
    Доступ:
    - Manager — всегда
    - Chemist / Agronomist — только если поле типа 'health'
    """
    return await HumidityMeasurementService(db).list_in_bbox(
        field_id, min_lat, max_lat, min_lon, max_lon
    )


@router.delete("/{measurement_id}", 
              response_model=OkResponse, 
              dependencies=[_chemist])
async def delete_humidity(
    measurement_id: int,
    current: Person = _any,                   # Для удаления по measurement_id — оставляем chemist
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить измерение влажности.
    Только химик может удалять свои измерения.
    """
    ok = await HumidityMeasurementService(db).delete(measurement_id)
    if not ok:
        raise HTTPException(
            status_code=404, 
            detail="Измерение влажности не найдено"
        )
    return OkResponse(message="Измерение влажности удалено")