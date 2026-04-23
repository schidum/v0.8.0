# =============================================================================
# ФАЙЛ: app/routers/queries/risk.py – получение прогнозов (SQL, без ORM)
# =============================================================================
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db

router = APIRouter(prefix="/queries/risk", tags=["Queries - Risk Predictions"])

@router.get("/field/{field_id}")
async def get_risk_predictions(
    field_id: int,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """Актуальные прогнозы рисков для поля (прямой SQL)"""
    query = text("""
        SELECT id, field_id, risk_type, probability, predicted_at, valid_until, notes
        FROM risk_predictions
        WHERE field_id = :field_id
        {} 
        ORDER BY predicted_at DESC
    """.format("AND valid_until > datetime('now')" if active_only else ""))
    result = await db.execute(query, {"field_id": field_id})
    rows = result.mappings().all()
    return [dict(row) for row in rows]