"""
WebSocket Connection Manager with Redis PubSub backing.

Supports multi-worker deployments by using Redis PubSub channels per project_id.
Each worker subscribes to its project channels and forwards messages to local
WebSocket connections.

In single-worker / dev mode (no Redis), falls back to in-process broadcasting.
"""

import asyncio
import json
import logging
from typing import Optional
from fastapi import WebSocket
from config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections with optional Redis PubSub for multi-worker."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._redis = None
        self._pubsub = None
        self._listener_task: Optional[asyncio.Task] = None

    async def _ensure_redis(self):
        """Lazily connect to Redis if available."""
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("WebSocket: Redis PubSub connected")
        except Exception:
            self._redis = False  # Sentinel — don't retry
            logger.info("WebSocket: Redis unavailable, using in-process broadcast (single-worker only)")
        return self._redis

    async def _start_listener(self):
        """Background task that listens for Redis PubSub messages and forwards to local WS."""
        redis = await self._ensure_redis()
        if not redis:
            return
        self._pubsub = redis.pubsub()
        # Subscribe to all project channels we care about (dynamic)
        while True:
            try:
                async for message in self._pubsub.listen():
                    if message["type"] == "message":
                        data = json.loads(message["data"])
                        project_id = data.get("project_id")
                        if project_id and project_id in self.active_connections:
                            payload = data.get("payload", data)
                            await self._broadcast_local(project_id, payload)
            except Exception as e:
                logger.error(f"WebSocket Redis listener error: {e}")
                await asyncio.sleep(5)

    async def connect(self, ws: WebSocket, project_id: str):
        """Accept a WebSocket connection and register it."""
        await ws.accept()
        self.active_connections.setdefault(project_id, []).append(ws)

    def disconnect(self, ws: WebSocket, project_id: str):
        """Remove a WebSocket connection and clean up empty project entries."""
        if project_id in self.active_connections:
            self.active_connections[project_id] = [
                c for c in self.active_connections[project_id] if c != ws
            ]
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]

    async def broadcast_to_project(self, project_id: str, message: dict):
        """Broadcast a message to all clients watching a project.

        Uses Redis PubSub for cross-worker broadcast when available,
        with local delivery as fallback.
        """
        redis = await self._ensure_redis()
        if redis:
            # Publish to Redis — all workers (including this one) receive it
            channel = f"project:{project_id}"
            await redis.publish(channel, json.dumps({
                "project_id": project_id,
                "payload": message,
            }, default=str))
        else:
            # No Redis — broadcast directly to local connections
            await self._broadcast_local(project_id, message)

    async def _broadcast_local(self, project_id: str, message: dict):
        """Send a message to all local WebSocket connections for a project."""
        connections = self.active_connections.get(project_id, [])
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        # Clean up dead connections
        for ws in dead:
            self.disconnect(ws, project_id)


manager = ConnectionManager()
