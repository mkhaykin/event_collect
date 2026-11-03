# apps/device_provider/notifier.py
import logging

import redis.asyncio as valkey
from redis.maint_notifications import MaintNotificationsConfig

from libs.events.models import (
    DeviceConfig,
    DeviceCreatedEvent,
    DeviceUpdatedEvent,
)
from libs.null_logger import NullLogger


class DeviceNotificationService:
    CONFIG_EVENT_CREATED: str = "events:device_created"
    CONFIG_EVENT_UPDATED: str = "events:device_updated"
    CONFIG_EVENT_DELETED: str = "events:device_deleted"

    def __init__(
        self,
        dsn: str,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)

        self._url = dsn
        self._client: valkey.Redis | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = valkey.from_url(
                self._url,
                decode_responses=True,
                socket_timeout=None,
                socket_keepalive=True,
                maint_notifications_config=MaintNotificationsConfig(enabled=False),
            )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_device_created(self, device: DeviceConfig) -> None:
        """Публикует извещение о создании нового устройства."""
        if self._client is None:
            raise RuntimeError("Клиент не создан")

        event = DeviceCreatedEvent(uid=device.uid, device=device)
        await self._client.publish(self.CONFIG_EVENT_CREATED, event.model_dump_json())

    async def send_device_updated(self, device: DeviceConfig, old_value: DeviceConfig | None = None) -> None:
        """Публикует извещение об изменении конфигурации устройства."""
        if self._client is None:
            raise RuntimeError("Клиент не создан")

        event = DeviceUpdatedEvent(uid=device.uid, device=device, device_old=old_value)
        await self._client.publish(self.CONFIG_EVENT_UPDATED, event.model_dump_json())
