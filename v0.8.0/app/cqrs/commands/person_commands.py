# app/cqrs/commands/person_commands.py
from pydantic import BaseModel
from typing import List, Optional

from app.models import RoleEnum


class CreatePersonCommand(BaseModel):
    full_name: str
    login: str
    password: str
    roles: List[RoleEnum]
    phone: Optional[str] = None
    qualification: Optional[str] = None


class UpdatePersonCommand(BaseModel):
    person_id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[str] = None
    is_active: Optional[bool] = None
    roles: Optional[List[RoleEnum]] = None