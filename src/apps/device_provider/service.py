# apps/device_provider/service.py
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Self

from apps.device_provider.loader import (
    DeviceLoader,
    DeviceYamlLoader,
)
from apps.device_provider.notifier import DeviceNotificationService
from apps.device_provider.repository import DeviceValkeyRepository
from libs.events.models import (
    DeviceConfig,
)
from libs.null_logger import NullLogger


class DeviceProviderService:
    _loader: DeviceLoader
    _notifier: DeviceNotificationService
    _repository: DeviceValkeyRepository

    _logger: logging.Logger

    def __init__(
        self,
        loader: DeviceLoader,
        repository: DeviceValkeyRepository,
        notifier: DeviceNotificationService,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger()

        self._loader = loader
        self._repository = repository
        self._notifier = notifier

    async def connect(self) -> None:
        await self._repository.connect()
        await self._notifier.connect()

    async def close(self) -> None:
        await self._repository.close()
        await self._notifier.close()

    async def sync_configuration(self) -> None:
        """Дифференциальная синхронизация конфигурации в Valkey и отправка эвентов."""
        self._logger.debug("Старт синхронизации ...")
        if self._repository is None:
            raise RuntimeError("Не подготовили хэндлер")
        if self._notifier is None:
            raise RuntimeError("Не подготовили извещатель")

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

        self._logger.debug("Синхронизация завершена, обработано %s устройств", str(count))

    @classmethod
    def factory(
        cls,
        config_path: str | Path,
        valkey_dsn: str,
        logger: logging.Logger | None = None,
    ) -> Self:
        loader = DeviceYamlLoader(
            config_path=config_path,
            logger=logger,
        )

        repository = DeviceValkeyRepository(
            dsn=valkey_dsn,
            logger=logger,
        )

        notifier = DeviceNotificationService(
            dsn=valkey_dsn,
            logger=logger,
        )

        return cls(
            loader=loader,
            repository=repository,
            notifier=notifier,
            logger=logger,
        )
