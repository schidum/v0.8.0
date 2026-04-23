# app/routers/ws.py — WebSocket для реального времени
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket — Реал-тайм"])


@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket):
    """
    Основной WebSocket-эндпоинт для реального времени.
    Клиент подключается после логина и получает обновления в реальном времени.
    """
    await manager.connect(websocket)
    try:
        # Ожидаем приветствие от клиента (например, user_id для идентификации)
        try:
            data = await websocket.receive_json()
            logger.info(f"WebSocket greeting received: {data}")
        except Exception as e:
            logger.warning(f"Failed to receive greeting message: {e}")
            await websocket.close(code=1002, reason="Invalid greeting format")
            manager.disconnect(websocket)
            return

        # Держим соединение открытым, слушаем сообщения
        while True:
            try:
                await websocket.receive_text()  # ждём, чтобы соединение было alive
            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                logger.debug(f"WebSocket runtime error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected WebSocket error: {e}")
                break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Critical WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)