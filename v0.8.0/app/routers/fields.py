# app/routers/fields.py — CRUD полей с поддержкой переходов состояния

from pydoc import text
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles
from app.models import MapTypeEnum, RoleEnum,Person
from app.schemas import (
    BoundaryPointOut, FieldCreate, FieldListItem, FieldOut, FieldUpdate, OkResponse,
    FieldStatusIn, FieldStatusOut,
)
from app.services.field_service import FieldService
from app.dependencies import require_field_access



router = APIRouter(prefix="/fields", tags=["Поля (карты) с системой состояний"])

# Зависимости для авторизации
_any  = Depends(get_current_person)
_mgr  = Depends(require_roles(RoleEnum.manager))


@router.get("/", response_model=List[FieldListItem], dependencies=[_any])
async def list_fields(
    map_type: Optional[MapTypeEnum] = Query(None, description="Фильтр по типу карты (health/irrigation)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Список всех полей с их текущими статусами.
    Агроном может фильтровать по map_type=health, менеджер — по irrigation.
    """
    svc = FieldService(db)
    if map_type:
        return await svc.list_by_type(map_type)
    return await svc.list_all()


@router.post("/", response_model=FieldOut, status_code=201, dependencies=[_mgr])
async def create_field(body: FieldCreate, db: AsyncSession = Depends(get_db)):
    """
    Создать новое поле с граничными точками.
    Начальный статус: preparation (подготовка земли).
    """
    return await FieldService(db).create(body)


_field_access = Depends(require_field_access())

@router.get("/{field_id}", response_model=FieldOut)
async def get_field(
    field_id: int,
    current: Person = _field_access,   # ← теперь проверка
    db: AsyncSession = Depends(get_db),
    ):
    """
    Получить поле по ID с метаданными, граничными точками и текущим статусом.
    """
    field = await FieldService(db).get(field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return field


@router.patch("/{field_id}", response_model=FieldOut, dependencies=[_mgr])
async def update_field(field_id: int, body: FieldUpdate, db: AsyncSession = Depends(get_db)):
    """
    Обновить метаданные поля (имя, площадь, описание).
    НЕ используйте для смены статуса — используйте /transition endpoint.
    """
    field = await FieldService(db).update(field_id, body)
    if not field:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return field


@router.delete("/{field_id}", response_model=OkResponse, dependencies=[_mgr])
async def delete_field(field_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить поле."""
    ok = await FieldService(db).delete(field_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return OkResponse(message="Поле удалено")


@router.get("/{field_id}/boundary", response_model=List[BoundaryPointOut], dependencies=[_any])
async def get_boundary(field_id: int, db: AsyncSession = Depends(get_db)):
    """
    Точки границы поля (контур полигона).
    Используется для отрисовки на карте.
    """
    return await FieldService(db).get_boundary(field_id)


# ── НОВОЕ: управление состояниями ──

@router.get("/{field_id}/status", response_model=FieldStatusOut, dependencies=[_any])
async def get_field_status(field_id: int, db: AsyncSession = Depends(get_db)):
    """
    Получить текущий статус поля и доступные переходы.
    
    Returns:
        {
            'field_id': ...,
            'current_status': 'monitoring',
            'status_changed_at': '2026-04-10T14:30:00',
            'status_reason': 'Посев завершен',
            'available_transitions': ['harvesting', 'disease']
        }
    
    Если поле в статусе disease, также возвращает 'recovery_sequence'.
    """
    status_info = await FieldService(db).get_current_status(field_id)
    if not status_info:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return status_info


@router.post("/{field_id}/transition", response_model=FieldOut, dependencies=[_mgr])
async def transition_field_status(
    field_id: int,
    body: FieldStatusIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Смена статуса поля.
    
    Допустимые переходы определены в FieldStateTransitionValidator.
    
    Ошибки:
    - 404: поле не найдено
    - 409: переход не разрешён (нарушены правила state machine)
    
    Пример запроса:
    {
        'new_status': 'sowing',
        'reason': 'Посев завершен, начинаем мониторинг'
    }
    """
    svc = FieldService(db)
    field, error = await svc.transition_status(field_id, body)
    
    if field is None:
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        else:
            # Переход не разрешён → 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error
            )
    
    return field


@router.get("/{field_id}/status-info", dependencies=[_any])
async def get_field_status_info(field_id: int, db: AsyncSession = Depends(get_db)):
    """
    Получить подробное описание текущего статуса поля.
    
    Returns:
        {
            'field_id': ...,
            'status': 'monitoring',
            'status_name': 'monitoring',
            'description': 'Мониторинг (рост пшеницы, сбор данных pH и влажности)',
            'changed_at': '2026-04-20T10:00:00',
            'reason': 'Посев завершен'
        }
    """
    info = await FieldService(db).get_status_description(field_id)
    if not info:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return info


# Добавить в конец файла app/routers/fields.py после существующих эндпоинтов

@router.get("/{field_id}/risk-map", dependencies=[_any])
async def get_field_risk_map(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    current: Person = Depends(get_current_person)
):
    """
    Возвращает геоданные поля с наложенными прогнозами рисков.
    Для каждого GPS-точки вычисляется риск засухи/болезни на основе последних прогнозов.
    """
    # 1. Получить границы поля
    svc = FieldService(db)
    boundary = await svc.get_boundary(field_id)
    # 2. Получить прогнозы
    query = text("""
        SELECT risk_type, probability
        FROM risk_predictions
        WHERE field_id = :field_id AND valid_until > datetime('now')
    """)
    result = await db.execute(query, {"field_id": field_id})
    risks = result.mappings().all()
    risk_dict = {row["risk_type"]: row["probability"] for row in risks}

    # 3. Получить важные GPS-точки (например, центроид)
    points_query = text("SELECT latitude, longitude FROM gps_points WHERE field_id = :field_id LIMIT 10")
    points_result = await db.execute(points_query, {"field_id": field_id})
    points = [{"lat": p.latitude, "lon": p.longitude} for p in points_result]

    return {
        "field_id": field_id,
        "boundary": [{"lat": b.latitude, "lon": b.longitude} for b in boundary],
        "risk_predictions": risk_dict,
        "sample_points": points
    }