# app/dependencies.py — FastAPI зависимости: аутентификация и авторизация по ролям

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from app.schemas import LoginRequest

from fastapi import Request

from collections import defaultdict
import time
import logging
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import Person, RoleEnum, MapTypeEnum
from app.repositories import FieldRepository, PersonRepository
from app.services import AuthService

_bearer = HTTPBearer()


async def get_current_person(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Person:
    """
    Декодировать Bearer JWT → вернуть Person с загруженными ролями.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Невалидный или истёкший токен",
    )
    try:
        payload = AuthService.decode_token(credentials.credentials)
        person_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError) as e:
        logger.debug(f"Token validation failed: {e}")
        raise exc

    try:
        person = await PersonRepository(db).get_by_id(person_id)
    except SQLAlchemyError as e:
        logger.error(f"Database error while fetching user: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable",
        )
    
    if not person or not person.is_active:
        logger.warning(f"User {person_id} not found or inactive")
        raise exc
    return person


def require_roles(*roles: RoleEnum):
    """
    Dependency-фабрика: пропустить запрос, если у пользователя есть
    ХОТЯ БЫ ОДНА из перечисленных ролей.

    Пример:
        Depends(require_roles(RoleEnum.manager))
        Depends(require_roles(RoleEnum.chemist, RoleEnum.agronomist))

    Пользователь с ролями [manager, agronomist] пройдёт проверку
    require_roles(agronomist) — достаточно одного совпадения.
    """
    async def _check(current: Person = Depends(get_current_person)) -> Person:
        if not current.has_any_role(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Требуется одна из ролей: {[r.value for r in roles]}. "
                    f"Ваши роли: {[r.value for r in current.role_set]}."
                ),
            )
        return current
    return _check



# In-memory rate limiter (для dev). В проде → Redis + slowapi
_login_attempts = defaultdict(list)


def rate_limit_login(max_attempts: int = 10, window_seconds: int = 60):
    """
    Рейт-лимит для логина: максимум N попыток за M секунд по логину + IP
    """
    async def _limiter(request: Request, body):
        # Ключ = login + IP (защита от брутфорса с разных IP)
        client_ip = request.client.host if request.client else "unknown"
        key = f"{body.login.lower()}:{client_ip}"

        now = time.time()

        # Очищаем старые попытки
        _login_attempts[key] = [
            ts for ts in _login_attempts[key] if now - ts < window_seconds
        ]

        if len(_login_attempts[key]) >= max_attempts:
            raise HTTPException(
                status_code=429,
                detail=f"Слишком много попыток входа. Попробуйте через {window_seconds//60} минут."
            )

        _login_attempts[key].append(now)
        return body

    return _limiter

def require_field_access():
    """Manager — всё. Agronomist/Chemist — только health-карты."""
    async def _check(
        field_id: int,
        current: Person = Depends(get_current_person),
        db: AsyncSession = Depends(get_db),
    ) -> Person:
        field = await FieldRepository(db).get_by_id(field_id)
        if not field:
            raise HTTPException(status_code=404, detail="Поле не найдено")

        if current.has_role(RoleEnum.manager):
            return current

        if (field.map_type == MapTypeEnum.health and
                current.has_any_role(RoleEnum.agronomist, RoleEnum.chemist)):
            return current

        raise HTTPException(
            status_code=403,
            detail=f"Нет доступа к полю типа {field.map_type.value}. Требуется роль manager."
        )
    return _check


def require_web_app():
    """Доступ к управлению пользователями — ТОЛЬКО через веб-приложение"""
    async def _check(request: Request):
        if request.headers.get("X-App-Client") != "web":
            raise HTTPException(
                status_code=403,
                detail="Управление пользователями разрешено только через официальное веб-приложение"
            )
        return True
    return _check