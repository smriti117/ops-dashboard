import asyncio
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework.authtoken.models import Token

from .services import build_snapshot

log = logging.getLogger(__name__)
PUSH_INTERVAL = 2  # seconds


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """Pushes a fresh snapshot every PUSH_INTERVAL. Bounded load no matter how many
    transactions arrive (we never broadcast per-transaction), and time-window alerts stay fresh."""

    async def connect(self):
        token = parse_qs(self.scope["query_string"].decode()).get("token", [""])[0]
        if not await self._valid(token):
            await self.close(code=4401)
            return
        await self.accept()
        self.task = asyncio.create_task(self._loop())

    @database_sync_to_async
    def _valid(self, token):
        return bool(token) and Token.objects.filter(key=token).exists()

    async def _loop(self):
        while True:
            try:
                snap = await database_sync_to_async(build_snapshot)()
                await self.send_json(snap)
            except Exception:
                log.exception("snapshot push failed")
            await asyncio.sleep(PUSH_INTERVAL)

    async def disconnect(self, code):
        if getattr(self, "task", None):
            self.task.cancel()
