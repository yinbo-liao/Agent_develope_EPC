"""
WebSocket Connection Manager with Redis PubSub backing.

Supports multi-worker deployments by using Redis PubSub channels per project_id.
Each worker subscribes only to the channels that have local connections, and
forwards messages to its own WebSocket clients.

Delivery guarantees:
- A publish is ALWAYS delivered to local connections directly (even when Redis
  is configured), so a Redis hiccup can never silently drop a message.
- Messages carry an ``origin`` instance id; the Redis listener ignores messages
  published by this same worker to avoid duplicate local delivery.

In single-worker / dev mode (no Redis), delivery is purely in-process.
"""

import asyncio
import json
import logging
import uuid
from contextlib import suppress
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
        self._channels: set[str] = set()
        self._lock = asyncio.Lock()
        self._instance_id = uuid.uuid4().hex
        self._closing = False

    # -- Redis lifecycle ---------------------------------------------------

    async def _ensure_redis(self):
        """Lazily connect to Redis if available."""
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis
            redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await redis.ping()
            self._redis = redis
            logger.info("WebSocket: Redis PubSub connected")
        except Exception:
            self._redis = False  # Sentinel — don't retry
            logger.info("WebSocket: Redis unavailable, using in-process broadcast (single-worker only)")
        return self._redis

    async def start_redis_listener(self):
        """Start the background PubSub listener. Safe to call without Redis."""
        if self._listener_task and not self._listener_task.done():
            return
        self._closing = False
        redis = await self._ensure_redis()
        if not redis:
            return
        self._listener_task = asyncio.create_task(self._listen_loop())
        logger.info("WebSocket: Redis PubSub listener started")

    async def stop_redis_listener(self):
        """Cancel the listener and close Redis resources at shutdown."""
        self._closing = True
        task = self._listener_task
        self._listener_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

        pubsub = self._pubsub
        self._pubsub = None
        if pubsub is not None:
            with suppress(Exception):
                await pubsub.close()

        redis = self._redis
        self._redis = None
        if redis:
            with suppress(Exception):
                if hasattr(redis, "aclose"):
                    await redis.aclose()
                else:  # pragma: no cover - older redis-py
                    await redis.close()
        logger.info("WebSocket: Redis PubSub listener stopped")

    async def _listen_loop(self):
        """Forward Redis PubSub messages to local WebSocket connections."""
        while not self._closing:
            try:
                redis = await self._ensure_redis()
                if not redis:
                    await asyncio.sleep(2)
                    continue

                if self._pubsub is None:
                    self._pubsub = redis.pubsub()
                    async with self._lock:
                        for channel in list(self._channels):
                            await self._pubsub.subscribe(channel)

                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0,
                )
                if message and message.get("type") == "message":
                    await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("WebSocket Redis listener error: %s", exc)
                self._pubsub = None
                await asyncio.sleep(5)

    async def _handle_message(self, message):
        try:
            data = json.loads(message["data"])
        except (TypeError, ValueError):
            logger.warning("WebSocket: dropping non-JSON PubSub message")
            return
        if data.get("origin") == self._instance_id:
            return  # already delivered locally by broadcast_to_project
        project_id = data.get("project_id")
        if project_id:
            await self._broadcast_local(project_id, data.get("payload", data))

    async def subscribe(self, project_id: str):
        """Subscribe this worker to a project channel when the first client connects."""
        channel = f"project:{project_id}"
        async with self._lock:
            if channel in self._channels:
                return
            self._channels.add(channel)
            pubsub = self._pubsub
            if pubsub is not None:
                with suppress(Exception):
                    await pubsub.subscribe(channel)

    async def unsubscribe(self, project_id: str):
        """Unsubscribe when the last local client for a project disconnects."""
        channel = f"project:{project_id}"
        async with self._lock:
            if channel not in self._channels:
                return
            self._channels.discard(channel)
            pubsub = self._pubsub
            if pubsub is not None:
                with suppress(Exception):
                    await pubsub.unsubscribe(channel)

    # -- Connection lifecycle ---------------------------------------------

    async def connect(self, ws: WebSocket, project_id: str, subprotocol: Optional[str] = None):
        """Accept a WebSocket connection, register it, and subscribe its channel."""
        if subprotocol:
            await ws.accept(subprotocol=subprotocol)
        else:
            await ws.accept()
        self.active_connections.setdefault(project_id, []).append(ws)
        await self.subscribe(project_id)

    async def disconnect(self, ws: WebSocket, project_id: str):
        """Remove a WebSocket connection and clean up empty project entries."""
        connections = self.active_connections.get(project_id)
        if connections is not None:
            self.active_connections[project_id] = [c for c in connections if c != ws]
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
                await self.unsubscribe(project_id)

    # -- Broadcast ---------------------------------------------------------

    async def broadcast_to_project(self, project_id: str, message: dict):
        """Broadcast a message to all clients watching a project.

        Publishes to Redis for cross-worker delivery (when available) and
        always delivers to local connections directly.
        """
        channel = f"project:{project_id}"
        redis = await self._ensure_redis()
        if redis:
            try:
                await redis.publish(channel, json.dumps({
                    "project_id": project_id,
                    "payload": message,
                    "origin": self._instance_id,
                }, default=str))
            except Exception as exc:
                logger.warning("WebSocket: Redis publish failed (%s); delivering locally", exc)

        # Always deliver locally — never rely solely on the PubSub round-trip.
        await self._broadcast_local(project_id, message)

    async def _broadcast_local(self, project_id: str, message: dict):
        """Send a message to all local WebSocket connections for a project."""
        connections = list(self.active_connections.get(project_id, []))
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        # Clean up dead connections
        for ws in dead:
            await self.disconnect(ws, project_id)


manager = ConnectionManager()
