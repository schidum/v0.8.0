# app/repositories/__init__.py — слой доступа к данным



from typing import List, Optional, Sequence, Tuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Field, FieldBoundary, GpsPoint,
    HumidityMeasurement, MeasurementMap,
    Notification, Person, PersonRole, PhMeasurement,
    MapTypeEnum, RoleEnum,Equipment,Task,TaskStatusEnum,Fueling,Maintenance, WearAnalysis, RiskPrediction, RoleEnum
)


# ══════════════════════════════════════════════════════════════════════════════
# PersonRepository
# ═════════════════════════════════

class PersonRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    def _with_roles(self):
        """Базовый запрос с eager-загрузкой ролей."""
        return select(Person).options(selectinload(Person.roles))

    async def get_by_id(self, person_id: int) -> Optional[Person]:
        result = await self.db.execute(
            self._with_roles().where(Person.id == person_id)
        )
        return result.scalar_one_or_none()

    async def get_by_login(self, login: str) -> Optional[Person]:
        result = await self.db.execute(
            self._with_roles().where(Person.login == login)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Person]:
        result = await self.db.execute(
            self._with_roles().order_by(Person.id)
        )
        return result.scalars().all()

    async def create(self, person: Person) -> Person:
        from sqlalchemy.exc import IntegrityError, SQLAlchemyError
        import logging
        logger = logging.getLogger(__name__)
        try:
            self.db.add(person)
            await self.db.commit()
            await self.db.refresh(person)
            # Перезагружаем с ролями
            return await self.get_by_id(person.id)
        except IntegrityError as e:
            await self.db.rollback()
            logger.error(f"Database integrity error creating person: {e}")
            raise ValueError(f"Person with login '{person.login}' already exists")
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Database error creating person: {e}")
            raise

    async def update(self, person: Person) -> Person:
        from sqlalchemy.exc import SQLAlchemyError
        import logging
        logger = logging.getLogger(__name__)
        try:
            await self.db.commit()
            return await self.get_by_id(person.id)
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Database error updating person: {e}")
            raise

    async def set_roles(self, person: Person, roles: List[RoleEnum]) -> None:
        """
        Полностью заменить набор ролей пользователя.
        Удаляем старые записи, вставляем новые.
        """
        from sqlalchemy.exc import SQLAlchemyError
        import logging
        logger = logging.getLogger(__name__)
        try:
            # Удалить все текущие роли
            for pr in list(person.roles):
                await self.db.delete(pr)
            await self.db.flush()
            # Добавить новые — через person.roles.append(), а не db.add()
            # db.add() пишет только в сессию, НЕ обновляет ORM-коллекцию в памяти
            for role in roles:
                pr = PersonRole(person_id=person.id, role=role)
                person.roles.append(pr)  # синхронизируем in-memory коллекцию
            await self.db.flush()
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Database error updating user roles: {e}")
            raise

    async def delete(self, person: Person) -> None:
        from sqlalchemy.exc import SQLAlchemyError
        import logging
        logger = logging.getLogger(__name__)
        try:
            await self.db.delete(person)
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Database error deleting person: {e}")
            raise


# ══════════════════════════════════════════════════════════════════════════════
# FieldRepository
# ══════════════════════════════════════════════════════════════════════════════

class FieldRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, field_id: int) -> Optional[Field]:
        result = await self.db.execute(
            select(Field)
            .options(selectinload(Field.boundary_points))
            .where(Field.id == field_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Field]:
        result = await self.db.execute(select(Field).order_by(Field.id))
        return result.scalars().all()

    async def list_by_type(self, map_type: MapTypeEnum) -> Sequence[Field]:
        result = await self.db.execute(
            select(Field).where(Field.map_type == map_type).order_by(Field.id)
        )
        return result.scalars().all()

    async def create(self, field: Field) -> Field:
        self.db.add(field)
        await self.db.commit()
        await self.db.refresh(field)
        return field

    async def update(self, field: Field) -> Field:
        await self.db.commit()
        await self.db.refresh(field)
        return field

    async def delete(self, field: Field) -> None:
        await self.db.delete(field)
        await self.db.commit()

    async def get_boundary_points(self, field_id: int) -> Sequence[FieldBoundary]:
        result = await self.db.execute(
            select(FieldBoundary)
            .where(FieldBoundary.field_id == field_id)
            .order_by(FieldBoundary.order_idx)
        )
        return result.scalars().all()


# ══════════════════════════════════════════════════════════════════════════════
# GpsPointRepository
# ══════════════════════════════════════════════════════════════════════════════

class GpsPointRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, point_id: int) -> Optional[GpsPoint]:
        return await self.db.get(GpsPoint, point_id)

    async def find_by_field(self, field_id: int) -> Sequence[GpsPoint]:
        result = await self.db.execute(
            select(GpsPoint).where(GpsPoint.field_id == field_id)
        )
        return result.scalars().all()

    async def find_in_bbox(
        self, field_id: int,
        min_lat: float, max_lat: float,
        min_lon: float, max_lon: float,
    ) -> Sequence[GpsPoint]:
        result = await self.db.execute(
            select(GpsPoint).where(
                and_(
                    GpsPoint.field_id == field_id,
                    GpsPoint.latitude  >= min_lat,
                    GpsPoint.latitude  <= max_lat,
                    GpsPoint.longitude >= min_lon,
                    GpsPoint.longitude <= max_lon,
                )
            )
        )
        return result.scalars().all()

    async def find_or_create(
        self, field_id: int, lat: float, lon: float
    ) -> Tuple[GpsPoint, bool]:
        result = await self.db.execute(
            select(GpsPoint).where(
                and_(
                    GpsPoint.field_id  == field_id,
                    GpsPoint.latitude  == lat,
                    GpsPoint.longitude == lon,
                )
            )
        )
        point = result.scalar_one_or_none()
        if point:
            return point, False
        point = GpsPoint(field_id=field_id, latitude=lat, longitude=lon)
        self.db.add(point)
        await self.db.commit()
        await self.db.refresh(point)
        return point, True

    async def delete(self, point: GpsPoint) -> None:
        await self.db.delete(point)
        await self.db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# MeasurementMapRepository
# ══════════════════════════════════════════════════════════════════════════════

class MeasurementMapRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, map_id: int) -> Optional[MeasurementMap]:
        return await self.db.get(MeasurementMap, map_id)

    async def list_by_field(self, field_id: int) -> Sequence[MeasurementMap]:
        result = await self.db.execute(
            select(MeasurementMap)
            .where(MeasurementMap.field_id == field_id)
            .order_by(MeasurementMap.measured_at.desc())
        )
        return result.scalars().all()

    async def create(self, mmap: MeasurementMap) -> MeasurementMap:
        self.db.add(mmap)
        await self.db.commit()
        await self.db.refresh(mmap)
        return mmap

    async def delete(self, mmap: MeasurementMap) -> None:
        await self.db.delete(mmap)
        await self.db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# PhMeasurementRepository
# ══════════════════════════════════════════════════════════════════════════════

class PhMeasurementRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, m_id: int) -> Optional[PhMeasurement]:
        return await self.db.get(PhMeasurement, m_id)

    async def list_by_point(self, point_id: int) -> Sequence[PhMeasurement]:
        result = await self.db.execute(
            select(PhMeasurement)
            .where(PhMeasurement.point_id == point_id)
            .order_by(PhMeasurement.recorded_at.desc())
        )
        return result.scalars().all()

    async def list_in_bbox(
        self, field_id: int,
        min_lat: float, max_lat: float,
        min_lon: float, max_lon: float,
    ) -> Sequence[PhMeasurement]:
        result = await self.db.execute(
            select(PhMeasurement)
            .join(GpsPoint, PhMeasurement.point_id == GpsPoint.id)
            .where(
                and_(
                    GpsPoint.field_id  == field_id,
                    GpsPoint.latitude.between(min_lat, max_lat),
                    GpsPoint.longitude.between(min_lon, max_lon),
                )
            )
            .order_by(PhMeasurement.recorded_at.desc())
        )
        return result.scalars().all()

    async def create(self, m: PhMeasurement) -> PhMeasurement:
        self.db.add(m)
        await self.db.commit()
        await self.db.refresh(m)
        return m

    async def delete(self, m: PhMeasurement) -> None:
        await self.db.delete(m)
        await self.db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# HumidityMeasurementRepository
# ══════════════════════════════════════════════════════════════════════════════

class HumidityMeasurementRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, m_id: int) -> Optional[HumidityMeasurement]:
        return await self.db.get(HumidityMeasurement, m_id)

    async def list_by_point(self, point_id: int) -> Sequence[HumidityMeasurement]:
        result = await self.db.execute(
            select(HumidityMeasurement)
            .where(HumidityMeasurement.point_id == point_id)
            .order_by(HumidityMeasurement.recorded_at.desc())
        )
        return result.scalars().all()

    async def list_in_bbox(
        self, field_id: int,
        min_lat: float, max_lat: float,
        min_lon: float, max_lon: float,
    ) -> Sequence[HumidityMeasurement]:
        result = await self.db.execute(
            select(HumidityMeasurement)
            .join(GpsPoint, HumidityMeasurement.point_id == GpsPoint.id)
            .where(
                and_(
                    GpsPoint.field_id  == field_id,
                    GpsPoint.latitude.between(min_lat, max_lat),
                    GpsPoint.longitude.between(min_lon, max_lon),
                )
            )
            .order_by(HumidityMeasurement.recorded_at.desc())
        )
        return result.scalars().all()

    async def create(self, m: HumidityMeasurement) -> HumidityMeasurement:
        self.db.add(m)
        await self.db.commit()
        await self.db.refresh(m)
        return m

    async def delete(self, m: HumidityMeasurement) -> None:
        await self.db.delete(m)
        await self.db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# NotificationRepository
# ══════════════════════════════════════════════════════════════════════════════

class NotificationRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_unread(self, person_id: int) -> Sequence[Notification]:
        result = await self.db.execute(
            select(Notification)
            .where(
                and_(
                    Notification.person_id == person_id,
                    Notification.is_read   == False,        # noqa: E712
                )
            )
            .order_by(Notification.created_at.desc())
        )
        return result.scalars().all()

    async def list_all_for_user(self, person_id: int) -> Sequence[Notification]:
        result = await self.db.execute(
            select(Notification)
            .where(Notification.person_id == person_id)
            .order_by(Notification.created_at.desc())
        )
        return result.scalars().all()

    async def create(self, n: Notification) -> Notification:
        self.db.add(n)
        await self.db.commit()
        await self.db.refresh(n)
        return n

    async def mark_read(self, notification_id: int) -> Optional[Notification]:
        n = await self.db.get(Notification, notification_id)
        if n:
            n.is_read = True
            await self.db.commit()
            await self.db.refresh(n)
        return n
    
# ====================== НОВЫЕ РЕПОЗИТОРИИ ======================

class EquipmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> Sequence[Equipment]:
        result = await self.db.execute(
            select(Equipment).options(selectinload(Equipment.assigned_driver))
        )
        return result.scalars().all()

    async def get_by_id(self, eq_id: int) -> Optional[Equipment]:
        return await self.db.get(Equipment, eq_id)

    async def update_position(self, eq_id: int, lat: float, lon: float) -> Optional[Equipment]:
        eq = await self.get_by_id(eq_id)
        if eq:
            eq.current_latitude = lat
            eq.current_longitude = lon
            eq.last_position_update = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(eq)
        return eq

    async def create(self, equipment: Equipment) -> Equipment:
        self.db.add(equipment)
        await self.db.commit()
        await self.db.refresh(equipment)
        return equipment


class TaskRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> Sequence[Task]:
        result = await self.db.execute(
            select(Task).options(
                selectinload(Task.assigned_by),
                selectinload(Task.assigned_to),
                selectinload(Task.equipment),
                selectinload(Task.field)
            ).order_by(Task.created_at.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, task_id: int) -> Optional[Task]:
        return await self.db.get(Task, task_id)

    async def create(self, task: Task) -> Task:
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_status(self, task_id: int, new_status: TaskStatusEnum, comment: Optional[str] = None) -> Optional[Task]:
        task = await self.get_by_id(task_id)
        if task:
            task.status = new_status
            if new_status == TaskStatusEnum.completed:
                task.completed_at = datetime.utcnow()
            if comment:
                task.result_comment = comment
            await self.db.commit()
            await self.db.refresh(task)
        return task


class FuelingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, fueling: Fueling) -> Fueling:
        self.db.add(fueling)
        await self.db.commit()
        await self.db.refresh(fueling)
        return fueling

    async def list_by_equipment(self, equipment_id: int) -> Sequence[Fueling]:
        result = await self.db.execute(
            select(Fueling).where(Fueling.equipment_id == equipment_id).order_by(Fueling.date.desc())
        )
        return result.scalars().all()


# ====================== НОВЫЕ РЕПОЗИТОРИИ ======================
class MaintenanceRepository:
    async def get_by_id(self, maintenance_id: int) -> Optional[Maintenance]:
        result = await self.session.execute(select(Maintenance).where(Maintenance.id == maintenance_id))
        return result.scalar_one_or_none()

    async def list_by_equipment(self, equipment_id: int, limit: int = 100) -> List[Maintenance]:
        result = await self.session.execute(
            select(Maintenance).where(Maintenance.equipment_id == equipment_id).order_by(Maintenance.maintenance_date.desc()).limit(limit)
        )
        return result.scalars().all()

    async def create(self, maintenance: Maintenance) -> Maintenance:
        self.session.add(maintenance)
        await self.session.flush()
        return maintenance

    async def update(self, maintenance: Maintenance) -> Maintenance:
        await self.session.flush()
        return maintenance

    async def delete(self, maintenance: Maintenance):
        await self.session.delete(maintenance)

class WearAnalysisRepository:
    async def create(self, wear: WearAnalysis) -> WearAnalysis:
        self.session.add(wear)
        await self.session.flush()
        return wear

    async def get_latest_for_equipment(self, equipment_id: int) -> Optional[WearAnalysis]:
        result = await self.session.execute(
            select(WearAnalysis).where(WearAnalysis.equipment_id == equipment_id).order_by(WearAnalysis.analysis_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

class RiskPredictionRepository:
    async def create(self, risk: RiskPrediction) -> RiskPrediction:
        self.session.add(risk)
        await self.session.flush()
        return risk

    async def get_active_for_field(self, field_id: int) -> List[RiskPrediction]:
        result = await self.session.execute(
            select(RiskPrediction).where(
                RiskPrediction.field_id == field_id,
                RiskPrediction.valid_until > datetime.utcnow()
            )
        )
        return result.scalars().all()
    
    