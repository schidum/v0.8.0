# app/routers/auth.py — аутентификация (исправленная версия)

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import LoginRequest, TokenResponse
from app.services import AuthService, PersonService


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Простая версия без rate limiter для диагностики"""
    print(f"🔑 Попытка входа: login = {body.login}")

    person = await PersonService(db).authenticate(body.login, body.password)
    
    if not person:
        print("❌ Неверный логин или пароль")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

    token = AuthService.create_token(person.id, list(person.role_set))
    print(f"✅ Успешный вход: {person.login} (ID={person.id})")

    return TokenResponse(access_token=token)