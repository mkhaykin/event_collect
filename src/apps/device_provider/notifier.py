# apps/device_provider/notifier.py
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum

import redis.asyncio as valkey

from libs.config import config
from libs.events.models import (
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    DeviceUpdatedEvent,
)
from libs.model_saver import IEventModel
from libs.models.config import DeviceConfig
from libs.null_logger import NullLogger


class DeviceStatus(IntEnum):
    CREATED = 0
    UPDATED = 1
    DELETED = 2


@dataclass
class DeviceDiscovery:
    device_uid: str
    status: int
    description: str
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def table_name(self) -> str:
        return "device_discovery"

    def to_row(self) -> tuple:
        return self.device_uid, self.status, self.timestamp, self.description

    @classmethod
    def get_columns(cls) -> tuple[str, ...]:
        return (
            "device_uid",
            "status",
            "timestamp",
            "description",
        )


class DeviceNotificationService:
    CONFIG_EVENT_CREATED: str = config.CONFIG_EVENT_CREATED
    CONFIG_EVENT_UPDATED: str = config.CONFIG_EVENT_UPDATED
    CONFIG_EVENT_DELETED: str = config.CONFIG_EVENT_DELETED

    _client: valkey.Redis
    _logger: logging.Logger

    def __init__(
        self,
        client: valkey.Redis,
        event_queue: asyncio.Queue[IEventModel],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._client = client
        self._event_queue = event_queue

    async def send_device_created(self, device: DeviceConfig) -> None:
        """Публикует извещение о создании нового устройства."""
        event = DeviceCreatedEvent(uid=device.uid, device=device)
        await self._client.publish(self.CONFIG_EVENT_CREATED, event.model_dump_json())
        await self._event_queue.put(
            DeviceDiscovery(
                device_uid=device.uid,
                status=DeviceStatus.CREATED,
                description=device.model_dump_json(),
            ),
        )

    async def send_device_updated(self, device: DeviceConfig, old_value: DeviceConfig | None = None) -> None:
        """Публикует извещение об изменении конфигурации устройства."""
        event = DeviceUpdatedEvent(uid=device.uid, device=device, device_old=old_value)
        await self._client.publish(self.CONFIG_EVENT_UPDATED, event.model_dump_json())
        await self._event_queue.put(
            DeviceDiscovery(
                device_uid=device.uid,
                status=DeviceStatus.UPDATED,
                description=device.model_dump_json(),
            ),
        )

    async def send_device_deleted(self, uid: str) -> None:
        """Публикует извещение об изменении конфигурации устройства."""
        event = DeviceDeletedEvent(uid=uid)
        await self._client.publish(self.CONFIG_EVENT_DELETED, event.model_dump_json())
        await self._event_queue.put(
            DeviceDiscovery(
                device_uid=uid,
                status=DeviceStatus.DELETED,
                description="{}",
            ),
        )
