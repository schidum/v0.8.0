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
# ФАЙЛ: app/models/__init__.py – расширенный ORM (добавлены Maintenance, WearAnalysis, RiskPrediction)
# =============================================================================

# ====================== НОВЫЕ ПЕРЕЧИСЛЕНИЯ ======================

class MaintenanceType(str, enum.Enum):
    planned = "planned"          # плановое ТО
    unscheduled = "unscheduled"  # внеплановый ремонт

class RiskType(str, enum.Enum):
    drought = "drought"   # засуха
    disease = "disease"   # болезнь


# ====================== НОВЫЕ СУЩНОСТИ ======================

class Maintenance(Base):
    """Техническое обслуживание и ремонт оборудования"""
    __tablename__ = "maintenances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"))
    maintenance_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[MaintenanceType] = mapped_column(Enum(MaintenanceType), nullable=False)
    cost: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    mileage_at_service: Mapped[float] = mapped_column(Float, nullable=False)   # пробег на момент обслуживания
    performed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)  # ownership
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    equipment: Mapped["Equipment"] = relationship("Equipment", backref="maintenances")
    performed_by: Mapped[Optional["Person"]] = relationship("Person", foreign_keys=[performed_by_id])

class WearAnalysis(Base):
    """Анализ износа оборудования (исторические периодические расчёты)"""
    __tablename__ = "wear_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id", ondelete="CASCADE"))
    analysis_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    wear_percentage: Mapped[float] = mapped_column(Float, nullable=False)   # 0..100
    factors: Mapped[Optional[str]] = mapped_column(Text)   # JSON строка с факторами (пробег, кол-во ремонтов и пр.)
    owner_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)

    equipment: Mapped["Equipment"] = relationship("Equipment", backref="wear_analyses")

class RiskPrediction(Base):
    """Прогноз агрорисков (засуха, болезни) для поля"""
    __tablename__ = "risk_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"))
    risk_type: Mapped[RiskType] = mapped_column(Enum(RiskType), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)   # 0..1
    predicted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valid_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)   # до какой даты прогноз актуален
    notes: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)

    field: Mapped["Field"] = relationship("Field", backref="risk_predictions")