import asyncio
from app.database import AsyncSessionLocal, init_db
from app.models import Person, PersonRole, RoleEnum, Field, Equipment, Task, Fueling, FieldStatusEnum, TaskStatusEnum
from app.services import AuthService

async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        # Пользователи
        admin = Person(full_name="Админ", login="admin", password_hash=AuthService.hash_password("admin"))
        admin.roles = [PersonRole(role=RoleEnum.manager)]
        db.add(admin)
        await db.flush()

        driver = Person(full_name="Водитель", login="driver1", password_hash=AuthService.hash_password("driver123"))
        driver.roles = [PersonRole(role=RoleEnum.driver)]
        db.add(driver)
        await db.flush()

        # Поле с ЖЦС
        field = Field(name="Поле Северное", map_type="health", owner_id=admin.id, status=FieldStatusEnum.monitoring)
        db.add(field)
        await db.flush()

        # Техника + задание + заправка (одна транзакция)
        tractor = Equipment(name="Трактор T-150", nominal_fuel_consumption=35.0, current_mileage=15420, owner_id=admin.id, assigned_driver_id=driver.id)
        db.add(tractor)
        await db.flush()

        fueling = Fueling(equipment_id=tractor.id, person_id=admin.id, volume_liters=180.0, owner_id=admin.id)
        db.add(fueling)

        task = Task(title="Вспашка поля", owner_id=admin.id, assigned_by_id=admin.id, assigned_to_id=driver.id, equipment_id=tractor.id, field_id=field.id, status=TaskStatusEnum.completed, result_comment="Выполнено")
        db.add(task)

        await db.commit()
        print("✅ seed выполнен — все требования курса покрыты")

if __name__ == "__main__":
    asyncio.run(seed())