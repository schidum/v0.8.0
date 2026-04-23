# app/routers/queries/persons.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, require_web_app
from app.models import RoleEnum
from app.cqrs.queries.person_queries import PersonQuery


router = APIRouter(prefix="/persons", tags=["Queries — Чтение"])

_web_app = Depends(require_web_app)
_manager = Depends(require_roles(RoleEnum.manager))


@router.get("/", dependencies=[_web_app, _manager])
async def list_persons(db: AsyncSession = Depends(get_db)):
    query = PersonQuery(db)
    return await query.list_all()


@router.get("/{person_id}", dependencies=[_web_app, _manager])
async def get_person(person_id: int, db: AsyncSession = Depends(get_db)):
    query = PersonQuery(db)
    person = await query.get_by_id(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return person