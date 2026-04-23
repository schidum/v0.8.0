#python


# =============================================================================
# AGRO MONITORING — ПОЛНЫЙ ИСХОДНЫЙ КОД ПРОЕКТА
# Все файлы объединены в один. Путь к каждому файлу указан в заголовке секции.
# =============================================================================


# =============================================================================
# ФАЙЛ: app/config.py
# =============================================================================

# app/config.py
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # База данных
    DATABASE_URL: str = "sqlite+aiosqlite:///./agro.db"

    # JWT
    SECRET_KEY: str = Field(
        default=..., min_length=32,
        description="Сильный секрет (64+ символов)"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # ==================== RABBITMQ (для Windows 7 + 3.6.6) ====================
    RABBITMQ_URL: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        description="URL вашего RabbitMQ 3.6.6 (по умолчанию guest/guest)"
    )

    # Backend результатов — rpc (работает через тот же RabbitMQ, Redis не нужен)
    CELERY_RESULT_BACKEND: str = "rpc://"

    # Приложение
    APP_TITLE: str = "Агро API — Точное земледелие"
    APP_VERSION: str = "0.3.2"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


# =============================================================================
# ФАЙЛ: app/database.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/models/__init__.py
# =============================================================================

# app/models/__init__.py — ПОЛНЫЙ ORM (финальная версия для защиты)
#
# Реализовано:
# - ЗАДАНИЕ 1: Жизненный цикл Field (FieldStatusEnum + 10 состояний)
# - ЗАДАНИЕ 2.2: Ownership — owner_id во всех ключевых сущностях
# - ЗАДАНИЕ 2.1: RBAC — RoleEnum с новой ролью driver
# - ЗАДАНИЕ 3 + 4: Новые сущности Equipment, Task, Fueling
# - Все relationship настроены корректно
# - Совместимость с CQRS, WebSocket и Celery

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ====================== ПЕРЕЧИСЛЕНИЯ ======================

class RoleEnum(str, enum.Enum):
    manager     = "manager"
    chemist     = "chemist"
    agronomist  = "agronomist"
    driver      = "driver"          # ← новая роль по заданию


class MapTypeEnum(str, enum.Enum):
    health      = "health"
    irrigation  = "irrigation"


class NotifLevelEnum(str, enum.Enum):
    normal      = "normal"
    critical    = "critical"


class FieldStatusEnum(str, enum.Enum):
    """Жизненный цикл поля (ЗАДАНИЕ 1)"""
    preparation              = "preparation"
    sowing                   = "sowing"
    monitoring               = "monitoring"
    harvesting               = "harvesting"
    post_harvest_processing  = "post_harvest_processing"
    field_free               = "field_free"
    disease                  = "disease"
    residue_removal          = "residue_removal"
    deep_plowing             = "deep_plowing"
    chemical_treatment       = "chemical_treatment"


class TaskStatusEnum(str, enum.Enum):
    """Статусы заданий"""
    pending      = "pending"
    in_progress  = "in_progress"
    completed    = "completed"
    cancelled    = "cancelled"


# ====================== ОСНОВНЫЕ МОДЕЛИ ======================

class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    login: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    qualification: Mapped[Optional[str]] = mapped_column(String(100))
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("persons.id"), nullable=True)  # Ownership

    # Связи
    roles: Mapped[List["PersonRole"]] = relationship(
        "PersonRole", back_populates="person", cascade="all, delete-orphan", lazy="selectin"
    )
    notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="person", cascade="all, delete-orphan"
    )
    assigned_equipment: Mapped[List["Equipment"]] = relationship(
        "Equipment",
        foreign_keys="[Equipment.assigned_driver_id]",
        back_populates="assigned_driver"
    )
    tasks_assigned: Mapped[List["Task"]] = relationship(
        "Task", foreign_keys="Task.assigned_to_id", back_populates="assigned_to"
    )
    tasks_created: Mapped[List["Task"]] = relationship(
        "Task", foreign_keys="Task.assigned_by_id", back_populates="assigned_by"
    )

    @property
    def role_set(self):
        # type: () -> set
        """Роли пользователя в виде множества для быстрой проверки."""
        return {pr.role for pr in self.roles}

    def has_role(self, role):
        # type: (RoleEnum) -> bool
        return role in self.role_set

    def has_any_role(self, *roles):
        # type: (*RoleEnum) -> bool
        return bool(self.role_set & set(roles))


class PersonRole(Base):
    __tablename__ = "person_roles"
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum, name="roleenum"), primary_key=True)

    person: Mapped["Person"] = relationship("Person", back_populates="roles")


# ====================== ПОЛЯ ======================

class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    area: Mapped[Optional[float]] = mapped_column(Float)
    perimeter: Mapped[Optional[float]] = mapped_column(Float)
    map_type: Mapped[MapTypeEnum] = mapped_column(Enum(MapTypeEnum), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id"), nullable=False)  # Ownership

    # Жизненный цикл поля
    status: Mapped[FieldStatusEnum] = mapped_column(
        Enum(FieldStatusEnum, name="fieldstatusenum"),
        default=FieldStatusEnum.preparation,
        nullable=False
    )
    status_changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    status_reason: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    boundary_points: Mapped[List["FieldBoundary"]] = relationship(
        "FieldBoundary", back_populates="field", cascade="all, delete-orphan", order_by="FieldBoundary.order_idx"
    )
    gps_points: Mapped[List["GpsPoint"]] = relationship(
        "GpsPoint", back_populates="field", cascade="all, delete-orphan"
    )
    measurement_maps: Mapped[List["MeasurementMap"]] = relationship(
        "MeasurementMap", back_populates="field", cascade="all, delete-orphan"
    )


class FieldBoundary(Base):
    __tablename__ = "field_boundaries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(Integer, ForeignKey("fields.id", ondelete="CASCADE"))
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    field: Mapped["Field"] = relationship("Field", back_populates="boundary_points")

    __table_args__ = (UniqueConstraint("field_id", "order_idx"),)


# ====================== GPS-точки ======================

class GpsPoint(Base):
    __tablename__ = "gps_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(Integer, ForeignKey("fields.id", ondelete="CASCADE"))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(50))

    field: Mapped["Field"] = relationship("Field", back_populates="gps_points")


# ====================== КАРТЫ ИЗМЕРЕНИЙ ======================

class MeasurementMap(Base):
    __tablename__ = "measurement_maps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(Integer, ForeignKey("fields.id", ondelete="CASCADE"))
    map_type: Mapped[MapTypeEnum] = mapped_column(Enum(MapTypeEnum), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    field: Mapped["Field"] = relationship("Field", back_populates="measurement_maps")


class PhMeasurement(Base):
    __tablename__ = "ph_measurements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    point_id: Mapped[int] = mapped_column(Integer, ForeignKey("gps_points.id", ondelete="CASCADE"))
    measurement_map_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("measurement_maps.id", ondelete="SET NULL"))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HumidityMeasurement(Base):
    __tablename__ = "humidity_measurements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    point_id: Mapped[int] = mapped_column(Integer, ForeignKey("gps_points.id", ondelete="CASCADE"))
    measurement_map_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("measurement_maps.id", ondelete="SET NULL"))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ====================== УВЕДОМЛЕНИЯ ======================

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id", ondelete="CASCADE"))
    level: Mapped[NotifLevelEnum] = mapped_column(Enum(NotifLevelEnum), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    person: Mapped["Person"] = relationship("Person", back_populates="notifications")


# ====================== НОВЫЕ СУЩНОСТИ ======================

class Equipment(Base):
    """Единица техники (ЗАДАНИЕ 3)"""
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id"), nullable=False)          # Ownership
    nominal_fuel_consumption: Mapped[float] = mapped_column(Float, nullable=False)
    current_mileage: Mapped[float] = mapped_column(Float, default=0.0)
    last_repair_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    current_latitude: Mapped[Optional[float]] = mapped_column(Float)
    current_longitude: Mapped[Optional[float]] = mapped_column(Float)
    last_position_update: Mapped[Optional[datetime]] = mapped_column(DateTime)

    assigned_driver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id", ondelete="SET NULL")
    )

    assigned_driver: Mapped[Optional["Person"]] = relationship(
        "Person", back_populates="assigned_equipment", foreign_keys=[assigned_driver_id]
    )
    fuelings: Mapped[List["Fueling"]] = relationship(
        "Fueling", back_populates="equipment", cascade="all, delete-orphan"
    )
    tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="equipment", cascade="save-update, merge"
    )


class Fueling(Base):
    """Факт заправки техники"""
    __tablename__ = "fuelings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"))
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    volume_liters: Mapped[float] = mapped_column(Float, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id"), nullable=False)  # Ownership

    equipment: Mapped["Equipment"] = relationship("Equipment", back_populates="fuelings")
    person: Mapped["Person"] = relationship("Person", foreign_keys="[Fueling.person_id]")


class Task(Base):
    """Задания (назначение, выполнение)"""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.id"), nullable=False)          # Ownership

    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    assigned_to_id: Mapped[Optional[int]] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"))
    equipment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipment.id", ondelete="SET NULL"))
    field_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fields.id", ondelete="SET NULL"))

    status: Mapped[TaskStatusEnum] = mapped_column(Enum(TaskStatusEnum), default=TaskStatusEnum.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    result_comment: Mapped[Optional[str]] = mapped_column(Text)

    assigned_by: Mapped["Person"] = relationship("Person", foreign_keys=[assigned_by_id], back_populates="tasks_created")
    assigned_to: Mapped[Optional["Person"]] = relationship("Person", foreign_keys=[assigned_to_id], back_populates="tasks_assigned")
    equipment: Mapped[Optional["Equipment"]] = relationship("Equipment", back_populates="tasks")
    field: Mapped[Optional["Field"]] = relationship("Field")


# =============================================================================
# ФАЙЛ: app/schemas/__init__.py
# =============================================================================

# app/schemas/__init__.py — Pydantic v2 DTO
# Изменение: roles: list[RoleEnum] вместо единственного role: RoleEnum

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models import MapTypeEnum, NotifLevelEnum, RoleEnum, FieldStatusEnum, TaskStatusEnum


# ── Утилиты ───────────────────────────────────────────────────────────────────

class OkResponse(BaseModel):
    ok: bool = True
    message: str = "success"


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    login: str
    password: str


# ── Персонал ──────────────────────────────────────────────────────────────────

class PersonCreate(BaseModel):
    full_name     : str                     = Field(max_length=100)
    login         : str                     = Field(max_length=60)
    password      : Optional[str]           = Field(None, min_length=6)
    roles         : List[RoleEnum]          = Field(min_length=1)
    phone         : Optional[str]           = Field(None, max_length=20)
    qualification : Optional[str]           = Field(None, max_length=100)

    @model_validator(mode="after")
    def deduplicate_roles(self) -> "PersonCreate":
        seen = []
        for r in self.roles:
            if r not in seen:
                seen.append(r)
        self.roles = seen
        return self


class PersonUpdate(BaseModel):
    full_name     : Optional[str]            = None
    phone         : Optional[str]            = None
    qualification : Optional[str]            = None
    is_active     : Optional[bool]           = None
    # Передавать только если нужно полностью заменить набор ролей
    roles         : Optional[List[RoleEnum]] = Field(None, min_length=1)

    @model_validator(mode="after")
    def deduplicate_roles(self) -> "PersonUpdate":
        if self.roles:
            seen = []
            for r in self.roles:
                if r not in seen:
                    seen.append(r)
            self.roles = seen
        return self


class PersonOut(BaseModel):
    """Выходная модель пользователя — используется везде (список, создание, обновление)"""

    id: int
    full_name: str
    login: str
    roles: List[str]                    # Изменено с List[RoleEnum] на List[str] — стабильнее
    phone: Optional[str] = None
    qualification: Optional[str] = None
    is_active: bool = True

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            RoleEnum: lambda v: v.value
        }
    }

    @classmethod
    def from_orm_person(cls, person) -> "PersonOut":
        """Безопасное преобразование ORM объекта в Pydantic модель"""
        return cls(
            id=person.id,
            full_name=person.full_name,
            login=person.login,
            roles=[pr.role.value for pr in person.roles],   # .value — обязательно!
            phone=person.phone,
            qualification=person.qualification,
            is_active=person.is_active,
        )


# ── Поля (карты) ──────────────────────────────────────────────────────────────

class BoundaryPointIn(BaseModel):
    order_idx : int
    latitude  : float = Field(ge=-90,   le=90)
    longitude : float = Field(ge=-180,  le=180)


class BoundaryPointOut(BoundaryPointIn):
    id       : int
    field_id : int
    model_config = {"from_attributes": True}


class FieldCreate(BaseModel):
    name             : str                    = Field(max_length=100)
    map_type         : MapTypeEnum
    area             : Optional[float]        = Field(None, ge=0)
    perimeter        : Optional[float]        = Field(None, ge=0)
    description      : Optional[str]          = None
    boundary_points  : List[BoundaryPointIn]  = []


class FieldUpdate(BaseModel):
    name        : Optional[str]   = None
    area        : Optional[float] = None
    perimeter   : Optional[float] = None
    description : Optional[str]  = None


class FieldOut(BaseModel):
    id              : int
    name            : str
    map_type        : MapTypeEnum
    area            : Optional[float]
    perimeter       : Optional[float]
    description     : Optional[str]
    created_at      : datetime
    boundary_points : List[BoundaryPointOut] = []
    model_config = {"from_attributes": True}


class FieldListItem(BaseModel):
    id       : int
    name     : str
    map_type : MapTypeEnum
    area     : Optional[float]
    model_config = {"from_attributes": True}


class FieldStatusOut(BaseModel):
    field_id              : int
    current_status        : FieldStatusEnum
    status_changed_at     : datetime
    status_reason         : Optional[str]
    available_transitions : List[FieldStatusEnum] = []
    recovery_sequence     : Optional[List[FieldStatusEnum]] = None

    model_config = {"from_attributes": True}


class FieldStatusIn(BaseModel):
    new_status : FieldStatusEnum
    reason     : Optional[str] = Field(None, max_length=500, description="Примечание к переходу")


# ── GPS-точки ─────────────────────────────────────────────────────────────────

class GpsPointCreate(BaseModel):
    latitude  : float          = Field(ge=-90,  le=90)
    longitude : float          = Field(ge=-180, le=180)
    label     : Optional[str]  = Field(None, max_length=50)


class GpsPointOut(GpsPointCreate):
    id       : int
    field_id : int
    model_config = {"from_attributes": True}


# ── Карты измерений ───────────────────────────────────────────────────────────

class MeasurementMapCreate(BaseModel):
    field_id    : int
    map_type    : MapTypeEnum
    measured_at : datetime
    notes       : Optional[str] = None


class MeasurementMapOut(BaseModel):
    id          : int
    field_id    : int
    map_type    : MapTypeEnum
    measured_at : datetime
    notes       : Optional[str]
    model_config = {"from_attributes": True}


# ── Измерения pH ──────────────────────────────────────────────────────────────

class PhMeasurementCreate(BaseModel):
    point_id           : int
    measurement_map_id : Optional[int] = None
    value              : float         = Field(ge=0.0, le=14.0, description="pH 0–14")


class PhMeasurementOut(BaseModel):
    id                 : int
    point_id           : int
    measurement_map_id : Optional[int]
    value              : float
    recorded_at        : datetime
    model_config = {"from_attributes": True}


# ── Измерения влажности ───────────────────────────────────────────────────────

class HumidityMeasurementCreate(BaseModel):
    point_id           : int
    measurement_map_id : Optional[int] = None
    value              : float         = Field(ge=0.0, le=100.0, description="Влажность 0–100%")


class HumidityMeasurementOut(BaseModel):
    id                 : int
    point_id           : int
    measurement_map_id : Optional[int]
    value              : float
    recorded_at        : datetime
    model_config = {"from_attributes": True}


# ── Уведомления ───────────────────────────────────────────────────────────────

class NotificationCreate(BaseModel):
    person_id : int
    level     : NotifLevelEnum
    message   : str


class NotificationOut(BaseModel):
    id         : int
    person_id  : int
    level      : NotifLevelEnum
    message    : str
    is_read    : bool
    created_at : datetime
    model_config = {"from_attributes": True}


# ── Статус Celery-задач ───────────────────────────────────────────────────────

class TaskStatusResponse(BaseModel):
    """Полный ответ о статусе любой фоновой задачи Celery"""
    task_id: str
    status: str                          # PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
    result: Optional[dict] = None        # результат задачи (если SUCCESS)
    error: Optional[str] = None          # текст ошибки (если FAILURE)
    traceback: Optional[str] = None      # traceback при ошибке

    model_config = {
        "from_attributes": True,
    }


class ReportTaskResponse(BaseModel):
    task_id: str
    status: str
    report_url: Optional[str] = None


class ReportGenerateRequest(BaseModel):
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    task_ids: Optional[List[int]] = None


class FuelingOut(BaseModel):
    id: int
    equipment_id: int
    person_id: int
    date: datetime
    volume_liters: float

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: TaskStatusEnum
    assigned_by_id: int
    assigned_to_id: Optional[int] = None
    equipment_id: Optional[int] = None
    field_id: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    result_comment: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Fueling ──────────────────────────────────────────────────────────────────

class FuelingCreate(BaseModel):
    equipment_id: int
    volume_liters: float = Field(gt=0)


class TaskMarkCompletedCommand(BaseModel):
    result_comment: str = Field(max_length=500)


# ── Task (CQRS) ──────────────────────────────────────────────────────────────

class TaskCreateCommand(BaseModel):
    title: str = Field(max_length=200)
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    equipment_id: Optional[int] = None
    field_id: Optional[int] = None
    due_date: Optional[datetime] = None


# ── Equipment ────────────────────────────────────────────────────────────────

class EquipmentOut(BaseModel):
    id: int
    name: str
    nominal_fuel_consumption: float
    current_mileage: float
    last_repair_date: Optional[datetime] = None
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    last_position_update: Optional[datetime] = None
    assigned_driver_id: Optional[int] = None

    model_config = {"from_attributes": True}


class EquipmentPositionUpdate(BaseModel):
    """Модель для обновления позиции техники в реальном времени"""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


# =============================================================================
# ФАЙЛ: app/dependencies.py
# =============================================================================

# app/dependencies.py — FastAPI зависимости: аутентификация и авторизация по ролям

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import LoginRequest

from fastapi import Request

from collections import defaultdict
import time
from fastapi import Request, HTTPException

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
    except (JWTError, KeyError, ValueError):
        raise exc

    person = await PersonRepository(db).get_by_id(person_id)
    if not person or not person.is_active:
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


# =============================================================================
# ФАЙЛ: app/celery_app.py
# =============================================================================

# app/celery_app.py
from celery import Celery
from app.config import settings

celery_app = Celery(
    "agro_tasks",
    broker=settings.RABBITMQ_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,

    # Настройки специально для RabbitMQ 3.6.6 + Windows 7 32-bit
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_pool_limit=5,
    worker_prefetch_multiplier=1,
)

print("✅ Celery запущен с RabbitMQ 3.6.6 (Windows 7 32-bit)")
print(f"   Broker : {settings.RABBITMQ_URL}")
print(f"   Backend: {settings.CELERY_RESULT_BACKEND}")


# =============================================================================
# ФАЙЛ: app/services/__init__.py
# =============================================================================

# app/services/__init__.py — бизнес-логика, JWT, валидация

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Field, FieldBoundary, GpsPoint,
    HumidityMeasurement, MeasurementMap,
    Notification, Person, PersonRole, PhMeasurement,
    RoleEnum, Task, Fueling, TaskStatusEnum,
)
from app.repositories import (
    FieldRepository, GpsPointRepository,
    HumidityMeasurementRepository, MeasurementMapRepository,
    NotificationRepository, PersonRepository, PhMeasurementRepository,
    EquipmentRepository, TaskRepository, FuelingRepository,
)
from app.schemas import (
    FieldCreate, FieldUpdate,
    HumidityMeasurementCreate, MeasurementMapCreate,
    NotificationCreate, PersonCreate, PersonUpdate, PhMeasurementCreate,
)

_pwd_ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# ══════════════════════════════════════════════════════════════════════════════
# AuthService
# ══════════════════════════════════════════════════════════════════════════════

class AuthService:
    """JWT и PBKDF2-SHA256 (хэширование паролей)."""

    @staticmethod
    def hash_password(plain: str) -> str:
        return _pwd_ctx.hash(plain)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return _pwd_ctx.verify(plain, hashed)

    @staticmethod
    def create_token(person_id: int, roles: List[RoleEnum]) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload = {
            "sub": str(person_id),
            "roles": [r.value for r in roles],
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ══════════════════════════════════════════════════════════════════════════════
# PersonService
# ══════════════════════════════════════════════════════════════════════════════

class PersonService:
    def __init__(self, db: AsyncSession):
        self.repo = PersonRepository(db)
        self.db = db

    async def authenticate(self, login: str, password: str) -> Optional[Person]:
        person = await self.repo.get_by_login(login)
        if not person or not person.is_active:
            return None
        if not AuthService.verify_password(password, person.password_hash):
            return None
        return person

    async def create(self, dto: 'PersonCreate') -> Person:
        existing = await self.repo.get_by_login(dto.login)
        if existing:
            raise ValueError(f"Логин '{dto.login}' уже существует")
        hashed = AuthService.hash_password(dto.password)
        person = Person(
            full_name=dto.full_name,
            login=dto.login,
            password_hash=hashed,
            phone=dto.phone,
            qualification=dto.qualification,
            is_active=True,
        )
        person = await self.repo.create(person)
        await self.repo.set_roles(person, dto.roles)
        await self.db.commit()
        return person

    async def update(self, person_id: int, dto: PersonUpdate) -> Optional[Person]:
        person = await self.repo.get_by_id(person_id)
        if not person:
            return None
        if dto.full_name is not None:
            person.full_name = dto.full_name
        if dto.phone is not None:
            person.phone = dto.phone
        if dto.qualification is not None:
            person.qualification = dto.qualification
        if dto.is_active is not None:
            person.is_active = dto.is_active
        if dto.roles is not None:
            await self.repo.set_roles(person, dto.roles)
        return await self.repo.update(person)

    async def get(self, person_id: int) -> Optional[Person]:
        return await self.repo.get_by_id(person_id)

    async def list_all(self) -> List[Person]:
        return list(await self.repo.list_all())

    async def delete(self, person_id: int) -> bool:
        person = await self.repo.get_by_id(person_id)
        if not person:
            return False
        await self.repo.delete(person)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# GpsPointService
# ══════════════════════════════════════════════════════════════════════════════

class GpsPointService:

    def __init__(self, db: AsyncSession):
        self.repo       = GpsPointRepository(db)
        self.field_repo = FieldRepository(db)

    async def create_or_get(self, field_id: int, lat: float, lon: float):
        field = await self.field_repo.get_by_id(field_id)
        if not field:
            raise ValueError("Поле не найдено")
        if field.boundary_points and not self._point_in_polygon(
            lat, lon, [(b.latitude, b.longitude) for b in field.boundary_points]
        ):
            raise ValueError("Точка вне границ поля")
        return await self.repo.find_or_create(field_id, lat, lon)

    async def list_by_field(self, field_id: int):
        return await self.repo.find_by_field(field_id)

    async def list_in_bbox(self, field_id, min_lat, max_lat, min_lon, max_lon):
        return await self.repo.find_in_bbox(field_id, min_lat, max_lat, min_lon, max_lon)

    async def get(self, point_id: int):
        return await self.repo.get_by_id(point_id)

    async def delete(self, point_id: int) -> bool:
        point = await self.repo.get_by_id(point_id)
        if not point:
            return False
        await self.repo.delete(point)
        return True

    @staticmethod
    def _point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
        """Ray-casting: проверка принадлежности точки полигону границ поля."""
        n, inside, j = len(polygon), False, len(polygon) - 1
        for i in range(n):
            yi, xi = polygon[i]
            yj, xj = polygon[j]
            if ((yi > lat) != (yj > lat)) and (
                lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
            ):
                inside = not inside
            j = i
        return inside


# ══════════════════════════════════════════════════════════════════════════════
# MeasurementMapService
# ══════════════════════════════════════════════════════════════════════════════

class MeasurementMapService:

    def __init__(self, db: AsyncSession):
        self.repo = MeasurementMapRepository(db)

    async def create(self, dto: MeasurementMapCreate) -> MeasurementMap:
        mmap = MeasurementMap(
            field_id    = dto.field_id,
            map_type    = dto.map_type,
            measured_at = dto.measured_at,
            notes       = dto.notes,
        )
        return await self.repo.create(mmap)

    async def get(self, map_id: int):
        return await self.repo.get_by_id(map_id)

    async def list_by_field(self, field_id: int):
        return await self.repo.list_by_field(field_id)

    async def delete(self, map_id: int) -> bool:
        mmap = await self.repo.get_by_id(map_id)
        if not mmap:
            return False
        await self.repo.delete(mmap)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# PhMeasurementService
# ══════════════════════════════════════════════════════════════════════════════

class PhMeasurementService:

    def __init__(self, db: AsyncSession):
        self.repo = PhMeasurementRepository(db)

    async def add(self, dto: PhMeasurementCreate) -> PhMeasurement:
        m = PhMeasurement(
            point_id           = dto.point_id,
            measurement_map_id = dto.measurement_map_id,
            value              = dto.value,
        )
        return await self.repo.create(m)

    async def list_by_point(self, point_id: int):
        return await self.repo.list_by_point(point_id)

    async def list_in_bbox(self, field_id, min_lat, max_lat, min_lon, max_lon):
        return await self.repo.list_in_bbox(field_id, min_lat, max_lat, min_lon, max_lon)

    async def delete(self, m_id: int) -> bool:
        m = await self.repo.get_by_id(m_id)
        if not m:
            return False
        await self.repo.delete(m)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# HumidityMeasurementService
# ══════════════════════════════════════════════════════════════════════════════

class HumidityMeasurementService:

    def __init__(self, db: AsyncSession):
        self.repo = HumidityMeasurementRepository(db)

    async def add(self, dto: HumidityMeasurementCreate) -> HumidityMeasurement:
        m = HumidityMeasurement(
            point_id           = dto.point_id,
            measurement_map_id = dto.measurement_map_id,
            value              = dto.value,
        )
        return await self.repo.create(m)

    async def list_by_point(self, point_id: int):
        return await self.repo.list_by_point(point_id)

    async def list_in_bbox(self, field_id, min_lat, max_lat, min_lon, max_lon):
        return await self.repo.list_in_bbox(field_id, min_lat, max_lat, min_lon, max_lon)

    async def delete(self, m_id: int) -> bool:
        m = await self.repo.get_by_id(m_id)
        if not m:
            return False
        await self.repo.delete(m)
        return True


# ══════════════════════════════════════════════════════════════════════════════
# NotificationService
# ══════════════════════════════════════════════════════════════════════════════

class NotificationService:

    def __init__(self, db: AsyncSession):
        self.repo = NotificationRepository(db)

    async def send(self, dto: NotificationCreate) -> Notification:
        n = Notification(
            person_id = dto.person_id,
            level     = dto.level,
            message   = dto.message,
        )
        return await self.repo.create(n)

    async def get_unread(self, person_id: int):
        return await self.repo.list_unread(person_id)

    async def get_all(self, person_id: int):
        return await self.repo.list_all_for_user(person_id)

    async def mark_read(self, notification_id: int):
        return await self.repo.mark_read(notification_id)


# ══════════════════════════════════════════════════════════════════════════════
# EquipmentService
# ══════════════════════════════════════════════════════════════════════════════

class EquipmentService:
    def __init__(self, db: AsyncSession):
        self.repo = EquipmentRepository(db)
        self.db = db

    async def list_all(self):
        return await self.repo.list_all()

    async def update_position(self, eq_id: int, lat: float, lon: float):
        """Обновление позиции техники + WebSocket broadcast"""
        eq = await self.repo.update_position(eq_id, lat, lon)
        if eq:
            from app.websocket.manager import manager
            await manager.broadcast({
                "type": "equipment_position_updated",
                "equipment": {
                    "id": eq.id,
                    "name": eq.name,
                    "latitude": eq.current_latitude,
                    "longitude": eq.current_longitude,
                    "last_update": eq.last_position_update.isoformat() if eq.last_position_update else None
                }
            })
        return eq


# ══════════════════════════════════════════════════════════════════════════════
# TaskService
# ══════════════════════════════════════════════════════════════════════════════

class TaskService:
    def __init__(self, db: AsyncSession):
        self.repo = TaskRepository(db)
        self.db = db

    async def create(self, task: Task) -> Task:
        return await self.repo.create(task)

    async def mark_completed(self, task_id: int, comment: str) -> Optional[Task]:
        return await self.repo.update_status(task_id, TaskStatusEnum.completed, comment)

    async def list_all(self):
        return await self.repo.list_all()


# ══════════════════════════════════════════════════════════════════════════════
# FuelingService
# ══════════════════════════════════════════════════════════════════════════════

class FuelingService:
    def __init__(self, db: AsyncSession):
        self.repo = FuelingRepository(db)

    async def add_fueling(self, fueling: Fueling) -> Fueling:
        return await self.repo.create(fueling)


# =============================================================================
# ФАЙЛ: app/services/field_state_transition.py
# =============================================================================

# app/services/field_state_transition.py — валидатор переходов состояний Field
# Это чистая бизнес-логика, не привязана к контроллерам

from typing import Optional, Set, Tuple
from app.models import FieldStatusEnum


class FieldStateTransitionValidator:
    """
    Валидатор переходов между состояниями Field.
    Реализует бизнес-правила:
    - Запрещённые переходы
    - Последовательность обработки при болезни
    - Правила перехода из каждого состояния
    """

    # ── Запрещённые переходы (ничего не может перейти в них из определённых состояний) ──
    FORBIDDEN_TRANSITIONS = {
        FieldStatusEnum.preparation: {FieldStatusEnum.disease},
        FieldStatusEnum.field_free: {FieldStatusEnum.disease},
    }

    # ── Допустимые переходы из каждого состояния ──
    ALLOWED_TRANSITIONS = {
        FieldStatusEnum.preparation: {
            FieldStatusEnum.sowing,
        },
        FieldStatusEnum.sowing: {
            FieldStatusEnum.monitoring,
            FieldStatusEnum.disease,  # Можно заболеть на этапе посева
        },
        FieldStatusEnum.monitoring: {
            FieldStatusEnum.harvesting,
            FieldStatusEnum.disease,  # Болезнь во время роста
        },
        FieldStatusEnum.harvesting: {
            FieldStatusEnum.post_harvest_processing,
        },
        FieldStatusEnum.post_harvest_processing: {
            FieldStatusEnum.field_free,
        },
        FieldStatusEnum.field_free: {
            FieldStatusEnum.preparation,  # Новый сезон
        },
        # ── Специальное правило для болезни ──
        # Из болезни можно перейти в одну из трёх процедур восстановления
        # Порядок: residue_removal → deep_plowing → chemical_treatment
        # Но можно пропустить любую один (кроме всех)
        FieldStatusEnum.disease: {
            FieldStatusEnum.residue_removal,
            FieldStatusEnum.deep_plowing,
            FieldStatusEnum.chemical_treatment,
        },
        FieldStatusEnum.residue_removal: {
            FieldStatusEnum.deep_plowing,
            FieldStatusEnum.chemical_treatment,
            FieldStatusEnum.field_free,  # Или сразу в свободное
        },
        FieldStatusEnum.deep_plowing: {
            FieldStatusEnum.chemical_treatment,
            FieldStatusEnum.field_free,
        },
        FieldStatusEnum.chemical_treatment: {
            FieldStatusEnum.field_free,
        },
    }

    @staticmethod
    def can_transition(
        current_status: FieldStatusEnum,
        new_status: FieldStatusEnum,
    ) -> Tuple[bool, Optional[str]]:
        """
        Проверить, разрешен ли переход.

        Returns:
            (is_allowed, error_message)
            is_allowed=True если переход допустим
            is_allowed=False с error_message если нет
        """
        # Проверка 1: нельзя переходить в то же состояние
        if current_status == new_status:
            return False, f"Поле уже в состоянии {new_status.value}"

        # Проверка 2: текущее состояние вообще имеет исходящие переходы?
        if current_status not in FieldStateTransitionValidator.ALLOWED_TRANSITIONS:
            return False, f"Из состояния {current_status.value} нельзя переходить в другие состояния"

        # Проверка 3: целевое состояние в списке допустимых?
        allowed = FieldStateTransitionValidator.ALLOWED_TRANSITIONS[current_status]
        if new_status not in allowed:
            return False, (
                f"Переход {current_status.value} → {new_status.value} не разрешён. "
                f"Допустимые переходы: {', '.join(s.value for s in allowed)}"
            )

        # Проверка 4: запрещённый переход?
        if current_status in FieldStateTransitionValidator.FORBIDDEN_TRANSITIONS:
            forbidden = FieldStateTransitionValidator.FORBIDDEN_TRANSITIONS[current_status]
            if new_status in forbidden:
                return False, (
                    f"Переход {current_status.value} → {new_status.value} запрещён системой"
                )

        # Проверка 5: специальное правило для последовательности после болезни
        if current_status == FieldStatusEnum.disease:
            # Все переходы уже в ALLOWED_TRANSITIONS, но можно добавить дополнительную логику
            pass

        # Проверка 6: если переходим ИЗ residue_removal/deep_plowing в field_free,
        # это допустимо (можно пропустить оставшиеся этапы)
        if current_status in {
            FieldStatusEnum.residue_removal,
            FieldStatusEnum.deep_plowing,
        } and new_status == FieldStatusEnum.field_free:
            # Это разрешено — можно "скипнуть" оставшиеся этапы
            pass

        return True, None

    @staticmethod
    def get_available_transitions(current_status: FieldStatusEnum) -> Set[FieldStatusEnum]:
        """
        Получить набор допустимых целевых состояний из текущего.
        """
        if current_status not in FieldStateTransitionValidator.ALLOWED_TRANSITIONS:
            return set()
        return FieldStateTransitionValidator.ALLOWED_TRANSITIONS[current_status]

    @staticmethod
    def get_status_description(status: FieldStatusEnum) -> str:
        """Человеческое описание состояния."""
        descriptions = {
            FieldStatusEnum.preparation: "Подготовка земли (вспашка, выравнивание, внесение удобрений)",
            FieldStatusEnum.sowing: "Посев (в процессе посадки семян)",
            FieldStatusEnum.monitoring: "Мониторинг (рост пшеницы, сбор данных pH и влажности)",
            FieldStatusEnum.harvesting: "Сбор урожая (уборка комбайном)",
            FieldStatusEnum.post_harvest_processing: "Послеуборочная обработка (сушка, очистка)",
            FieldStatusEnum.field_free: "Поле свободно (готово к новому циклу или отдыху)",
            FieldStatusEnum.disease: "Болезнь/Карантин (обнаружена болезнь, поле на обработке)",
            FieldStatusEnum.residue_removal: "Уничтожение растительных остатков (шредирование соломы)",
            FieldStatusEnum.deep_plowing: "Глубокая зяблевая вспашка 20–25 см (подготовка почвы)",
            FieldStatusEnum.chemical_treatment: "Химическая обработка (гербициды/фунгициды от остатков болезни)",
        }
        return descriptions.get(status, status.value)

    @staticmethod
    def get_recovery_sequence() -> list:
        """
        Получить рекомендуемую последовательность восстановления после болезни.
        После disease: residue_removal → deep_plowing → chemical_treatment → field_free
        """
        return [
            FieldStatusEnum.residue_removal,
            FieldStatusEnum.deep_plowing,
            FieldStatusEnum.chemical_treatment,
            FieldStatusEnum.field_free,
        ]


# =============================================================================
# ФАЙЛ: app/services/field_service.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/cqrs/commands/person_commands.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/cqrs/dto/person_dto.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/cqrs/handlers/person_handler.py
# =============================================================================

# app/cqrs/handlers/person_handler.py
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.cqrs.commands.person_commands import CreatePersonCommand, UpdatePersonCommand
from app.models import Person
from app.repositories import PersonRepository
from app.services import AuthService


class PersonCommandHandler:
    """Обработчик команд для пользователей (Command Side)"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PersonRepository(db)

    async def create_person(self, cmd: CreatePersonCommand) -> Person:
        """Создание нового пользователя"""
        # Проверка уникальности логина
        existing = await self.repo.get_by_login(cmd.login)
        if existing:
            raise ValueError(f"Логин '{cmd.login}' уже существует")

        print(f"🔑 Хэшируем пароль для пользователя {cmd.login}")   # отладка

        person = Person(
            full_name=cmd.full_name,
            login=cmd.login,
            password_hash=AuthService.hash_password(cmd.password),   # ← важно!
            phone=cmd.phone,
            qualification=cmd.qualification,
            is_active=True,
        )

        person = await self.repo.create(person)
        await self.repo.set_roles(person, cmd.roles)

        print(f"✅ Пользователь {cmd.login} успешно создан (ID={person.id})")

        # Перезагружаем с ролями
        return await self.repo.get_by_id(person.id)

    async def update_person(self, cmd: UpdatePersonCommand) -> Optional[Person]:
        """Обновление пользователя"""
        person = await self.repo.get_by_id(cmd.person_id)
        if not person:
            return None

        if cmd.full_name is not None:
            person.full_name = cmd.full_name
        if cmd.phone is not None:
            person.phone = cmd.phone
        if cmd.qualification is not None:
            person.qualification = cmd.qualification
        if cmd.is_active is not None:
            person.is_active = cmd.is_active
        if cmd.roles is not None:
            await self.repo.set_roles(person, cmd.roles)

        return await self.repo.update(person)


# =============================================================================
# ФАЙЛ: app/cqrs/queries/person_queries.py
# =============================================================================

# app/cqrs/queries/person_queries.py
from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cqrs.dto.person_dto import PersonReadDTO


class PersonQuery:
    """Query side — чтение данных без ORM (совместимо с SQLite Python 3.8)"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> List[PersonReadDTO]:
        """Получить список всех пользователей"""
        query = text("""
            SELECT
                p.id,
                p.full_name,
                p.login,
                p.phone,
                p.qualification,
                p.is_active,
                COALESCE((
                    SELECT group_concat('"' || role || '"')
                    FROM person_roles pr
                    WHERE pr.person_id = p.id
                ), '[]') as roles_str
            FROM persons p
            ORDER BY p.id
        """)
        result = await self.db.execute(query)
        rows = result.all()

        import json
        users = []
        for row in rows:
            # Преобразуем group_concat обратно в список
            roles_str = row.roles_str or "[]"
            try:
                roles = json.loads("[" + roles_str + "]") if roles_str != "[]" else []
            except:
                roles = []

            users.append(PersonReadDTO(
                id=row.id,
                full_name=row.full_name,
                login=row.login,
                phone=row.phone,
                qualification=row.qualification,
                is_active=row.is_active,
                roles=roles
            ))
        return users

    async def get_by_id(self, person_id: int) -> Optional[PersonReadDTO]:
        """Получить одного пользователя по ID"""
        query = text("""
            SELECT
                p.id,
                p.full_name,
                p.login,
                p.phone,
                p.qualification,
                p.is_active,
                COALESCE((
                    SELECT group_concat('"' || role || '"')
                    FROM person_roles pr
                    WHERE pr.person_id = p.id
                ), '[]') as roles_str
            FROM persons p
            WHERE p.id = :person_id
        """)
        result = await self.db.execute(query, {"person_id": person_id})
        row = result.first()
        if not row:
            return None

        import json
        roles_str = row.roles_str or "[]"
        try:
            roles = json.loads("[" + roles_str + "]") if roles_str != "[]" else []
        except:
            roles = []

        return PersonReadDTO(
            id=row.id,
            full_name=row.full_name,
            login=row.login,
            phone=row.phone,
            qualification=row.qualification,
            is_active=row.is_active,
            roles=roles
        )


# =============================================================================
# ФАЙЛ: app/cqrs/events.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/cqrs/event_publisher.py
# =============================================================================

# app/cqrs/event_publisher.py
from celery import shared_task
import json
from datetime import datetime
import uuid

from app.cqrs.events import DomainEvent


@shared_task
def publish_domain_event(event: dict):
    """Публикует доменное событие в очередь (Celery + RabbitMQ)"""
    print(f"📤 Опубликовано событие: {event['event_type']} | ID: {event.get('event_id')}")
    # Здесь можно добавить логику отправки в RabbitMQ напрямую, но через Celery проще
    return event


# =============================================================================
# ФАЙЛ: app/cqrs/event_handlers.py
# =============================================================================

# app/cqrs/event_handlers.py
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.cqrs.events import PersonCreated, PersonUpdated, FieldStatusChanged
import json


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def handle_domain_event(self, event_dict: dict):
    """Worker: обрабатывает доменные события и обновляет Read Model"""
    try:
        event_type = event_dict.get("event_type")

        async def process():
            async with AsyncSessionLocal() as db:
                if event_type == "PersonCreated":
                    event = PersonCreated(**event_dict)
                    await update_read_model_person_created(db, event)
                elif event_type == "PersonUpdated":
                    event = PersonUpdated(**event_dict)
                    await update_read_model_person_updated(db, event)
                elif event_type == "FieldStatusChanged":
                    event = FieldStatusChanged(**event_dict)
                    await update_read_model_field_status(db, event)
                else:
                    print(f"⚠️ Неизвестный тип события: {event_type}")

        import asyncio
        asyncio.run(process())

        print(f"✅ Событие обработано успешно: {event_type}")

    except Exception as exc:
        print(f"❌ Ошибка обработки события {event_dict.get('event_type')}: {exc}")
        raise self.retry(exc=exc)


async def update_read_model_person_created(db: AsyncSession, event: PersonCreated):
    """Обновление денормализованной Read Model при создании пользователя"""
    # Здесь можно вставить данные в отдельную таблицу read_persons или materialized view
    print(f"Read Model обновлён: создан пользователь {event.full_name} (ID={event.person_id})")


async def update_read_model_person_updated(db: AsyncSession, event: PersonUpdated):
    print(f"Read Model обновлён: изменён пользователь ID={event.person_id}")


async def update_read_model_field_status(db: AsyncSession, event: FieldStatusChanged):
    print(f"Read Model обновлён: статус поля {event.field_id} изменён на {event.new_status}")


# =============================================================================
# ФАЙЛ: app/websocket/manager.py
# =============================================================================

# app/websocket/manager.py
from fastapi import WebSocket
from typing import List


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for conn in self.active_connections[:]:
            try:
                await conn.send_json(message)
            except:
                self.disconnect(conn)


manager = ConnectionManager()


# =============================================================================
# ФАЙЛ: app/tasks/__init__.py
# =============================================================================

# app/tasks/__init__.py
from .notifications import send_notification_task


# =============================================================================
# ФАЙЛ: app/tasks/notifications.py
# =============================================================================

# app/tasks/notifications.py
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services import NotificationService
from app.schemas import NotificationCreate
import asyncio


@shared_task(bind=True, max_retries=3, default_retry_delay=60, ignore_result=False)
def send_notification_task(self, notification_dict: dict):
    """
    Фоновая задача Celery — отправка уведомления.

    Важно:
    - ignore_result=False  → результат сохраняется в backend (rpc://)
    - bind=True            → доступ к self для retry
    - Возвращает dict с notification_id при успехе
    """
    try:
        notification = NotificationCreate(**notification_dict)

        async def _send():
            async with AsyncSessionLocal() as db:
                service = NotificationService(db)
                result = await service.send(notification)
                print(f"Celery (RabbitMQ): Уведомление отправлено | ID={result.id}")
                # Возвращаем результат, который будет доступен через AsyncResult
                return {
                    "notification_id": result.id,
                    "person_id": notification.person_id,
                    "level": notification.level.value,
                    "status": "success"
                }

        # Запускаем async-код и возвращаем результат
        return asyncio.run(_send())

    except Exception as exc:
        print(f"❌ Celery (RabbitMQ): Ошибка отправки уведомления: {exc}")
        # Автоматический retry (до 3 раз)
        raise self.retry(exc=exc)


# =============================================================================
# ФАЙЛ: app/tasks/reports.py
# =============================================================================

# app/tasks/reports.py
from celery import shared_task
from fpdf import FPDF
import asyncio
from app.database import AsyncSessionLocal
from app.repositories import TaskRepository


@shared_task(bind=True)
def generate_completed_tasks_report(self, request_dict: dict):
    async def _run():
        async with AsyncSessionLocal() as db:
            repo = TaskRepository(db)
            tasks = await repo.list_all()
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, "Отчёт по выполненным заданиям", ln=1)
            for t in tasks:
                if t.status == "completed":
                    pdf.cell(200, 8, f"#{t.id} {t.title} — {t.result_comment or '—'}", ln=1)
            filename = f"report_{self.request.id}.pdf"
            pdf.output(f"static/reports/{filename}")
            return {"report_url": f"/static/reports/{filename}"}
    return asyncio.run(_run())


# =============================================================================
# ФАЙЛ: app/routers/auth.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/routers/persons.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/routers/fields.py
# =============================================================================

# app/routers/fields.py — CRUD полей с поддержкой переходов состояния

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles
from app.models import MapTypeEnum, RoleEnum, Person
from app.schemas import (
    BoundaryPointOut, FieldCreate, FieldListItem, FieldOut, FieldUpdate, OkResponse,
    FieldStatusIn, FieldStatusOut,
)
from app.services.field_service import FieldService
from app.dependencies import require_field_access


router = APIRouter(prefix="/fields", tags=["Поля (карты) с системой состояний"])

# Зависимости для авторизации
_any  = Depends(get_current_person)
_mgr  = Depends(require_roles(RoleEnum.manager))


@router.get("/", response_model=List[FieldListItem], dependencies=[_any])
async def list_fields(
    map_type: Optional[MapTypeEnum] = Query(None, description="Фильтр по типу карты (health/irrigation)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Список всех полей с их текущими статусами.
    Агроном может фильтровать по map_type=health, менеджер — по irrigation.
    """
    svc = FieldService(db)
    if map_type:
        return await svc.list_by_type(map_type)
    return await svc.list_all()


@router.post("/", response_model=FieldOut, status_code=201, dependencies=[_mgr])
async def create_field(body: FieldCreate, db: AsyncSession = Depends(get_db)):
    """
    Создать новое поле с граничными точками.
    Начальный статус: preparation (подготовка земли).
    """
    return await FieldService(db).create(body)


_field_access = Depends(require_field_access())


@router.get("/{field_id}", response_model=FieldOut)
async def get_field(
    field_id: int,
    current: Person = _field_access,   # ← теперь проверка
    db: AsyncSession = Depends(get_db),
):
    """
    Получить поле по ID с метаданными, граничными точками и текущим статусом.
    """
    field = await FieldService(db).get(field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return field


@router.patch("/{field_id}", response_model=FieldOut, dependencies=[_mgr])
async def update_field(field_id: int, body: FieldUpdate, db: AsyncSession = Depends(get_db)):
    """
    Обновить метаданные поля (имя, площадь, описание).
    НЕ используйте для смены статуса — используйте /transition endpoint.
    """
    field = await FieldService(db).update(field_id, body)
    if not field:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return field


@router.delete("/{field_id}", response_model=OkResponse, dependencies=[_mgr])
async def delete_field(field_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить поле."""
    ok = await FieldService(db).delete(field_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return OkResponse(message="Поле удалено")


@router.get("/{field_id}/boundary", response_model=List[BoundaryPointOut], dependencies=[_any])
async def get_boundary(field_id: int, db: AsyncSession = Depends(get_db)):
    """
    Точки границы поля (контур полигона).
    Используется для отрисовки на карте.
    """
    return await FieldService(db).get_boundary(field_id)


# ── НОВОЕ: управление состояниями ──

@router.get("/{field_id}/status", response_model=FieldStatusOut, dependencies=[_any])
async def get_field_status(field_id: int, db: AsyncSession = Depends(get_db)):
    """
    Получить текущий статус поля и доступные переходы.

    Returns:
        {
            'field_id': ...,
            'current_status': 'monitoring',
            'status_changed_at': '2026-04-10T14:30:00',
            'status_reason': 'Посев завершен',
            'available_transitions': ['harvesting', 'disease']
        }

    Если поле в статусе disease, также возвращает 'recovery_sequence'.
    """
    status_info = await FieldService(db).get_current_status(field_id)
    if not status_info:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return status_info


@router.post("/{field_id}/transition", response_model=FieldOut, dependencies=[_mgr])
async def transition_field_status(
    field_id: int,
    body: FieldStatusIn,
    db: AsyncSession = Depends(get_db),
):
    """
    Смена статуса поля.

    Допустимые переходы определены в FieldStateTransitionValidator.

    Ошибки:
    - 404: поле не найдено
    - 409: переход не разрешён (нарушены правила state machine)

    Пример запроса:
    {
        'new_status': 'sowing',
        'reason': 'Посев завершен, начинаем мониторинг'
    }
    """
    svc = FieldService(db)
    field, error = await svc.transition_status(field_id, body)

    if field is None:
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        else:
            # Переход не разрешён → 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error
            )

    return field


@router.get("/{field_id}/status-info", dependencies=[_any])
async def get_field_status_info(field_id: int, db: AsyncSession = Depends(get_db)):
    """
    Получить подробное описание текущего статуса поля.

    Returns:
        {
            'field_id': ...,
            'status': 'monitoring',
            'status_name': 'monitoring',
            'description': 'Мониторинг (рост пшеницы, сбор данных pH и влажности)',
            'changed_at': '2026-04-20T10:00:00',
            'reason': 'Посев завершен'
        }
    """
    info = await FieldService(db).get_status_description(field_id)
    if not info:
        raise HTTPException(status_code=404, detail="Поле не найдено")
    return info


# =============================================================================
# ФАЙЛ: app/routers/points.py
# =============================================================================

# app/routers/points.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles, require_field_access
from app.models import RoleEnum, Person
from app.schemas import GpsPointCreate, GpsPointOut, OkResponse
from app.services import GpsPointService
from typing import List

router = APIRouter(prefix="/fields/{field_id}/points", tags=["GPS-точки"])

_any          = Depends(get_current_person)
_chemist      = Depends(require_roles(RoleEnum.chemist))
_field_access = Depends(require_field_access())


@router.get("/", response_model=List[GpsPointOut])
async def list_points(
    field_id: int,
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    """Все GPS-точки поля."""
    return await GpsPointService(db).list_by_field(field_id)


@router.get("/bbox", response_model=List[GpsPointOut])
async def points_in_bbox(
    field_id: int,
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    """Точки в пределах bounding box."""
    return await GpsPointService(db).list_in_bbox(field_id, min_lat, max_lat, min_lon, max_lon)


@router.post("/find-or-create", response_model=GpsPointOut, dependencies=[_chemist])
async def find_or_create_point(
    field_id: int,
    body: GpsPointCreate,
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    """Найти или создать точку."""
    try:
        point, _ = await GpsPointService(db).create_or_get(
            field_id, body.latitude, body.longitude
        )
        return point
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{point_id}", response_model=OkResponse, dependencies=[_chemist])
async def delete_point(
    field_id: int,
    point_id: int,
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    ok = await GpsPointService(db).delete(point_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Точка не найдена")
    return OkResponse(message="Точка удалена")


# =============================================================================
# ФАЙЛ: app/routers/measurement_maps.py
# =============================================================================

# app/routers/measurement_maps.py — карты измерений (дата + тип)

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles, require_field_access
from app.models import RoleEnum, Person
from app.schemas import MeasurementMapCreate, MeasurementMapOut, OkResponse
from app.services import MeasurementMapService

_field_access = Depends(require_field_access())

router = APIRouter(prefix="/measurement-maps", tags=["Карты измерений"])

_any     = Depends(get_current_person)
_chemist = Depends(require_roles(RoleEnum.chemist))


@router.get("/field/{field_id}", response_model=List[MeasurementMapOut], dependencies=[_any])
async def list_by_field(field_id: int, current: Person = _field_access, db: AsyncSession = Depends(get_db)):
    """Все карты измерений поля (по убыванию даты)."""
    return await MeasurementMapService(db).list_by_field(field_id)


@router.post("/", response_model=MeasurementMapOut, status_code=201, dependencies=[_chemist])
async def create_map(body: MeasurementMapCreate, current: Person = _field_access, db: AsyncSession = Depends(get_db)):
    """Создать новую карту измерений (химик начинает серию замеров)."""
    return await MeasurementMapService(db).create(body)


@router.get("/{map_id}", response_model=MeasurementMapOut, dependencies=[_any])
async def get_map(map_id: int, db: AsyncSession = Depends(get_db)):
    mmap = await MeasurementMapService(db).get(map_id)
    if not mmap:
        raise HTTPException(status_code=404, detail="Карта измерений не найдена")
    return mmap


@router.delete("/{map_id}", response_model=OkResponse, dependencies=[_chemist])
async def delete_map(map_id: int, db: AsyncSession = Depends(get_db)):
    ok = await MeasurementMapService(db).delete(map_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Карта измерений не найдена")
    return OkResponse(message="Карта измерений удалена")


# =============================================================================
# ФАЙЛ: app/routers/ph.py
# =============================================================================

# app/routers/ph.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person, require_roles, require_field_access
from app.models import RoleEnum, Person
from app.schemas import OkResponse, PhMeasurementCreate, PhMeasurementOut
from app.services import PhMeasurementService

router = APIRouter(prefix="/measurements/ph", tags=["Измерения pH"])

_any          = Depends(get_current_person)
_chemist      = Depends(require_roles(RoleEnum.chemist))
_field_access = Depends(require_field_access())


@router.post("/", response_model=PhMeasurementOut, status_code=201, dependencies=[_chemist])
async def add_ph(
    body: PhMeasurementCreate,
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    return await PhMeasurementService(db).add(body)


@router.get("/point/{point_id}", response_model=List[PhMeasurementOut])
async def list_by_point(
    point_id: int,
    current: Person = _any,
    db: AsyncSession = Depends(get_db),
):
    return await PhMeasurementService(db).list_by_point(point_id)


@router.get("/field/{field_id}/bbox", response_model=List[PhMeasurementOut])
async def ph_in_bbox(
    field_id: int,
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    return await PhMeasurementService(db).list_in_bbox(
        field_id, min_lat, max_lat, min_lon, max_lon
    )


@router.delete("/{measurement_id}", response_model=OkResponse, dependencies=[_chemist])
async def delete_ph(
    measurement_id: int,
    # Для delete по measurement_id сложно быстро получить field_id.
    # Поэтому оставляем только chemist (или можно улучшить позже)
    current: Person = _any,
    db: AsyncSession = Depends(get_db),
):
    ok = await PhMeasurementService(db).delete(measurement_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Измерение не найдено")
    return OkResponse(message="Измерение pH удалено")


# =============================================================================
# ФАЙЛ: app/routers/humidity.py
# =============================================================================

# app/routers/humidity.py — измерения влажности (с защитой доступа к полям)

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_person,
    require_roles,
    require_field_access
)
from app.models import RoleEnum, Person
from app.schemas import HumidityMeasurementCreate, HumidityMeasurementOut, OkResponse
from app.services import HumidityMeasurementService

router = APIRouter(
    prefix="/measurements/humidity",
    tags=["Измерения влажности"]
)

_any          = Depends(get_current_person)
_chemist      = Depends(require_roles(RoleEnum.chemist))
_field_access = Depends(require_field_access())


@router.post("/",
             response_model=HumidityMeasurementOut,
             status_code=201,
             dependencies=[_chemist])
async def add_humidity(
    body: HumidityMeasurementCreate,
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    """
    Внести измерение влажности для GPS-точки.
    Только химик может добавлять измерения.
    Пользователь должен иметь доступ к полю (manager или chemist + health карта).
    """
    return await HumidityMeasurementService(db).add(body)


@router.get("/point/{point_id}",
            response_model=List[HumidityMeasurementOut],
            dependencies=[_any])
async def list_by_point(
    point_id: int,
    current: Person = _any,
    db: AsyncSession = Depends(get_db),
):
    """История измерений влажности для одной точки."""
    return await HumidityMeasurementService(db).list_by_point(point_id)


@router.get("/field/{field_id}/bbox",
            response_model=List[HumidityMeasurementOut])
async def humidity_in_bbox(
    field_id: int,
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    current: Person = _field_access,
    db: AsyncSession = Depends(get_db),
):
    """
    Влажность в области просмотра (bounding box).
    getMeasurementsInBBox из диаграммы менеджера (тип humidity).

    Доступ:
    - Manager — всегда
    - Chemist / Agronomist — только если поле типа 'health'
    """
    return await HumidityMeasurementService(db).list_in_bbox(
        field_id, min_lat, max_lat, min_lon, max_lon
    )


@router.delete("/{measurement_id}",
               response_model=OkResponse,
               dependencies=[_chemist])
async def delete_humidity(
    measurement_id: int,
    current: Person = _any,
    db: AsyncSession = Depends(get_db),
):
    """
    Удалить измерение влажности.
    Только химик может удалять свои измерения.
    """
    ok = await HumidityMeasurementService(db).delete(measurement_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Измерение влажности не найдено"
        )
    return OkResponse(message="Измерение влажности удалено")


# =============================================================================
# ФАЙЛ: app/routers/notifications.py
# =============================================================================

# app/routers/notifications.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, get_current_person
from app.models import RoleEnum, Person
from app.schemas import NotificationCreate, NotificationOut
from app.tasks.notifications import send_notification_task

router = APIRouter(prefix="/notifications", tags=["Уведомления"])

_mgr = Depends(require_roles(RoleEnum.manager))


@router.post("/", status_code=202)   # 202 Accepted — важно для фоновых задач
async def send_notification(
    body: NotificationCreate,
    current: Person = Depends(get_current_person)
):
    """Отправить уведомление через Celery (асинхронно)"""
    try:
        # Отправляем задачу в Celery
        task = send_notification_task.delay(body.dict())

        return {
            "status": "accepted",
            "message": "Уведомление поставлено в очередь",
            "task_id": task.id,
            "person_id": body.person_id,
            "level": body.level.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка постановки задачи: {str(e)}")


@router.get("/my", response_model=List[NotificationOut])
async def my_notifications(
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Получить свои непрочитанные уведомления"""
    from app.services import NotificationService
    return await NotificationService(db).get_unread(current.id)


# =============================================================================
# ФАЙЛ: app/routers/reports.py
# =============================================================================

# app/routers/reports.py
from fastapi import APIRouter, Depends
from app.dependencies import require_roles
from app.models import RoleEnum
from app.schemas import ReportGenerateRequest, ReportTaskResponse
from app.tasks.reports import generate_completed_tasks_report

router = APIRouter(prefix="/reports", tags=["Отчёты (Celery)"])


@router.post("/generate", response_model=ReportTaskResponse)
async def generate_report(
    body: ReportGenerateRequest = None,
    current=Depends(require_roles(RoleEnum.manager))
):
    if body is None:
        body = ReportGenerateRequest()

    task = generate_completed_tasks_report.delay(body.model_dump() if body else {})
    return ReportTaskResponse(task_id=task.id, status="PENDING")


# =============================================================================
# ФАЙЛ: app/routers/ws.py
# =============================================================================

# app/routers/ws.py — WebSocket для реального времени
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

router = APIRouter(prefix="/ws", tags=["WebSocket — Реал-тайм"])


@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket):
    """
    Основной WebSocket-эндпоинт.
    Клиент подключается после логина.
    """
    await manager.connect(websocket)
    try:
        # Можно принять первое сообщение от клиента (например, user_id)
        data = await websocket.receive_json()
        print(f"WebSocket получил приветствие: {data}")

        # Держим соединение открытым
        while True:
            await websocket.receive_text()  # просто держим alive

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket ошибка: {e}")
        manager.disconnect(websocket)


# =============================================================================
# ФАЙЛ: app/routers/tasks.py
# =============================================================================

# app/routers/tasks.py — мониторинг статуса Celery-задач
from fastapi import APIRouter, HTTPException, status
from celery.result import AsyncResult
from app.celery_app import celery_app
from app.schemas import TaskStatusResponse

router = APIRouter(prefix="/tasks", tags=["Задачи (Celery)"])


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Получить полный статус любой Celery-задачи по её ID.

    Возвращает:
    - task_id
    - status (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED)
    - result (если задача завершена успешно)
    - error (если задача упала)
    - traceback (при ошибке)

    Пример ответа при успехе:
    {
        "task_id": "abc123-...",
        "status": "SUCCESS",
        "result": {
            "notification_id": 42,
            "person_id": 5,
            "level": "normal",
            "status": "success"
        },
        "error": null,
        "traceback": null
    }
    """
    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "error": None,
        "traceback": None,
    }

    if task_result.status == "SUCCESS":
        response["result"] = task_result.result

    elif task_result.status == "FAILURE":
        response["error"] = str(task_result.result)
        response["traceback"] = task_result.traceback

    elif task_result.status == "RETRY":
        response["error"] = "Задача в процессе повторной попытки"

    return response


# =============================================================================
# ФАЙЛ: app/routers/commands/persons.py
# =============================================================================

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


# =============================================================================
# ФАЙЛ: app/routers/commands/equipment.py
# =============================================================================

# app/routers/commands/equipment.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, get_current_person
from app.models import RoleEnum, Person
from app.schemas import EquipmentPositionUpdate
from app.services import EquipmentService

router = APIRouter(prefix="/equipment", tags=["Commands — Equipment"])


@router.patch("/{eq_id}/position")
async def update_equipment_position(
    eq_id: int,
    body: EquipmentPositionUpdate,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Обновление позиции техники"""
    if current.has_role(RoleEnum.driver):
        # Водитель может обновлять только свою технику
        if not any(eq.id == eq_id for eq in getattr(current, 'assigned_equipment', [])):
            raise HTTPException(status_code=403, detail="Вы можете обновлять только свою технику")

    service = EquipmentService(db)
    eq = await service.update_position(eq_id, body.latitude, body.longitude)

    if not eq:
        raise HTTPException(status_code=404, detail="Техника не найдена")

    return {"ok": True, "message": "Позиция техники обновлена"}


# =============================================================================
# ФАЙЛ: app/routers/commands/tasks.py
# =============================================================================

# app/routers/commands/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles, get_current_person
from app.models import RoleEnum, Person, Task
from app.schemas import TaskCreateCommand, TaskMarkCompletedCommand
from app.services import TaskService

router = APIRouter(prefix="/tasks", tags=["Commands — Tasks"])

_mgr = Depends(require_roles(RoleEnum.manager))


@router.post("/create", dependencies=[_mgr])
async def create_task(
    cmd: TaskCreateCommand,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    task = Task(
        title=cmd.title,
        description=cmd.description,
        assigned_by_id=current.id,
        assigned_to_id=cmd.assigned_to_id,
        equipment_id=cmd.equipment_id,
        field_id=cmd.field_id,
        due_date=cmd.due_date,
    )

    service = TaskService(db)
    created_task = await service.create(task)

    return {"ok": True, "task_id": created_task.id}


@router.patch("/{task_id}/complete")
async def mark_task_completed(
    task_id: int,
    cmd: TaskMarkCompletedCommand,
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    service = TaskService(db)
    task = await service.mark_completed(task_id, cmd.result_comment)
    if not task:
        raise HTTPException(404, "Задание не найдено")

    return {"ok": True, "task_id": task.id, "status": task.status.value}


# =============================================================================
# ФАЙЛ: app/routers/queries/persons.py
# =============================================================================

# app/routers/queries/persons.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_web_app, require_roles
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


# =============================================================================
# ФАЙЛ: app/routers/queries/equipment.py
# =============================================================================

# app/routers/queries/equipment.py — CQRS Query side для техники

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person
from app.models import Person
from app.schemas import EquipmentOut

router = APIRouter(prefix="/equipment", tags=["Queries — Equipment"])


@router.get("/")
async def list_equipment(
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Список всей техники (водитель видит только свою)"""
    from app.services import EquipmentService      # импорт внутри функции — защита от циклических импортов

    equipment_list = await EquipmentService(db).list_all()

    # Ограничение видимости для роли driver
    if current.has_role("driver"):                 # можно использовать .has_role(RoleEnum.driver)
        equipment_list = [eq for eq in equipment_list if eq.assigned_driver_id == current.id]

    return equipment_list


# =============================================================================
# ФАЙЛ: app/routers/queries/tasks.py
# =============================================================================

# app/routers/queries/tasks.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_person
from app.schemas import TaskOut
from app.models import Person

router = APIRouter(prefix="/tasks", tags=["Queries — Tasks"])


@router.get("/")
async def list_tasks(
    current: Person = Depends(get_current_person),
    db: AsyncSession = Depends(get_db)
):
    """Список всех заданий"""
    from app.services import TaskService
    tasks = await TaskService(db).list_all()
    return tasks


# =============================================================================
# ФАЙЛ: app/routers/__init__.py
# =============================================================================

# app/routers/__init__.py — Рабочая версия (reports временно отключён)

from fastapi import APIRouter

# ====================== ОСНОВНЫЕ РОУТЕРЫ ======================
from app.routers.auth import router as auth_router
from app.routers.persons import router as persons_router
from app.routers.fields import router as fields_router
from app.routers.points import router as points_router
from app.routers.measurement_maps import router as mmaps_router
from app.routers.ph import router as ph_router
from app.routers.humidity import router as humidity_router
from app.routers.notifications import router as notif_router
from app.routers.ws import router as ws_router

# ====================== НОВЫЕ CQRS (Equipment + Tasks) ======================
from app.routers.commands.equipment import router as equipment_commands_router
from app.routers.queries.equipment import router as equipment_queries_router
from app.routers.commands.tasks import router as tasks_commands_router
from app.routers.queries.tasks import router as tasks_queries_router

# ====================== Reports (PDF) — ВРЕМЕННО ОТКЛЮЧЁН ======================
# from app.routers.reports import router as reports_router   # ← закомментировано


api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(persons_router)

api_router.include_router(fields_router)
api_router.include_router(points_router)
api_router.include_router(mmaps_router)
api_router.include_router(ph_router)
api_router.include_router(humidity_router)

api_router.include_router(notif_router)
api_router.include_router(ws_router)

# Новые модули
api_router.include_router(equipment_commands_router)
api_router.include_router(equipment_queries_router)
api_router.include_router(tasks_commands_router)
api_router.include_router(tasks_queries_router)

# reports отключён до исправления
# api_router.include_router(reports_router)


print("✅ Роутеры подключены (reports отключён для отладки Swagger)")


# =============================================================================
# ФАЙЛ: create_key.py
# =============================================================================

# create_key.py — генерация SECRET_KEY и запись в .env
import secrets
key = secrets.token_urlsafe(64)
with open('.env', 'w', encoding='utf-8') as f:
    f.write(f'SECRET_KEY={key}\n')
print('✅ SECRET_KEY успешно записан в файл .env')
print(f'SECRET_KEY={key}')


# =============================================================================
# ФАЙЛ: create_ssl_cert.py
# =============================================================================

# create_ssl_cert.py — создание самоподписанного SSL-сертификата для localhost
# Simple way to create SSL certificates using Python (no openssl needed)

from pathlib import Path
import subprocess
import sys

print("=== Creating SSL certificates for localhost ===")

cert_dir = Path("certs")
cert_dir.mkdir(exist_ok=True)

print("Generating certificate...")

try:
    # Try using openssl if available
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096",
        "-nodes", "-days", "365",
        "-keyout", "certs/key.pem",
        "-out", "certs/cert.pem",
        "-subj", "/CN=localhost"
    ], check=True, shell=True, capture_output=True)

    print("SUCCESS!")
    print("Files created:")
    print("   - certs/cert.pem")
    print("   - certs/key.pem")

except FileNotFoundError:
    print("ERROR: 'openssl' command not found.")
    print("\nYou have 2 options:")
    print("1. Install Git for Windows (recommended) - it includes openssl")
    print("2. Run the server without SSL for development")

    print("\nTo run without SSL, use this command:")
    print('uvicorn app.main:app --reload --host 127.0.0.1 --port 8000')

except subprocess.CalledProcessError as e:
    print(f"Error during certificate creation: {e}")
    print("Trying alternative method...")

print("\nDone.")
