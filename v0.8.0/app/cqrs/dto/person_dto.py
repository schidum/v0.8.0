# app/cqrs/dto/person_dto.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class PersonReadDTO(BaseModel):
    """Денормализованная Read Model для чтения пользователей"""
    id: int
    full_name: str
    login: str
    roles: List[str]
    phone: Optional[str] = None
    qualification: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True