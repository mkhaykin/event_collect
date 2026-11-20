# apps/poller/bus_notifier.py
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum

import redis.asyncio as valkey

from libs.config import config
from libs.null_logger import NullLogger
from libs.poller.models import DeviceOfflineEvent, DeviceOnlineEvent


class DeviceStatus(IntEnum):
    OFFLINE = 0
    ONLINE = 1


@dataclass
class DeviceOnline:
    device_uid: str
    status: int
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def table_name(self) -> str:
        return "device_states"

    def to_row(self) -> tuple:
        return self.device_uid, self.status, self.timestamp

    @classmethod
    def get_columns(cls) -> tuple[str, ...]:
        return (
            "device_uid",
            "status",
            "timestamp",
        )


class StatusNotifier:
    CONFIG_EVENT_ONLINE: str = config.CONFIG_EVENT_ONLINE
    CONFIG_EVENT_OFFLINE: str = config.CONFIG_EVENT_OFFLINE

    def __init__(
        self,
        client: valkey.Redis,
        event_queue: asyncio.Queue,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._client = client
        self._event_queue = event_queue

    async def notify_online(self, uid: str) -> None:
        event = DeviceOnlineEvent(uid=uid, status="online")
        await self._client.publish(self.CONFIG_EVENT_ONLINE, event.model_dump_json())
        await self._event_queue.put(
            DeviceOnline(
                device_uid=uid,
                status=DeviceStatus.ONLINE,
            ),
        )
        self._logger.info(f"устройство {uid} выведено в ONLINE")

    async def notify_offline(self, uid: str) -> None:
        event = DeviceOfflineEvent(uid=uid, status="offline")
        await self._client.publish(self.CONFIG_EVENT_OFFLINE, event.model_dump_json())
        await self._event_queue.put(
            DeviceOnline(
                device_uid=uid,
                status=DeviceStatus.OFFLINE,
            ),
        )
        self._logger.info(f"устройство {uid} отправлено в OFFLINE")
