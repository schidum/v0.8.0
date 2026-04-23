# app/routers/persons.py — CRUD пользователей (только менеджер)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, require_web_app
from app.models import RoleEnum
from app.schemas import PersonCreate, PersonUpdate
from app.services import PersonService


router = APIRouter(prefix="/persons", tags=["Персонал"])

# Зависимости
_web_app = Depends(require_web_app())   # FIX: фабрика — нужны скобки
_manager = Depends(require_roles(RoleEnum.manager))


@router.get("/", dependencies=[_web_app, _manager])
async def list_persons(db: AsyncSession = Depends(get_db)):
    """Список всех пользователей"""
    persons = await PersonService(db).list_all()
    return [
        {
            "id": p.id,
            "full_name": p.full_name,
            "login": p.login,
            "roles": [pr.role.value for pr in p.roles],
            "phone": p.phone,
            "qualification": p.qualification,
            "is_active": p.is_active,
        }
        for p in persons
    ]


@router.post("/", status_code=201, dependencies=[_web_app, _manager])
async def create_person(body: PersonCreate, db: AsyncSession = Depends(get_db)):
    """Создать пользователя"""
    try:
        person = await PersonService(db).create(body)
        return {
            "id": person.id,
            "full_name": person.full_name,
            "login": person.login,
            "roles": [pr.role.value for pr in person.roles],
            "phone": person.phone,
            "qualification": person.qualification,
            "is_active": person.is_active,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/{person_id}", dependencies=[_web_app, _manager])
async def get_person(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await PersonService(db).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {
        "id": person.id,
        "full_name": person.full_name,
        "login": person.login,
        "roles": [pr.role.value for pr in person.roles],
        "phone": person.phone,
        "qualification": person.qualification,
        "is_active": person.is_active,
    }


@router.patch("/{person_id}", dependencies=[_web_app, _manager])
async def update_person(
    person_id: int, body: PersonUpdate, db: AsyncSession = Depends(get_db)
):
    person = await PersonService(db).update(person_id, body)
    if not person:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {
        "id": person.id,
        "full_name": person.full_name,
        "login": person.login,
        "roles": [pr.role.value for pr in person.roles],
        "phone": person.phone,
        "qualification": person.qualification,
        "is_active": person.is_active,
    }


@router.delete("/{person_id}", dependencies=[_web_app, _manager])
async def delete_person(person_id: int, db: AsyncSession = Depends(get_db)):
    person = await PersonService(db).get(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if person.login == "admin":
        raise HTTPException(status_code=403, detail="Нельзя удалить суперадминистратора")

    await PersonService(db).delete(person_id)
    return {"ok": True, "message": "Пользователь успешно удалён"}