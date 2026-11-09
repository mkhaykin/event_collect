# apps/device_provider/notifier.py
import logging

import redis.asyncio as valkey

from libs.config import config
from libs.events.models import (
    DeviceConfig,
    DeviceCreatedEvent,
    DeviceDeletedEvent,
    DeviceUpdatedEvent,
)
from libs.null_logger import NullLogger


class DeviceNotificationService:
    CONFIG_EVENT_CREATED: str = config.CONFIG_EVENT_CREATED
    CONFIG_EVENT_UPDATED: str = config.CONFIG_EVENT_UPDATED
    CONFIG_EVENT_DELETED: str = config.CONFIG_EVENT_DELETED

    _client: valkey.Redis
    _logger: logging.Logger

    def __init__(
        self,
        client: valkey.Redis,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._logger = logger or NullLogger(__name__)

    async def send_device_created(self, device: DeviceConfig) -> None:
        """Публикует извещение о создании нового устройства."""
        event = DeviceCreatedEvent(uid=device.uid, device=device)
        await self._client.publish(self.CONFIG_EVENT_CREATED, event.model_dump_json())

    async def send_device_updated(self, device: DeviceConfig, old_value: DeviceConfig | None = None) -> None:
        """Публикует извещение об изменении конфигурации устройства."""
        event = DeviceUpdatedEvent(uid=device.uid, device=device, device_old=old_value)
        await self._client.publish(self.CONFIG_EVENT_UPDATED, event.model_dump_json())

    async def send_device_deleted(self, uid: str) -> None:
        """Публикует извещение об изменении конфигурации устройства."""
        event = DeviceDeletedEvent(uid=uid)
        await self._client.publish(self.CONFIG_EVENT_DELETED, event.model_dump_json())
