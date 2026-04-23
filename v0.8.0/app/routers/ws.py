# app/routers/ws.py — WebSocket для реального времени
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

router = APIRouter(prefix="/ws", tags=["WebSocket — Реал-тайм"])


@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket):
    """
    Основной WebSocket-эндпоинт.
    Клиент подключается после логина.
    """
    await manager.connect(websocket)
    try:
        # Можно принять первое сообщение от клиента (например, user_id)
        data = await websocket.receive_json()
        print(f"WebSocket получил приветствие: {data}")

        # Держим соединение открытым
        while True:
            await websocket.receive_text()  # просто держим alive

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket ошибка: {e}")
        manager.disconnect(websocket)