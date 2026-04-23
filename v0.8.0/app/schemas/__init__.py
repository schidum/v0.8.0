# app/schemas/__init__.py — Pydantic v2 DTO
# Изменение: roles: list[RoleEnum] вместо единственного role: RoleEnum



from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models import MapTypeEnum, NotifLevelEnum, RoleEnum,FieldStatusEnum,TaskStatusEnum


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
    password      : Optional[str]           = Field(None, min_length=6)   # ← ИСПРАВЛЕНО
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
        "from_attributes": True,        # Позволяет работать с ORM объектами
        "json_encoders": {
            RoleEnum: lambda v: v.value  # На всякий случай
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
    recovery_sequence     : Optional[List[FieldStatusEnum]] = None   # ← добавлено

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
        "json_encoders": {
            # Можно добавить при необходимости
        }
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
    
# class PersonUpdate(BaseModel):
#     full_name: Optional[str] = None
#     phone: Optional[str] = None
#     qualification: Optional[str] = None
#     is_active: Optional[bool] = None
#     roles: Optional[List[RoleEnum]] = None


# class PersonOut(BaseModel):
#     id: int
#     full_name: str
#     login: str
#     roles: List[str]
#     phone: Optional[str] = None
#     qualification: Optional[str] = None
#     is_active: bool = True

#     model_config = {"from_attributes": True}    



# ====================== NEW SCHEMAS ======================

class MaintenanceTypeEnum(str, enum.Enum):
    planned = "planned"
    unscheduled = "unscheduled"

class RiskTypeEnum(str, enum.Enum):
    drought = "drought"
    disease = "disease"

# Maintenance
class MaintenanceCreate(BaseModel):
    equipment_id: int
    maintenance_date: datetime
    type: MaintenanceTypeEnum
    cost: float = Field(gt=0)
    description: Optional[str] = None
    mileage_at_service: float = Field(ge=0)

class MaintenanceUpdate(BaseModel):
    maintenance_date: Optional[datetime] = None
    type: Optional[MaintenanceTypeEnum] = None
    cost: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    mileage_at_service: Optional[float] = Field(None, ge=0)

class MaintenanceOut(BaseModel):
    id: int
    equipment_id: int
    maintenance_date: datetime
    type: MaintenanceTypeEnum
    cost: float
    description: Optional[str]
    mileage_at_service: float
    performed_by_id: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}

# WearAnalysis
class WearAnalysisOut(BaseModel):
    id: int
    equipment_id: int
    analysis_date: datetime
    wear_percentage: float
    factors: Optional[str]
    model_config = {"from_attributes": True}

class CurrentWearResponse(BaseModel):
    equipment_id: int
    equipment_name: str
    wear_percentage: float
    based_on_factors: dict

# RiskPrediction
class RiskPredictionCreate(BaseModel):
    field_id: int
    risk_type: RiskTypeEnum
    probability: float = Field(ge=0, le=1)
    valid_until: datetime
    notes: Optional[str] = None

class RiskPredictionOut(BaseModel):
    id: int
    field_id: int
    risk_type: RiskTypeEnum
    probability: float
    predicted_at: datetime
    valid_until: datetime
    notes: Optional[str]
    model_config = {"from_attributes": True}

class RiskPredictionListQuery(BaseModel):
    field_id: Optional[int] = None
    risk_type: Optional[RiskTypeEnum] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

class RiskMapPoint(BaseModel):
    latitude: float
    longitude: float
    risk_drought: float      # 0..1
    risk_disease: float
    # при необходимости дополнительные поля