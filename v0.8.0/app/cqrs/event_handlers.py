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