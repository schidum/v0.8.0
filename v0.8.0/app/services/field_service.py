# app/services/field_service.py — сервис для работы с полями (совместим с Python 3.8)

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Field, FieldBoundary, FieldStatusEnum
from app.repositories import FieldRepository
from app.schemas import FieldCreate, FieldUpdate, FieldStatusIn
from app.services.field_state_transition import FieldStateTransitionValidator


class FieldService:
    """Сервис работы с полями, включая управление состояниями."""

    def __init__(self, db: AsyncSession):
        self.repo = FieldRepository(db)
        self.db = db

    async def create(self, dto: FieldCreate) -> Field:
        """Создать новое поле (начальное состояние: preparation)."""
        field = Field(
            name        = dto.name,
            map_type    = dto.map_type,
            area        = dto.area,
            perimeter   = dto.perimeter,
            description = dto.description,
            status      = FieldStatusEnum.preparation,
        )
        for bp in dto.boundary_points:
            field.boundary_points.append(
                FieldBoundary(
                    order_idx=bp.order_idx,
                    latitude=bp.latitude,
                    longitude=bp.longitude
                )
            )
        return await self.repo.create(field)

    async def get(self, field_id: int) -> Optional[Field]:
        """Получить поле по ID."""
        return await self.repo.get_by_id(field_id)

    async def list_all(self):
        """Список всех полей."""
        return await self.repo.list_all()

    async def list_by_type(self, map_type):
        """Список полей по типу карты."""
        return await self.repo.list_by_type(map_type)

    async def update(self, field_id: int, dto: FieldUpdate) -> Optional[Field]:
        """Обновить метаданные поля."""
        field = await self.repo.get_by_id(field_id)
        if not field:
            return None
        for attr, val in dto.model_dump(exclude_none=True).items():
            setattr(field, attr, val)
        return await self.repo.update(field)

    async def delete(self, field_id: int) -> bool:
        """Удалить поле."""
        field = await self.repo.get_by_id(field_id)
        if not field:
            return False
        await self.repo.delete(field)
        return True

    async def get_boundary(self, field_id: int):
        """Получить граничные точки поля."""
        return await self.repo.get_boundary_points(field_id)

    # ── Управление состояниями Field ───────────────────────────────────────

    async def transition_status(
        self, field_id: int, transition_dto: FieldStatusIn
    ) -> Tuple[Optional[Field], Optional[str]]:
        """
        Смена статуса поля.
        Возвращает (field, error_message)
        """
        field = await self.repo.get_by_id(field_id)
        if not field:
            return None, "Field not found (404)"

        current_status = field.status
        new_status = transition_dto.new_status

        is_allowed, error_msg = FieldStateTransitionValidator.can_transition(
            current_status, new_status
        )

        if not is_allowed:
            return None, error_msg

        field.status = new_status
        field.status_changed_at = datetime.now(timezone.utc)
        field.status_reason = transition_dto.reason

        await self.repo.update(field)
        
        from app.websocket.manager import manager
        await manager.broadcast({
            "type": "field_status_changed",
            "field_id": field.id,
            "old_status": current_status.value,
            "new_status": new_status.value,
            "reason": transition_dto.reason,
            "changed_at": datetime.now(timezone.utc).isoformat()
        })
                
        
        
        return field, None

    async def get_current_status(self, field_id: int):
        """
        Получить текущий статус поля и доступные переходы.
        """
        field = await self.repo.get_by_id(field_id)
        if not field:
            return None

        available = FieldStateTransitionValidator.get_available_transitions(field.status)
        
        result = {
            'field_id': field.id,
            'current_status': field.status,
            'status_changed_at': field.status_changed_at,
            'status_reason': field.status_reason,
            'available_transitions': list(available),
        }

        if field.status == FieldStatusEnum.disease:
            result['recovery_sequence'] = FieldStateTransitionValidator.get_recovery_sequence()

        return result

    async def get_status_description(self, field_id: int):
        """
        Получить подробное описание текущего статуса поля.
        """
        field = await self.repo.get_by_id(field_id)
        if not field:
            return None

        return {
            'field_id': field.id,
            'status': field.status,
            'status_name': field.status.value,
            'description': FieldStateTransitionValidator.get_status_description(field.status),
            'changed_at': field.status_changed_at,
            'reason': field.status_reason,
        }