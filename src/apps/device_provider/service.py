# apps/device_provider/service.py
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Self

from redis.asyncio import from_url
from redis.maint_notifications import MaintNotificationsConfig

from apps.device_provider.loader import (
    DeviceLoader,
    DeviceYamlLoader,
)
from apps.device_provider.notifier import DeviceNotificationService
from apps.device_provider.repository import DeviceConfigRepository
from libs.events.models import (
    DeviceConfig,
)
from libs.null_logger import NullLogger


class DeviceProviderService:
    _loader: DeviceLoader
    _notifier: DeviceNotificationService
    _repository: DeviceConfigRepository

    _logger: logging.Logger

    def __init__(
        self,
        loader: DeviceLoader,
        repository: DeviceConfigRepository,
        notifier: DeviceNotificationService,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger()

        self._loader = loader
        self._repository = repository
        self._notifier = notifier

    async def sync_configuration(self) -> None:
        """Дифференциальная синхронизация конфигурации в Valkey и отправка эвентов."""
        self._logger.debug("Старт синхронизации ...")

        sync_time = datetime.now(timezone.utc).isoformat()

        count = 0
        async for dev in self._loader.devices(schema=DeviceConfig):
            uid = dev.uid
            try:
                result = await self._repository.upsert_device(dev, sync_time=sync_time)
                count += 1
            except Exception as e:
                self._logger.error(f"Ошибка при сохранении устройства {uid}: {e}")
            else:
                if result.action == "created":
                    await self._notifier.send_device_created(dev)
                    self._logger.info("устройство %s успешно создано", uid)

                elif result.action == "updated":
                    await self._notifier.send_device_updated(dev, result.old_value)
                    self._logger.info("устройство %s изменено", uid)

                elif result.action == "none":
                    self._logger.debug("продлен TTL/Heartbeat для %s, изменений нет", uid)

        self._logger.debug("Изменено или добавлено %s устройств", str(count))

        deleted_devices = await self._repository.clear_deleted_devices()
        self._logger.debug("%s устройств к удалению", len(deleted_devices))
        for uid in deleted_devices:
            await self._notifier.send_device_deleted(uid)
            self._logger.info("устройство %s удалено", uid)

    @classmethod
    @asynccontextmanager
    async def factory(
        cls,
        config_path: str | Path,
        valkey_dsn: str,
        logger: logging.Logger | None = None,
    ) -> AsyncGenerator[Self, None]:
        client = await from_url(
            valkey_dsn,
            decode_responses=True,
            socket_timeout=None,
            socket_keepalive=True,
            maint_notifications_config=MaintNotificationsConfig(enabled=False),
        )

        loader = DeviceYamlLoader(
            config_path=config_path,
            logger=logger,
        )

        repository = DeviceConfigRepository(
            client=client,
            logger=logger,
        )

        notifier = DeviceNotificationService(
            client=client,
            logger=logger,
        )

        instance = cls(
            loader=loader,
            repository=repository,
            notifier=notifier,
            logger=logger,
        )

        try:
            yield instance
        finally:
            await client.aclose()
