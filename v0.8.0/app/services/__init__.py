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
    HumidityMeasurement, Maintenance, MeasurementMap,
    Notification, Person, PersonRole, PhMeasurement, RiskPrediction,
    RoleEnum,Task,Fueling, WearAnalysis
)
from app.repositories import (
    FieldRepository, GpsPointRepository,
    HumidityMeasurementRepository, MaintenanceRepository, MeasurementMapRepository,
    NotificationRepository, PersonRepository, PhMeasurementRepository,EquipmentRepository, RiskPredictionRepository, WearAnalysisRepository
)
from app.schemas import (
    FieldCreate, FieldUpdate,
    HumidityMeasurementCreate, MaintenanceCreate, MeasurementMapCreate,
    NotificationCreate, PersonCreate, PersonUpdate, PhMeasurementCreate, RiskPredictionCreate,
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

    async def create(self, dto: 'PersonCreate') -> Person:   # используем строковую аннотацию
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


class FuelingService:
    def __init__(self, db: AsyncSession):
        self.repo = FuelingRepository(db)

    async def add_fueling(self, fueling: Fueling) -> Fueling:
        return await self.repo.create(fueling)




# ====================== NEW SERVICES ======================
class MaintenanceService:
    def __init__(self, db: AsyncSession):
        self.repo = MaintenanceRepository(db)
        self.db = db

    async def create(self, dto: MaintenanceCreate, performed_by_id: int, owner_id: int) -> Maintenance:
        maintenance = Maintenance(
            equipment_id=dto.equipment_id,
            maintenance_date=dto.maintenance_date,
            type=dto.type,
            cost=dto.cost,
            description=dto.description,
            mileage_at_service=dto.mileage_at_service,
            performed_by_id=performed_by_id,
            owner_id=owner_id,
        )
        created = await self.repo.create(maintenance)
        # broadcast через WebSocket
        from app.websocket.manager import manager
        await manager.broadcast({
            "type": "maintenance_created",
            "maintenance": {
                "id": created.id,
                "equipment_id": created.equipment_id,
                "type": created.type.value,
                "date": created.maintenance_date.isoformat(),
                "cost": created.cost
            }
        })
        return created

    async def list_by_equipment(self, equipment_id: int) -> List[Maintenance]:
        return await self.repo.list_by_equipment(equipment_id)

    async def delete(self, maintenance_id: int) -> bool:
        m = await self.repo.get_by_id(maintenance_id)
        if not m: return False
        await self.repo.delete(m)
        return True

class WearAnalysisService:
    def __init__(self, db: AsyncSession):
        self.repo = WearAnalysisRepository(db)
        self.equipment_repo = EquipmentRepository(db)  # предположим, он есть
        self.db = db

    async def calculate_and_save(self, equipment_id: int, owner_id: int) -> WearAnalysis:
        """Рассчитать износ на основе пробега, ремонтов и других факторов"""
        equipment = await self.equipment_repo.get_by_id(equipment_id)
        if not equipment:
            raise ValueError("Equipment not found")

        # Получить историю обслуживания
        maint_repo = MaintenanceRepository(self.db)
        maintenances = await maint_repo.list_by_equipment(equipment_id, limit=50)

        # Простейшая формула: износ = (пробег / (средний ресурс 5000)) * 100 + штраф за внеплановые ремонты
        factor_mileage = min(equipment.current_mileage / 5000, 1.0)
        penalty = sum(1 for m in maintenances if m.type == "unscheduled") * 0.05
        wear = min(factor_mileage + penalty, 1.0) * 100

        factors = {
            "current_mileage": equipment.current_mileage,
            "maintenance_count": len(maintenances),
            "unscheduled_count": sum(1 for m in maintenances if m.type == "unscheduled"),
            "last_repair_date": equipment.last_repair_date.isoformat() if equipment.last_repair_date else None
        }
        wear_analysis = WearAnalysis(
            equipment_id=equipment_id,
            wear_percentage=wear,
            factors=json.dumps(factors),
            owner_id=owner_id
        )
        saved = await self.repo.create(wear_analysis)

        # broadcast обновления износа
        from app.websocket.manager import manager
        await manager.broadcast({
            "type": "wear_updated",
            "equipment_id": equipment_id,
            "wear_percentage": wear
        })
        return saved

    async def get_current_wear(self, equipment_id: int) -> Optional[WearAnalysis]:
        return await self.repo.get_latest_for_equipment(equipment_id)

class RiskPredictionService:
    def __init__(self, db: AsyncSession):
        self.repo = RiskPredictionRepository(db)
        self.db = db

    async def save_prediction(self, dto: RiskPredictionCreate, owner_id: int) -> RiskPrediction:
        pred = RiskPrediction(
            field_id=dto.field_id,
            risk_type=dto.risk_type,
            probability=dto.probability,
            valid_until=dto.valid_until,
            notes=dto.notes,
            owner_id=owner_id
        )
        return await self.repo.create(pred)

    async def get_active_for_field(self, field_id: int) -> List[RiskPrediction]:
        return await self.repo.get_active_for_field(field_id)

    async def delete_old_predictions(self, before_date: datetime) -> int:
        # cleanup logic
        pass