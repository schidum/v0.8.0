# app/routers/commands/persons.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, require_web_app
from app.models import RoleEnum
from app.cqrs.commands.person_commands import CreatePersonCommand, UpdatePersonCommand
from app.cqrs.handlers.person_handler import PersonCommandHandler


router = APIRouter(prefix="/persons", tags=["Commands — Изменение"])

_web_app = Depends(require_web_app)
_manager = Depends(require_roles(RoleEnum.manager))


@router.post("/create", status_code=201, dependencies=[_web_app, _manager])
async def create_person(cmd: CreatePersonCommand, db: AsyncSession = Depends(get_db)):
    handler = PersonCommandHandler(db)
    try:
        person = await handler.create_person(cmd)
        return {"message": "Пользователь создан", "id": person.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{person_id}", dependencies=[_web_app, _manager])
async def update_person(person_id: int, cmd: UpdatePersonCommand, db: AsyncSession = Depends(get_db)):
    if cmd.person_id != person_id:
        raise HTTPException(status_code=400, detail="ID в пути и команде не совпадают")

    handler = PersonCommandHandler(db)
    person = await handler.update_person(cmd)
    if not person:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"message": "Пользователь обновлён", "id": person.id}