# =============================================================================
# ФАЙЛ: app/routers/queries/maintenance.py – чтение данных об обслуживании (прямой SQL)
# =============================================================================
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.dependencies import get_current_person

router = APIRouter(prefix="/queries/maintenance", tags=["Queries - Maintenance"])

@router.get("/equipment/{equipment_id}")
async def list_maintenances_for_equipment(
    equipment_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """Получить историю обслуживания для техники (прямой SQL)"""
    query = text("""
        SELECT m.id, m.equipment_id, m.maintenance_date, m.type, m.cost, 
               m.description, m.mileage_at_service, m.performed_by_id, m.created_at,
               p.full_name as performed_by_name
        FROM maintenances m
        LEFT JOIN persons p ON m.performed_by_id = p.id
        WHERE m.equipment_id = :eq_id
        ORDER BY m.maintenance_date DESC
        LIMIT :limit
    """)
    result = await db.execute(query, {"eq_id": equipment_id, "limit": limit})
    rows = result.mappings().all()
    return [dict(row) for row in rows]s