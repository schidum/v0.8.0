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


# Добавить в api_router после существующих

# Новые роутеры
from app.routers.commands.maintenance import router as maintenance_cmd_router
from app.routers.queries.maintenance import router as maintenance_query_router
from app.routers.commands.risk import router as risk_cmd_router
from app.routers.queries.risk import router as risk_query_router

api_router.include_router(maintenance_cmd_router)
api_router.include_router(maintenance_query_router)
api_router.include_router(risk_cmd_router)
api_router.include_router(risk_query_router)

print("✅ Роутеры подключены (reports отключён для отладки Swagger)")