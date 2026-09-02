"""
WebSocket broadcast manager.

Handles graceful client disconnects: a client dropping mid-stream never
crashes the streamer or loses server-side state -- it's simply removed from
the broadcast set and can reconnect at any time. On reconnect, the client
immediately receives a `snapshot` message so it never has to guess what it
missed (no partial/inconsistent client state after a drop).
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger("fraud_sentinel.ws")


class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self.active.add(ws)
        logger.info("client connected (%d active)", len(self.active))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self.active.discard(ws)
        logger.info("client disconnected (%d active)", len(self.active))

    async def broadcast(self, message: dict):
        dead: list[WebSocket] = []
        payload = json.dumps(message, default=str)
        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.warning("broadcast failed for a client, dropping it: %s", exc)
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
