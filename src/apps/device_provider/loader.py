# apps/device_provider/loader.py
import logging
from pathlib import Path
from typing import AsyncGenerator, Protocol

import aiofiles
import yaml

from libs.events.models import BaseDeviceConfig
from libs.null_logger import NullLogger


class DeviceLoader(Protocol):
    def devices[T: BaseDeviceConfig](
        self,
        schema: type[T],
    ) -> AsyncGenerator[T, None]: ...


class DeviceYamlLoader:
    def __init__(
        self,
        config_path: str | Path,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger(__name__)
        self._config_path = config_path

    async def devices[T: BaseDeviceConfig](
        self,
        schema: type[T],
    ) -> AsyncGenerator[T, None]:
        """Читает и валидирует YAML-конфигурацию устройств."""
        self._logger.debug("Загрузка устройств из файла: %s", self._config_path)

        try:
            async with aiofiles.open(self._config_path, "r") as fr:
                data = await fr.read()
        except FileNotFoundError as e:
            raise ValueError(f"Файл конфигурации не найден: {self._config_path}") from e
        except PermissionError as e:
            raise ValueError(f"Нет прав на чтение файла конфигурации: {self._config_path}") from e

        content = yaml.safe_load(data) or {}
        if "devices" not in content:
            raise ValueError("Нет ключа `devices`")

        devices = content.get("devices", [])
        if not devices:
            self._logger.warning("Список устройств в файле %s пуст", self._config_path)

        count = 0
        for item in devices:
            try:
                device = schema.model_validate(item)
                count += 1
                yield device
            except Exception as e:
                self._logger.error(f"Ошибка валидации устройства {item.get('uid')}: {e}")

        self._logger.debug("Получили %s устройств(-а)", count)
