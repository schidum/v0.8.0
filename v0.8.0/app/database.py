# app/database.py — настройка SQLAlchemy async-движка и сессий

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Асинхронный движок SQLite
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,          # True — выводить SQL в лог (удобно при отладке)
    connect_args={"check_same_thread": False},
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""
    pass


async def get_db():
    """
    FastAPI dependency — предоставляет сессию на время одного запроса.
    Гарантирует закрытие сессии даже при исключении.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Создать все таблицы (используется при старте приложения)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
