# apps/poller/bus_notifier.py
import logging

import redis.asyncio as valkey

from libs.config import config
from libs.null_logger import NullLogger
from libs.poller.models import DeviceOfflineEvent, DeviceOnlineEvent


class StatusBusNotifier:
    CONFIG_EVENT_ONLINE: str = config.CONFIG_EVENT_ONLINE
    CONFIG_EVENT_OFFLINE: str = config.CONFIG_EVENT_OFFLINE

    def __init__(
        self,
        client: valkey.Redis,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._client = client

    async def notify_online(self, uid: str) -> None:
        event = DeviceOnlineEvent(uid=uid, status="online")
        await self._client.publish(self.CONFIG_EVENT_ONLINE, event.model_dump_json())
        self._logger.info(f"устройство {uid} выведено в ONLINE")

    async def notify_offline(self, uid: str) -> None:
        event = DeviceOfflineEvent(uid=uid, status="offline")
        await self._client.publish(self.CONFIG_EVENT_OFFLINE, event.model_dump_json())
        self._logger.info(f"устройство {uid} отправлено в OFFLINE")
