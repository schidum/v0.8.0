# =============================================================================
# ФАЙЛ: app/tasks/risk_prediction.py – прогнозирование рисков для полей (Celery)
# =============================================================================
from celery import shared_task
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List
from app.database import AsyncSessionLocal
from app.models import Field, RiskType, RiskPrediction
from app.services import RiskPredictionService
from app.schemas import RiskPredictionCreate

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_risk_predictions(self, field_ids: List[int] = None):
    """
    Фоновая задача: вычисляет вероятности рисков (засуха, болезни) для заданных полей.
    Если field_ids = None – для всех полей.
    Результат сохраняется в таблицу risk_predictions.
    Использует безопасный async runner для предотвращения конфликтов event loop.
    """
    from app.tasks.async_runner import run_async_task
    import logging
    logger = logging.getLogger(__name__)
    try:
        async def _run():
            async with AsyncSessionLocal() as db:
                # 1. Определить поля
                if field_ids is None:
                    from sqlalchemy import select
                    result = await db.execute(select(Field.id))
                    field_ids = [row[0] for row in result.all()]

                created_predictions = []
                for fid in field_ids:
                    # Имитация сложного прогноза (на самом деле: вызов ML модели, анализ данных полей, погоды)
                    # Используем реальные данные: pH, влажность, статус поля
                    # (упрощённо – генерируем случайные значения с учётом статуса)
                    from app.repositories import FieldRepository
                    field = await FieldRepository(db).get_by_id(fid)
                    if not field:
                        continue

                    # Базовые вероятности
                    prob_drought = 0.1
                    prob_disease = 0.05

                    if field.status == "disease":
                        prob_disease = 0.8
                    elif field.status == "monitoring":
                        # Если поле в мониторинге и нет данных о влажности – выше риск засухи
                        prob_drought = 0.3

                    # Можно добавить анализ измерений pH и влажности ...
                    prob_disease += random.uniform(-0.1, 0.1)
                    prob_drought += random.uniform(-0.1, 0.2)

                    prob_disease = max(0.0, min(1.0, prob_disease))
                    prob_drought = max(0.0, min(1.0, prob_drought))

                    valid_until = datetime.utcnow() + timedelta(days=7)

                    # Сохраняем прогнозы
                    svc = RiskPredictionService(db)

                    # Удаляем старые прогнозы для этого поля (опционально)
                    # ...

                    for risk_type, prob in [(RiskType.disease, prob_disease), (RiskType.drought, prob_drought)]:
                        dto = RiskPredictionCreate(
                            field_id=fid,
                            risk_type=risk_type,
                            probability=prob,
                            valid_until=valid_until,
                            notes="Автоматический прогноз"
                        )
                        pred = await svc.save_prediction(dto, owner_id=1)  # owner=system
                        created_predictions.append(pred.id)

                # broadcast через WebSocket
                from app.websocket.manager import manager
                await manager.broadcast({
                    "type": "risk_predictions_updated",
                    "field_ids": field_ids,
                    "predictions_count": len(created_predictions)
                })
                logger.info(f"Risk predictions generated for {len(field_ids)} fields")
                return {"status": "success", "fields_processed": len(field_ids), "predictions_created": len(created_predictions)}

        return run_async_task(_run())

    except Exception as exc:
        logger.error(f"Error in risk prediction task: {exc}", exc_info=True)
        raise self.retry(exc=exc)