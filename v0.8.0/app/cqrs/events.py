# app/cqrs/events.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from app.models import RoleEnum, FieldStatusEnum


class DomainEvent(BaseModel):
    """Базовый класс для всех доменных событий"""
    event_id: str
    occurred_on: datetime
    event_type: str


class PersonCreated(DomainEvent):
    event_type: str = "PersonCreated"
    person_id: int
    full_name: str
    login: str
    roles: List[str]
    phone: Optional[str] = None
    qualification: Optional[str] = None


class PersonUpdated(DomainEvent):
    event_type: str = "PersonUpdated"
    person_id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[List[str]] = None


class FieldStatusChanged(DomainEvent):
    event_type: str = "FieldStatusChanged"
    field_id: int
    old_status: FieldStatusEnum
    new_status: FieldStatusEnum
    reason: Optional[str] = None
    changed_by_person_id: Optional[int] = None