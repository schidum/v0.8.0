from fastapi import WebSocket
from typing import List
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connection established. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket connection closed. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients with proper error handling."""
        disconnected = []
        for conn in self.active_connections[:]:
            try:
                await conn.send_json(message)
            except (RuntimeError, ConnectionError) as e:
                logger.warning(f"Failed to send message to client: {e}")
                disconnected.append(conn)
            except Exception as e:
                logger.error(f"Unexpected error broadcasting message: {e}")
                disconnected.append(conn)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()